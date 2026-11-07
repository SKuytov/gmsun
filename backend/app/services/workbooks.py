"""Excel outputs: client/internal КСС workbook, purchase list and supplier RFQ (request-for-quotation) workbooks.

All sheets share one restrained corporate style (company letterhead block, dark header row, thin rules, proper
number formats, frozen header, print setup) so the files can be sent out without any manual touch-up.
"""
from __future__ import annotations

import io
import re
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from ..models import CatalogItem, Quote
from . import pricing, procurement
from .settings import get_setting

NAVY = "1F3A5F"
GREY = "F3F4F6"
LIGHT = "E8EEF5"
INK = "111827"
MUTED = "6B7280"
THIN = Side(style="thin", color="D1D5DB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
BOTTOM = Border(bottom=Side(style="medium", color=NAVY))
MONEY = '#,##0.00 "€"'
QTY = "#,##0.##"

F_TITLE = Font(name="Calibri", size=18, bold=True, color=NAVY)
F_H1 = Font(name="Calibri", size=12, bold=True, color=NAVY)
F_LABEL = Font(name="Calibri", size=9, color=MUTED)
F_BODY = Font(name="Calibri", size=10, color=INK)
F_BOLD = Font(name="Calibri", size=10, bold=True, color=INK)
F_HEAD = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
F_SMALL = Font(name="Calibri", size=9, color=MUTED, italic=False)
FILL_HEAD = PatternFill("solid", fgColor=NAVY)
FILL_SECTION = PatternFill("solid", fgColor=LIGHT)
FILL_TOTAL = PatternFill("solid", fgColor=GREY)


_CYR = dict(zip("абвгдежзийклмнопрстуфхцчшщъьюяАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЬЮЯ",
                ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h", "ts", "ch", "sh", "sht", "a", "y", "yu", "ya",
                 "A", "B", "V", "G", "D", "E", "Zh", "Z", "I", "Y", "K", "L", "M", "N", "O", "P", "R", "S", "T", "U", "F", "H", "Ts", "Ch", "Sh", "Sht", "A", "Y", "Yu", "Ya"]))


def ascii_name(s: str) -> str:
    """Latin-only file name part (HTTP headers are latin-1): transliterate Cyrillic, drop the rest."""
    out = "".join(_CYR.get(ch, ch) for ch in s)
    out = "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_. ") else "_" for ch in out)
    return (out.strip("_ ").replace(" ", "_") or "x")[:40]


def _safe(s: str) -> str:
    s = re.sub(r"[^\w\-. ]+", "_", s, flags=re.U).strip("_ ")
    return (s or "x")[:40]


def _letterhead(ws: Worksheet, company: dict[str, Any], title: str, subtitle: str | None, meta: list[tuple[str, str]], ncols: int) -> int:
    """Company block (left) + document meta (right). Returns the next free row."""
    last = get_column_letter(ncols)
    ws.merge_cells(f"A1:{get_column_letter(max(2, ncols // 2))}1")
    ws["A1"] = company.get("name") or ""
    ws["A1"].font = Font(name="Calibri", size=13, bold=True, color=NAVY)
    lines = [company.get("address"), " · ".join(x for x in [f"ЕИК {company['eik']}" if company.get("eik") else "", f"ДДС № {company['vat_no']}" if company.get("vat_no") else ""] if x),
             " · ".join(x for x in [company.get("phone"), company.get("email"), company.get("website")] if x)]
    r = 2
    for ln in lines:
        if ln:
            ws.cell(row=r, column=1, value=ln).font = F_SMALL
            r += 1
    # meta on the right
    mr = 1
    for k, v in meta:
        c = ws.cell(row=mr, column=ncols - 1, value=k)
        c.font = F_LABEL
        c.alignment = Alignment(horizontal="right")
        c2 = ws.cell(row=mr, column=ncols, value=v)
        c2.font = F_BOLD
        c2.alignment = Alignment(horizontal="right")
        mr += 1
    r = max(r, mr) + 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
    ws.cell(row=r, column=1, value=title).font = F_TITLE
    ws.row_dimensions[r].height = 28
    r += 1
    if subtitle:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(row=r, column=1, value=subtitle)
        c.font = F_BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 30
        r += 1
    for col in range(1, ncols + 1):
        ws.cell(row=r, column=col).border = BOTTOM
    ws.row_dimensions[r].height = 6
    _ = last
    return r + 2


