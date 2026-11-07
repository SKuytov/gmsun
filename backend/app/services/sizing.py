"""Equipment sizing helpers: inverter ranking, battery quantity, string check."""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem


def _f(d: dict[str, Any], k: str, default: float = 0.0) -> float:
    try:
        v = d.get(k)
        return float(v) if v is not None and v != "" else default
    except (TypeError, ValueError):
        return default


def inverter_count(ac_kw: float, pv_kwp: float, max_pv_kw: float = 0.0, dc_ac_max: float = 1.35, max_units: int = 10) -> int:
    """How many identical ``ac_kw`` inverters a ``pv_kwp`` array needs.

    Rules: per-unit PV ≤ max PV input (or ``ac·dc_ac_max``), and a preferred DC/AC ratio ≤ ~1.25 when that costs
    at most one extra unit. Returns 0 when more than ``max_units`` would be needed (model too small)."""
    if ac_kw <= 0 or pv_kwp <= 0:
        return 1
    cap = min(max_pv_kw, ac_kw * dc_ac_max) if max_pv_kw and max_pv_kw > 0 else ac_kw * dc_ac_max
    n = max(1, math.ceil(pv_kwp / cap - 1e-9))
    if pv_kwp / (n * ac_kw) > 1.25 and pv_kwp / ((n + 1) * ac_kw) >= 0.85:
        n += 1
    return n if n <= max_units else 0


def suggest_inverters(
    db: Session,
    phase: int,
    connected_kw: float,
    pv_kwp: float,
    voltage_class: str | None,
    hybrid: bool | None,
    default_markup: float,
    dc_ac_max: float = 1.35,
    max_units: int = 10,
    min_parallel_unit_kw: float = 8.0,
) -> list[dict[str, Any]]:
    """Rank catalogue inverters for the project. Every row carries ``qty`` – the number of identical units needed for
    ``pv_kwp`` (1 for a single-inverter plant, N for parallel operation), ``ac_total_kw`` and the DC/AC ``ratio``.

    Parallel operation is only proposed with units of at least ``min_parallel_unit_kw`` – paralleling several small
    residential inverters is never the sound answer for a larger array."""
    items = db.query(CatalogItem).filter(CatalogItem.category == "inverter", CatalogItem.active.is_(True)).all()
    out: list[dict[str, Any]] = []
    for it in items:
        sp = it.specs or {}
        reasons: list[str] = []
        warnings: list[str] = []
        score = 0.0
        ph = int(_f(sp, "phases", 3))
        if ph != phase:
            continue
        ac = _f(sp, "ac_power_kw")
        if ac <= 0:
            warnings.append("липсва AC мощност в характеристиките")
        vc = (sp.get("battery_voltage_class") or "").upper()
        if voltage_class and vc and vc != voltage_class.upper():
            continue
        if hybrid is not None and bool(sp.get("hybrid", True)) != hybrid:
            continue
        max_pv = _f(sp, "max_pv_kw") or (ac * dc_ac_max if ac else 0)
        unit_cap = int(_f(sp, "max_parallel", 0)) or max_units
        qty = inverter_count(ac, pv_kwp, max_pv, dc_ac_max, max_units=max(1, min(unit_cap, max_units)))
        if qty == 0:
            continue  # would need too many units of this model
        if qty > 1 and ac < min_parallel_unit_kw:
            continue  # too small to make sense in parallel
        ac_tot = ac * qty
        ratio = (pv_kwp / ac_tot) if (pv_kwp > 0 and ac_tot > 0) else 0.0
        if qty > 1:
            reasons.append(f"{qty} × {ac:g} kW = {ac_tot:g} kW AC в паралел")
            score -= 1.2 * (qty - 1)  # more units = more wiring, commissioning and points of failure
            if not sp.get("parallel_capable", True):
                warnings.append("моделът няма потвърдена паралелна работа — проверете datasheet")
        # connected power: total inverter AC should not exceed grid connection (with 10% tolerance)
        if connected_kw > 0 and ac > 0:
            if ac_tot > connected_kw * 1.1:
                score -= (ac_tot - connected_kw) * 2
                warnings.append(f"AC {ac_tot:g} kW надвишава присъединената мощност {connected_kw:g} kW")
            else:
                score += 10 - abs(connected_kw - ac_tot)
                reasons.append(f"AC {ac_tot:g} kW ≤ присъединена {connected_kw:g} kW")
        if pv_kwp > 0 and ac > 0:
            per_unit = pv_kwp / qty
            if max_pv and per_unit > max_pv + 1e-9:
                score -= (per_unit - max_pv) * 3
                warnings.append(f"PV {per_unit:g} kWp на инвертор надвишава макс. вход {max_pv:g} kW")
            elif 0.8 <= ratio <= dc_ac_max:
                score += 8 - abs(ratio - 1.15) * 2
                reasons.append(f"DC/AC {ratio:.2f} — оптимално")
            elif ratio < 0.8:
                score += 3 - (0.8 - ratio) * 4
                reasons.append(f"инверторът е с резерв (DC/AC {ratio:.2f})")
            else:
                score += 5
                reasons.append(f"DC/AC {ratio:.2f}")
        if it.purchase_price <= 0 and it.sell_price is None:
            warnings.append("няма цена в каталога")
        if not sp.get("specs_verified") and sp.get("spec_source"):
            warnings.append("характеристиките са извлечени автоматично от datasheet — непроверени")
        if sp.get("datasheet_url") or sp.get("datasheet_file"):
            reasons.append("datasheet наличен")
        out.append(
            {
                "item": it,
                "qty": qty,
                "ac_total_kw": round(ac_tot, 2),
                "ratio": round(ratio, 2),
                "score": round(score, 2),
                "reasons": reasons,
                "warnings": warnings,
            }
        )
    out.sort(key=lambda r: (-r["score"], r["qty"], _f(r["item"].specs or {}, "ac_power_kw")))
    return out


