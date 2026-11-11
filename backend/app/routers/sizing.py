from __future__ import annotations

from typing import Any

from fastapi import HTTPException, APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import CatalogItem, User
from ..schemas import BatterySuggestion, CatalogItemOut, InverterSuggestion
from ..services import sizing
from ..services.pricing import estimate_yield
from ..services.settings import get_setting

router = APIRouter(prefix="/sizing", tags=["sizing"])


def _item_out(db: Session, it: CatalogItem) -> CatalogItemOut:
    markup = float(get_setting(db, "pricing").get("default_markup_pct", 0))
    o = CatalogItemOut.model_validate(it)
    o.effective_price = it.price_for(markup)
    return o


@router.get("/inverters", response_model=list[InverterSuggestion])
def inverters(
    phase: int = Query(3),
    connected_kw: float = Query(0),
    pv_kwp: float = Query(0),
    voltage_class: str | None = None,
    hybrid: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    pr = get_setting(db, "pricing")
    proc = get_setting(db, "procurement")
    res = sizing.suggest_inverters(
        db, phase, connected_kw, pv_kwp, voltage_class, hybrid, float(pr.get("default_markup_pct", 0)), float(pr.get("dc_ac_ratio_max", 1.35)),
        max_units=int(proc.get("max_parallel_inverters", 6) or 6), min_parallel_unit_kw=float(proc.get("min_parallel_unit_kw", 8) or 8),
    )
    return [InverterSuggestion(item=_item_out(db, r["item"]), qty=r["qty"], ac_total_kw=r["ac_total_kw"], ratio=r["ratio"], score=r["score"], reasons=r["reasons"], warnings=r["warnings"]) for r in res]


@router.get("/batteries", response_model=list[BatterySuggestion])
def batteries(
    inverter_id: int | None = None,
    target_kwh: float = Query(0),
    voltage_class: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.get(CatalogItem, inverter_id) if inverter_id else None
    pr = get_setting(db, "pricing")
    res = sizing.suggest_batteries(db, inv, target_kwh, voltage_class, float(pr.get("default_markup_pct", 0)))
    return [BatterySuggestion(item=_item_out(db, r["item"]), qty=r["qty"], total_kwh=r["total_kwh"], reasons=r["reasons"], warnings=r["warnings"], accessories=r["accessories"]) for r in res]


@router.post("/battery-parts")
def battery_parts(body: dict[str, Any] | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """BMS / rack / other accessory options for the chosen battery, the automatic choice and the resolved result
    for the given (draft) selections — drives the two independent selectors in the Equipment step."""
    from ..services import battery_acc

    sel = dict((body or {}).get("selections") or {})
    bat = db.get(CatalogItem, int(sel["battery_item_id"])) if sel.get("battery_item_id") else None
    inv = db.get(CatalogItem, int(sel["inverter_item_id"])) if sel.get("inverter_item_id") else None
    qty = int(sel.get("battery_qty") or 1) if bat else 0
    n_inv = max(1, int(sel.get("inverter_qty") or 1)) if inv else 1
    res = battery_acc.resolve(db, sel, inv, bat, qty, n_inv)
    cfg = battery_acc.normalize(sel)
    return {
        "hv": battery_acc.is_hv(bat),
        "family": (bat.specs or {}).get("family") if bat else None,
        "clusters": battery_acc.clusters_for(inv, bat, qty, n_inv) if bat and battery_acc.is_hv(bat) else [],
        "config": {k: {"mode": v["mode"], "items": v["items"]} for k, v in cfg.items()},
        "auto": res["auto"],
        "resolved": {k: [{"item_id": it.id, "name": it.name, "qty": q} for it, q, _w in res[k]] for k in ("bms", "rack", "other")},
        "warnings": res["warnings"],
        "notes": res["notes"],
        "options": battery_acc.options(db, bat),
    }


@router.get("/strings")
def strings(panel_id: int, inverter_id: int, n_panels: int, n_inverters: int = 1, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Quick string check (single plane) using the temperature-corrected engine; ``n_inverters`` splits the array over
    identical inverters in parallel."""
    from ..services import engineering

    pr = get_setting(db, "pricing")
    sd = engineering.string_design(db.get(CatalogItem, panel_id), db.get(CatalogItem, inverter_id), [{"name": "", "modules": n_panels}], {"design_tmin_c": pr.get("design_tmin_c", -20), "design_tcell_max_c": pr.get("design_tcell_max_c", 70), "voc_margin": pr.get("voc_margin", engineering.VOC_MARGIN)}, n_inverters=max(1, n_inverters))
    return {"strings": sd.get("count", 0), "modules_per_string": sd.get("modules_per_string", 0), "mppts": sd.get("mppts", 0), "inverters": sd.get("inverters", 1), "per_inverter": sd.get("per_inverter") or [], "warnings": sd.get("warnings", []), "detail": sd}


@router.post("/projects/{pid}/design")
def project_design(pid: int, body: dict[str, Any] | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Run the full engineering design for a project with the given (draft) selections —
    used by the Materials step to preview quantities before a quote exists."""
    from ..models import Project, RoofTypeConfig
    from ..services import pricing as pricing_svc

    project = db.get(Project, pid)
    if not project:
        raise HTTPException(404, "Проектът не е намерен")
    sel = dict((body or {}).get("selections") or (project.params or {}).get("selections") or {})
    pr = get_setting(db, "pricing")
    layout_sum = pricing_svc.active_layout_summary(project)
    panel = pricing_svc._item(db, sel.get("panel_item_id")) or (pricing_svc._item(db, project.layouts[0].panel_item_id) if project.layouts else None)
    panel_qty = int(sel.get("panel_qty") or 0)
    if sel.get("use_layout", True) and layout_sum["count"] > 0:
        panel_qty = layout_sum["count"]
        limit = int(sel.get("panel_limit") or 0)
        if 0 < limit < panel_qty:
            panel_qty = limit
    inverter = pricing_svc._item(db, sel.get("inverter_item_id"))
    battery = pricing_svc._item(db, sel.get("battery_item_id"))
    bq = int(sel.get("battery_qty") or 1) if battery else 0
    inv_qty = max(1, int(sel.get("inverter_qty") or 1)) if inverter else 1
    d = pricing_svc._design(db, project, sel, pr, panel, inverter, battery, bq, panel_qty, layout_sum, inverter_qty=inv_qty)
    # resolve catalog items for the preview
    from ..services import engineering

    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    # the equipped AC/DC board (picked by inverter phases, like the quote does) covers protection / enclosure roles
    want_ph = int((inverter.specs or {}).get("phases") or project.phase or 3) if inverter else int(project.phase or 3)
    sb = pricing_svc._item(db, sel.get("switchboard_item_id"))
    if sb is None or ((sb.specs or {}).get("phases") and int((sb.specs or {}).get("phases")) != want_ph and sel.get("auto_switchboard", True)):
        sb = next((b for b in sorted(items, key=lambda x: (x.sort_order or 0, x.id)) if b.category == "switchboard"
                   and int((b.specs or {}).get("phases") or 0) == want_ph), sb)
    covered = {str(x) for x in ((sb.specs or {}).get("covers_roles") or [])} if sb else set()
    roof = db.get(RoofTypeConfig, project.roof_type) if project.roof_type else None
    mmode = sel.get("mounting_mode", "auto")
    lump = bool(roof) and (roof.pricing_mode if mmode == "auto" else mmode) == "lump"
    d["switchboard"] = {"item_id": sb.id, "name": sb.name, "qty": inv_qty, "covers_roles": sorted(covered)} if sb else None
    for r in d.get("roles") or []:
        if r.get("role") in covered:
            r["item_id"], r["item_name"], r["unit_price"], r["status"] = None, None, None, "covered"
            continue
        it = engineering.find_item_for_role(items, r)
        if it is not None and lump and it.category == "mounting":
            # per-module construction price already includes fixings / earthing clamps (same rule as the quote)
            r["item_id"], r["item_name"], r["unit_price"], r["status"] = None, None, None, "covered"
            r["covered_by"] = "construction"
            continue
        r["item_id"] = it.id if it else None
        r["item_name"] = it.name if it else None
        r["unit_price"] = it.price_for(float(pr.get("default_markup_pct", 0))) if it else None
        r["status"] = "quoted" if it else "not_quoted"
    return d


@router.get("/yield")
def yield_estimate(kwp: float, azimuth_deg: float = 180, tilt_deg: float = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pr = get_setting(db, "pricing")
    sy = float(pr.get("specific_yield_kwh_per_kwp", 1250))
    return {"annual_kwh": estimate_yield(kwp, sy, azimuth_deg, tilt_deg), "specific_yield": sy}