def _header_row(ws: Worksheet, row: int, headers: list[str]) -> None:
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = F_HEAD
        c.fill = FILL_HEAD
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BORDER
    ws.row_dimensions[row].height = 30


def _cell(ws: Worksheet, row: int, col: int, value: Any, fmt: str | None = None, bold: bool = False, align: str | None = None, fill: PatternFill | None = None, wrap: bool = False) -> None:
    c = ws.cell(row=row, column=col, value=value)
    c.font = F_BOLD if bold else F_BODY
    c.border = BORDER
    if fmt:
        c.number_format = fmt
    c.alignment = Alignment(horizontal=align, vertical="top", wrap_text=wrap)
    if fill:
        c.fill = fill


def _widths(ws: Worksheet, widths: list[float]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _print(ws: Worksheet, landscape: bool = False, title_row: int | None = None) -> None:
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    if title_row:
        ws.print_title_rows = f"{title_row}:{title_row}"
    ws.oddFooter.left.text = "&8gmsun · &F"
    ws.oddFooter.right.text = "&8Стр. &P / &N"


def _kv_block(ws: Worksheet, row: int, col: int, title: str, pairs: list[tuple[str, str]]) -> int:
    """Small 'Label  value' block written as rich text in one column (spills into the empty cells to the right)."""
    ws.cell(row=row, column=col, value=title).font = F_H1
    row += 1
    lab = InlineFont(rFont="Calibri", sz=9, color=MUTED)
    val = InlineFont(rFont="Calibri", sz=10, color=INK, b=True)
    for k, v in pairs:
        if not v:
            continue
        ws.cell(row=row, column=col).value = CellRichText(TextBlock(lab, f"{k}:  "), TextBlock(val, str(v)))
        row += 1
    return row


# ====================================================================================== КСС / quote workbook
def quote_workbook(db: Session, q: Quote, internal: bool = False) -> bytes:
    company = get_setting(db, "company")
    pr = get_setting(db, "pricing")
    sel = q.selections or {}
    info = sel.get("_info") or {}
    p = q.project
    wb = Workbook()
    ws = wb.active
    ws.title = "Оферта"
    ncols = 8 if internal else 6
    meta = [("Оферта №", q.number), ("Дата", (q.created_at.date() if q.created_at else date.today()).strftime("%d.%m.%Y")), ("Валидност", f"{q.valid_days or pr.get('quote_validity_days', 10)} дни"), ("Версия", f"v{q.version}")]
    r = _letterhead(ws, company, q.title or get_setting(db, "texts").get("quote_title", "Оферта"), None, meta, ncols)
    # client / site
    r0 = r
    r1 = _kv_block(ws, r, 2, "Възложител", [("Име", p.client_name), ("Фирма", p.client_company or ""), ("ЕИК", p.client_eik or ""), ("Телефон", p.client_phone or ""), ("E-mail", p.client_email or ""), ("Адрес", p.client_address or "")])
    r2 = _kv_block(ws, r0, 4, "Обект", [("Адрес", p.site_address or ""), ("Мощност", f"{info.get('kwp', 0):g} kWp · {info.get('panel_qty', 0)} модула"), ("Батерия", f"{info.get('storage_kwh'):g} kWh" if info.get('storage_kwh') else "без батерия"), ("Срок за изпълнение", f"{q.execution_days} дни" if q.execution_days else ""), ("Срок на доставка", f"{info.get('lead_time_days')} работни дни" if info.get("lead_time_days") else "")])
    r = max(r1, r2) + 1
    headers = ["№", "Наименование", "Мярка", "Количество", "Ед. цена", "Общо"] + (["Доставна", "Марж"] if internal else [])
    _header_row(ws, r, headers)
    head_row = r
    r += 1
    roman = ["I", "II", "III", "IV", "V", "VI", "VII"]
    i = 0
    for code, title, _en in pricing.SECTIONS:
        lns = [l for l in q.lines if l.section == code and not l.hidden]
        if not lns:
            continue
        _cell(ws, r, 1, roman[i], bold=True, align="center", fill=FILL_SECTION)
        _cell(ws, r, 2, title, bold=True, fill=FILL_SECTION)
        for c in range(3, 6):
            _cell(ws, r, c, None, fill=FILL_SECTION)
        _cell(ws, r, 6, round(sum(l.total for l in lns), 2), MONEY, bold=True, fill=FILL_SECTION)
        if internal:
            cost = round(sum(l.qty * (l.purchase_price or 0) for l in lns), 2)
            _cell(ws, r, 7, cost, MONEY, bold=True, fill=FILL_SECTION)
            _cell(ws, r, 8, round(sum(l.total for l in lns) - cost, 2), MONEY, bold=True, fill=FILL_SECTION)
        r += 1
        for j, l in enumerate(lns, 1):
            _cell(ws, r, 1, j, align="center")
            _cell(ws, r, 2, l.name, wrap=True)
            _cell(ws, r, 3, l.unit, align="center")
            _cell(ws, r, 4, l.qty, QTY, align="right")
            _cell(ws, r, 5, l.unit_price, MONEY)
            _cell(ws, r, 6, l.total, MONEY)
            if internal:
                _cell(ws, r, 7, round(l.qty * (l.purchase_price or 0), 2), MONEY)
                _cell(ws, r, 8, round(l.total - l.qty * (l.purchase_price or 0), 2), MONEY)
            r += 1
        i += 1
    r += 1
    tot = [("Общо без ДДС", q.net_total, True), (f"ДДС {q.vat_pct:g} %", q.vat_amount, False), ("Общо с ДДС", q.total, True)]
    if q.discount_pct:
        tot.insert(0, (f"Отстъпка {q.discount_pct:g} %", -q.discount_amount, False))
        tot.insert(0, ("Сума преди отстъпка", q.subtotal, False))
    for label, val, bold in tot:
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
        _cell(ws, r, 4, label, bold=bold, align="right", fill=FILL_TOTAL if bold else None)
        _cell(ws, r, 6, val, MONEY, bold=bold, fill=FILL_TOTAL if bold else None)
        r += 1
    if internal:
        cost, margin = pricing.cost_and_margin(q)
        r += 1
        for label, val in [("Доставна стойност", cost), ("Марж", margin), ("Марж %", (margin / q.net_total * 100) if q.net_total else 0)]:
            ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=5)
            _cell(ws, r, 4, label, align="right")
            _cell(ws, r, 6, val, MONEY if "%" not in label else '0.0 "%"')
            r += 1
    r += 1
    basis = "без ДДС" if sel.get("advance_basis", "net") == "net" else "с ДДС"
    ws.cell(row=r, column=1, value="Условия на плащане").font = F_H1
    r += 1
    for txt in [f"Аванс {q.advance_pct:g} % при подписване на договор: {q.advance_amount:,.2f} € {basis}", f"Остатък след монтаж и пуск: {q.balance_amount:,.2f} € {basis}"]:
        ws.cell(row=r, column=1, value=txt).font = F_BODY
        r += 1
    r += 1
    texts = get_setting(db, "texts")
    for key, label in (("warranty", "Гаранционни условия"), ("notes", "Забележки")):
        val = (sel.get("texts") or {}).get(key) or texts.get(key)
        if val:
            ws.cell(row=r, column=1, value=label).font = F_H1
            r += 1
            for ln in str(val).splitlines():
                ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
                c = ws.cell(row=r, column=1, value=ln)
                c.font = F_BODY
                c.alignment = Alignment(wrap_text=True)
                r += 1
            r += 1
    r += 1
    ws.cell(row=r, column=1, value="Изготвил:").font = F_LABEL
    ws.cell(row=r, column=2, value=company.get("signatory") or "").font = F_BOLD
    ws.cell(row=r, column=4, value="Приел:").font = F_LABEL
    ws.cell(row=r, column=5, value=p.client_name).font = F_BOLD
    _widths(ws, [6, 62, 9, 12, 14, 15] + ([14, 13] if internal else []))
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    _print(ws, title_row=head_row)

    # ---- purchase list (internal only) + supplier summary
    if internal:
        wo = wb.create_sheet("Поръчка")
        scfg = get_setting(db, "suppliers")
        r = _letterhead(wo, company, f"Списък за поръчка — оферта {q.number}", "Материали и оборудване за поръчка, групирани по доставчик. Доставните цени са последните известни от каталога.", [("Оферта №", q.number), ("Дата", date.today().strftime("%d.%m.%Y"))], 10)
        _header_row(wo, r, ["Доставчик", "Код", "Наименование", "Производител", "Мярка", "Количество", "Доставна цена", "Общо", "Срок (раб. дни)", "Раздел / правило"])
        hr = r
        r += 1
        rows = []
        for l in q.lines:
            if l.hidden or l.section in ("labor", "other") or (l.catalog_item_id is None and not (l.meta or {}).get("role")):
                continue
            ci = l.catalog_item
            meta = l.meta or {}
            sup = (procurement.supplier_of(ci) if ci else None) or "Неразпределени"
            rule = f"{meta.get('basis')} × {meta.get('factor')}" if meta.get("basis") else (meta.get("role") or ("ръчно" if l.locked else ""))
            rows.append([sup, (ci.supplier_sku or ci.sku) if ci else "", ci.name if ci else l.name, ci.manufacturer if ci else "", l.unit, l.qty, l.purchase_price or 0, round(l.qty * (l.purchase_price or 0), 2), procurement.lead_time_days(ci, scfg) if ci else None, f"{l.section} · {rule}"])
        for row in sorted(rows, key=lambda x: (x[0], x[9], x[2])):
            for c, v in enumerate(row, 1):
                _cell(wo, r, c, v, MONEY if c in (7, 8) else (QTY if c == 6 else None), wrap=(c == 3))
            r += 1
        _widths(wo, [20, 14, 56, 16, 8, 11, 13, 13, 10, 24])
        wo.freeze_panes = wo.cell(row=hr + 1, column=1)
        _print(wo, landscape=True, title_row=hr)
        _supplier_summary_sheet(wb, db, q, company)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ====================================================================================== RFQ (supplier request)
