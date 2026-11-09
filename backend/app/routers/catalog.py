from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..db import get_db
from ..models import CATEGORIES, MOUNTING_BASES, CatalogItem, LaborOption, MountingRule, RoofTypeConfig, User, TIERS
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
from ..services import dataset_io, procurement
from ..services.datafill import fill_missing
from ..services.settings import get_setting

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _out(db: Session, it: CatalogItem) -> CatalogItemOut:
    return _outs(db, [it])[0]


def _outs(db: Session, items: list[CatalogItem]) -> list[CatalogItemOut]:
    markup = float(get_setting(db, "pricing").get("default_markup_pct", 0))
    eff = procurement.effective(db, items)
    out: list[CatalogItemOut] = []
    for it in items:
        o = CatalogItemOut.model_validate(it)
        o.effective_price = it.price_for(markup)
        e = eff.get(it.id, {})
        o.effective_lead_time_days = e.get("lead_time_days")
        o.effective_tier = e.get("tier")
        if not o.supplier:
            o.supplier = e.get("supplier")
        out.append(o)
    return out


@router.get("/meta")
def meta():
    return {"categories": CATEGORIES, "mounting_bases": MOUNTING_BASES, "tiers": list(TIERS)}


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
    return _outs(db, items)


def _resync(db: Session) -> None:
    """Prices / items / labor / roof data changed → every working (draft) quote is refreshed automatically."""
    from ..services import autosync

    autosync.recalc_all_drafts(db)


