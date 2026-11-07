"""Procurement helpers: suppliers, lead times and price-tier classification of catalog items.

* ``supplier_of(item)`` – who we order the item from (item.supplier → specs.supplier → manufacturer rule).
* ``lead_time_days(item, cfg)`` – item override → supplier default → global default (working days).
* ``classify(items, cfg)`` – automatic economy / standard / premium tier per item, computed from the price per
  functional unit inside a comparable group (€/Wp for modules, €/kW per phase class for inverters, €/kWh for
  batteries, plain price otherwise), a configurable brand list and a few quality signals (efficiency, warranty,
  cycles). A manual ``item.tier`` always wins.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem
from .settings import get_setting

TIER_LABELS = {
    "economy": ("Икономичен", "Economy"),
    "standard": ("Стандартен", "Standard"),
    "premium": ("Премиум", "Premium"),
}

STRATEGIES = ("economy", "balanced", "premium", "fastest")
STRATEGY_LABELS = {
    "economy": ("Най-ниска цена", "Lowest price"),
    "balanced": ("Балансиран", "Balanced"),
    "premium": ("Премиум", "Premium"),
    "fastest": ("Най-бърза доставка", "Fastest delivery"),
}


# ----------------------------------------------------------------------------- suppliers / lead time
def suppliers_cfg(db: Session) -> dict[str, Any]:
    return get_setting(db, "suppliers")


def supplier_map(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(s.get("name", "")).strip().lower(): s for s in (cfg.get("list") or []) if s.get("name")}


def supplier_of(item: CatalogItem) -> str | None:
    if item.supplier:
        return item.supplier
    sp = item.specs or {}
    if sp.get("supplier"):
        return str(sp["supplier"])
    if (item.manufacturer or "").lower() == "aerocompact":
        return "Aerocompact"
    return None


def lead_time_days(item: CatalogItem, cfg: dict[str, Any]) -> int:
    if item.lead_time_days is not None:
        return int(item.lead_time_days)
    sup = supplier_of(item)
    smap = supplier_map(cfg)
    if sup and sup.lower() in smap and smap[sup.lower()].get("lead_time_days") is not None:
        base = int(smap[sup.lower()]["lead_time_days"])
    else:
        base = int(cfg.get("default_lead_time_days", 7))
    st = (item.specs or {}).get("stock_status")
    if st == "backorder":
        base = max(base, int(cfg.get("backorder_lead_time_days", 21)))
    elif st == "outofstock":
        base = max(base, int(cfg.get("backorder_lead_time_days", 21)))
    return base


# ----------------------------------------------------------------------------- tiers
def _f(d: dict[str, Any] | None, k: str) -> float | None:
    try:
        v = (d or {}).get(k)
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _warranty_years(s: str | None) -> float | None:
    if not s:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(год|г\.|year|yr|y\b)", s, re.I)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+)\s*(мес|month)", s, re.I)
    if m:
        return float(m.group(1)) / 12
    return None


def group_key(item: CatalogItem) -> str:
    sp = item.specs or {}
    if item.category == "panel":
        return "panel"
    if item.category == "inverter":
        ph = int(_f(sp, "phases") or 3)
        hyb = "hyb" if sp.get("hybrid") or sp.get("battery_voltage_class") else "grid"
        return f"inverter:{ph}:{hyb}"
    if item.category == "battery":
        return f"battery:{(sp.get('voltage_class') or 'LV')}"
    return item.category


def unit_price_metric(item: CatalogItem) -> float | None:
    """Price per functional unit used to compare items inside a group (None if not comparable)."""
    p = float(item.purchase_price or 0)
    if p <= 0:
        return None
    sp = item.specs or {}
    if item.category == "panel":
        wp = _f(sp, "wp")
        return p / wp if wp else None
    if item.category == "inverter":
        kw = _f(sp, "ac_power_kw")
        return p / kw if kw else None
    if item.category == "battery":
        kwh = _f(sp, "kwh")
        return p / kwh if kwh else None
    return p


def quality_score(item: CatalogItem) -> float:
    """0..1 from datasheet facts that customers pay a premium for."""
    sp = item.specs or {}
    pts: list[float] = []
    wy = _warranty_years(item.warranty) or _f(sp, "warranty_years")
    if item.category == "panel":
        eff = _f(sp, "efficiency")
        if eff:
            pts.append(min(1.0, max(0.0, (eff - 20.5) / 3.0)))  # 20.5 % → 0, 23.5 % → 1
        if wy:
            pts.append(min(1.0, (wy - 10) / 15))  # 10 y → 0, 25 y → 1
        if sp.get("bifaciality") or "bifacial" in item.name.lower():
            pts.append(0.6)
    elif item.category == "inverter":
        if wy:
            pts.append(min(1.0, max(0.0, (wy - 5) / 5)))  # 5 y → 0, 10 y → 1
        mppt = _f(sp, "mppt_count")
        if mppt:
            pts.append(min(1.0, (mppt - 1) / 3))
        if sp.get("specs_verified"):
            pts.append(0.5)
    elif item.category == "battery":
        cyc = _f(sp, "cycles")
        if cyc:
            pts.append(min(1.0, max(0.0, (cyc - 4000) / 4000)))  # 4000 → 0, 8000 → 1
        if wy:
            pts.append(min(1.0, max(0.0, (wy - 5) / 5)))
        if (sp.get("chemistry") or "").upper().startswith("LFP") or "lifepo" in (sp.get("chemistry") or "").lower():
            pts.append(0.5)
    else:
        if wy:
            pts.append(min(1.0, wy / 5))
    return sum(pts) / len(pts) if pts else 0.5


def brand_score(item: CatalogItem, cfg: dict[str, Any]) -> float:
    """0 economy brand, 0.5 unknown, 1 premium brand (lists editable in Settings → Procurement)."""
    name = f"{item.manufacturer or ''} {item.name}".lower()
    tiers = cfg.get("brand_tiers") or {}
    for b in tiers.get("premium") or []:
        if b and b.lower() in name:
            return 1.0
    for b in tiers.get("economy") or []:
        if b and b.lower() in name:
            return 0.0
    return 0.5


def classify(items: list[CatalogItem], cfg: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return {item_id: {"tier", "score", "price_pct", "metric", "quality", "brand", "auto"}} for every item."""
    w = cfg.get("tier_weights") or {}
    w_price, w_brand, w_quality = float(w.get("price", 0.6)), float(w.get("brand", 0.25)), float(w.get("quality", 0.15))
    lo, hi = float(cfg.get("tier_economy_max", 0.38)), float(cfg.get("tier_premium_min", 0.62))
    groups: dict[str, list[tuple[CatalogItem, float]]] = defaultdict(list)
    metric: dict[int, float | None] = {}
    for it in items:
        m = unit_price_metric(it)
        metric[it.id] = m
        if m is not None:
            groups[group_key(it)].append((it, m))
    pct: dict[int, float] = {}
    for _g, rows in groups.items():
        rows.sort(key=lambda r: r[1])
        n = len(rows)
        for i, (it, _m) in enumerate(rows):
            pct[it.id] = 0.5 if n == 1 else i / (n - 1)
    out: dict[int, dict[str, Any]] = {}
    for it in items:
        b = brand_score(it, cfg)
        q = quality_score(it)
        p = pct.get(it.id)
        if p is None:  # no price → brand + quality only
            score = (w_brand * b + w_quality * q) / max(1e-9, w_brand + w_quality)
        else:
            score = w_price * p + w_brand * b + w_quality * q
        auto = "economy" if score < lo else ("premium" if score > hi else "standard")
        out[it.id] = {
            "tier": it.tier or auto,
            "auto_tier": auto,
            "manual": bool(it.tier),
            "score": round(score, 3),
            "price_pct": None if p is None else round(p, 3),
            "metric": None if metric[it.id] is None else round(metric[it.id], 4),
            "quality": round(q, 2),
            "brand": b,
        }
    return out


