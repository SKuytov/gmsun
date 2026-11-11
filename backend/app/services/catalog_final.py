"""One-time, idempotent switch to the GM SUN final catalog (``seed_data/gmsun_final.py``).

What it does (all in one transaction, a JSON backup of the previous catalog is written first):

1. Upserts the 56 final items – matched by ``sku``, then by name – with real prices and datasheet specs.
2. Re-points references to removed items to their closest final equivalent where one exists
   (same inverter kW / phases / battery class, same battery class and capacity, closest panel size) in project
   selections, draft quote selections and layouts; everything else is cleared.
3. Deletes every other catalog item. Lines of existing quotes and purchase orders keep their name and price
   (only the catalog link is removed), mounting rules of deleted items are deleted.
4. Switches all roof types to per-module (lump) construction pricing with the GM SUN prices, refreshes the labor
   matrix and the pricing / procurement settings.

The migration key is stored in the ``migrations`` setting, so it never runs twice. ``sanitize_selections`` is also
used at runtime to drop item references that no longer exist.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, LaborOption, Layout, MountingRule, Project, PurchaseOrderLine, Quote, QuoteLine, RoofTypeConfig, Setting
from ..seed_data import gmsun_final as F

ID_KEYS = ("panel_item_id", "inverter_item_id", "battery_item_id", "switchboard_item_id", "solar_cable_item_id", "mc4_item_id", "power_cable_item_id")
LIST_KEYS = ("battery_accessories", "electrical_items", "extra_items")


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).casefold()


def _setting(db: Session, key: str) -> dict[str, Any]:
    row = db.get(Setting, key)
    return dict(row.value or {}) if row and row.value else {}


def _put_setting(db: Session, key: str, patch: dict[str, Any]) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=dict(patch)))
    else:
        merged = dict(row.value or {})
        merged.update(patch)
        row.value = merged


def is_done(db: Session) -> bool:
    return bool(_setting(db, "migrations").get(F.MIGRATION_KEY))


def is_curated(db: Session) -> bool:
    """True once the final catalog is the only source of items (blocks re-seeding of legacy catalogs)."""
    return bool(_setting(db, "catalog").get("curated")) or is_done(db)


# --------------------------------------------------------------------------- remapping helpers
def _spec(it: CatalogItem, k: str) -> Any:
    return (it.specs or {}).get(k)


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _equivalent(old: CatalogItem, finals: list[CatalogItem]) -> CatalogItem | None:
    """Closest final item for a removed one (only for the main equipment; accessories are not guessed)."""
    cat = old.category
    if cat == "inverter":
        kw, ph, vc = _num(_spec(old, "ac_power_kw")), int(_num(_spec(old, "phases")) or 0), str(_spec(old, "battery_voltage_class") or "").upper()
        same = [f for f in finals if f.category == "inverter" and abs(_num(_spec(f, "ac_power_kw")) - kw) < 0.01 and int(_num(_spec(f, "phases"))) == ph
                and (not vc or str(_spec(f, "battery_voltage_class")).upper() == vc)]
        return min(same, key=lambda f: f.purchase_price or 0) if same else None
    if cat == "battery":
        kwh, vc = _num(_spec(old, "kwh")), str(_spec(old, "voltage_class") or "").upper()
        if not kwh:
            return None
        same = [f for f in finals if f.category == "battery" and str(_spec(f, "voltage_class")).upper() == (vc or "LV") and abs(_num(_spec(f, "kwh")) - kwh) / kwh <= 0.06]
        return min(same, key=lambda f: f.purchase_price or 0) if same else None
    if cat == "panel":
        h = _num(_spec(old, "height_mm")) or _num(_spec(old, "length_mm"))
        panels = [f for f in finals if f.category == "panel"]
        if not panels:
            return None
        if not h:
            wp = _num(_spec(old, "wp"))
            return min(panels, key=lambda f: abs(_num(_spec(f, "wp")) - wp)) if wp else None
        return min(panels, key=lambda f: (abs(_num(_spec(f, "height_mm")) - h), f.purchase_price or 0))
    if cat == "switchboard":
        ph = int(_num(_spec(old, "phases")) or 0)
        boards = [f for f in finals if f.category == "switchboard" and (not ph or int(_num(_spec(f, "phases"))) == ph)]
        return boards[0] if len(boards) == 1 else None
    if cat == "solar_cable" or _spec(old, "role") == "pv_cable":
        cables = [f for f in finals if _spec(f, "role") == "pv_cable"]
        return cables[0] if cables else None
    return None


def sanitize_selections(sel: dict[str, Any] | None, valid_ids: set[int], remap: dict[int, int | None] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Re-point or drop catalog references in a selections dict. Returns (new selections, list of changed keys)."""
    remap = remap or {}
    out = dict(sel or {})
    changed: list[str] = []

    def fix(v: Any) -> Any:
        try:
            i = int(v)
        except (TypeError, ValueError):
            return None
        if i in valid_ids:
            return i
        return remap.get(i)

    for k in ID_KEYS:
        if out.get(k) in (None, "", 0):
            continue
        nv = fix(out[k])
        if nv != out[k]:
            out[k] = nv
            changed.append(k)
    for k in ("battery_bms", "battery_rack"):
        cfg = out.get(k)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("items"), list):
            continue
        new_items = []
        for row in cfg["items"]:
            if isinstance(row, dict) and row.get("item_id") is not None:
                nv = fix(row.get("item_id"))
                if nv:
                    new_items.append({**row, "item_id": nv})
        if new_items != cfg["items"]:
            out[k] = {**cfg, "items": new_items}
            changed.append(k)
    for k in LIST_KEYS:
        lst = out.get(k)
        if not isinstance(lst, list):
            continue
        new = []
        for row in lst:
            if not isinstance(row, dict):
                continue
            key = "catalog_item_id" if "catalog_item_id" in row else ("item_id" if "item_id" in row else None)
            if key is None:
                continue
            nv = fix(row.get(key))
            if nv:
                new.append({**row, key: nv})
        if new != lst:
            out[k] = new
            changed.append(k)
    pf = out.get("panel_fit")
    if isinstance(pf, dict) and pf.get("panel_item_id") is not None:
        nv = fix(pf.get("panel_item_id"))
        if nv != pf.get("panel_item_id"):
            out.pop("panel_fit", None)  # the fit was computed for another module – recomputed on the next visit
            changed.append("panel_fit")
    return out, changed