@router.post("/items", response_model=CatalogItemOut, status_code=201)
def create_item(body: CatalogItemCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if body.category not in CATEGORIES:
        raise HTTPException(400, "Unknown category")
    if body.tier and body.tier not in TIERS:
        raise HTTPException(400, "Unknown tier")
    it = CatalogItem(**body.model_dump())
    db.add(it)
    db.commit()
    db.refresh(it)
    _resync(db)
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
    data = body.model_dump(exclude_unset=True)
    if data.get("tier") and data["tier"] not in TIERS:
        raise HTTPException(400, "Unknown tier")
    for k, v in data.items():
        setattr(it, k, v)
    db.commit()
    db.refresh(it)
    _resync(db)
    return _out(db, it)


@router.delete("/items/{item_id}", status_code=204)
def deactivate_item(item_id: int, hard: bool = False, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404)
    if hard:
        from ..services.catalog_final import remove_items

        keep = {i for (i,) in db.query(CatalogItem.id).filter(CatalogItem.id != item_id).all()}
        remove_items(db, [it], keep)  # quote/order lines keep their text, rules and selections are cleaned
    else:
        it.active = False
    db.commit()
    _resync(db)
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


# ------------------------------------------------------------------ whole dataset (all tables) round trip
@router.get("/dataset.xlsx")
def dataset_xlsx(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """One workbook, one sheet per editable table (items, labor, roof types, mounting rules, suppliers, settings)."""
    return Response(
        dataset_io.export_workbook(db),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=gmsun-dataset.xlsx"},
    )


@router.get("/dataset.zip")
def dataset_zip(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Same tables as separate .xlsx files in one .zip package."""
    return Response(dataset_io.export_zip(db), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=gmsun-dataset.zip"})


@router.post("/dataset/import")
async def dataset_import(file: UploadFile = File(...), replace_items: bool = Query(False, description="delete catalog items that are not in the file"),
                         db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Import an edited dataset workbook (.xlsx) or a .zip of per-table workbooks. Only filled cells are applied."""
    data = await file.read()
    try:
        rep = dataset_io.import_dataset(db, data, file.filename or "", replace_items=replace_items)
        from ..services import autosync

        rep["quotes_updated"] = autosync.recalc_all_drafts(db)
        db.commit()
        return rep
    except Exception as e:  # noqa: BLE001
        db.rollback()
        raise HTTPException(400, f"Импортът е неуспешен: {e}")


@router.post("/dataset/fill-missing")
def dataset_fill_missing(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Fill empty prices / lead times / tiers / SKUs / suppliers with marked indicative values (never overwrites data)."""
    st = fill_missing(db)
    return {k: v for k, v in st.items() if k != "unpriced_left"} | {"unpriced_left": st["unpriced_left"][:50]}


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
    _resync(db)
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
    _resync(db)
    return lo


@router.delete("/labor/{lid}", status_code=204)
def delete_labor(lid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    lo = db.get(LaborOption, lid)
    if lo:
        db.delete(lo)
        db.commit()
        _resync(db)
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
    _resync(db)
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
    _resync(db)
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
    _resync(db)
    return r


@router.delete("/mounting-rules/{rid}", status_code=204)
def delete_rule(rid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.get(MountingRule, rid)
    if r:
        db.delete(r)
        db.commit()
        _resync(db)
    return Response(status_code=204)


# ----------------------------------------------------------------------------- Aerocompact mounting systems
@router.get("/mounting/systems")
def mounting_systems(_: User = Depends(get_current_user)):
    """Aerocompact system catalogue (technical data + documents) and the roof type -> system mapping."""
    from ..seed_data.aerocompact import DOCS, ROOF_SYSTEM, SYSTEMS, all_documents

    return {"systems": SYSTEMS, "roof_system": ROOF_SYSTEM, "documents": all_documents(), "doc_sets": DOCS}


@router.post("/mounting/reseed", status_code=200)
def mounting_reseed(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Legacy: added the built-in Aerocompact catalogue. Disabled once the GM SUN final catalog is active – the system
    may only quote the curated items (add new ones manually or via the dataset import)."""
    from ..services import catalog_final

    if catalog_final.is_curated(db):
        raise HTTPException(409, "Каталогът е фиксиран към финалния набор артикули на GM SUN — вграденият каталог Aerocompact не се добавя. Добавете нови артикули ръчно или чрез импорт на набора данни.")
    from ..seed import seed_legacy_catalog

    before = db.query(CatalogItem).count()
    seed_legacy_catalog(db)
    return {"added_items": db.query(CatalogItem).count() - before}


@router.get("/final/status")
def final_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """State of the GM SUN final catalog migration (when, how many items were kept / deleted, backup file)."""
    from ..services import catalog_final
    from ..seed_data import gmsun_final as F

    mig = get_setting(db, "migrations").get(F.MIGRATION_KEY) or {}
    skus = {d["sku"] for d in F.ITEMS}
    present = {r.sku for r in db.query(CatalogItem).filter(CatalogItem.sku.in_(skus)).all()}
    return {"curated": catalog_final.is_curated(db), "done": catalog_final.is_done(db), "migration": mig, "final_items": len(skus), "final_present": len(present),
            "items_total": db.query(CatalogItem).count(), "missing": sorted(skus - present)}


@router.post("/final/reapply")
def final_reapply(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Restore the GM SUN final catalog: re-applies the 56 items with their datasheet specs and prices and deletes
    every other item (backup first). Use after experiments in the catalog."""
    from ..config import get_settings
    from ..services import catalog_final

    res = catalog_final.apply(db, get_settings().data_dir, force=True)
    from ..services import autosync

    res["quotes_updated"] = autosync.recalc_all_drafts(db)
    db.commit()
    return res


# ----------------------------------------------------------------------------- supplier portfolio & datasheets
@router.get("/supplier/status")
def supplier_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """How much of the catalog comes from the supplier snapshot / live sync."""
    from ..services.supplier_sync import SEED_FILE, SUPPLIER, load_seed_items

    rows = db.query(CatalogItem).all()
    linked = [r for r in rows if (r.specs or {}).get("supplier") == SUPPLIER]
    with_ds = [r for r in linked if (r.specs or {}).get("datasheet_url")]
    unverified = [r for r in rows if r.category in ("panel", "inverter", "battery") and not (r.specs or {}).get("specs_verified")]
    return {
        "supplier": SUPPLIER,
        "snapshot_items": len(load_seed_items()),
        "snapshot_file": SEED_FILE.name if SEED_FILE.exists() else None,
        "linked_items": len(linked),
        "with_datasheet": len(with_ds),
        "unverified_items": len(unverified),
    }


@router.post("/sync/green-energy")
def sync_green_energy(
    parse_datasheets: bool = Query(True, description="download + parse PDF datasheets (slower, needs internet)"),
    overwrite_specs: bool = Query(False, description="refresh auto-parsed specs of items not marked as verified"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Re-import the supplier portfolio from the live green-energy.bg Store API (prices, links, new products)."""
    from ..config import get_settings
    from ..services import catalog_final
    from ..services.supplier_sync import sync_from_site

    if catalog_final.is_curated(db):
        raise HTTPException(409, "Каталогът е фиксиран към финалния набор артикули на GM SUN — синхронизацията с green-energy.bg би добавила други артикули и е изключена. Цените се редактират в каталога или чрез импорт на набора данни.")

    try:
        return sync_from_site(db, get_settings().data_dir, parse_datasheets=parse_datasheets, overwrite_specs=overwrite_specs)
    except Exception as exc:  # network / parsing problems must not 500 without a message
        raise HTTPException(502, f"Синхронизацията не успя: {exc}") from exc


@router.get("/items/{item_id}/datasheet")
def item_datasheet(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Serve the datasheet PDF (uploaded or downloaded from the supplier and cached under DATA_DIR/datasheets)."""
    from ..config import get_settings
    from ..services.supplier_sync import cached_datasheet

    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404, "Артикулът не е намерен")
    sp = it.specs or {}
    data_dir = get_settings().data_dir
    path = None
    if sp.get("datasheet_file"):
        from pathlib import Path

        p = Path(data_dir) / "datasheets" / sp["datasheet_file"]
        path = p if p.exists() else None
    if path is None and sp.get("datasheet_url"):
        path = cached_datasheet(sp["datasheet_url"], data_dir)
    if path is None:
        raise HTTPException(404, "Няма наличен datasheet за този артикул")
    fname = f"{(it.sku or it.name)[:60]}.pdf".replace("/", "-")
    return Response(path.read_bytes(), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fname}"'})


@router.post("/items/{item_id}/datasheet", response_model=CatalogItemOut)
async def upload_datasheet(
    item_id: int,
    file: UploadFile = File(...),
    autofill: bool = Query(True, description="parse the PDF and fill empty spec fields"),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Upload a datasheet PDF for an item; optionally auto-fill its technical specs from the PDF text."""
    import hashlib
    from pathlib import Path

    from ..config import get_settings
    from ..services import datasheet_parse as dp
    from ..services.supplier_sync import datasheet_cache_dir

    it = db.get(CatalogItem, item_id)
    if not it:
        raise HTTPException(404, "Артикулът не е намерен")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Файлът не е PDF")
    d = datasheet_cache_dir(get_settings().data_dir)
    fname = f"item{item_id}-{hashlib.sha1(content).hexdigest()[:10]}.pdf"
    (d / fname).write_bytes(content)
    sp = dict(it.specs or {})
    sp["datasheet_file"] = fname
    filled: list[str] = []
    if autofill and it.category in ("panel", "inverter", "battery"):
        text = dp.pdf_to_text(str(d / fname))
        cols = dp.parse_by_category(it.category, text, [it.sku] if it.sku else None)
        col: dict = {}
        if cols:
            if it.category == "panel" and sp.get("wp"):
                col = min(cols, key=lambda c: abs((c.get("wp") or 0) - float(sp["wp"])))
            elif it.category == "inverter" and sp.get("ac_power_kw"):
                col = min(cols, key=lambda c: abs((c.get("ac_power_kw") or 0) - float(sp["ac_power_kw"])))
            else:
                col = cols[0]
        for k, v in col.items():
            if k in ("parsed_fields", "specs_verified", "spec_source", "model"):
                continue
            if sp.get(k) in (None, "", 0) and v not in (None, ""):
                sp[k] = v
                filled.append(k)
        if filled:
            sp["spec_source"] = "datasheet-upload"
    it.specs = sp
    db.commit()
    db.refresh(it)
    out = _out(db, it)
    out.specs = {**out.specs, "_autofilled": filled} if filled else out.specs
    return out