def rfq_groups(db: Session, q: Quote) -> dict[str, list[dict[str, Any]]]:
    """Material lines of a quote grouped by supplier → rows ready for an RFQ table."""
    scfg = get_setting(db, "suppliers")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for l in q.lines:
        if l.hidden or l.section in ("labor", "other"):
            continue
        ci: CatalogItem | None = l.catalog_item
        if ci is None:
            if (l.meta or {}).get("role"):
                groups["Неразпределени"].append({"sku": "", "manufacturer": "", "name": l.name, "unit": l.unit, "qty": l.qty, "price": 0.0, "lead": None, "note": "няма артикул в каталога — моля предложете", "section": l.section})
            continue
        sup = procurement.supplier_of(ci) or "Неразпределени"
        sp = ci.specs or {}
        note_bits = []
        if sp.get("product_url"):
            note_bits.append(str(sp["product_url"]))
        if (l.meta or {}).get("spec"):
            spec = l.meta["spec"]
            for k, lab in (("rating_a", "A"), ("cross_section_mm2", "mm²"), ("poles", "полюса")):
                if spec.get(k):
                    note_bits.append(f"{spec[k]} {lab}")
        groups[sup].append({"sku": ci.supplier_sku or ci.sku or "", "manufacturer": ci.manufacturer or "", "name": ci.name, "unit": l.unit, "qty": l.qty, "price": l.purchase_price or 0.0, "lead": procurement.lead_time_days(ci, scfg), "note": " · ".join(note_bits), "section": l.section, "item_id": ci.id})
    # merge duplicates of the same item
    merged: dict[str, list[dict[str, Any]]] = {}
    for sup, rows in groups.items():
        acc: dict[tuple, dict[str, Any]] = {}
        for rw in rows:
            k = (rw.get("item_id"), rw["name"], rw["unit"])
            if k in acc:
                acc[k]["qty"] = round(acc[k]["qty"] + rw["qty"], 3)
            else:
                acc[k] = dict(rw)
        merged[sup] = sorted(acc.values(), key=lambda x: (pricing.SECTION_ORDER.get(x["section"], 9), x["name"]))
    return merged


