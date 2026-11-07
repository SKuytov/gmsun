"""Purchase orders, goods receipt, material readiness (ERP part of the hub)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Project, PurchaseOrder, PurchaseOrderLine, Quote, User
from ..services import documents, orders

router = APIRouter(tags=["orders"])
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _po(db: Session, oid: int) -> PurchaseOrder:
    po = db.get(PurchaseOrder, oid)
    if not po:
        raise HTTPException(404, "Order not found")
    return po


def _dt(d: date | None) -> datetime | None:
    return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) if d else None


class GenerateIn(BaseModel):
    suppliers: list[str] | None = None
    replace_drafts: bool = True


class OrderUpdate(BaseModel):
    status: str | None = None
    supplier: str | None = None
    supplier_ref: str | None = None
    ordered_at: date | None = None
    expected_at: date | None = None
    notes: str | None = None


class LineUpdate(BaseModel):
    qty_ordered: float | None = None
    unit_price: float | None = None
    expected_at: date | None = None
    notes: str | None = None
    status: str | None = None
    name: str | None = None
    sku: str | None = None


class LineIn(BaseModel):
    name: str
    unit: str = "бр."
    qty_ordered: float = 1
    unit_price: float = 0
    sku: str | None = None
    catalog_item_id: int | None = None
    expected_at: date | None = None
    notes: str | None = None


class ReceiveIn(BaseModel):
    qty: float | None = None  # None → the whole open quantity
    received_on: date | None = None
    note: str | None = None


@router.post("/quotes/{qid}/orders/generate")
def generate(qid: int, body: GenerateIn | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.get(Quote, qid)
    if not q:
        raise HTTPException(404, "Quote not found")
    body = body or GenerateIn()
    pos = orders.generate_orders(db, q, user.id, body.suppliers, body.replace_drafts)
    if q.status in ("draft", "sent"):
        q.status = "accepted"
    if q.project.status in ("draft", "quoted", "sent"):
        q.project.status = "accepted"
    db.commit()
    return [orders.order_dict(db.get(PurchaseOrder, po.id)) for po in pos]


@router.get("/projects/{pid}/orders")
def project_orders(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [orders.order_dict(po) for po in db.query(PurchaseOrder).filter(PurchaseOrder.project_id == pid).order_by(PurchaseOrder.number).all()]


@router.get("/projects/{pid}/readiness")
def project_readiness(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return orders.readiness(db, p)


@router.get("/orders")
def list_orders(status: str | None = None, supplier: str | None = None, overdue: bool = False, project_id: int | None = None,
                db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return orders.awaiting(db, status, supplier, overdue, project_id)


@router.get("/orders/{oid}")
def get_order(oid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return orders.order_dict(_po(db, oid))


@router.patch("/orders/{oid}")
def update_order(oid: int, body: OrderUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = _po(db, oid)
    data = body.model_dump(exclude_unset=True)
    if "status" in data:
        st = data.pop("status")
        if st not in orders.ORDER_STATUSES:
            raise HTTPException(422, "invalid status")
        po.status = st
        if st in ("sent", "confirmed") and not po.ordered_at:
            po.ordered_at = datetime.now(timezone.utc)
        if po.project and st in ("sent", "confirmed", "partial", "received") and po.project.status in ("quoted", "sent", "accepted"):
            po.project.status = "ordered"
    for k in ("ordered_at", "expected_at"):
        if k in data:
            setattr(po, k, _dt(data.pop(k)))
    for k, v in data.items():
        setattr(po, k, v)
    if po.status not in ("cancelled",):
        orders.recompute(po)
    db.commit()
    return orders.order_dict(po)


@router.delete("/orders/{oid}", status_code=204)
def delete_order(oid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = _po(db, oid)
    if po.status not in ("draft", "cancelled"):
        raise HTTPException(409, "Само чернови или отказани поръчки могат да се изтриват; иначе маркирайте като отказана.")
    db.delete(po)
    db.commit()
    return Response(status_code=204)


@router.post("/orders/{oid}/lines")
def add_line(oid: int, body: LineIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = _po(db, oid)
    po.lines.append(PurchaseOrderLine(position=max((l.position for l in po.lines), default=-1) + 1, name=body.name, unit=body.unit, qty_ordered=body.qty_ordered, qty_received=0.0, status="open", receipts=[],
                                      unit_price=body.unit_price, sku=body.sku, catalog_item_id=body.catalog_item_id, expected_at=_dt(body.expected_at) or po.expected_at, notes=body.notes, meta={"manual": True}))
    orders.recompute(po)
    db.commit()
    return orders.order_dict(po)


@router.patch("/orders/{oid}/lines/{lid}")
def update_line(oid: int, lid: int, body: LineUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = _po(db, oid)
    l = next((x for x in po.lines if x.id == lid), None)
    if not l:
        raise HTTPException(404, "Line not found")
    data = body.model_dump(exclude_unset=True)
    if "expected_at" in data:
        l.expected_at = _dt(data.pop("expected_at"))
    if "status" in data:
        st = data.pop("status")
        if st == "cancelled":
            l.status = "cancelled"
        elif l.status == "cancelled":
            l.status = "open"
    for k, v in data.items():
        setattr(l, k, v)
    orders.recompute(po)
    db.commit()
    return orders.order_dict(po)


@router.delete("/orders/{oid}/lines/{lid}")
def delete_line(oid: int, lid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    po = _po(db, oid)
    l = next((x for x in po.lines if x.id == lid), None)
    if not l:
        raise HTTPException(404, "Line not found")
    po.lines.remove(l)
    db.delete(l)
    orders.recompute(po)
    db.commit()
    return orders.order_dict(po)


@router.post("/orders/{oid}/lines/{lid}/receive")
def receive_line(oid: int, lid: int, body: ReceiveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    po = _po(db, oid)
    l = next((x for x in po.lines if x.id == lid), None)
    if not l:
        raise HTTPException(404, "Line not found")
    qty = body.qty if body.qty is not None else max(0.0, float(l.qty_ordered) - float(l.qty_received))
    if qty <= 0 and body.qty is None:
        raise HTTPException(409, "Позицията е доставена изцяло.")
    orders.receive(po, lid, qty, body.note, user.name or user.email, body.received_on)
    _sync_project_status(po)
    db.commit()
    return orders.order_dict(po)


@router.post("/orders/{oid}/receive-all")
def receive_all(oid: int, body: ReceiveIn | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    po = _po(db, oid)
    body = body or ReceiveIn()
    orders.receive_all(po, user.name or user.email, body.received_on)
    _sync_project_status(po)
    db.commit()
    return orders.order_dict(po)


def _sync_project_status(po: PurchaseOrder) -> None:
    if po.project and po.project.status in ("quoted", "sent", "accepted"):
        po.project.status = "ordered"


@router.get("/orders/{oid}/xlsx")
def order_xlsx(oid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    po = _po(db, oid)
    data = orders.order_workbook(db, po)
    name = orders.order_filename(po)
    documents.archive(db, po.project, "order", name, data, quote=po.quote, title=f"Поръчка {po.number} — {po.supplier}", user_id=user.id)
    db.commit()
    return Response(data, media_type=XLSX_MIME, headers={"Content-Disposition": f"attachment; filename={name}"})


@router.get("/orders/{oid}/summary")
def order_summary(oid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict[str, Any]:
    po = _po(db, oid)
    d = orders.order_dict(po)
    return {"number": d["number"], "supplier": d["supplier"], "status": d["status"], "lines": d["lines_total"], "received": d["lines_received"], "overdue": d["lines_overdue"], "total": d["total"]}
