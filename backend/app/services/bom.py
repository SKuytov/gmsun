"""Mounting-structure bill of materials derived from the panel layout.

The quantities follow the logic used by racking configurators (e.g. the
Aerocompact CompactPITCH report in the project files):

* rail lines  = contiguous module runs x rails per module
* rail metres = sum(run length) x rails, + waste
* rail pieces = ceil(rail metres / stock length)
* connectors  = rail pieces - rail lines (splices), min 0
* fixations   = per rail line: ceil(length / spacing) + 1 (roof hooks, hanger
  bolts, trapezoidal brackets, ballast feet ...)
* mid clamps  = (modules - 1) x rails per module, per run
* end clamps  = 2 x rails per module, per run
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, MountingRule, RoofTypeConfig


@dataclass
class LayoutStats:
    modules: int
    kwp: float
    lines: int  # rail lines (runs x rails)
    rail_m: float  # total rail metres incl. waste
    rail_pieces: int
    fixations: int
    mid_clamps: int
    end_clamps: int
    strings: int
    connectors: int

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def compute_stats(summary: dict[str, Any], roof: RoofTypeConfig, modules_override: int | None = None, strings: int = 1) -> LayoutStats:
    lines = summary.get("lines") or []
    modules = int(summary.get("count") or 0)
    if modules_override is not None and modules_override > 0:
        modules = modules_override
        if not lines:
            # no layout -> assume rows of up to 10 modules, module width 1.134 m
            per_row = 10
            rows = math.ceil(modules / per_row)
            lines = []
            left = modules
            for _ in range(rows):
                n = min(per_row, left)
                left -= n
                lines.append({"modules": n, "length_m": n * 1.134 + (n - 1) * 0.02, "rails": roof.rails_per_module})
    rails_per_module = roof.rails_per_module
    rail_lines = 0
    rail_m = 0.0
    fixations = 0
    mid = 0
    end = 0
    for ln in lines:
        n = int(ln.get("modules", 0))
        length = float(ln.get("length_m", 0.0))
        rails = int(ln.get("rails") or rails_per_module)
        rail_lines += rails
        rail_m += length * rails
        fixations += (math.ceil(length / max(roof.fixation_spacing_m, 0.1)) + 1) * rails
        mid += max(n - 1, 0) * rails
        end += 2 * rails
    rail_m_waste = rail_m * (1 + roof.waste_pct / 100.0)
    pieces = math.ceil(rail_m_waste / max(roof.rail_stock_length_m, 0.5)) if rail_m_waste > 0 else 0
    connectors = max(pieces - rail_lines, 0)
    kwp = float(summary.get("kwp") or 0.0)
    return LayoutStats(
        modules=modules,
        kwp=kwp,
        lines=rail_lines,
        rail_m=round(rail_m_waste, 2),
        rail_pieces=pieces,
        fixations=fixations,
        mid_clamps=mid,
        end_clamps=end,
        strings=max(strings, 1),
        connectors=connectors,
    )


def quantity_for_rule(rule: MountingRule, st: LayoutStats) -> float:
    basis = rule.basis
    base: float
    if basis == "per_module":
        base = st.modules
    elif basis == "per_line":
        base = st.lines
    elif basis == "per_rail":
        base = st.rail_pieces
    elif basis == "per_rail_meter":
        base = st.rail_m
    elif basis == "per_fixation":
        base = st.fixations
    elif basis == "per_string":
        base = st.strings
    elif basis == "per_kwp":
        base = st.kwp
    elif basis == "per_project":
        base = 1
    elif basis == "per_mid_clamp":
        base = st.mid_clamps
    elif basis == "per_end_clamp":
        base = st.end_clamps
    elif basis == "per_connector":
        base = st.connectors
    else:
        base = 0
    q = base * rule.factor
    return float(math.ceil(q - 1e-9)) if rule.round_up else round(q, 2)


def mounting_lines(db: Session, roof: RoofTypeConfig, st: LayoutStats, default_markup: float, fastener_margin_pct: float = 0.0) -> list[dict[str, Any]]:
    """Priced mounting lines. Small parts (specs.small_part: screws, clamps, clips,
    caps, splices) get the fastener/consumable reserve on top (industry practice
    5-10 % for loss and breakage on site)."""
    rules = (
        db.query(MountingRule)
        .filter(MountingRule.roof_type == roof.code, MountingRule.active.is_(True))
        .order_by(MountingRule.sort_order, MountingRule.id)
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rules:
        qty = quantity_for_rule(r, st)
        if qty <= 0:
            continue
        item: CatalogItem | None = r.item
        meta_extra: dict[str, Any] = {}
        if item and (item.specs or {}).get("small_part") and fastener_margin_pct > 0:
            meta_extra = {"base_qty": qty, "margin_pct": fastener_margin_pct}
            qty = float(math.ceil(qty * (1 + fastener_margin_pct / 100.0) - 1e-9))
        unit_price = item.price_for(default_markup) if item else 0.0
        purchase = item.purchase_price if item else 0.0
        out.append(
            {
                "key": f"mount:{r.id}",
                "section": "construction",
                "name": item.name if item else r.name,
                "unit": item.unit if item else "бр.",
                "qty": qty,
                "unit_price": unit_price,
                "purchase_price": purchase,
                "catalog_item_id": item.id if item else None,
                "meta": {"rule_id": r.id, "basis": r.basis, "factor": r.factor, **meta_extra},
            }
        )
    return out
