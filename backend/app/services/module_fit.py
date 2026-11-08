"""Module (panel) recommendation engine.

Connects the roof planes (step 3), the client's demand (step 2) and the catalog (step 4): every active PV module
is laid out on every plane with the real geometry (roof polygon, obstacles, setback, gaps, both orientations), so
the recommendation is based on what *physically fits* and what that costs, not on nameplate data alone.

Industry practice encoded here (and documented in docs/ENGINEERING.md):

* a module is judged by its **effective €/Wp** – module price plus the balance-of-system cost that scales per
  module (clamps, rail length, labour) – not by the sticker price;
* **residential pitched roofs** (tile, metal, fibre cement) favour the 1.7–2.0 m "residential format" (108/120
  half-cells, ≤ 25 kg): safe to carry up a ladder, fits between hooks, less wind load on the ridge;
* **commercial flat roofs and ground mounts** favour large-format modules (2.3–2.4 m, 144/132 half-cells) for
  the lowest BOS €/Wp, bifacial where the structure is elevated;
* roof load matters on old/poor roofs and timber structures (prefer ≤ 13 kg/m², warn on glass-glass);
* frame thickness has to match the clamp range of the mounting system (Aerocompact 30–46 mm);
* when a target power is given the recommendation is the configuration that *meets* the target with the fewest
  modules on the best-oriented planes; when the whole roof is to be used it is the one with the most kWp per m².
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, Layout, Project, RoofTypeConfig
from . import layout_engine as le
from . import procurement
from .settings import get_setting

RESIDENTIAL_ROOFS = {"tile", "tile_xt", "tile_xtr", "plain_tile", "lt_sheet", "lt_sheet_ts", "standing_seam", "fibre_cement"}
FLAT_ROOFS = {"flat_concrete", "flat_ew", "flat_bifacial"}
GROUND = {"ground", "ground_ballast"}
CLAMP_MIN_MM, CLAMP_MAX_MM = 30.0, 46.0  # Aerocompact universal clamps
RESIDENTIAL_MAX_LEN_M = 2.05
RESIDENTIAL_MAX_KG = 26.0
HEAVY_KG_M2 = 13.5
BOS_PER_MODULE_EUR = 55.0  # clamps + rail share + labour share that scales with the module count (not with Wp); settings.procurement.bos_per_module_eur


def default_dims_mm(wp: float) -> tuple[int, int]:
    """Typical module format for a power class, used only when the datasheet dimensions are not in the catalog
    (66/72-cell 182 mm wafer classes → 2382/2278 mm, 54-cell → 1762 mm, small modules → 1722 mm)."""
    if wp >= 600:
        return 1134, 2382
    if wp >= 520:
        return 1134, 2278
    if wp >= 400:
        return 1134, 1762
    return 1134, 1722


def module_dims_m(sp: dict[str, Any] | None) -> tuple[float, float, bool]:
    """(width_m, height_m, estimated) for a panel's specs; falls back to the power-class default."""
    sp = sp or {}
    dw, dh = default_dims_mm(_f(sp, "wp"))
    w, h = _f(sp, "width_mm"), _f(sp, "height_mm")
    est = w <= 0 or h <= 0
    return (w if w > 0 else dw) / 1000, (h if h > 0 else dh) / 1000, est


def _f(d: dict[str, Any] | None, k: str, default: float = 0.0) -> float:
    try:
        v = (d or {}).get(k)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _has_price(it: CatalogItem) -> bool:
    return float(it.purchase_price or 0) > 0 or (it.sell_price is not None and float(it.sell_price) > 0)


# ----------------------------------------------------------------------------- geometry
def layout_geometry(lay: Layout) -> tuple[le.Polygon, list[le.Polygon]]:
    roof = [tuple(p) for p in (lay.roof_polygon or [])]
    if len(roof) < 3:
        roof = [(0.0, 0.0), (float(lay.plane_w_m), 0.0), (float(lay.plane_w_m), float(lay.plane_h_m)), (0.0, float(lay.plane_h_m))]
    obstacles = [[tuple(p) for p in ob] for ob in (lay.obstacles or []) if len(ob) >= 3]
    return roof, obstacles  # type: ignore[return-value]


