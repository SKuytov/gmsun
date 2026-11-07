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
from ..services import procurement, workbooks
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


@router.get("/quotes/{qid}/techfile.pdf")
def quote_techfile(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Technical file: string design, single-line diagram, mounting plan, full BOM, order list."""
    from ..services.techfile import render_techfile_pdf

    q = _quote(db, qid)
    path = render_techfile_pdf(db, q)
    return FileResponse(str(path), media_type="application/pdf", filename=f"Tehnichesko_dosie_{q.number}_v{q.version}.pdf")


@router.get("/quotes/{qid}/techfile.html", response_class=HTMLResponse)
def quote_techfile_html(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    from ..services.techfile import render_techfile_html

    return render_techfile_html(db, _quote(db, qid))


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/quotes/{qid}/xlsx")
def quote_xlsx(qid: int, internal: bool = False, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """КСС workbook. ``internal=true`` adds purchase/margin columns plus the purchase list and supplier plan sheets."""
    q = _quote(db, qid)
    data = workbooks.quote_workbook(db, q, internal=internal)
    name = f"{'KSS_vatreshna' if internal else 'KSS'}_{q.number}_v{q.version}.xlsx"
    return Response(data, media_type=XLSX_MIME, headers={"Content-Disposition": f"attachment; filename={name}"})


@router.get("/quotes/{qid}/rfq")
def quote_rfq_summary(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Suppliers involved in the quote with line counts, value and lead time (for the UI)."""
    q = _quote(db, qid)
    scfg = get_setting(db, "suppliers")
    smap = procurement.supplier_map(scfg)
    out = []
    for sup, rows in workbooks.rfq_groups(db, q).items():
        s = smap.get(sup.lower(), {})
        out.append({
            "supplier": sup, "lines": len(rows), "value": round(sum(r["qty"] * r["price"] for r in rows), 2),
            "lead_time_days": max((r["lead"] or 0) for r in rows), "email": s.get("email"), "contact": s.get("contact"),
            "unpriced": sum(1 for r in rows if not r["price"]),
        })
    return sorted(out, key=lambda x: -x["lead_time_days"])


@router.get("/quotes/{qid}/rfq.xlsx")
def quote_rfq_xlsx(qid: int, supplier: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Request-for-quotation workbook: summary sheet + one sheet per supplier (or a single supplier)."""
    q = _quote(db, qid)
    data = workbooks.rfq_workbook(db, q, supplier)
    suffix = f"_{workbooks._safe(supplier)}" if supplier else ""
    return Response(data, media_type=XLSX_MIME, headers={"Content-Disposition": f"attachment; filename=Zapitvane_{q.number}{suffix}.xlsx"})


@router.get("/quotes/{qid}/rfq.zip")
def quote_rfq_zip(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """One RFQ workbook per supplier, zipped – ready to attach to separate e-mails."""
    q = _quote(db, qid)
    return Response(workbooks.rfq_zip(db, q), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=Zapitvania_{q.number}.zip"})
