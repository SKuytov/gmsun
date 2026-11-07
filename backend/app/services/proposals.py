"""Automatic proposal engine.

For a project it builds complete, costed configurations (modules × inverter × battery + mounting, protection,
cabling, labour) for several purchasing strategies and ranks them, so the user can compare and pick one:

* ``economy``  – lowest client price
* ``balanced`` – best compromise between price, delivery time and equipment class
* ``premium``  – highest equipment class (brand / warranty / efficiency), then price
* ``fastest``  – shortest overall delivery time (the slowest line decides), then price

Every candidate is evaluated through the real pricing pipeline (``pricing.build_lines``) so the numbers shown in
the comparison are exactly what the quote will contain after "apply".
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, LaborOption, Project, Quote
from . import pricing, procurement, sizing
from .settings import get_setting

STRATEGIES = procurement.STRATEGIES


def _f(d: dict[str, Any] | None, k: str, default: float = 0.0) -> float:
    try:
        v = (d or {}).get(k)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _has_price(it: CatalogItem) -> bool:
    return float(it.purchase_price or 0) > 0 or (it.sell_price is not None and float(it.sell_price) > 0)


class Ctx:
    def __init__(self, db: Session, project: Project):
        self.db = db
        self.project = project
        self.pricing = get_setting(db, "pricing")
        self.proc = get_setting(db, "procurement")
        self.sup = get_setting(db, "suppliers")
        self.items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
        self.by_id = {i.id: i for i in self.items}
        self.tiers = procurement.classify(self.items, self.proc)
        self.markup = float(self.pricing.get("default_markup_pct", 0))

    def lead(self, it: CatalogItem) -> int:
        return procurement.lead_time_days(it, self.sup)

    def tier_score(self, it: CatalogItem) -> float:
        row = self.tiers.get(it.id)
        if it.tier:
            return {"economy": 0.15, "standard": 0.5, "premium": 0.85}[it.tier]
        return float(row["score"]) if row else 0.5

    def tier(self, it: CatalogItem) -> str:
        return procurement.tier_of(it, self.tiers)

    def rank(self, strategy: str, cands: list[CatalogItem], unit_cost) -> list[CatalogItem]:
        """Order candidate items for a strategy. ``unit_cost(item)`` → comparable cost (e.g. €/Wp)."""
        epd = float(self.proc.get("balanced_eur_per_day", 25.0))
        if strategy == "economy":
            key = lambda it: (unit_cost(it), self.lead(it))  # noqa: E731
        elif strategy == "premium":
            key = lambda it: (-self.tier_score(it), unit_cost(it))  # noqa: E731
        elif strategy == "fastest":
            key = lambda it: (self.lead(it), unit_cost(it))  # noqa: E731
        else:  # balanced: normalised cost + lead-time penalty − quality bonus
            costs = [unit_cost(it) for it in cands] or [1.0]
            lo, hi = min(costs), max(costs)
            span = (hi - lo) or 1.0

            def key(it: CatalogItem):
                c = (unit_cost(it) - lo) / span
                l = min(1.0, self.lead(it) / 30.0)
                q = self.tier_score(it)
                return (0.55 * c + 0.2 * l - 0.25 * q, unit_cost(it))

        return sorted(cands, key=key)


# ----------------------------------------------------------------------------- target sizing
def target_kwp(ctx: Ctx, base_sel: dict[str, Any]) -> tuple[float, str]:
    p = ctx.project
    lay = pricing.active_layout_summary(p)
    panel = ctx.by_id.get(int(base_sel.get("panel_item_id") or 0))
    if base_sel.get("use_layout", True) and lay.get("count"):
        wp = _f(panel.specs if panel else None, "wp", 0) or (_f(ctx.by_id.get(p.layouts[0].panel_item_id).specs, "wp") if p.layouts and p.layouts[0].panel_item_id in ctx.by_id else 0)
        return round(lay["count"] * wp / 1000, 3), "layout"
    if base_sel.get("panel_qty") and panel:
        return round(int(base_sel["panel_qty"]) * _f(panel.specs, "wp") / 1000, 3), "selection"
    sy = float(ctx.pricing.get("specific_yield", 1250) or 1250)
    if p.annual_consumption_kwh and p.annual_consumption_kwh > 0:
        kwp = p.annual_consumption_kwh / sy
        if p.connected_power_kw > 0:
            kwp = min(kwp, p.connected_power_kw * float(ctx.pricing.get("dc_ac_ratio_max", 1.35)))
        return round(max(kwp, 2.0), 2), "consumption"
    if p.connected_power_kw > 0:
        return round(p.connected_power_kw * 1.2, 2), "connected_power"
    return 10.0, "default"


# ----------------------------------------------------------------------------- evaluation
def evaluate(ctx: Ctx, sel: dict[str, Any]) -> dict[str, Any]:
    """Run the pricing pipeline on a transient quote and summarise it."""
    q = Quote(
        number="PREVIEW", status="draft", selections=sel, vat_pct=float(ctx.pricing.get("vat_pct", 20)),
        markup_pct=None, discount_pct=0.0, advance_pct=float(ctx.pricing.get("default_advance_pct", 70)),
    )
    lines, warnings, info = pricing.build_lines(ctx.db, ctx.project, q)
    subtotal = round(sum(float(l["qty"]) * float(l["unit_price"]) for l in lines if not l.get("hidden")), 2)
    cost = round(sum(float(l["qty"]) * float(l.get("purchase_price") or 0) for l in lines if not l.get("hidden")), 2)
    vat = round(subtotal * float(q.vat_pct or 0) / 100, 2)
    lead = 0
    bottleneck = None
    suppliers: dict[str, int] = {}
    by_section: dict[str, float] = {}
    for l in lines:
        by_section[l["section"]] = round(by_section.get(l["section"], 0) + float(l["qty"]) * float(l["unit_price"]), 2)
        it = ctx.by_id.get(l.get("catalog_item_id") or 0)
        if not it:
            continue
        ld = ctx.lead(it)
        sup = procurement.supplier_of(it) or "—"
        suppliers[sup] = max(suppliers.get(sup, 0), ld)
        if ld > lead:
            lead, bottleneck = ld, l["name"]
    missing_price = [l["name"] for l in lines if l.get("catalog_item_id") and float(l["unit_price"]) <= 0]
    return {
        "lines": lines,
        "warnings": warnings,
        "info": info,
        "subtotal": subtotal,
        "vat": vat,
        "total": round(subtotal + vat, 2),
        "cost": cost,
        "margin": round(subtotal - cost, 2),
        "lead_time_days": lead,
        "lead_bottleneck": bottleneck,
        "suppliers": suppliers,
        "by_section": by_section,
        "missing_price": missing_price,
    }


def _labor_for(ctx: Ctx, base_sel: dict[str, Any], kwp: float) -> dict[str, Any]:
    if base_sel.get("labor_mode") in ("per_w", "manual") or base_sel.get("labor_option_id"):
        return {}
    # pick the matrix option closest to a rule of thumb: ~1 day per 4 kWp with 3 workers, min 2 days
    opts = ctx.db.query(LaborOption).all()
    if not opts:
        return {"labor_mode": "per_w"}
    want_days = max(2, math.ceil(kwp / 4))
    best = min(opts, key=lambda o: (abs(o.days - want_days), abs(o.workers - 3), o.price))
    return {"labor_mode": "matrix", "labor_option_id": best.id}


def _key_items(ctx: Ctx, sel: dict[str, Any], ev: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    roles = [("panel", "Модули", sel.get("panel_item_id"), ev["info"].get("panel_qty")), ("inverter", "Инвертор", sel.get("inverter_item_id"), sel.get("inverter_qty") or 1), ("battery", "Батерия", sel.get("battery_item_id"), sel.get("battery_qty") or 0)]
    for role, label, iid, qty in roles:
        it = ctx.by_id.get(int(iid or 0))
        if not it:
            if role == "battery":
                out.append({"role": role, "label": label, "name": "без батерия", "qty": 0, "tier": None, "lead_time_days": None, "supplier": None, "item_id": None})
            continue
        out.append({
            "role": role, "label": label, "item_id": it.id, "name": it.name, "manufacturer": it.manufacturer, "qty": qty,
            "tier": ctx.tier(it), "lead_time_days": ctx.lead(it), "supplier": procurement.supplier_of(it),
            "unit_price": it.price_for(ctx.markup), "warranty": it.warranty,
        })
    mount = [l for l in ev["lines"] if l["section"] == "construction"]
    if mount:
        syst = {(ctx.by_id.get(l.get("catalog_item_id") or 0).specs or {}).get("system") for l in mount if ctx.by_id.get(l.get("catalog_item_id") or 0)}
        syst.discard(None)
        out.append({"role": "mounting", "label": "Монтаж", "name": ("Aerocompact " + ", ".join(sorted(str(s) for s in syst))) if syst else f"{len(mount)} позиции", "qty": len(mount), "tier": None, "lead_time_days": max((ctx.lead(ctx.by_id[l['catalog_item_id']]) for l in mount if l.get("catalog_item_id") in ctx.by_id), default=None), "supplier": None, "item_id": None})
    return out


# ----------------------------------------------------------------------------- generation
def generate(db: Session, project: Project, strategies: list[str] | None = None, base_sel: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = Ctx(db, project)
    base = dict(base_sel if base_sel is not None else (project.params or {}).get("selections") or {})
    for k in ("_info", "_warnings"):
        base.pop(k, None)
    strategies = [s for s in (strategies or list(STRATEGIES)) if s in STRATEGIES]
    kwp_target, basis = target_kwp(ctx, base)
    lay = pricing.active_layout_summary(project)
    layout_fixed = bool(base.get("use_layout", True) and lay.get("count"))
    n_p, n_i, n_b = int(ctx.proc.get("candidate_panels", 6)), int(ctx.proc.get("candidate_inverters", 4)), int(ctx.proc.get("candidate_batteries", 3))

    panels_all = [i for i in ctx.items if i.category == "panel" and _f(i.specs, "wp") > 0]
    priced = [i for i in panels_all if _has_price(i)]
    panel_pool = priced or panels_all
    if layout_fixed:
        pid = int(base.get("panel_item_id") or (project.layouts[0].panel_item_id if project.layouts else 0) or 0)
        panel_pool = [ctx.by_id[pid]] if pid in ctx.by_id else panel_pool[:1]

    want_battery = float(project.desired_storage_kwh or 0) > 0 or bool(base.get("battery_item_id"))
    target_kwh = float(project.desired_storage_kwh or 0)
    if target_kwh <= 0 and base.get("battery_item_id") and int(base["battery_item_id"]) in ctx.by_id:
        target_kwh = _f(ctx.by_id[int(base["battery_item_id"])].specs, "kwh") * int(base.get("battery_qty") or 1)

    variants: list[dict[str, Any]] = []
    for strat in strategies:
        cand_panels = ctx.rank(strat, panel_pool, lambda it: it.price_for(ctx.markup) / max(1.0, _f(it.specs, "wp")))[:n_p]
        best: dict[str, Any] | None = None
        evaluated = 0
        for panel in cand_panels:
            wp = _f(panel.specs, "wp")
            if layout_fixed:
                panel_qty = int(lay["count"])
            else:
                panel_qty = max(1, round(kwp_target * 1000 / wp))
            kwp = panel_qty * wp / 1000
            inv_rows = sizing.suggest_inverters(ctx.db, project.phase, project.connected_power_kw, kwp, project.voltage_class if want_battery else None, True if want_battery else None, ctx.markup, float(ctx.pricing.get("dc_ac_ratio_max", 1.35)))
            dc_ac_max = float(ctx.pricing.get("dc_ac_ratio_max", 1.35))

            def fits(it: CatalogItem) -> bool:
                ac = _f(it.specs, "ac_power_kw")
                if ac <= 0:
                    return False
                max_pv = _f(it.specs, "max_pv_kw") or ac * dc_ac_max
                if kwp > max_pv * 1.02 or ac < kwp / dc_ac_max * 0.98:
                    return False
                if project.connected_power_kw > 0 and ac > project.connected_power_kw * 1.1:
                    return False
                return ac <= max(kwp * 1.6, kwp + 3)  # not absurdly oversized

            ok_rows = [r for r in inv_rows if fits(r["item"]) and not any("надвишава" in w for w in r["warnings"])]
            inv_rows = ok_rows or [r for r in inv_rows if r["score"] > 0][: n_i * 2] or inv_rows[:n_i]
            inv_items = [r["item"] for r in inv_rows if _has_price(r["item"])] or [r["item"] for r in inv_rows]
            inv_cands = ctx.rank(strat, inv_items, lambda it: it.price_for(ctx.markup) / max(0.5, _f(it.specs, "ac_power_kw", 1)))[:n_i]
            for inv in inv_cands:
                bat_opts: list[tuple[CatalogItem | None, int, list[dict[str, Any]]]] = [(None, 0, [])]
                if want_battery and target_kwh > 0:
                    rows = sizing.suggest_batteries(ctx.db, inv, target_kwh, project.voltage_class, ctx.markup)
                    rows = [r for r in rows if not r["warnings"]] or rows
                    bitems = [r["item"] for r in rows if _has_price(r["item"])] or [r["item"] for r in rows]
                    rank_b = ctx.rank(strat, bitems, lambda it: it.price_for(ctx.markup) / max(0.5, _f(it.specs, "kwh", 1)))[:n_b]
                    bat_opts = [(r["item"], int(r["qty"]), r["accessories"]) for r in rows if r["item"] in rank_b] or [(None, 0, [])]
                for bat, bq, acc in bat_opts:
                    sel = dict(base)
                    sel.update({
                        "panel_item_id": panel.id, "panel_qty": panel_qty, "inverter_item_id": inv.id, "inverter_qty": 1,
                        "battery_item_id": bat.id if bat else None, "battery_qty": bq if bat else 0,
                        "battery_accessories": [{"item_id": a.get("item_id"), "qty": a.get("qty")} for a in acc] if bat else [],
                        "strategy": strat,
                    })
                    if not layout_fixed:
                        sel["use_layout"] = False
                    sel.update(_labor_for(ctx, base, kwp))
                    ev = evaluate(ctx, sel)
                    evaluated += 1
                    score = _score(ctx, strat, sel, ev)
                    if best is None or score < best["_score"]:
                        best = {"_score": score, "sel": sel, "ev": ev, "panel": panel, "inv": inv, "bat": bat}
        if best is None:
            continue
        ev = best["ev"]
        bg, en = procurement.STRATEGY_LABELS[strat]
        variants.append({
            "strategy": strat, "label_bg": bg, "label_en": en,
            "selections": best["sel"],
            "kwp": ev["info"].get("kwp"), "panel_qty": ev["info"].get("panel_qty"),
            "battery_kwh": round(_f(best["bat"].specs, "kwh") * int(best["sel"].get("battery_qty") or 0), 1) if best["bat"] else 0,
            "subtotal": ev["subtotal"], "vat": ev["vat"], "total": ev["total"], "cost": ev["cost"], "margin": ev["margin"],
            "lead_time_days": ev["lead_time_days"], "lead_bottleneck": ev["lead_bottleneck"], "suppliers": ev["suppliers"],
            "by_section": ev["by_section"], "execution_days": ev["info"].get("execution_days"),
            "yield_kwh": round(pricing.estimate_yield(float(ev["info"].get("kwp") or 0), float(ctx.pricing.get("specific_yield", 1250)))),
            "key_items": _key_items(ctx, best["sel"], ev),
            "warnings": [w for w in ev["warnings"] if "Липсва цена" not in w][:8],
            "missing_price": ev["missing_price"][:8],
            "evaluated": evaluated,
            "quality": round(_quality(ctx, best["sel"]), 2),
        })
    # relative badges
    if variants:
        cheapest = min(v["total"] for v in variants)
        fastest = min(v["lead_time_days"] for v in variants)
        seen: dict[tuple, str] = {}
        for v in variants:
            v["delta_total"] = round(v["total"] - cheapest, 2)
            v["delta_days"] = v["lead_time_days"] - fastest
            sig = (v["selections"].get("panel_item_id"), v["selections"].get("panel_qty"), v["selections"].get("inverter_item_id"), v["selections"].get("battery_item_id"), v["selections"].get("battery_qty"), v["total"])
            v["same_as"] = seen.get(sig)
            seen.setdefault(sig, v["strategy"])
    return {"target_kwp": kwp_target, "target_basis": basis, "layout_fixed": layout_fixed, "target_kwh": target_kwh, "variants": variants}


def _quality(ctx: Ctx, sel: dict[str, Any]) -> float:
    ws = [(sel.get("panel_item_id"), 0.4), (sel.get("inverter_item_id"), 0.4), (sel.get("battery_item_id"), 0.2)]
    tot, acc = 0.0, 0.0
    for iid, w in ws:
        it = ctx.by_id.get(int(iid or 0))
        if it:
            acc += w * ctx.tier_score(it)
            tot += w
    return acc / tot if tot else 0.5


def _score(ctx: Ctx, strat: str, sel: dict[str, Any], ev: dict[str, Any]) -> float:
    """Lower is better."""
    total = ev["total"]
    lead = ev["lead_time_days"]
    q = _quality(ctx, sel)
    penalty = 0.0
    if ev["missing_price"]:
        penalty += 1e6  # configurations with unpriced items are last resort
    penalty += 2000.0 * sum(1 for w in ev["warnings"] if "надвишава" in w or "извън" in w)
    if strat == "economy":
        return total + penalty
    if strat == "premium":
        return -q * 1e5 + total + penalty
    if strat == "fastest":
        return lead * 1e5 + total + penalty
    epd = float(ctx.proc.get("balanced_eur_per_day", 25.0))
    return total + epd * lead - q * 0.15 * total + penalty