def _rfq_sheet(wb: Workbook, db: Session, q: Quote, supplier: str, rows: list[dict[str, Any]], company: dict[str, Any], scfg: dict[str, Any], texts: dict[str, Any], sheet_title: str | None = None) -> Worksheet:
    smap = procurement.supplier_map(scfg)
    s = smap.get(supplier.lower(), {})
    ws = wb.create_sheet((sheet_title or _safe(supplier))[:31])
    ncols = 9
    needed = date.today() + timedelta(days=int(s.get("lead_time_days") or scfg.get("default_lead_time_days", 7)) * 7 // 5 + 2)
    meta = [("Запитване №", f"{q.number}-RFQ"), ("Дата", date.today().strftime("%d.%m.%Y")), ("Желана доставка до", needed.strftime("%d.%m.%Y"))]
    r = _letterhead(ws, company, "Запитване за оферта и наличност", texts.get("rfq_note"), meta, ncols)
    r0 = r
    r1 = _kv_block(ws, r, 2, "До доставчик", [("Фирма", supplier), ("Лице за контакт", s.get("contact") or ""), ("E-mail", s.get("email") or ""), ("Телефон", s.get("phone") or ""), ("Уеб", s.get("url") or "")])
    r2 = _kv_block(ws, r0, 7, "Доставка до", [("Адрес", scfg.get("delivery_address") or company.get("address") or ""), ("Получател", company.get("name") or ""), ("Контакт", company.get("signatory") or ""), ("Телефон", company.get("phone") or ""), ("E-mail", company.get("email") or ""), ("Референция", f"Проект {q.project.number} · {q.project.name}")])
    r = max(r1, r2) + 1
    _header_row(ws, r, ["№", "Код (доставчик)", "Производител", "Наименование", "Мярка", "Количество", "Последна цена (без ДДС)", "Очакван срок (раб. дни)", "Вашата оферта: цена / срок / забележка"])
    hr = r
    r += 1
    for i, rw in enumerate(rows, 1):
        _cell(ws, r, 1, i, align="center")
        _cell(ws, r, 2, rw["sku"], align="center", wrap=True)
        _cell(ws, r, 3, rw["manufacturer"])
        _cell(ws, r, 4, rw["name"] + (f"\n{rw['note']}" if rw["note"] else ""), wrap=True)
        _cell(ws, r, 5, rw["unit"], align="center")
        _cell(ws, r, 6, rw["qty"], QTY, bold=True, align="right")
        _cell(ws, r, 7, rw["price"] if rw["price"] else None, MONEY)
        _cell(ws, r, 8, rw["lead"], "0", align="center")
        _cell(ws, r, 9, None, fill=PatternFill("solid", fgColor="FFFBEB"))
        r += 1
    r += 1
    ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=6)
    _cell(ws, r, 4, "Ориентировъчна стойност по последни цени", bold=True, align="right", fill=FILL_TOTAL)
    _cell(ws, r, 7, round(sum(x["qty"] * x["price"] for x in rows), 2), MONEY, bold=True, fill=FILL_TOTAL)
    r += 2
    for txt in ["Моля, посочете: единична цена без ДДС, наличност и срок на доставка за всяка позиция, валидност на офертата и условия на плащане.", "При липса на точен артикул предложете еквивалент със същите технически параметри и приложете техническа документация."]:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncols)
        c = ws.cell(row=r, column=1, value=txt)
        c.font = F_BODY
        c.alignment = Alignment(wrap_text=True)
        ws.row_dimensions[r].height = 28
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="С уважение,").font = F_BODY
    r += 1
    ws.cell(row=r, column=1, value=company.get("signatory") or "").font = F_BOLD
    ws.cell(row=r + 1, column=1, value=company.get("name") or "").font = F_SMALL
    _widths(ws, [5, 16, 16, 58, 8, 11, 15, 12, 30])
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    _print(ws, landscape=True, title_row=hr)
    return ws


