"""Project document archive, client package, local datasheet library, quote completeness check and the dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import CatalogItem, Project, ProjectDocument, PurchaseOrder, Quote, User
from ..services import completeness, documents, orders, pricing
from ..services.settings import get_setting

router = APIRouter(tags=["documents"])


def _project(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _quote(db: Session, qid: int) -> Quote:
    q = db.get(Quote, qid)
    if not q:
        raise HTTPException(404, "Quote not found")
    return q


# ----------------------------------------------------------------------------- project documents
@router.get("/projects/{pid}/documents")
def list_documents(pid: int, kind: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _project(db, pid)
    qs = db.query(ProjectDocument).filter(ProjectDocument.project_id == pid)
    if kind:
        qs = qs.filter(ProjectDocument.kind == kind)
    docs = [documents.doc_dict(d) for d in qs.order_by(ProjectDocument.created_at.desc()).all()]
    return {"documents": docs, "kinds": [{"code": k, "label": documents.KIND_LABELS_BG[k], "count": sum(1 for d in docs if d["kind"] == k)} for k in documents.KINDS]}


@router.post("/projects/{pid}/documents", status_code=201)
async def upload_document(pid: int, file: UploadFile = File(...), kind: str = Form("other"), title: str | None = Form(None), notes: str | None = Form(None),
                          quote_id: int | None = Form(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _project(db, pid)
    raw = await file.read()
    if not raw:
        raise HTTPException(422, "Празен файл")
    if len(raw) > 60 * 1024 * 1024:
        raise HTTPException(413, "Файлът е над 60 MB")
    doc = documents.store_upload(db, p, kind, file.filename or "file", raw, user_id=user.id, title=title, notes=notes, quote_id=quote_id)
    db.commit()
    return documents.doc_dict(doc)


class DocUpdate(BaseModel):
    title: str | None = None
    kind: str | None = None
    notes: str | None = None


@router.patch("/documents/{did}")
def update_document(did: int, body: DocUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = db.get(ProjectDocument, did)
    if not d:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in documents.KINDS:
        raise HTTPException(422, "invalid kind")
    if "notes" in data:
        sha = (d.notes or "").split(" ")[0] if (d.notes or "").startswith("sha1:") else ""
        data["notes"] = (sha + " " + (data["notes"] or "")).strip() or None
    for k, v in data.items():
        setattr(d, k, v)
    db.commit()
    return documents.doc_dict(d)


@router.delete("/documents/{did}", status_code=204)
def delete_document(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = db.get(ProjectDocument, did)
    if not d:
        raise HTTPException(404)
    documents.delete(db, d)
    db.commit()
    return Response(status_code=204)


@router.get("/documents/{did}/download")
def download_document(did: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    d = db.get(ProjectDocument, did)
    if not d:
        raise HTTPException(404)
    p = get_settings().data_dir / d.path
    if not p.exists():
        raise HTTPException(404, "Файлът липсва на диска")
    return FileResponse(str(p), media_type=d.mime or "application/octet-stream", filename=d.filename)


@router.get("/quotes/{qid}/client-package.zip")
def client_package(qid: int, merged: bool = True, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Everything the client receives, in one ZIP: quote, technical file, layout renders, datasheets (+ merged PDF)."""
    q = _quote(db, qid)
    data, name = documents.client_package(db, q, merged_pdf=merged)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={name}"})


