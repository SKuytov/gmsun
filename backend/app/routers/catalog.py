from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import CATEGORIES, MOUNTING_BASES, CatalogItem, LaborOption, MountingRule, RoofTypeConfig, User
from ..schemas import (
    CatalogItemCreate,
    CatalogItemOut,
    CatalogItemUpdate,
    LaborOptionIn,
    LaborOptionOut,
    MountingRuleIn,
    MountingRuleOut,
    RoofTypeIn,
    RoofTypeOut,
)
from ..services.excel import export_catalog_xlsx, import_catalog_xlsx
from ..services.settings import get_setting

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _out(db: Session, it: CatalogItem) -> CatalogItemOut:
    markup = float(get_setting(db, "pricing").get("default_markup_pct", 0))
    o = CatalogItemOut.model_validate(it)
    o.effective_price = it.price_for(markup)
    return o


@router.get("/meta")
def meta():
    return {"categories": CATEGORIES, "mounting_bases": MOUNTING_BASES}


@router.get("/items", response_model=list[CatalogItemOut])
def list_items(
    category: str | None = None,
    q: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    qry = db.query(CatalogItem)
    if category:
        qry = qry.filter(CatalogItem.category.in_(category.split(",")))
    if not include_inactive:
        qry = qry.filter(CatalogItem.active.is_(True))
    if q:
        qry = qry.filter(CatalogItem.name.ilike(f"%{q}%"))
    items = qry.order_by(CatalogItem.category, CatalogItem.sort_order, CatalogItem.name).all()
    return [_out(db, i) for i in items]


@router.post("/items", response_model=CatalogItemOut, status_code=201)
def create_item(body: CatalogItemCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")
    it = CatalogItem(**body.model_dump())
    db.add(it)
    db.commit()
    db.refresh(it)
    return _out(db, it)


@router.get("/items/{item_id}", response_model=CatalogItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404)
    return _out(db, it)


@router.patch("/items/{item_id}", response_model=CatalogItemOut)
def update_item(item_id: int, body: CatalogItemUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(it, k, v)
    db.commit()
    db.refresh(it)
    return _out(db, it)


@router.delete("/items/{item_id}", status_code=204)
def deactivate_item(item_id: int, hard: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404)
    if hard:
        db.query(MountingRule).filter(MountingRule.catalog_item_id == item_id).update({MountingRule.catalog_item_id: None})
        db.delete(it)
    else:
        it.active = False
    db.commit()
    return Response(status_code=204)


@router.post("/items/{item_id}/duplicate", response_model=CatalogItemOut, status_code=201)
def duplicate_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404)
    cp = CatalogItem(
        category=it.category, sku=it.sku, name=f"{it.name} (копие)", manufacturer=it.manufacturer, description=it.description,
        unit=it.unit, purchase_price=it.purchase_price, markup_pct=it.markup_pct, sell_price=it.sell_price, currency=it.currency,
        warranty=it.warranty, active=True, specs=dict(it.specs or {}), sort_order=it.sort_order,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return _out(db, cp)


@router.post("/import")
async def import_xlsx(category: str = Query("inverter"), file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(require_admin)):
    data = await file.read()
    try:
        return import_catalog_xlsx(db, data, category)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Import failed: {e}")


@router.get("/export")
def export_xlsx(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    data = export_catalog_xlsx(db)
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=gmsun-catalog.xlsx"},
    )


# ------------------------------------------------------------------ labor
@router.get("/labor", response_model=list[LaborOptionOut])
def list_labor(include_inactive: bool = False, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(LaborOption)
    if not include_inactive:
        q = q.filter(LaborOption.active.is_(True))
    return q.order_by(LaborOption.days, LaborOption.workers).all()


@router.post("/labor", response_model=LaborOptionOut, status_code=201)
def create_labor(body: LaborOptionIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lo = LaborOption(**body.model_dump())
    db.add(lo)
    db.commit()
    db.refresh(lo)
    return lo


@router.put("/labor/{lid}", response_model=LaborOptionOut)
def update_labor(lid: int, body: LaborOptionIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lo = db.get(LaborOption, lid)
    if not lo:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(lo, k, v)
    db.commit()
    db.refresh(lo)
    return lo


@router.delete("/labor/{lid}", status_code=204)
def delete_labor(lid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lo = db.get(LaborOption, lid)
    if lo:
        db.delete(lo)
        db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------------ roof types
@router.get("/roof-types", response_model=list[RoofTypeOut])
def list_roof_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(RoofTypeConfig).order_by(RoofTypeConfig.sort_order).all()


@router.put("/roof-types/{code}", response_model=RoofTypeOut)
def upsert_roof_type(code: str, body: RoofTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    rt = db.get(RoofTypeConfig, code)
    if rt is None:
        rt = RoofTypeConfig(code=code)
        db.add(rt)
    for k, v in body.model_dump().items():
        if k != "code":
            setattr(rt, k, v)
    db.commit()
    db.refresh(rt)
    return rt


# ------------------------------------------------------------------ mounting rules
@router.get("/mounting-rules", response_model=list[MountingRuleOut])
def list_rules(roof_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(MountingRule)
    if roof_type:
        q = q.filter(MountingRule.roof_type == roof_type)
    return q.order_by(MountingRule.roof_type, MountingRule.sort_order, MountingRule.id).all()


@router.post("/mounting-rules", response_model=MountingRuleOut, status_code=201)
def create_rule(body: MountingRuleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.basis not in MOUNTING_BASES:
        raise HTTPException(400, "Unknown basis")
    r = MountingRule(**body.model_dump())
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.put("/mounting-rules/{rid}", response_model=MountingRuleOut)
def update_rule(rid: int, body: MountingRuleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(MountingRule, rid)
    if not r:
        raise HTTPException(404)
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return r


@router.delete("/mounting-rules/{rid}", status_code=204)
def delete_rule(rid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(MountingRule, rid)
    if r:
        db.delete(r)
        db.commit()
    return Response(status_code=204)
