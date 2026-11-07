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
    res = sizing.suggest_inverters(db, phase, connected_kw, pv_kwp, voltage_class, hybrid, float(pr.get("default_markup_pct", 0)), float(pr.get("dc_ac_ratio_max", 1.35)))
    return [InverterSuggestion(item=_item_out(db, r["item"]), score=r["score"], reasons=r["reasons"], warnings=r["warnings"]) for r in res]


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


@router.get("/strings")
def strings(panel_id: int, inverter_id: int, n_panels: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Quick string check (single plane) using the temperature-corrected engine."""
    from ..services import engineering

    pr = get_setting(db, "pricing")
    sd = engineering.string_design(db.get(CatalogItem, panel_id), db.get(CatalogItem, inverter_id), [{"name": "", "modules": n_panels}], {"design_tmin_c": pr.get("design_tmin_c", -20), "design_tcell_max_c": pr.get("design_tcell_max_c", 70)})
    return {"strings": sd.get("count", 0), "modules_per_string": sd.get("modules_per_string", 0), "mppts": sd.get("mppts", 0), "warnings": sd.get("warnings", []), "detail": sd}


@router.post("/projects/{pid}/design")
def project_design(pid: int, body: dict[str, Any] | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Run the full engineering design for a project with the given (draft) selections —
    used by the Materials step to preview quantities before a quote exists."""
    from ..models import Project
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
    inverter = pricing_svc._item(db, sel.get("inverter_item_id"))
    battery = pricing_svc._item(db, sel.get("battery_item_id"))
    bq = int(sel.get("battery_qty") or 1) if battery else 0
    d = pricing_svc._design(db, project, sel, pr, panel, inverter, battery, bq, panel_qty, layout_sum)
    # resolve catalog items for the preview
    from ..services import engineering

    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    for r in d.get("roles") or []:
        it = engineering.find_item_for_role(items, r)
        r["item_id"] = it.id if it else None
        r["item_name"] = it.name if it else None
        r["unit_price"] = it.price_for(float(pr.get("default_markup_pct", 0))) if it else None
    return d


@router.get("/yield")
def yield_estimate(kwp: float, azimuth_deg: float = 180, tilt_deg: float = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pr = get_setting(db, "pricing")
    sy = float(pr.get("specific_yield_kwh_per_kwp", 1250))
    return {"annual_kwh": estimate_yield(kwp, sy, azimuth_deg, tilt_deg), "specific_yield": sy}