def remove_items(db: Session, others: list[CatalogItem], keep: set[int], remap: dict[int, int | None] | None = None) -> dict[str, int]:
    """Delete ``others`` safely: quote/order lines keep their text (link removed), mounting rules of the items are
    deleted, layouts and project / draft quote selections are re-pointed via ``remap`` or cleared."""
    remap = remap or {}
    removed = {o.id for o in others}
    if removed:
        ids = list(removed)
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            db.query(QuoteLine).filter(QuoteLine.catalog_item_id.in_(part)).update({QuoteLine.catalog_item_id: None}, synchronize_session=False)
            db.query(PurchaseOrderLine).filter(PurchaseOrderLine.catalog_item_id.in_(part)).update({PurchaseOrderLine.catalog_item_id: None}, synchronize_session=False)
            db.query(MountingRule).filter(MountingRule.catalog_item_id.in_(part)).delete(synchronize_session=False)
    db.query(MountingRule).filter(MountingRule.catalog_item_id.is_(None)).delete(synchronize_session=False)
    lay_fixed = 0
    for lay in db.query(Layout).all():
        if lay.panel_item_id and lay.panel_item_id in removed:
            lay.panel_item_id = remap.get(lay.panel_item_id)
            lay_fixed += 1
    sel_fixed = 0
    for p in db.query(Project).all():
        params = dict(p.params or {})
        if isinstance(params.get("selections"), dict):
            new, ch = sanitize_selections(params["selections"], keep, remap)
            if ch:
                params["selections"] = new
                p.params = params
                sel_fixed += 1
    for q in db.query(Quote).all():
        if (q.status or "draft") != "draft":
            continue
        new, ch = sanitize_selections(q.selections, keep, remap)
        if ch:
            q.selections = new
            sel_fixed += 1
    db.flush()
    for o in others:
        db.delete(o)
    db.flush()
    return {"deleted": len(removed), "selections_fixed": sel_fixed, "layouts_fixed": lay_fixed}


