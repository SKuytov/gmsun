"""Optional item packs on top of the GM SUN final catalog.

The final catalog (``catalog_final``) holds only GM SUN's own 56 articles. Two built-in reference databases can be
switched on next to it:

* ``aerocompact`` – the AEROCOMPACT mounting catalogue (hooks, rails, clamps, ballast …, 159 articles) with the
  per-roof-type mounting rules, so the construction can be specified piece by piece ("detailed") and ordered.
* ``cables``      – AC power cables (СВТ 3×/5× 6…120 mm²), 10 mm² solar cable, MC4 connectors, cable lugs, battery /
  communication / CT / RS485 cables, conduits, clips, ties and glands.

Items of a pack carry ``specs["pack"] = <key>``. Enabled packs are stored in the ``catalog`` setting (``packs``);
``catalog_final.apply`` keeps their items when the final catalog is restored. Installing is additive and idempotent
(existing names are never overwritten – edited prices survive), removing deletes only the pack's items safely
(quote / order lines keep their text).

GM SUN's own articles always win: a pack item that duplicates a final article (e.g. 6 mm² solar cable – GM SUN uses
KBE) is not added, and roof types keep their per-module construction price unless the user switches them to
"detailed".
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, MountingRule, Setting

PACKS: dict[str, dict[str, str]] = {
    "aerocompact": {
        "label_bg": "AEROCOMPACT — монтажни системи",
        "label_en": "AEROCOMPACT mounting systems",
        "description_bg": "Куки, шини, скоби, мостове, баласт и крепежи за всички 14 типа покрив/терен, с правилата за количества.",
    },
    "cables": {
        "label_bg": "Кабели и кабелни аксесоари",
        "label_en": "Cables and cable accessories",
        "description_bg": "AC кабели СВТ (3×/5× 6–120 mm²), соларен кабел 10 mm², MC4, кабелни обувки, батерийни и комуникационни кабели, гофре, скоби, връзки, салници.",
    },
}

# roles / categories that make up the cables pack (from the built-in electrical catalogue)
CABLE_CATEGORIES = {"power_cable", "solar_cable", "cable_management"}
CABLE_ROLES = {
    "pv_cable", "ac_cable", "mc4_pair", "ac_lug", "battery_cable", "battery_lug", "comm_cable", "ct_cable", "rs485_cable",
    "parallel_cable", "cable_gland", "cable_tie_uv", "end_sleeve", "conduit_32", "conduit_40", "conduit_clip",
}
CABLE_EXCLUDE_ROLES = {"labels"}


def _setting(db: Session, key: str) -> dict[str, Any]:
    row = db.get(Setting, key)
    return dict(row.value or {}) if row and row.value else {}


def _put(db: Session, key: str, patch: dict[str, Any]) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=dict(patch)))
        db.flush()
    else:
        v = dict(row.value or {})
        v.update(patch)
        row.value = v


def enabled(db: Session) -> list[str]:
    return [p for p in (_setting(db, "catalog").get("packs") or []) if p in PACKS]


def pack_of(it: CatalogItem) -> str | None:
    return (it.specs or {}).get("pack")


def _cable_items() -> list[dict[str, Any]]:
    from ..seed import CATALOG

    out = []
    for d in CATALOG:
        sp = d.get("specs") or {}
        role = sp.get("role")
        name = d["name"]
        is_cable = d["category"] in CABLE_CATEGORIES or role in CABLE_ROLES or name.lower().startswith("кабел")
        if not is_cable or role in CABLE_EXCLUDE_ROLES or d["category"] == "service":
            continue
        out.append(d)
    return out


def _source_items(key: str) -> list[dict[str, Any]]:
    if key == "aerocompact":
        from ..seed_data.aerocompact import ITEMS

        return list(ITEMS)
    if key == "cables":
        return _cable_items()
    raise KeyError(key)


def _duplicates_final(d: dict[str, Any], finals: list[CatalogItem]) -> bool:
    """A pack article that GM SUN already has in the final catalog (same role and cross-section) is skipped."""
    sp = d.get("specs") or {}
    role = sp.get("role")
    if not role:
        return False
    for f in finals:
        fs = f.specs or {}
        if fs.get("role") != role:
            continue
        if role in ("pv_cable", "ac_cable"):
            if float(fs.get("cross_section_mm2") or 0) == float(sp.get("cross_section_mm2") or -1) and (role != "ac_cable" or fs.get("cores") == sp.get("cores")):
                return True
        else:
            return True
    return False


def install(db: Session, key: str) -> dict[str, Any]:
    if key not in PACKS:
        raise KeyError(key)
    from ..seed_data import gmsun_final as F
    from .procurement import supplier_of

    final_skus = {d["sku"] for d in F.ITEMS}
    rows = db.query(CatalogItem).all()
    finals = [r for r in rows if r.sku in final_skus]
    by_name = {r.name: r for r in rows}
    added = tagged = skipped = 0
    base = max([r.sort_order or 0 for r in rows] + [0]) + 1
    for i, d in enumerate(_source_items(key)):
        if _duplicates_final(d, finals):
            skipped += 1
            continue
        cur = by_name.get(d["name"])
        if cur is not None:
            if cur.sku in final_skus:
                skipped += 1
                continue
            if pack_of(cur) != key:  # already there (e.g. added by hand) – adopt it into the pack, keep its price
                cur.specs = {**(cur.specs or {}), "pack": key}
                tagged += 1
            continue
        specs = {**(d.get("specs") or {}), "pack": key}
        it = CatalogItem(**{k: v for k, v in d.items() if k != "specs"}, specs=specs, active=True, sort_order=base + i)
        db.add(it)
        db.flush()
        if not it.supplier:
            it.supplier = supplier_of(it)
        by_name[it.name] = it
        added += 1
    rules = 0
    if key == "aerocompact":
        rules = _install_rules(db, by_name)
    packs = enabled(db)
    if key not in packs:
        packs.append(key)
    _put(db, "catalog", {"packs": packs})
    db.flush()
    return {"pack": key, "added": added, "adopted": tagged, "skipped": skipped, "rules": rules}


def _install_rules(db: Session, by_name: dict[str, CatalogItem]) -> int:
    from ..seed_data.aerocompact import RULES

    existing = {(r.roof_type, r.name): r for r in db.query(MountingRule).all()}
    n = 0
    for i, (roof, name, basis, factor, ru) in enumerate(RULES):
        item = by_name.get(name)
        cur = existing.get((roof, name))
        if item is None:  # article deleted by the user – no orphan rule (they are purged on catalog restore anyway)
            continue
        if cur is not None:
            if cur.catalog_item_id is None and item is not None:
                cur.catalog_item_id = item.id
            cur.active = True
            continue
        db.add(MountingRule(roof_type=roof, catalog_item_id=item.id, name=name, basis=basis, factor=factor, round_up=ru, sort_order=i, active=True))
        n += 1
    return n


def remove(db: Session, key: str) -> dict[str, Any]:
    if key not in PACKS:
        raise KeyError(key)
    from .catalog_final import remove_items

    rows = db.query(CatalogItem).all()
    others = [r for r in rows if pack_of(r) == key]
    keep = {r.id for r in rows if pack_of(r) != key}
    res = remove_items(db, others, keep, {})
    _put(db, "catalog", {"packs": [p for p in enabled(db) if p != key]})
    if key == "aerocompact":
        # without mounting items the construction can only be priced per module
        from ..models import RoofTypeConfig

        for r in db.query(RoofTypeConfig).all():
            r.pricing_mode = "lump"
    db.flush()
    return {"pack": key, **res}


def status(db: Session) -> list[dict[str, Any]]:
    rows = db.query(CatalogItem).all()
    on = set(enabled(db))
    out = []
    for key, meta in PACKS.items():
        items = [r for r in rows if pack_of(r) == key]
        out.append({"key": key, **meta, "enabled": key in on, "items": len(items),
                    "indicative": sum(1 for r in items if (r.specs or {}).get("price_source") == "indicative")})
    return out


MIGRATION_KEY = "packs_v1_aerocompact_cables"


def migrate(db: Session) -> None:
    """Once: bring back the Aerocompact and cable databases next to the final catalog (requested by GM SUN)."""
    mig = _setting(db, "migrations")
    if mig.get(MIGRATION_KEY):
        return
    res = {k: install(db, k) for k in ("aerocompact", "cables")}
    _put(db, "migrations", {**mig, MIGRATION_KEY: {"at": datetime.now(timezone.utc).isoformat(), **res}})
    db.commit()
