"""Battery accessories: BMS / control box and rack / cabinet as two independent selections.

Selections (per quote / project):

    battery_bms  = {"mode": "auto" | "manual" | "none", "items": [{"item_id": int, "qty": float}, ...]}
    battery_rack = {"mode": "auto" | "manual" | "none", "items": [{"item_id": int, "qty": float}, ...]}
    battery_accessories = [{"item_id": int, "qty": float}, ...]   # any other battery accessory (cables, covers …)

``auto`` (default) = the engineering choice (HV stacks: one BMS per series cluster, cheapest racks that hold the
modules; LV batteries have the BMS built in and need no rack).  ``manual`` = exactly the listed catalog items.
``none`` = nothing (a warning is raised when an HV stack is left without BMS).

Only items of the curated catalog (category ``battery_accessory``) can be chosen; items of another battery family
are rejected, generic items (no ``family``) fit every battery.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem

BMS_ROLES = {"hv_bms", "bms", "control_box"}
RACK_ROLES = {"hv_rack", "rack", "cabinet"}
MODES = ("auto", "manual", "none")
# sized by the engineering engine (Materials step) — not offered as "other" accessories to avoid double counting
ENGINE_ROLES = {"battery_cable", "battery_lug", "comm_cable"}


def kind_of(item: CatalogItem | None) -> str:
    role = str(((item.specs or {}) if item else {}).get("role") or "")
    if role in BMS_ROLES:
        return "bms"
    if role in RACK_ROLES:
        return "rack"
    return "other"


def _f(d: dict | None, k: str, default: float = 0.0) -> float:
    try:
        return float((d or {}).get(k) if (d or {}).get(k) is not None else default)
    except (TypeError, ValueError):
        return default


def is_hv(battery: CatalogItem | None) -> bool:
    return bool(battery) and str((battery.specs or {}).get("voltage_class") or "").upper() == "HV"


def fits(item: CatalogItem, battery: CatalogItem | None) -> bool:
    """Generic accessories (no family) fit every battery; family-bound ones only their own family."""
    fam = (item.specs or {}).get("family")
    if not fam:
        return True
    return bool(battery) and fam == (battery.specs or {}).get("family")


def _row_id(row: Any) -> int | None:
    if not isinstance(row, dict):
        return None
    v = row.get("item_id") if row.get("item_id") is not None else row.get("catalog_item_id")
    try:
        return int(v) if v not in (None, "", 0) else None
    except (TypeError, ValueError):
        return None


def _row_qty(row: dict) -> float:
    try:
        return max(0.0, float(row.get("qty") if row.get("qty") is not None else 1))
    except (TypeError, ValueError):
        return 1.0


def normalize(sel: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {"bms": {...}, "rack": {...}} in the current format, upgrading legacy selections.

    Legacy: ``battery_auto_accessories`` / ``battery_accessories_auto`` = False meant "take BMS / rack from the
    battery_accessories list" — those rows become manual picks."""
    legacy_off = sel.get("battery_auto_accessories") is False or sel.get("battery_accessories_auto") is False
    out: dict[str, dict[str, Any]] = {}
    for kind in ("bms", "rack"):
        raw = sel.get(f"battery_{kind}")
        if isinstance(raw, dict) and raw.get("mode") in MODES:
            items = [{"item_id": _row_id(r), "qty": _row_qty(r)} for r in (raw.get("items") or []) if _row_id(r)]
            out[kind] = {"mode": raw["mode"], "items": items}
        else:
            out[kind] = {"mode": "manual" if legacy_off else "auto", "items": [], "legacy": legacy_off}
    return out


def auto_plan(db: Session, inverter: CatalogItem | None, battery: CatalogItem | None, qty: int, n_inv: int = 1) -> tuple[dict[str, list[tuple[CatalogItem, int, str]]], list[str]]:
    """Engineering choice split by kind."""
    from . import compat

    res: dict[str, list[tuple[CatalogItem, int, str]]] = {"bms": [], "rack": []}
    if not battery or qty <= 0 or not is_hv(battery):
        return res, []
    items, notes = compat.hv_accessories(db, inverter, battery, qty, n_inv)
    for it, q, why in items:
        k = kind_of(it)
        if k in res:
            res[k].append((it, q, why))
    return res, notes


def clusters_for(inverter: CatalogItem | None, battery: CatalogItem, qty: int, n_inv: int = 1) -> list[int]:
    from . import engineering

    bs = battery.specs or {}
    cl = engineering.hv_clusters(inverter.specs or {}, bs, qty, n_inv) if inverter else None
    if not cl:
        hi = int(_f(bs, "series_max", 16)) or 16
        k = max(1, math.ceil(qty / hi))
        base, rem = divmod(qty, k)
        cl = [base + (1 if i < rem else 0) for i in range(k)]
    return cl