def classify_all(db: Session) -> dict[int, dict[str, Any]]:
    cfg = get_setting(db, "procurement")
    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    return classify(items, cfg)


def tier_of(item: CatalogItem, table: dict[int, dict[str, Any]] | None) -> str:
    if item.tier:
        return item.tier
    if table and item.id in table:
        return table[item.id]["tier"]
    return "standard"


def effective(db: Session, items: list[CatalogItem]) -> dict[int, dict[str, Any]]:
    """Per-item effective lead time / tier / supplier for API output."""
    scfg = suppliers_cfg(db)
    cats = {it.category for it in items}
    pool = db.query(CatalogItem).filter(CatalogItem.active.is_(True), CatalogItem.category.in_(cats)).all()
    known = {it.id for it in pool}
    pool += [it for it in items if it.id not in known]
    table = classify(pool, get_setting(db, "procurement"))
    return {
        it.id: {
            "lead_time_days": lead_time_days(it, scfg),
            "tier": tier_of(it, table),
            "auto_tier": table.get(it.id, {}).get("auto_tier"),
            "supplier": supplier_of(it),
        }
        for it in items
    }


def chooser(db: Session, strategy: str | None, items: list[CatalogItem] | None = None):
    """Return a function that picks one of several technically equivalent items according to ``strategy``
    (None/"economy" → cheapest, "fastest" → shortest lead time, "premium" → highest tier, "balanced" → price with a
    lead-time penalty). Used by the engineering engine for protection devices, cables, earthing parts, …"""
    scfg = suppliers_cfg(db)
    pcfg = get_setting(db, "procurement")
    table = classify(items, pcfg) if items else {}
    epd = float(pcfg.get("balanced_eur_per_day", 25.0))

    def price(it: CatalogItem) -> float:
        return float(it.purchase_price or 0) or float(it.sell_price or 0) or 1e9

    def pick(cands: list[CatalogItem]) -> CatalogItem:
        if strategy == "fastest":
            return min(cands, key=lambda it: (lead_time_days(it, scfg), price(it)))
        if strategy == "premium":
            rank = {"economy": 0, "standard": 1, "premium": 2}
            return min(cands, key=lambda it: (-rank.get(tier_of(it, table), 1), price(it)))
        if strategy == "balanced":
            return min(cands, key=lambda it: price(it) + epd * lead_time_days(it, scfg) * 0.1)
        return min(cands, key=price)

    return pick