def usable_area_m2(lay: Layout) -> float:
    roof, obstacles = layout_geometry(lay)
    return max(0.0, le.polygon_area(roof) - sum(le.polygon_area(o) for o in obstacles))


def orientation_factor(azimuth_deg: float, tilt_deg: float, optimal_tilt: float = 33.0) -> float:
    """Relative annual yield of a plane vs. the optimum (south, ~33° in Bulgaria). Simple transposition proxy:
    south 30° → 1.00, flat → ~0.90, east/west 30° → ~0.85, north 30° → ~0.70, south vertical → ~0.71."""
    tilt = max(0.0, min(90.0, float(tilt_deg or 0)))
    ft = 1.0 - 0.00009 * (tilt - optimal_tilt) ** 2
    az = 180.0 if azimuth_deg is None else float(azimuth_deg)
    d = math.radians((az % 360.0) - 180.0)  # 0 = south
    k = min(1.0, tilt / 45.0) * 0.45
    fa = 1.0 - (1.0 - math.cos(d)) * 0.5 * k
    return round(max(0.3, ft * fa), 3)


@lru_cache(maxsize=2048)
def _fill_cached(roof_key: tuple, obst_key: tuple, w_m: float, h_m: float, gap_x: float, gap_y: float, setback: float, row_sp: float, orientation: str) -> tuple[int, tuple]:
    roof = [tuple(p) for p in roof_key]
    obstacles = [[tuple(p) for p in ob] for ob in obst_key]
    params = le.FillParams(panel_w_m=w_m, panel_h_m=h_m, orientation=orientation, gap_x_m=gap_x, gap_y_m=gap_y, setback_m=setback, row_spacing_m=row_sp, offsets=4)
    res = le.auto_fill(roof, obstacles, params)  # type: ignore[arg-type]
    return res.count, tuple((p.x, p.y, p.w, p.h, p.row) for p in res.panels)


def fit_on_layout(lay: Layout, w_m: float, h_m: float, orientation: str = "auto") -> dict[str, Any]:
    """Best orientation and count of a module of w×h metres on a layout (uses the layout's gaps/setback)."""
    roof, obstacles = layout_geometry(lay)
    rk = tuple((round(x, 3), round(y, 3)) for x, y in roof)
    ok = tuple(tuple((round(x, 3), round(y, 3)) for x, y in ob) for ob in obstacles)
    gx, gy, sb, rs = float(lay.gap_x_m or 0.02), float(lay.gap_y_m or 0.02), float(lay.setback_m or 0.3), float(lay.row_spacing_m or 0.0)
    out: dict[str, Any] = {"layout_id": lay.id, "name": lay.name, "azimuth": lay.azimuth_deg, "tilt": lay.tilt_deg, "area_m2": round(usable_area_m2(lay), 2),
                           "factor": orientation_factor(lay.azimuth_deg, lay.tilt_deg)}
    opts = ("portrait", "landscape") if orientation == "auto" else (orientation,)
    best = None
    for o in opts:
        n, panels = _fill_cached(rk, ok, round(w_m, 3), round(h_m, 3), gx, gy, sb, rs, o)
        if best is None or n > best[0]:
            best = (n, o, panels)
    n, o, panels = best or (0, "portrait", ())
    out.update({"orientation": o, "count_max": n, "panels": panels, "count_used": n, "utilization": round(n * w_m * h_m / out["area_m2"], 3) if out["area_m2"] > 0 else 0.0})
    return out


def distribute(fits: list[dict[str, Any]], needed: int) -> list[dict[str, Any]]:
    """Give ``needed`` modules to the planes in order of yield factor (best orientation first), filling each
    plane before moving to the next, so the quoted part of the roof is the productive part."""
    remaining = max(0, int(needed))
    for f in sorted(fits, key=lambda f: (-f["factor"], -f["count_max"])):
        take = min(remaining, int(f["count_max"]))
        f["count_used"] = take
        remaining -= take
    return fits