def resolve(
    db: Session, sel: dict[str, Any], inverter: CatalogItem | None, battery: CatalogItem | None, qty: int, n_inv: int = 1
) -> dict[str, Any]:
    """Final BMS / rack / other accessory lines + warnings + what the automatic choice would be."""
    out: dict[str, Any] = {"bms": [], "rack": [], "other": [], "warnings": [], "notes": [], "auto": {"bms": [], "rack": []}, "modes": {}}
    if not battery or qty <= 0:
        return out
    cfg = normalize(sel)
    auto, notes = auto_plan(db, inverter, battery, qty, n_inv)
    out["auto"] = {k: [{"item_id": it.id, "name": it.name, "qty": q, "why": why} for it, q, why in v] for k, v in auto.items()}
    hv = is_hv(battery)
    legacy_rows = [(db.get(CatalogItem, _row_id(r)), _row_qty(r)) for r in (sel.get("battery_accessories") or []) if _row_id(r)]
    legacy_rows = [(it, q) for it, q in legacy_rows if it is not None]
    clusters = clusters_for(inverter, battery, qty, n_inv) if hv else []

    for kind, label in (("bms", "BMS / контролна кутия"), ("rack", "Стелаж / кутия")):
        mode = cfg[kind]["mode"]
        out["modes"][kind] = mode
        chosen: list[tuple[CatalogItem, float, str]] = []
        if mode == "auto":
            chosen = [(it, float(q), why) for it, q, why in auto[kind]]  # missing-in-catalog notes come from auto_plan
        elif mode == "manual":
            rows = cfg[kind]["items"]
            if cfg[kind].get("legacy"):
                rows = [{"item_id": it.id, "qty": q} for it, q in legacy_rows if kind_of(it) == kind]
            for r in rows:
                it = db.get(CatalogItem, r["item_id"])
                if it is None or not it.active:
                    out["warnings"].append(f"{label}: избраният артикул вече не е в каталога.")
                    continue
                if it.category != "battery_accessory" or kind_of(it) != kind:
                    out["warnings"].append(f"{label}: „{it.name}“ не е {label.lower()} — пропуснат.")
                    continue
                if not fits(it, battery):
                    out["warnings"].append(f"НЕСЪВМЕСТИМО: {label} „{it.name}“ е за друга серия батерии ({(it.specs or {}).get('family')}) — пропуснат.")
                    continue
                if r["qty"] > 0:
                    chosen.append((it, r["qty"], "ръчен избор"))
            if not chosen and hv and kind == "bms":
                out["warnings"].append("Не е избран BMS / контролна кутия — HV батериите не работят без него.")
        else:  # none
            if hv and kind == "bms":
                out["warnings"].append("Без BMS / контролна кутия — HV батериите не работят без него (оставено по избор).")
        # engineering checks on the final choice (manual picks are not trusted blindly)
        if hv and chosen and mode == "manual":
            if kind == "bms":
                n = sum(q for _it, q, _w in chosen)
                if n < len(clusters):
                    out["warnings"].append(f"BMS: {n:g} бр., а батериите са в {len(clusters)} клъстера — нужен е по един BMS на клъстер.")
                cap = max((int(_f(it.specs, "max_series", 0)) for it, _q, _w in chosen), default=0)
                if cap and clusters and max(clusters) > cap:
                    out["warnings"].append(f"BMS: поддържа до {cap} модула в серия, а клъстерът е {max(clusters)}.")
            else:
                cap = sum(int(_f(it.specs, "capacity", 0)) * q for it, q, _w in chosen)
                if cap and cap < qty:
                    out["warnings"].append(f"Стелаж: побира {cap:g} модула, а батериите са {qty} бр.")
        out[kind] = chosen

    # other accessories (cables, covers …) — BMS / rack rows in this list are ignored (they have their own selector)
    for it, q in legacy_rows:
        if kind_of(it) != "other" or q <= 0:
            continue
        if not fits(it, battery):
            out["warnings"].append(f"НЕСЪВМЕСТИМО: „{it.name}“ е за друга серия батерии — пропуснат.")
            continue
        out["other"].append((it, q, "ръчен избор"))
    out["notes"] = notes
    return out


def options(db: Session, battery: CatalogItem | None) -> dict[str, list[dict[str, Any]]]:
    """Selectable catalog items per kind, compatible first; incompatible ones are listed but flagged."""
    rows = db.query(CatalogItem).filter(CatalogItem.active.is_(True), CatalogItem.category == "battery_accessory").all()
    res: dict[str, list[dict[str, Any]]] = {"bms": [], "rack": [], "other": []}
    for it in sorted(rows, key=lambda x: (x.sort_order or 0, x.name or "")):
        sp = it.specs or {}
        if kind_of(it) == "other" and str(sp.get("role") or "") in ENGINE_ROLES:
            continue
        res[kind_of(it)].append({
            "item_id": it.id, "name": it.name, "family": sp.get("family"), "role": sp.get("role"),
            "capacity": sp.get("capacity"), "max_series": sp.get("max_series"),
            "price": float(it.purchase_price or 0), "compatible": fits(it, battery),
        })
    for k in res:
        res[k].sort(key=lambda o: (not o["compatible"],))
    return res