# --------------------------------------------------------------------------- the migration
def _backup(db: Session, data_dir: Path | None) -> str | None:
    if data_dir is None:
        return None
    d = Path(data_dir) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = d / f"catalog_before_{F.MIGRATION_KEY}_{ts}.json"

    def item(i: CatalogItem) -> dict[str, Any]:
        return {c.name: getattr(i, c.name) for c in CatalogItem.__table__.columns if c.name not in ("created_at", "updated_at")}

    payload = {
        "created_at": ts,
        "items": [item(i) for i in db.query(CatalogItem).all()],
        "mounting_rules": [{c.name: getattr(r, c.name) for c in MountingRule.__table__.columns} for r in db.query(MountingRule).all()],
        "labor": [{c.name: getattr(r, c.name) for c in LaborOption.__table__.columns} for r in db.query(LaborOption).all()],
        "roof_types": [{c.name: getattr(r, c.name) for c in RoofTypeConfig.__table__.columns} for r in db.query(RoofTypeConfig).all()],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return str(path)


def upsert_final_items(db: Session, *, overwrite: bool = True) -> tuple[list[CatalogItem], dict[str, int]]:
    rows = db.query(CatalogItem).all()
    by_sku = {r.sku: r for r in rows if r.sku}
    by_name: dict[str, CatalogItem] = {}
    for r in rows:
        by_name.setdefault(_norm(r.name), r)
    stats = {"created": 0, "updated": 0}
    finals: list[CatalogItem] = []
    used: set[int] = set()
    for i, d in enumerate(F.ITEMS):
        it = by_sku.get(d["sku"])
        if it is None or it.id in used:
            cand = by_name.get(_norm(d["name"]))
            it = cand if cand is not None and cand.id not in used else None
        fields = {k: v for k, v in d.items() if k not in ("legacy_id",)}
        if it is None:
            it = CatalogItem(**{k: v for k, v in fields.items()}, supplier=F.SUPPLIER, active=True, sort_order=i)
            db.add(it)
            stats["created"] += 1
        else:
            stats["updated"] += 1
            if overwrite:
                for k, v in fields.items():
                    setattr(it, k, v)
                it.supplier = F.SUPPLIER
                it.supplier_sku = None
                it.sell_price = None
                it.active = True
                it.sort_order = i
                it.lead_time_days = None
                it.tier = None
        db.flush()
        used.add(it.id)
        finals.append(it)
    return finals, stats


def apply(db: Session, data_dir: Path | None = None, *, force: bool = False) -> dict[str, Any]:
    if is_done(db) and not force:
        return {"skipped": True}
    backup = _backup(db, data_dir) if db.query(CatalogItem).first() is not None else None
    finals, stats = upsert_final_items(db)
    keep = {f.id for f in finals}
    from . import catalog_packs

    packs = set(catalog_packs.enabled(db))  # enabled reference packs (Aerocompact, cables) survive a restore
    keep |= {r.id for r in db.query(CatalogItem).all() if catalog_packs.pack_of(r) in packs}
    others = [r for r in db.query(CatalogItem).all() if r.id not in keep]
    remap: dict[int, int | None] = {}
    for o in others:
        eq = _equivalent(o, finals)
        remap[o.id] = eq.id if eq else None
    removed = {o.id for o in others}
    ref = remove_items(db, others, keep, remap)
    sel_fixed, lay_fixed = ref["selections_fixed"], ref["layouts_fixed"]

    # --- construction: per-module prices
    roofs = 0
    for r in db.query(RoofTypeConfig).all():
        r.pricing_mode = "lump"
        if r.code in F.ROOF_LUMP:
            r.lump_price_per_module = float(F.ROOF_LUMP[r.code])
        roofs += 1

    # --- labor matrix: upsert by (days, workers), keep ids stable
    want = {(d, w): p for d, w, p in F.LABOR}
    seen: set[tuple[int, int]] = set()
    for lo in db.query(LaborOption).all():
        key = (int(lo.days), int(lo.workers))
        if key in want and key not in seen:
            lo.price, lo.active = float(want[key]), True
            seen.add(key)
        else:
            lo.active = False
    for key, price in want.items():
        if key not in seen:
            db.add(LaborOption(days=key[0], workers=key[1], price=float(price), active=True))

    # --- settings: the first migration writes GM SUN's values; a later "restore" (force) only fills keys that are
    # missing, so company data and pricing changed in Settings afterwards are never reset
    for key, patch in F.SETTINGS.items():
        if force and db.get(Setting, key) is not None:
            cur = dict(db.get(Setting, key).value or {})
            _put_setting(db, key, {k: v for k, v in patch.items() if k not in cur})
        else:
            _put_setting(db, key, patch)
    _put_setting(db, "datafill", {"done": True, "at": datetime.now(timezone.utc).isoformat(), "stats": {"note": "final catalog"}})
    _put_setting(db, "catalog", {"curated": True, "profile": "gmsun_final"})
    for pk in ("aerocompact", "pv_fence"):
        if pk in packs:
            catalog_packs.install(db, pk)  # re-links / re-creates the mounting rules
    result = {
        "at": datetime.now(timezone.utc).isoformat(), "kept": len(keep), "created": stats["created"], "updated": stats["updated"],
        "deleted": len(removed), "remapped": sum(1 for v in remap.values() if v), "selections_fixed": sel_fixed, "layouts_fixed": lay_fixed,
        "roof_types": roofs, "backup": backup,
    }
    _put_setting(db, "migrations", {F.MIGRATION_KEY: result})
    db.commit()
    return result
