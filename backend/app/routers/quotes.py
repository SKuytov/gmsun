from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..db import get_db
from ..models import Project, Quote, QuoteLine, User
from ..schemas import QuoteCreate, QuoteLineIn, QuoteLineUpdate, QuoteOut, QuoteUpdate
from ..services import pricing
from ..services.pdf import render_quote_html, render_quote_pdf
from ..services.settings import get_setting

router = APIRouter(tags=["quotes"])


def _quote(db: Session, qid: int) -> Quote:
    q = db.get(Quote, qid)
    if not q:
        raise HTTPException(404, "Quote not found")
    return q


def _out(db: Session, q: Quote) -> QuoteOut:
    o = QuoteOut.model_validate(q)
    extra = pricing.quote_dict(db, q)
    o.warnings = extra["warnings"]
    o.sections = extra["sections"]
    o.cost_total = extra["cost_total"]
    o.margin = extra["margin"]
    return o


@router.get("/projects/{pid}/quotes", response_model=list[QuoteOut])
def list_quotes(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    qs = db.query(Quote).filter(Quote.project_id == pid).order_by(Quote.version.desc()).all()
    return [_out(db, q) for q in qs]


@router.post("/projects/{pid}/quotes", response_model=QuoteOut, status_code=201)
def create_quote(pid: int, body: QuoteCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    project = db.get(Project, pid)
    if not project:
        raise HTTPException(404, "Project not found")
    pr = get_setting(db, "pricing")
    version = (max((q.version for q in project.quotes), default=0)) + 1
    base_sel = dict(body.selections or {})
    src = None
    if body.copy_from_quote_id:
        src = db.get(Quote, body.copy_from_quote_id)
        if src and not base_sel:
            base_sel = {k: v for k, v in (src.selections or {}).items() if not k.startswith("_")}
    q = Quote(
        project_id=pid,
        number=src.number if src else (project.quotes[-1].number if project.quotes else pricing.next_quote_number(db, project, pr.get("quote_number_prefix", ""))),
        version=version,
        title=body.title if body.title is not None else (src.title if src else None),
        selections=base_sel,
        currency=pr.get("currency", "EUR"),
        vat_pct=body.vat_pct if body.vat_pct is not None else (src.vat_pct if src else float(pr.get("vat_pct", 20))),
        markup_pct=body.markup_pct if body.markup_pct is not None else (src.markup_pct if src else float(pr.get("default_markup_pct", 0))),
        discount_pct=body.discount_pct if body.discount_pct is not None else (src.discount_pct if src else 0.0),
        advance_pct=body.advance_pct if body.advance_pct is not None else (src.advance_pct if src else float(pr.get("default_advance_pct", 70))),
        valid_days=body.valid_days if body.valid_days is not None else (src.valid_days if src else int(pr.get("quote_validity_days", 10))),
        notes=body.notes if body.notes is not None else (src.notes if src else None),
    )
    db.add(q)
    db.flush()
    if src:
        for ln in src.lines:
            if ln.source == "manual" or ln.locked:
                db.add(QuoteLine(quote_id=q.id, key=ln.key, section=ln.section, position=ln.position, name=ln.name, unit=ln.unit, qty=ln.qty,
                                 unit_price=ln.unit_price, purchase_price=ln.purchase_price, total=ln.total, catalog_item_id=ln.catalog_item_id,
                                 source=ln.source, locked=ln.locked, hidden=ln.hidden, meta=dict(ln.meta or {})))
        db.flush()
        db.refresh(q)
    pricing.recalculate(db, q)
    if project.status == "draft":
        project.status = "quoted"
    db.commit()
    db.refresh(q)
    return _out(db, q)


@router.get("/quotes/{qid}", response_model=QuoteOut)
def get_quote(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _out(db, _quote(db, qid))


@router.patch("/quotes/{qid}", response_model=QuoteOut)
def update_quote(qid: int, body: QuoteUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    data = body.model_dump(exclude_unset=True)
    recalc = data.pop("recalc", True)
    if "selections" in data and data["selections"] is not None:
        merged = {k: v for k, v in (q.selections or {}).items() if k.startswith("_")}
        merged.update(data.pop("selections"))
        q.selections = merged
    for k, v in data.items():
        setattr(q, k, v)
    if recalc:
        pricing.recalculate(db, q)
    else:
        pricing.compute_totals(q)
    db.commit()
    db.refresh(q)
    return _out(db, q)


@router.post("/quotes/{qid}/recalculate", response_model=QuoteOut)
def recalc(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    pricing.recalculate(db, q)
    db.commit()
    db.refresh(q)
    return _out(db, q)


@router.delete("/quotes/{qid}", status_code=204)
def delete_quote(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    db.delete(q)
    db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ lines
@router.post("/quotes/{qid}/lines", response_model=QuoteOut, status_code=201)
def add_line(qid: int, body: QuoteLineIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    import uuid

    ln = QuoteLine(
        quote_id=q.id,
        key=body.key or f"manual:{uuid.uuid4().hex[:8]}",
        section=body.section,
        position=body.position if body.position is not None else (max((l.position for l in q.lines), default=-1) + 1),
        name=body.name,
        unit=body.unit,
        qty=body.qty,
        unit_price=body.unit_price,
        purchase_price=body.purchase_price or 0.0,
        total=round(body.qty * body.unit_price, 2),
        catalog_item_id=body.catalog_item_id,
        source="manual",
        locked=True,
        hidden=body.hidden,
        meta=body.meta,
    )
    db.add(ln)
    db.flush()
    db.refresh(q)
    pricing.compute_totals(q)
    db.commit()
    db.refresh(q)
    return _out(db, q)


@router.patch("/quotes/{qid}/lines/{lid}", response_model=QuoteOut)
def update_line(qid: int, lid: int, body: QuoteLineUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    ln = db.get(QuoteLine, lid)
    if not ln or ln.quote_id != q.id:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(ln, k, v)
    if ln.source == "auto" and any(k in data for k in ("qty", "unit_price", "name", "unit")) and data.get("locked") is None:
        ln.locked = True
    pricing.compute_totals(q)
    db.commit()
    db.refresh(q)
    return _out(db, q)


@router.delete("/quotes/{qid}/lines/{lid}", response_model=QuoteOut)
def delete_line(qid: int, lid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    ln = db.get(QuoteLine, lid)
    if not ln or ln.quote_id != q.id:
        raise HTTPException(404)
    if ln.source == "auto":
        # hide instead of delete so recalculation does not bring it back
        ln.hidden = True
        ln.locked = True
    else:
        q.lines.remove(ln)
        db.delete(ln)
    pricing.compute_totals(q)
    db.commit()
    db.refresh(q)
    return _out(db, q)


# ------------------------------------------------------------------ documents
@router.get("/quotes/{qid}/html", response_class=HTMLResponse)
def quote_html(qid: int, mode: str = Query("client"), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return render_quote_html(db, _quote(db, qid), mode)


@router.get("/quotes/{qid}/pdf")
def quote_pdf(qid: int, mode: str = Query("client"), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    path = render_quote_pdf(db, q, mode)
    fname = f"Oferta_{q.number}_v{q.version}{'_internal' if mode == 'internal' else ''}.pdf"
    return FileResponse(str(path), media_type="application/pdf", filename=fname)


@router.get("/quotes/{qid}/xlsx")
def quote_xlsx(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """KSS-style Excel export (same structure as the original quote workbook)."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    q = _quote(db, qid)
    wb = Workbook()
    ws = wb.active
    ws.title = "KSS"
    ws["F1"] = f"№ {q.number}"
    ws["A2"] = "О Ф Е Р Т А"
    ws["A2"].font = Font(bold=True, size=14)
    ws["A4"] = q.title or ""
    ws.append([])
    ws.append([])
    ws.append([])
    ws.append(["№", "Наименование", "Мярка", "Количество", "Ед. цена", "Общо"])
    for c in ws[8]:
        c.font = Font(bold=True)
    roman = ["I", "II", "III", "IV", "V", "VI"]
    i = 0
    for code, title, _ in pricing.SECTIONS:
        lns = [l for l in q.lines if l.section == code and not l.hidden]
        if not lns:
            continue
        ws.append([roman[i], title, None, None, None, round(sum(l.total for l in lns), 2)])
        ws[ws.max_row][1].font = Font(bold=True)
        for j, l in enumerate(lns, 1):
            ws.append([j, l.name, l.unit, l.qty, l.unit_price, l.total])
        i += 1
    ws.append([])
    ws.append([None, None, None, None, "Общо без ДДС:", q.net_total])
    ws.append([None, None, None, None, f"ДДС {q.vat_pct:g}%:", q.vat_amount])
    ws.append([None, None, None, None, "Общо с ДДС:", q.total])
    ws.append([])
    ws.append([None, "Условия на плащане:"])
    ws.append([None, f"1. Аванс {q.advance_pct:g}%: {q.advance_amount:,.2f} € без ДДС"])
    ws.append([None, f"2. След монтаж: {q.balance_amount:,.2f} € без ДДС"])
    ws.column_dimensions["B"].width = 70
    for col in "CDEF":
        ws.column_dimensions[col].width = 14
    ws["A4"].alignment = Alignment(wrap_text=True)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=KSS_{q.number}_v{q.version}.xlsx"},
    )