def suggest_batteries(
    db: Session,
    inverter: CatalogItem | None,
    target_kwh: float,
    voltage_class: str | None,
    default_markup: float,
) -> list[dict[str, Any]]:
    inv_sp = (inverter.specs if inverter else {}) or {}
    inv_vc = (inv_sp.get("battery_voltage_class") or voltage_class or "").upper()
    inv_max_charge_kw = _f(inv_sp, "max_charge_kw")
    inv_max_parallel = int(_f(inv_sp, "max_battery_parallel", 0))
    items = db.query(CatalogItem).filter(CatalogItem.category == "battery", CatalogItem.active.is_(True)).all()
    out: list[dict[str, Any]] = []
    for it in items:
        sp = it.specs or {}
        vc = (sp.get("voltage_class") or "").upper()
        if inv_vc and vc and vc != inv_vc:
            continue
        kwh = _f(sp, "kwh")
        if kwh <= 0:
            continue
        qty = max(1, math.ceil(target_kwh / kwh)) if target_kwh > 0 else 1
        reasons = [f"{qty} × {kwh:g} kWh = {qty * kwh:g} kWh"]
        warnings: list[str] = []
        max_par = int(_f(sp, "max_parallel", 0))
        if max_par and qty > max_par:
            warnings.append(f"макс. {max_par} бр. паралелно за този модел")
        if inv_max_parallel and qty > inv_max_parallel:
            warnings.append(f"инверторът поддържа макс. {inv_max_parallel} батерийни модула")
        if vc == "HV" and inverter is not None:
            # HV stacks: check voltage window if given
            vmin, vmax = _f(inv_sp, "battery_v_min"), _f(inv_sp, "battery_v_max")
            vnom = _f(sp, "nominal_v")
            if vmin and vmax and vnom:
                if not (vmin <= vnom * qty <= vmax) and not (vmin <= vnom <= vmax):
                    warnings.append("напрежението на батерията е извън прозореца на инвертора — проверете")
        if it.purchase_price <= 0 and it.sell_price is None:
            warnings.append("няма цена в каталога")
        if not sp.get("specs_verified") and sp.get("spec_source"):
            warnings.append("характеристиките са извлечени автоматично от datasheet — непроверени")
        if inverter is not None:
            from .engineering import battery_compatibility

            warnings.extend(battery_compatibility(inverter, it, qty))
        accessories: list[dict[str, Any]] = []
        for acc in sp.get("accessories") or []:
            accessories.append(acc)
        out.append(
            {
                "item": it,
                "qty": qty,
                "total_kwh": round(qty * kwh, 2),
                "reasons": reasons,
                "warnings": warnings,
                "accessories": accessories,
            }
        )
    out.sort(key=lambda r: (len(r["warnings"]), abs(r["total_kwh"] - target_kwh)))
    return out


def string_check(panel: CatalogItem | None, inverter: CatalogItem | None, n_panels: int) -> dict[str, Any]:
    """Rough string design: how many strings and modules per string."""
    if not panel or not inverter or n_panels <= 0:
        return {}
    ps, inv = panel.specs or {}, inverter.specs or {}
    voc = _f(ps, "voc")
    vmp = _f(ps, "vmp")
    isc = _f(ps, "isc")
    max_dc_v = _f(inv, "max_dc_voltage", 1000 if (inv.get("battery_voltage_class") == "HV") else 500)
    mppt_v_min = _f(inv, "mppt_v_min", 150)
    mppt_v_max = _f(inv, "mppt_v_max", max_dc_v * 0.85 if max_dc_v else 850)
    mppts = int(_f(inv, "mppt_count", 2))
    strings_per_mppt = int(_f(inv, "strings_per_mppt", 1))
    max_isc = _f(inv, "max_input_current_a", 0)
    out: dict[str, Any] = {"mppts": mppts}
    if voc > 0:
        # cold-weather Voc margin +12% (BG winter -10 °C)
        max_modules = int(math.floor(max_dc_v / (voc * 1.12))) if max_dc_v else 0
        min_modules = int(math.ceil(mppt_v_min / (vmp * 0.9))) if vmp else 1
        out.update({"max_modules_per_string": max_modules, "min_modules_per_string": min_modules})
        strings = max(1, math.ceil(n_panels / max_modules)) if max_modules else 1
        per_string = math.ceil(n_panels / strings)
        out.update({"strings": strings, "modules_per_string": per_string})
        if per_string < min_modules:
            out["warning"] = "string voltage below MPPT minimum — consider fewer strings"
        if strings > mppts * max(strings_per_mppt, 1):
            out["warning"] = f"{strings} strings exceed inverter inputs ({mppts} MPPT × {strings_per_mppt})"
        if max_isc and isc > max_isc:
            out["warning"] = f"module Isc {isc:g} A exceeds inverter input current {max_isc:g} A"
    return out