def _supplier_summary_sheet(wb: Workbook, db: Session, q: Quote, company: dict[str, Any]) -> Worksheet:
    scfg = get_setting(db, "suppliers")
    groups = rfq_groups(db, q)
    ws = wb.create_sheet("Доставчици")
    ncols = 6
    r = _letterhead(ws, company, f"План за доставки — оферта {q.number}", "Обобщение по доставчици: брой позиции, ориентировъчна стойност и най-дълъг срок на доставка. Общият срок на доставка за обекта се определя от най-бавната позиция.", [("Оферта №", q.number), ("Дата", date.today().strftime("%d.%m.%Y"))], ncols)
    _header_row(ws, r, ["Доставчик", "Позиции", "Стойност (доставна)", "Най-дълъг срок (раб. дни)", "Контакт", "Най-бавна позиция"])
    hr = r
    r += 1
    smap = procurement.supplier_map(scfg)
    overall = 0
    for sup, rows in sorted(groups.items(), key=lambda kv: -max((x["lead"] or 0) for x in kv[1])):
        s = smap.get(sup.lower(), {})
        slow = max(rows, key=lambda x: x["lead"] or 0)
        lead = slow["lead"] or 0
        overall = max(overall, lead)
        _cell(ws, r, 1, sup, bold=True)
        _cell(ws, r, 2, len(rows), "0", align="center")
        _cell(ws, r, 3, round(sum(x["qty"] * x["price"] for x in rows), 2), MONEY)
        _cell(ws, r, 4, lead, "0", align="center")
        _cell(ws, r, 5, " · ".join(x for x in [s.get("contact"), s.get("email"), s.get("phone")] if x))
        _cell(ws, r, 6, slow["name"], wrap=True)
        r += 1
    r += 1
    _cell(ws, r, 1, "Общ срок на доставка (най-бавна позиция)", bold=True, fill=FILL_TOTAL)
    for c in (2, 3):
        _cell(ws, r, c, None, fill=FILL_TOTAL)
    _cell(ws, r, 4, overall, "0", bold=True, align="center", fill=FILL_TOTAL)
    for c in (5, 6):
        _cell(ws, r, c, None, fill=FILL_TOTAL)
    _widths(ws, [24, 10, 18, 14, 34, 50])
    ws.freeze_panes = ws.cell(row=hr + 1, column=1)
    _print(ws, landscape=True, title_row=hr)
    return ws