# ----------------------------------------------------------------------------- completeness
@router.get("/quotes/{qid}/completeness")
def quote_completeness(qid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return completeness.check(db, _quote(db, qid))


class FixesIn(BaseModel):
    fixes: list[dict[str, Any]]


@router.post("/quotes/{qid}/completeness/apply")
def apply_fixes(qid: int, body: FixesIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = _quote(db, qid)
    completeness.apply_fixes(db, q, body.fixes)
    pricing.recalculate(db, q)
    db.commit()
    db.refresh(q)
    return completeness.check(db, q)


# ----------------------------------------------------------------------------- local datasheet library
@router.get("/catalog/datasheets/status")
def datasheet_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return documents.datasheet_status(db)


@router.post("/catalog/datasheets/mirror")
def datasheet_mirror(only_missing: bool = Query(True), db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Download every datasheet / manual URL referenced by the catalog into DATA_DIR/datasheets (background)."""
    started = documents.mirror_datasheets(SessionLocal, only_missing=only_missing)
    return {"started": started, **documents.datasheet_status(db)}


@router.get("/catalog/datasheets/library")
def datasheet_library(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Local library: catalog items with a datasheet on our server + the Aerocompact manuals."""
    items = []
    for ci in db.query(CatalogItem).filter(CatalogItem.active.is_(True)).order_by(CatalogItem.category, CatalogItem.name).all():
        p = documents.item_datasheet_path(ci, download=False)
        urls = documents._item_urls(ci)
        if p or urls:
            items.append({"id": ci.id, "category": ci.category, "name": ci.name, "manufacturer": ci.manufacturer, "local": bool(p), "size": p.stat().st_size if p else 0,
                          "url": f"/api/catalog/items/{ci.id}/datasheet" if p else None, "source_url": urls[0] if urls else None})
    lib = []
    for d in documents.library_docs():
        p = documents.local_path_for_url(d["url"])
        lib.append({**d, "local": bool(p), "file": f"/api/files/datasheets/{p.name}" if p else None, "size": p.stat().st_size if p else 0})
    return {"items": items, "library": lib}


# ----------------------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    today = now.date()
    by_status = {s: n for s, n in db.query(Project.status, func.count(Project.id)).group_by(Project.status).all()}
    projects = db.query(Project).order_by(Project.updated_at.desc()).limit(8).all()
    recent = [{"id": p.id, "number": p.number, "name": p.name, "client_name": p.client_name, "status": p.status, "updated_at": p.updated_at.isoformat() if p.updated_at else None,
               "kwp": round(pricing.active_layout_summary(p).get("kwp") or 0, 2)} for p in projects]
    # quotes: sent and about to expire / expired
    expiring = []
    for q in db.query(Quote).filter(Quote.status.in_(["sent", "draft"])).all():
        created = q.created_at if q.created_at.tzinfo else q.created_at.replace(tzinfo=timezone.utc)
        until = (created + timedelta(days=int(q.valid_days or 10))).date()
        if q.status == "sent" and until <= today + timedelta(days=3):
            expiring.append({"id": q.id, "number": q.number, "version": q.version, "project_id": q.project_id, "project_name": q.project.name, "client_name": q.project.client_name,
                             "total": q.total, "valid_until": until.isoformat(), "expired": until < today})
    expiring.sort(key=lambda x: x["valid_until"])
    aw = orders.awaiting(db)
    pipeline = {"draft": by_status.get("draft", 0), "quoted": by_status.get("quoted", 0) + by_status.get("sent", 0), "accepted": by_status.get("accepted", 0),
                "ordered": by_status.get("ordered", 0) + by_status.get("installing", 0), "done": by_status.get("done", 0), "rejected": by_status.get("rejected", 0)}
    # catalog health
    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    no_price = [i for i in items if not i.purchase_price and i.sell_price is None and i.category not in ("service", "transport")]
    indicative = [i for i in items if (i.specs or {}).get("price_source") == "indicative"]
    unverified = [i for i in items if i.category in ("panel", "inverter", "battery") and not (i.specs or {}).get("specs_verified")]
    proc = get_setting(db, "procurement") or {}
    max_age = int(proc.get("price_max_age_days") or 120)
    stale = [i for i in items if i.updated_at and (now - (i.updated_at if i.updated_at.tzinfo else i.updated_at.replace(tzinfo=timezone.utc))).days > max_age and i.category in ("panel", "inverter", "battery")]
    ds = documents.datasheet_status(db)
    # value in pipeline
    value_open = sum(q.total for q in db.query(Quote).filter(Quote.status == "sent").all())
    value_won = sum(q.total for q in db.query(Quote).filter(Quote.status == "accepted").all())
    return {
        "today": today.isoformat(),
        "pipeline": pipeline, "projects_total": sum(by_status.values()), "recent_projects": recent,
        "quotes": {"sent": db.query(Quote).filter(Quote.status == "sent").count(), "accepted": db.query(Quote).filter(Quote.status == "accepted").count(), "value_open": round(value_open, 2), "value_won": round(value_won, 2), "expiring": expiring[:10]},
        "deliveries": {"open_orders": sum(1 for o in aw["orders"] if o["status"] not in ("received", "cancelled")), "open_lines": len(aw["open_lines"]), "overdue_lines": len(aw["overdue_lines"]),
                       "overdue": aw["overdue_lines"][:10], "next": [l for l in aw["open_lines"] if not l["overdue"]][:10], "suppliers": aw["suppliers"][:6]},
        "catalog": {"items": len(items), "no_price": len(no_price), "indicative": len(indicative), "unverified": len(unverified), "stale": len(stale), "max_age_days": max_age,
                    "no_price_items": [{"id": i.id, "name": i.name} for i in no_price[:8]], "unverified_items": [{"id": i.id, "name": i.name} for i in unverified[:8]]},
        "datasheets": {k: ds[k] for k in ("items_with_url", "items_local", "library_total", "library_local", "files", "size_mb", "running")},
    }
