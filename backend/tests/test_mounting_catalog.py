"""Aerocompact mounting catalogue (legacy "detailed" construction mode): every roof/terrain type must yield a complete,
priced, orderable component list, with quantities matching the manufacturer's assembly rules.

The production catalog is the curated GM SUN final catalog (no Aerocompact items, construction priced per module), so
the detailed engine is verified on a separate database seeded with the legacy catalog."""
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import CatalogItem, MountingRule, RoofTypeConfig
from app.seed_data.aerocompact import DOCS, ITEMS, ROOF_SYSTEM, ROOF_TYPES, RULES, SYSTEMS, system_for_roof
from app.services import bom


_LEGACY = {}


def SessionLocal():  # noqa: N802 - legacy database for this module
    if "maker" not in _LEGACY:
        from app import seed as S

        eng = create_engine(f"sqlite:///{tempfile.mkdtemp(prefix='gmsun_legacy_')}/legacy.db")
        Base.metadata.create_all(eng)
        _LEGACY["maker"] = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
        db = _LEGACY["maker"]()
        for rt in S.ROOF_TYPES:
            db.add(RoofTypeConfig(**rt))
        db.commit()
        S.seed_legacy_catalog(db)
        db.commit()
        db.close()
    return _LEGACY["maker"]()


def _summary(n_modules: int, rows: int = 1) -> dict:
    per = n_modules // rows
    return {"count": n_modules, "kwp": n_modules * 0.6, "lines": [{"modules": per, "length_m": per * 1.134 + (per - 1) * 0.02, "rails": 2, "direction": "h"} for _ in range(rows)]}


def test_catalogue_is_consistent():
    names = {i["name"] for i in ITEMS}
    assert len(names) == len(ITEMS), "duplicate item names"
    codes = {r["code"] for r in ROOF_TYPES}
    for roof, name, basis, factor, _ in RULES:
        assert roof in codes, (roof, name)
        assert name in names, name
        assert factor > 0
    for s in SYSTEMS:
        assert s["docs"], s["code"]
        for url in s["docs"].values():
            assert url.startswith("https://")
    assert set(ROOF_SYSTEM.values()) <= {s["code"] for s in SYSTEMS}
    assert system_for_roof("tile")["code"] == "XM-F"
    assert system_for_roof("ground") is None
    assert all(u.endswith(".pdf") or "aerocompact.com" in u for d in DOCS.values() for u in d.values())


def test_every_roof_type_has_rules_and_items(client, auth):
    db = SessionLocal()
    try:
        roofs = db.query(RoofTypeConfig).all()
        assert {r.code for r in roofs} >= {r["code"] for r in ROOF_TYPES}
        for roof in roofs:
            rules = db.query(MountingRule).filter(MountingRule.roof_type == roof.code, MountingRule.active.is_(True)).all()
            assert rules, roof.code
            assert all(r.catalog_item_id for r in rules), [r.name for r in rules if not r.catalog_item_id]
            st = bom.compute_stats(_summary(10, rows=2), roof)
            lines = bom.mounting_lines(db, roof, st, default_markup=20.0, fastener_margin_pct=10.0)
            assert lines and sum(l["qty"] for l in lines) > 0, roof.code
            assert any(l["qty"] >= 10 for l in lines), roof.code  # at least clamps scale with modules
    finally:
        db.close()


def test_tl25_two_modules_need_six_bridges(client, auth):
    """Assembly instruction CompactMETAL TL25: two modules require at least 6 bridges, 4 end clamps, 2 mid clamps."""
    db = SessionLocal()
    try:
        roof = db.get(RoofTypeConfig, "lt_sheet")
        st = bom.compute_stats(_summary(2), roof)
        assert (st.mid_clamps, st.end_clamps) == (2, 4)
        lines = {l["name"]: l for l in bom.mounting_lines(db, roof, st, 20.0, 0.0)}
        bridge = next(v for k, v in lines.items() if k.startswith("CompactMETAL TL25"))
        assert bridge["qty"] == 6
        screws = next(v for k, v in lines.items() if k.startswith("MSS 6×25"))
        assert screws["qty"] == 24  # 4 per bridge
        assert not any(k.startswith("X50") for k in lines), "TL mounts clamps directly, no long rails"
    finally:
        db.close()


def test_tile_quote_matches_real_configurator_logic(client, auth):
    db = SessionLocal()
    try:
        roof = db.get(RoofTypeConfig, "tile")
        st = bom.compute_stats(_summary(10), roof)
        lines = {l["name"]: l for l in bom.mounting_lines(db, roof, st, 20.0, 0.0)}
        hooks = lines["XM-F кука за керемиден покрив (регулируема)"]["qty"]
        assert hooks == st.fixations
        assert lines["SDS-W 8×100 самонарезен винт за дърво (A2)"]["qty"] == 2 * hooks
        assert lines["XM-FCMR покривна ламарина среден размер, червена"]["qty"] == hooks
        assert lines["CLE10 крайна скоба Click 30-46"]["qty"] == 4
        assert lines["CLM10 средна скоба Click 30-46 (със заземяващи щифтове)"]["qty"] == 18
    finally:
        db.close()


def test_mounting_systems_endpoint(client, auth):
    r = client.get("/api/catalog/mounting/systems", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert len(data["systems"]) >= 14 and len(data["documents"]) >= 60
    assert data["roof_system"]["standing_seam"] == "TM"
    # the Aerocompact pack is installed next to the final catalog; re-seeding is additive and idempotent
    items = client.get("/api/catalog/items", params={"category": "mounting"}, headers=auth).json()
    assert len(items) >= 150
    r = client.post("/api/catalog/mounting/reseed", headers=auth)
    assert r.status_code == 200 and r.json()["added_items"] == 0
    db = SessionLocal()
    aero = db.query(CatalogItem).filter(CatalogItem.manufacturer == "Aerocompact").all()
    assert len(aero) >= 150 and all((i.specs or {}).get("datasheet_url") for i in aero)
    try:
        assert db.query(CatalogItem).filter(CatalogItem.name.like("TMDS08%")).count() == 1
    finally:
        db.close()