def rfq_workbook(db: Session, q: Quote, supplier: str | None = None) -> bytes:
    """One workbook: summary sheet + one RFQ sheet per supplier (or only ``supplier`` if given)."""
    company = get_setting(db, "company")
    scfg = get_setting(db, "suppliers")
    texts = get_setting(db, "texts")
    groups = rfq_groups(db, q)
    if supplier:
        groups = {k: v for k, v in groups.items() if k.lower() == supplier.lower()}
    wb = Workbook()
    wb.remove(wb.active)
    if not supplier:
        _supplier_summary_sheet(wb, db, q, company)
    for sup, rows in groups.items():
        _rfq_sheet(wb, db, q, sup, rows, company, scfg, texts)
    if not wb.worksheets:
        wb.create_sheet("Няма позиции")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rfq_zip(db: Session, q: Quote) -> bytes:
    """ZIP with one workbook per supplier – ready to attach to separate e-mails."""
    company = get_setting(db, "company")
    scfg = get_setting(db, "suppliers")
    texts = get_setting(db, "texts")
    groups = rfq_groups(db, q)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for sup, rows in groups.items():
            wb = Workbook()
            wb.remove(wb.active)
            _rfq_sheet(wb, db, q, sup, rows, company, scfg, texts, sheet_title="Запитване")
            b = io.BytesIO()
            wb.save(b)
            z.writestr(f"Zayavka_{_safe(sup)}_{q.number}.xlsx", b.getvalue())
    return buf.getvalue()
