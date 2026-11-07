from __future__ import annotations

from fastapi import APIRouter, Depends, Query
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
    return sizing.string_check(db.get(CatalogItem, panel_id), db.get(CatalogItem, inverter_id), n_panels)


@router.get("/yield")
def yield_estimate(kwp: float, azimuth_deg: float = 180, tilt_deg: float = 20, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pr = get_setting(db, "pricing")
    sy = float(pr.get("specific_yield_kwh_per_kwp", 1250))
    return {"annual_kwh": estimate_yield(kwp, sy, azimuth_deg, tilt_deg), "specific_yield": sy}