def pick_compact(panels: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Choose ``n`` of the auto-filled modules as one tidy rectangular block (complete rows, symmetric row ends),
    the way a designer would draw a partial array: consecutive rows, the smallest bounding box, centred on the
    plane and away from the edge/corner wind zones.  Falls back to the most central modules on irregular planes."""
    n = max(0, min(int(n), len(panels)))
    if n == 0:
        return []
    if n == len(panels):
        return sorted(panels, key=lambda p: (p["row"], p["x"]))
    rows: dict[int, list[dict[str, Any]]] = {}
    for p in panels:
        rows.setdefault(int(p.get("row", 0)), []).append(p)
    order = sorted(rows)
    for r in order:
        rows[r].sort(key=lambda p: p["x"])
    cx = sum(p["x"] + p["w"] / 2 for p in panels) / len(panels)
    cy = sum(p["y"] + p["h"] / 2 for p in panels) / len(panels)
    best: tuple[float, float, list[dict[str, Any]]] | None = None
    for k in range(1, len(order) + 1):
        for s in range(0, len(order) - k + 1):
            window = [rows[r] for r in order[s : s + k]]
            if sum(len(r) for r in window) < n:
                continue
            m = math.ceil(n / k)
            # widen the block until it holds n (short rows next to obstacles give fewer than m modules)
            while sum(min(m, len(r)) for r in window) < n:
                m += 1
            # per row keep the m modules nearest the plane centre line
            chosen: list[list[dict[str, Any]]] = []
            for r in window:
                rr = sorted(r, key=lambda p: abs(p["x"] + p["w"] / 2 - cx))[:m]
                chosen.append(sorted(rr, key=lambda p: p["x"]))
            surplus = sum(len(r) for r in chosen) - n
            # trim the surplus from the ends of the rows farthest from the middle of the block, alternating sides
            ri = sorted(range(k), key=lambda i: -abs(i - (k - 1) / 2))
            side = 0
            while surplus > 0:
                for i in ri:
                    if surplus <= 0:
                        break
                    if len(chosen[i]) > 1:
                        chosen[i].pop(-1 if side == 0 else 0)
                        side ^= 1
                        surplus -= 1
                else:
                    if all(len(r) <= 1 for r in chosen):
                        break
            flat = [p for r in chosen for p in r][:n]
            xs0, xs1 = min(p["x"] for p in flat), max(p["x"] + p["w"] for p in flat)
            ys0, ys1 = min(p["y"] for p in flat), max(p["y"] + p["h"] for p in flat)
            area = (xs1 - xs0) * (ys1 - ys0)
            dist = math.hypot((xs0 + xs1) / 2 - cx, (ys0 + ys1) / 2 - cy)
            key = (round(area, 3), round(dist, 3))
            if best is None or key < (best[0], best[1]):
                best = (key[0], key[1], flat)
    if best is None:
        panels = sorted(panels, key=lambda p: math.hypot(p["x"] + p["w"] / 2 - cx, p["y"] + p["h"] / 2 - cy))[:n]
        return sorted(panels, key=lambda p: (p["row"], p["x"]))
    return sorted(best[2], key=lambda p: (p["row"], p["x"]))


# ----------------------------------------------------------------------------- recommendation
def demand(db: Session, project: Project, pricing: dict[str, Any]) -> tuple[float, str]:
    from .proposals import Ctx, demand_kwp  # local import to avoid a cycle

    return demand_kwp(Ctx(db, project))


def recommend(db: Session, project: Project, *, scope: str = "auto", strategy: str = "balanced", top: int = 6, orientation: str = "auto") -> dict[str, Any]:
    pricing = get_setting(db, "pricing")
    proc = get_setting(db, "procurement")
    sup = get_setting(db, "suppliers")
    markup = float(pricing.get("default_markup_pct", 0))
    survey = (project.params or {}).get("survey") or {}
    sel = (project.params or {}).get("selections") or {}
    layouts = list(project.layouts)
    need, need_basis = demand(db, project, pricing)
    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True), CatalogItem.category == "panel").all()
    tiers = procurement.classify(db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all(), proc)
    inverter = db.get(CatalogItem, int(sel.get("inverter_item_id") or 0)) if sel.get("inverter_item_id") else None
    roof_type = project.roof_type
    residential = roof_type in RESIDENTIAL_ROOFS
    flat_or_ground = roof_type in FLAT_ROOFS or roof_type in GROUND
    access = survey.get("roof_access")
    height = _f(survey, "building_height_m")
    roof_cond = survey.get("roof_condition")
    structure = survey.get("structure")
    total_area = sum(usable_area_m2(l) for l in layouts)
    small_roof = residential and (total_area < 120 or roof_type in ("tile", "tile_xt", "tile_xtr", "plain_tile", "fibre_cement"))
    residential_small_format = small_roof or access == "ladder"
    bos_per_module = float(proc.get("bos_per_module_eur", BOS_PER_MODULE_EUR) or BOS_PER_MODULE_EUR)

    cands: list[dict[str, Any]] = []
    for it in items:
        sp = it.specs or {}
        wp = _f(sp, "wp")
        w_m, h_m, dims_est = module_dims_m(sp)
        if wp <= 0 or w_m <= 0.3 or h_m <= 0.3:
            continue
        fits = [fit_on_layout(l, w_m, h_m, orientation) for l in layouts]
        count_max = sum(f["count_max"] for f in fits)
        if layouts and count_max == 0:
            continue
        kwp_max = count_max * wp / 1000
        # scope: how many modules are quoted
        if not layouts:
            count_used = max(1, round(need * 1000 / wp)) if need > 0 else 0
            mode = "target"
        elif scope == "roof" or need <= 0 or (scope == "auto" and kwp_max <= need * 1.15):
            count_used = count_max
            mode = "roof"
        else:
            count_used = min(count_max, max(1, math.ceil(need * 1000 / wp)))
            fits = distribute(fits, count_used)
            mode = "target"
        kwp = count_used * wp / 1000
        price = it.price_for(markup) if _has_price(it) else 0.0
        eur_wp = price / wp if price else None
        eur_wp_eff = (price + bos_per_module) / wp if price else None
        weight = _f(sp, "weight_kg")
        kg_m2 = weight / (w_m * h_m) if weight else 0.0
        eff = _f(sp, "efficiency") or round(wp / (w_m * h_m) / 10, 2)
        thick = _f(sp, "thickness_mm") or _f(sp, "frame_mm")
        lead = procurement.lead_time_days(it, sup)
        tier = procurement.tier_of(it, tiers)
        trow = tiers.get(it.id) or {}
        quality = {"economy": 0.15, "standard": 0.5, "premium": 0.85}[tier] if it.tier else float(trow.get("score", 0.5))
        large = h_m > RESIDENTIAL_MAX_LEN_M or (weight and weight > RESIDENTIAL_MAX_KG)
        warnings: list[str] = []
        reasons: list[str] = []
        penalty = 0.0
        if not price:
            warnings.append("Няма цена в каталога — поискайте оферта от доставчика.")
            penalty += 0.6
        if not sp.get("specs_verified"):
            warnings.append("Параметрите са извлечени автоматично и не са потвърдени.")
            penalty += 0.05
        if dims_est:
            warnings.append(f"Размерите липсват в каталога — приети {round(w_m * 1000)}×{round(h_m * 1000)} mm по класа мощност; проверете в datasheet-а.")
            penalty += 0.1
        if thick and not (CLAMP_MIN_MM <= thick <= CLAMP_MAX_MM):
            warnings.append(f"Рамка {thick:g} mm е извън обхвата на скобите 30–46 mm — нужни са други скоби.")
            penalty += 0.25
        if large and access == "ladder":
            warnings.append("Голям формат (над 2 m / 26 kg) при достъп по стълба — трудно и опасно носене; предвидете вишка/кран или жилищен формат.")
            penalty += 0.2
        elif small_roof and large:
            warnings.append("Голям формат върху малък скатен покрив — по-малко гъвкавост при подредбата и по-тежък монтаж.")
            penalty += 0.08
        if height >= 10 and large:
            warnings.append("Сграда ≥ 10 m: големите модули изискват кран/вишка и повече укрепване срещу вятър.")
            penalty += 0.1
        if kg_m2 > HEAVY_KG_M2 and (roof_cond in ("poor", "fair") or structure == "wood"):
            warnings.append(f"Тежък модул ({kg_m2:.1f} kg/m²) върху покрив в лошо състояние/дървена конструкция — проверете носимоспособността.")
            penalty += 0.2
        elif kg_m2 > HEAVY_KG_M2:
            reasons.append(f"{kg_m2:.1f} kg/m² — стъкло-стъкло/тежък модул, проверете носимоспособността.")
        if flat_or_ground and _f(sp, "bifaciality") > 0:
            reasons.append(f"Бифациален ({_f(sp, 'bifaciality'):g} %) — +5–10 % добив на повдигната конструкция.")
            penalty -= 0.08
        if flat_or_ground and not large and count_max > 40:
            reasons.append("На плосък покрив/терен големият формат обикновено дава по-ниска цена на конструкция и труд.")
            penalty += 0.05
        if small_roof and not large:
            reasons.append("Жилищен формат (≤ 2.05 m, ≤ 26 kg) — удобен за носене и монтаж на скатен покрив.")
        elif large and not residential_small_format:
            reasons.append("Голям формат — по-малко модули, скоби и труд за същата мощност.")
        if mode == "target" and need > 0 and kwp < need * 0.95:
            warnings.append(f"Побира само {kwp:.2f} kWp от необходимите {need:g} kWp.")
            penalty += 0.5 + (need - kwp) / need
        # string feasibility with the chosen inverter (quick check)
        if inverter and count_used > 0:
            s_ok, s_msg = _string_quick_check(it, inverter)
            if not s_ok:
                warnings.append(s_msg)
                penalty += 0.3
        cands.append({
            "item_id": it.id, "name": it.name, "manufacturer": it.manufacturer, "sku": it.sku, "wp": wp, "width_mm": round(w_m * 1000), "height_mm": round(h_m * 1000),
            "weight_kg": weight or None, "kg_m2": round(kg_m2, 1) if kg_m2 else None, "efficiency": round(eff, 2), "cells": sp.get("cells"), "thickness_mm": thick or None,
            "bifacial": _f(sp, "bifaciality") > 0, "tier": tier, "quality": round(quality, 2), "lead_time_days": lead, "supplier": procurement.supplier_of(it),
            "unit_price": round(price, 2) if price else None, "eur_per_wp": round(eur_wp, 3) if eur_wp else None, "eur_per_wp_effective": round(eur_wp_eff, 3) if eur_wp_eff else None,
            "modules_cost": round(price * count_used, 2) if price else None, "verified": bool(sp.get("specs_verified")),
            "layouts": [{k: v for k, v in f.items() if k != "panels"} for f in fits], "_fits": fits,
            "count_max": count_max, "kwp_max": round(kwp_max, 3), "count_used": count_used, "kwp": round(kwp, 3), "mode": mode,
            "utilization": round(sum(f["count_used"] * w_m * h_m for f in fits) / total_area, 3) if total_area > 0 else None,
            "kwp_per_m2": round(kwp_max / total_area, 4) if total_area > 0 else None,
            "warranty": it.warranty, "datasheet": bool(sp.get("datasheet_file") or sp.get("datasheet_url")),
            "warnings": warnings, "reasons": reasons, "_penalty": penalty,
        })

    if not cands:
        return {"candidates": [], "target_kwp": need, "demand_basis": need_basis, "scope": scope, "strategy": strategy, "layouts": [], "total_area_m2": round(total_area, 1)}

    # --------------------------------------------------------------- scoring (0 = best on every axis)
    def norm(vals: list[float | None], lower_better: bool = True) -> list[float]:
        xs = [v for v in vals if v is not None]
        if not xs:
            return [0.5 for _ in vals]
        lo, hi = min(xs), max(xs)
        span = (hi - lo) or 1.0
        out = []
        for v in vals:
            if v is None:
                out.append(1.0)
            else:
                n = (v - lo) / span
                out.append(n if lower_better else 1 - n)
        return out

    cost_n = norm([c["eur_per_wp_effective"] for c in cands])
    lead_n = norm([float(c["lead_time_days"]) for c in cands])
    qual_n = norm([c["quality"] + c["efficiency"] / 100 for c in cands], lower_better=False)
    if any(c["mode"] == "roof" for c in cands):
        fit_n = norm([c["kwp_max"] for c in cands], lower_better=False)
    else:
        fit_n = norm([abs(c["kwp"] - need) / need if need > 0 else 0.0 for c in cands])
    count_n = norm([float(c["count_used"] or c["count_max"]) for c in cands])  # fewer modules = less mounting/labour
    weights = {
        "economy": (0.55, 0.08, 0.05, 0.17, 0.15),
        "balanced": (0.38, 0.14, 0.18, 0.18, 0.12),
        "premium": (0.15, 0.08, 0.47, 0.18, 0.12),
        "fastest": (0.22, 0.5, 0.06, 0.12, 0.10),
    }[strategy if strategy in procurement.STRATEGIES else "balanced"]
    for i, c in enumerate(cands):
        c["score"] = round(weights[0] * cost_n[i] + weights[1] * lead_n[i] + weights[2] * qual_n[i] + weights[3] * fit_n[i] + weights[4] * count_n[i] + c.pop("_penalty"), 4)
    cands.sort(key=lambda c: (c["score"], c["eur_per_wp_effective"] or 9))
    # badges
    priced = [c for c in cands if c["eur_per_wp_effective"]]
    if priced:
        min(priced, key=lambda c: c["eur_per_wp_effective"])["badge_cost"] = True
    max(cands, key=lambda c: c["kwp_max"])["badge_kwp"] = True
    min(cands, key=lambda c: c["lead_time_days"])["badge_lead"] = True
    max(cands, key=lambda c: c["efficiency"])["badge_eff"] = True
    for rank, c in enumerate(cands, 1):
        c["rank"] = rank
        c["badges"] = [b for b, k in (("cost", "badge_cost"), ("kwp", "badge_kwp"), ("lead", "badge_lead"), ("eff", "badge_eff")) if c.pop(k, False)]
        if rank == 1:
            c["reasons"].insert(0, _why(c, strategy, need))
    for c in cands:
        c.pop("_fits", None)
    best = cands[0]
    return {
        "candidates": cands[: max(1, top)], "evaluated": len(cands), "target_kwp": need, "demand_basis": need_basis, "scope": best["mode"], "scope_requested": scope,
        "strategy": strategy, "total_area_m2": round(total_area, 1),
        "layouts": [{"layout_id": l.id, "name": l.name, "area_m2": round(usable_area_m2(l), 1), "azimuth": l.azimuth_deg, "tilt": l.tilt_deg, "factor": orientation_factor(l.azimuth_deg, l.tilt_deg), "panel_item_id": l.panel_item_id, "count": int((l.summary or {}).get("count") or 0)} for l in layouts],
        "current_panel_id": sel.get("panel_item_id") or (layouts[0].panel_item_id if layouts else None),
    }


def _why(c: dict[str, Any], strategy: str, need: float) -> str:
    parts = []
    if c["mode"] == "roof":
        parts.append(f"{c['count_max']} модула = {c['kwp_max']:.2f} kWp на наличната площ")
    else:
        parts.append(f"{c['count_used']} модула = {c['kwp']:.2f} kWp за цел {need:g} kWp")
    if c.get("eur_per_wp_effective"):
        parts.append(f"{c['eur_per_wp_effective']:.3f} €/Wp с конструкция и труд")
    parts.append({"economy": "най-ниска ефективна цена", "premium": "най-висок клас и ефективност", "fastest": "най-кратък срок на доставка", "balanced": "най-добър баланс цена/срок/качество"}.get(strategy, "балансиран избор"))
    return "; ".join(parts) + "."


def _string_quick_check(panel: CatalogItem, inverter: CatalogItem) -> tuple[bool, str]:
    """Is there any string length that fits the inverter's MPPT window with this module (Voc at −20 °C, Vmp at 70 °C)?"""
    sp, inv = panel.specs or {}, inverter.specs or {}
    voc, vmp = _f(sp, "voc"), _f(sp, "vmp")
    tc = _f(sp, "temp_coeff_voc", -0.28) / 100
    vmax = _f(inv, "max_dc_v") or _f(inv, "max_pv_voltage") or 1000
    mppt_min = _f(inv, "mppt_min_v") or _f(inv, "mppt_min") or 150
    if voc <= 0 or vmp <= 0:
        return True, ""
    voc_cold = voc * (1 + tc * (-20 - 25))
    vmp_hot = vmp * (1 + tc * (70 - 25))
    ns_max = int(vmax * 0.97 // voc_cold)
    ns_min = int(math.ceil(mppt_min / vmp_hot))
    if ns_max < ns_min:
        return False, f"Няма валидна дължина на стринга: Voc(−20 °C) {voc_cold:.0f} V → макс. {ns_max} модула, MPPT мин. изисква {ns_min}."
    return True, ""


# ----------------------------------------------------------------------------- apply
def apply(db: Session, project: Project, panel_item_id: int, *, scope: str = "auto", orientation: str = "auto", overrides: dict[int, str] | None = None) -> dict[str, Any]:
    """Set the module on every layout, re-place the panels (target mode: only the needed count, best planes first)
    and update the project selections. Returns a summary; the caller regenerates renders/quotes."""
    panel = db.get(CatalogItem, int(panel_item_id))
    if not panel or panel.category != "panel":
        raise ValueError("Невалиден модул")
    sp = panel.specs or {}
    wp = _f(sp, "wp")
    w_m, h_m, _dims_est = module_dims_m(sp)
    pricing = get_setting(db, "pricing")
    need, _basis = demand(db, project, pricing)
    layouts = list(project.layouts)
    fits = []
    for l in layouts:
        o = (overrides or {}).get(l.id) or orientation
        fits.append(fit_on_layout(l, w_m, h_m, o))
    count_max = sum(f["count_max"] for f in fits)
    kwp_max = count_max * wp / 1000
    if scope == "roof" or need <= 0 or (scope == "auto" and kwp_max <= need * 1.15):
        mode = "roof"
    else:
        mode = "target"
        fits = distribute(fits, min(count_max, max(1, math.ceil(need * 1000 / wp))))
    total = 0
    for l, f in zip(layouts, fits):
        panels = [dict(x=round(x, 4), y=round(y, 4), w=round(w, 4), h=round(h, 4), enabled=True, row=r) for (x, y, w, h, r) in f["panels"]]
        if f["count_used"] < len(panels):
            panels = pick_compact(panels, f["count_used"])
        l.panel_item_id = panel.id
        l.orientation = f["orientation"]
        l.panels = panels
        roof, _ = layout_geometry(l)
        if not l.roof_polygon:
            l.roof_polygon = [list(p) for p in roof]
        roof_cfg = db.get(RoofTypeConfig, project.roof_type)
        l.summary = le.summarize(panels, wp, l.gap_x_m, roof_cfg.rails_per_module if roof_cfg else 2, l.gap_y_m)
        total += len(panels)
    params = dict(project.params or {})
    sel = dict(params.get("selections") or {})
    sel["panel_item_id"] = panel.id
    sel["use_layout"] = True
    sel["panel_qty"] = total
    sel.pop("panel_limit", None)
    params["selections"] = sel
    project.params = params
    db.commit()
    db.refresh(project)
    return {"panel_item_id": panel.id, "mode": mode, "count": total, "kwp": round(total * wp / 1000, 3), "layouts": [{"layout_id": l.id, "orientation": l.orientation, "count": len(l.panels or [])} for l in layouts]}
