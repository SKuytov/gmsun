"""Purchase orders, goods receipt and material readiness.

Flow: accepted quote → ``generate_orders`` creates one draft order per supplier with every material line
(labor, transport and delivery fees are not ordered) → the user sends the order workbook, marks it *sent* /
*confirmed*, enters the supplier's confirmed delivery date → receipts are booked per line (partial deliveries are
normal) → ``readiness`` tells for the whole project what has arrived, what is still waiting, what is overdue and the
earliest date on which installation can start.  ``awaiting`` is the cross-project view for the Deliveries page.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import CatalogItem, Project, PurchaseOrder, PurchaseOrderLine, Quote
from . import pricing, procurement
from .settings import get_setting
from .workbooks import _header_row, _kv_block, _letterhead, ascii_name

NON_MATERIAL_KEYS = ("delivery:", "labor", "transport")
ORDER_STATUSES = ("draft", "sent", "confirmed", "partial", "received", "cancelled")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def next_number(db: Session) -> str:
    year = _today().year
    prefix = f"PO-{year}-"
    last = db.query(PurchaseOrder.number).filter(PurchaseOrder.number.like(prefix + "%")).order_by(PurchaseOrder.number.desc()).first()
    n = int(last[0].split("-")[-1]) + 1 if last else 1
    return f"{prefix}{n:04d}"


def _business_days_after(start: date, days: int) -> date:
    d = start
    left = max(0, int(days))
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def material_rows(db: Session, q: Quote) -> dict[str, list[dict[str, Any]]]:
    """Material lines of the quote grouped by supplier (merged duplicates), with purchase prices and lead times."""
    scfg = get_setting(db, "suppliers")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for l in q.lines:
        if l.hidden or l.section in ("labor",):
            continue
        if any(l.key.startswith(k) or l.key == k for k in NON_MATERIAL_KEYS):
            continue
        ci: CatalogItem | None = l.catalog_item
        if ci is None:
            if (l.meta or {}).get("role") or l.section in ("modules", "inverter", "construction", "electrical"):
                groups["Неразпределени"].append({"item_id": None, "sku": "", "name": l.name, "unit": l.unit, "qty": float(l.qty), "price": float(l.purchase_price or 0), "lead": None, "section": l.section, "key": l.key})
            continue
        if ci.category in ("service", "transport") or (ci.specs or {}).get("service"):
            continue
        sup = procurement.supplier_of(ci) or "Неразпределени"
        groups[sup].append({"item_id": ci.id, "sku": ci.supplier_sku or ci.sku or "", "name": ci.name, "unit": l.unit, "qty": float(l.qty), "price": float(l.purchase_price or ci.purchase_price or 0), "lead": procurement.lead_time_days(ci, scfg), "section": l.section, "key": l.key})
    merged: dict[str, list[dict[str, Any]]] = {}
    for sup, rows in groups.items():
        acc: dict[tuple, dict[str, Any]] = {}
        for rw in rows:
            k = (rw["item_id"], rw["name"], rw["unit"])
            if k in acc:
                acc[k]["qty"] = round(acc[k]["qty"] + rw["qty"], 3)
            else:
                acc[k] = dict(rw)
        merged[sup] = sorted(acc.values(), key=lambda x: (pricing.SECTION_ORDER.get(x["section"], 9), x["name"]))
    return merged


def generate_orders(db: Session, q: Quote, user_id: int | None = None, suppliers: list[str] | None = None, replace_drafts: bool = True) -> list[PurchaseOrder]:
    """Create draft purchase orders (one per supplier) from the quote. Existing *draft* orders of the same quote are
    replaced; sent/confirmed/received orders are never touched (new lines then go to a fresh order)."""
    scfg = get_setting(db, "suppliers")
    smap = procurement.supplier_map(scfg)
    groups = material_rows(db, q)
    if suppliers:
        want = {s.lower() for s in suppliers}
        groups = {k: v for k, v in groups.items() if k.lower() in want}
    if replace_drafts:
        for po in db.query(PurchaseOrder).filter(PurchaseOrder.quote_id == q.id, PurchaseOrder.status == "draft").all():
            if not suppliers or po.supplier.lower() in {s.lower() for s in suppliers}:
                db.delete(po)
        db.flush()
    out: list[PurchaseOrder] = []
    for sup, rows in groups.items():
        if not rows:
            continue
        s = smap.get(sup.lower(), {})
        lead = int(s.get("lead_time_days") or scfg.get("default_lead_time_days", 7) or 7)
        po = PurchaseOrder(number=next_number(db), project_id=q.project_id, quote_id=q.id, supplier=sup, status="draft", created_by=user_id,
                           expected_at=datetime.combine(_business_days_after(_today(), max(lead, max((r["lead"] or 0) for r in rows))), datetime.min.time(), tzinfo=timezone.utc))
        db.add(po)
        db.flush()
        for i, rw in enumerate(rows):
            exp = _business_days_after(_today(), int(rw["lead"] or lead))
            po.lines.append(PurchaseOrderLine(position=i, catalog_item_id=rw["item_id"], quote_line_key=rw["key"], sku=rw["sku"], name=rw["name"], unit=rw["unit"],
                                              qty_ordered=rw["qty"], qty_received=0.0, status="open", receipts=[], unit_price=rw["price"], expected_at=datetime.combine(exp, datetime.min.time(), tzinfo=timezone.utc),
                                              meta={"section": rw["section"], "lead_time_days": rw["lead"]}))
        recompute(po)
        out.append(po)
    db.flush()
    return out


def recompute(po: PurchaseOrder) -> None:
    """Line statuses, order status and total from the quantities."""
    total = 0.0
    n_open = n_recv = n_part = 0
    for l in po.lines:
        l.qty_received = float(l.qty_received or 0)
        l.qty_ordered = float(l.qty_ordered or 0)
        total += l.qty_ordered * float(l.unit_price or 0)
        if l.status == "cancelled":
            continue
        if l.qty_received >= l.qty_ordered - 1e-9 and l.qty_ordered > 0:
            l.status = "received"
            n_recv += 1
        elif l.qty_received > 0:
            l.status = "partial"
            n_part += 1
        else:
            l.status = "open"
            n_open += 1
    po.total = round(total, 2)
    if po.status == "cancelled":
        return
    if po.lines and n_open == 0 and n_part == 0 and n_recv > 0:
        po.status = "received"
    elif n_recv or n_part:
        po.status = "partial"
    elif po.status in ("partial", "received"):
        po.status = "confirmed" if po.ordered_at else "draft"


def receive(po: PurchaseOrder, line_id: int, qty: float, note: str | None, user: str | None, when: date | None = None) -> PurchaseOrderLine:
    l = next((x for x in po.lines if x.id == line_id), None)
    if l is None:
        raise ValueError("line not found")
    when = when or _today()
    qty = float(qty)
    l.qty_received = round(max(0.0, float(l.qty_received) + qty), 3)
    l.received_at = datetime.combine(when, datetime.min.time(), tzinfo=timezone.utc)
    l.receipts = list(l.receipts or []) + [{"date": when.isoformat(), "qty": qty, "note": note or "", "user": user or ""}]
    recompute(po)
    return l


def receive_all(po: PurchaseOrder, user: str | None, when: date | None = None) -> int:
    n = 0
    for l in list(po.lines):
        rest = float(l.qty_ordered) - float(l.qty_received)
        if l.status != "cancelled" and rest > 1e-9:
            receive(po, l.id, rest, "пълна доставка", user, when)
            n += 1
    return n


def _line_dict(l: PurchaseOrderLine, today: date) -> dict[str, Any]:
    rest = round(float(l.qty_ordered) - float(l.qty_received), 3)
    exp = l.expected_at.date() if l.expected_at else None
    return {
        "id": l.id, "order_id": l.order_id, "catalog_item_id": l.catalog_item_id, "sku": l.sku, "name": l.name, "unit": l.unit,
        "qty_ordered": l.qty_ordered, "qty_received": l.qty_received, "qty_open": max(0.0, rest), "unit_price": l.unit_price,
        "expected_at": exp.isoformat() if exp else None, "received_at": l.received_at.date().isoformat() if l.received_at else None,
        "status": l.status, "overdue": bool(l.status in ("open", "partial") and exp and exp < today), "notes": l.notes, "receipts": l.receipts or [], "meta": l.meta or {},
    }


def order_dict(po: PurchaseOrder) -> dict[str, Any]:
    today = _today()
    lines = [_line_dict(l, today) for l in po.lines]
    n_act = [l for l in lines if l["status"] != "cancelled"]
    return {
        "id": po.id, "number": po.number, "project_id": po.project_id, "project_number": po.project.number if po.project else None, "project_name": po.project.name if po.project else None,
        "quote_id": po.quote_id, "quote_number": po.quote.number if po.quote else None, "supplier": po.supplier, "status": po.status, "supplier_ref": po.supplier_ref,
        "ordered_at": po.ordered_at.date().isoformat() if po.ordered_at else None, "expected_at": po.expected_at.date().isoformat() if po.expected_at else None,
        "notes": po.notes, "currency": po.currency, "total": po.total, "created_at": po.created_at.isoformat() if po.created_at else None,
        "lines": lines, "lines_total": len(n_act), "lines_received": sum(1 for l in n_act if l["status"] == "received"),
        "lines_overdue": sum(1 for l in n_act if l["overdue"]), "overdue": any(l["overdue"] for l in n_act) or bool(po.status in ("sent", "confirmed", "partial") and po.expected_at and po.expected_at.date() < today),
    }


def readiness(db: Session, project: Project) -> dict[str, Any]:
    """Material readiness of a project: ordered vs. quoted, received vs. ordered, waiting/overdue lines, earliest start."""
    today = _today()
    orders = db.query(PurchaseOrder).filter(PurchaseOrder.project_id == project.id, PurchaseOrder.status != "cancelled").all()
    quote = next((q for q in sorted(project.quotes, key=lambda q: q.id, reverse=True) if q.status == "accepted"), None) or (max(project.quotes, key=lambda q: q.id) if project.quotes else None)
    needed = material_rows(db, quote) if quote else {}
    needed_keys: dict[tuple, dict[str, Any]] = {}
    for sup, rows in needed.items():
        for r in rows:
            needed_keys[(r["item_id"], r["name"])] = {**r, "supplier": sup, "ordered": 0.0, "received": 0.0}
    waiting: list[dict[str, Any]] = []
    for po in orders:
        for l in po.lines:
            if l.status == "cancelled":
                continue
            k = (l.catalog_item_id, l.name)
            if k not in needed_keys:
                needed_keys[k] = {"item_id": l.catalog_item_id, "name": l.name, "unit": l.unit, "qty": 0.0, "supplier": po.supplier, "section": (l.meta or {}).get("section", "other"), "ordered": 0.0, "received": 0.0}
            needed_keys[k]["ordered"] += float(l.qty_ordered)
            needed_keys[k]["received"] += float(l.qty_received)
            if l.status in ("open", "partial"):
                d = _line_dict(l, today)
                d.update({"order_number": po.number, "supplier": po.supplier, "order_status": po.status})
                waiting.append(d)
    not_ordered = [{"name": v["name"], "unit": v["unit"], "qty": round(v["qty"] - v["ordered"], 3), "supplier": v["supplier"], "section": v["section"], "item_id": v["item_id"]}
                   for v in needed_keys.values() if v["qty"] - v["ordered"] > 1e-6]
    n_items = len(needed_keys)
    n_received = sum(1 for v in needed_keys.values() if v["ordered"] > 0 and v["received"] >= min(v["ordered"], v["qty"] or v["ordered"]) - 1e-9)
    n_ordered = sum(1 for v in needed_keys.values() if v["ordered"] > 0)
    expected = [datetime.fromisoformat(w["expected_at"]).date() for w in waiting if w.get("expected_at")]
    earliest = max(expected) if expected else (today if n_items and n_received == n_items else None)
    value_total = sum(float(v["qty"] or v["ordered"]) * float(v.get("price") or 0) for v in needed_keys.values())
    value_recv = 0.0
    for po in orders:
        for l in po.lines:
            if l.status != "cancelled":
                value_recv += float(l.qty_received) * float(l.unit_price)
    waiting.sort(key=lambda w: (not w["overdue"], w["expected_at"] or "9999"))
    return {
        "project_id": project.id, "quote_id": quote.id if quote else None, "quote_number": quote.number if quote else None, "quote_status": quote.status if quote else None,
        "items_total": n_items, "items_ordered": n_ordered, "items_received": n_received,
        "pct_ordered": round(100 * n_ordered / n_items) if n_items else 0, "pct_received": round(100 * n_received / n_items) if n_items else 0,
        "value_total": round(value_total, 2), "value_received": round(value_recv, 2),
        "orders": [order_dict(po) for po in sorted(orders, key=lambda p: p.number)],
        "waiting": waiting, "overdue": [w for w in waiting if w["overdue"]], "not_ordered": not_ordered,
        "earliest_start": earliest.isoformat() if earliest else None,
        "ready": bool(n_items and n_received == n_items and not not_ordered),
    }


def awaiting(db: Session, status: str | None = None, supplier: str | None = None, only_overdue: bool = False, project_id: int | None = None) -> dict[str, Any]:
    """Cross-project view for the Deliveries page: open orders and open lines, overdue first."""
    today = _today()
    qs = db.query(PurchaseOrder)
    if project_id:
        qs = qs.filter(PurchaseOrder.project_id == project_id)
    if status:
        qs = qs.filter(PurchaseOrder.status == status)
    else:
        qs = qs.filter(PurchaseOrder.status != "cancelled")
    if supplier:
        qs = qs.filter(func.lower(PurchaseOrder.supplier) == supplier.lower())
    orders = [order_dict(po) for po in qs.order_by(PurchaseOrder.created_at.desc()).all()]
    if only_overdue:
        orders = [o for o in orders if o["overdue"]]
    open_lines = [dict(l, order_number=o["number"], supplier=o["supplier"], project_id=o["project_id"], project_number=o["project_number"], project_name=o["project_name"])
                  for o in orders if o["status"] != "received" for l in o["lines"] if l["status"] in ("open", "partial")]
    open_lines.sort(key=lambda l: (not l["overdue"], l["expected_at"] or "9999"))
    by_sup: dict[str, dict[str, Any]] = {}
    for o in orders:
        d = by_sup.setdefault(o["supplier"], {"supplier": o["supplier"], "orders": 0, "open_lines": 0, "overdue_lines": 0, "value": 0.0})
        d["orders"] += 1
        d["open_lines"] += sum(1 for l in o["lines"] if l["status"] in ("open", "partial"))
        d["overdue_lines"] += o["lines_overdue"]
        d["value"] += o["total"]
    return {"today": today.isoformat(), "orders": orders, "open_lines": open_lines, "overdue_lines": [l for l in open_lines if l["overdue"]], "suppliers": sorted(by_sup.values(), key=lambda s: -s["open_lines"])}


def order_workbook(db: Session, po: PurchaseOrder) -> bytes:
    """Purchase order as an .xlsx the installer sends to the supplier (letterhead, delivery address, lines)."""
    company = get_setting(db, "company")
    scfg = get_setting(db, "suppliers")
    texts = get_setting(db, "texts")
    smap = procurement.supplier_map(scfg)
    s = smap.get(po.supplier.lower(), {})
    wb = Workbook()
    ws = wb.active
    ws.title = "Поръчка"
    ncols = 8
    meta = [("Поръчка №", po.number), ("Дата", (po.ordered_at or datetime.now(timezone.utc)).strftime("%d.%m.%Y")), ("Желана доставка до", po.expected_at.strftime("%d.%m.%Y") if po.expected_at else "")]
    r = _letterhead(ws, company, "Поръчка за доставка", texts.get("order_note") or texts.get("rfq_note"), meta, ncols)
    r0 = r
    r1 = _kv_block(ws, r, 2, "До доставчик", [("Фирма", po.supplier), ("Лице за контакт", s.get("contact") or ""), ("E-mail", s.get("email") or ""), ("Телефон", s.get("phone") or ""), ("Ваша референция", po.supplier_ref or "")])
    r2 = _kv_block(ws, r0, 6, "Доставка до", [("Адрес", scfg.get("delivery_address") or company.get("address") or ""), ("Получател", company.get("name") or ""), ("Контакт", company.get("signatory") or ""), ("Телефон", company.get("phone") or ""), ("Референция", f"Проект {po.project.number} · {po.project.name}" if po.project else "")])
    r = max(r1, r2) + 1
    _header_row(ws, r, ["№", "Код (доставчик)", "Наименование", "Мярка", "Количество", "Ед. цена (без ДДС)", "Стойност", "Срок / забележка"])
    r += 1
    total = 0.0
    for i, l in enumerate(po.lines, 1):
        if l.status == "cancelled":
            continue
        val = float(l.qty_ordered) * float(l.unit_price)
        total += val
        ws.append([])
        for c, v in enumerate([i, l.sku or "", l.name, l.unit, l.qty_ordered, l.unit_price, round(val, 2), (l.expected_at.strftime("%d.%m.%Y") if l.expected_at else "") + (f" · {l.notes}" if l.notes else "")], 1):
            ws.cell(row=r, column=c, value=v)
        ws.cell(row=r, column=5).number_format = "#,##0.###"
        ws.cell(row=r, column=6).number_format = "#,##0.00"
        ws.cell(row=r, column=7).number_format = "#,##0.00"
        r += 1
    ws.cell(row=r, column=6, value="Общо без ДДС:")
    ws.cell(row=r, column=7, value=round(total, 2)).number_format = "#,##0.00"
    if po.notes:
        ws.cell(row=r + 2, column=1, value=f"Бележки: {po.notes}")
    for col, w in zip("ABCDEFGH", (5, 18, 58, 8, 12, 16, 14, 30)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def order_filename(po: PurchaseOrder) -> str:
    return f"Porachka_{ascii_name(po.supplier)}_{po.number}.xlsx"
