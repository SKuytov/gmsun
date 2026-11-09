"""GM SUN final catalog: migration, dataset replace mode, compatibility rules, inverter-based labor and live quote sync."""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from app.db import SessionLocal
from app.models import CatalogItem
from app.seed_data import gmsun_final as F
from app.services import catalog_final, compat, engineering
from tests.test_api import _make_project


def _items(client, auth, cat=None):
    params = {"category": cat} if cat else {}
    return client.get("/api/catalog/items", params=params, headers=auth).json()


def _by(client, auth, sub, cat=None):
    return next(i for i in _items(client, auth, cat) if sub in i["name"])


def _db_item(db, sub):
    return db.query(CatalogItem).filter(CatalogItem.name.like(f"%{sub}%")).first()


# ----------------------------------------------------------------------------------------------------------- migration
def test_final_catalog_is_the_only_catalog(client, auth):
    items = _items(client, auth)
    names = {i["name"] for i in items}
    assert names >= {i["name"] for i in F.ITEMS}
    st = client.get("/api/catalog/final/status", headers=auth).json()
    assert st["done"] is True
    db = SessionLocal()
    try:
        assert catalog_final.is_done(db) and catalog_final.is_curated(db)
        assert db.query(CatalogItem).filter(CatalogItem.manufacturer == "Aerocompact").count() == 0
    finally:
        db.close()
    # legacy seeders are refused once the curated catalog is active
    assert client.post("/api/catalog/mounting/reseed", headers=auth).status_code == 409


def test_reapply_removes_foreign_items_and_keeps_quotes_valid(client, auth):
    p = _make_project(client, auth)
    extra = client.post("/api/catalog/items", headers=auth, json={"category": "panel", "name": "Чужд панел 999W", "unit": "бр.", "purchase_price": 50.0,
                                                                  "specs": {"power_w": 999}}).json()
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_item_id": extra["id"], "panel_qty": 2}}).json()
    assert q["id"]
    r = client.post("/api/catalog/final/reapply", headers=auth)
    assert r.status_code == 200, r.text
    names = {i["name"] for i in _items(client, auth)}
    assert "Чужд панел 999W" not in names
    # the quote still loads and no longer points at the deleted item
    q2 = client.get(f"/api/quotes/{q['id']}", headers=auth)
    assert q2.status_code == 200
    assert q2.json()["selections"].get("panel_item_id") != extra["id"]
    # idempotent
    assert client.post("/api/catalog/final/reapply", headers=auth).status_code == 200
    assert len(_items(client, auth)) == len(F.ITEMS)


# ------------------------------------------------------------------------------------------------- dataset replace mode
def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Артикули"
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_dataset_replace_refuses_without_items_sheet(client, auth):
    wb = Workbook()
    wb.active.title = "Нещо"
    b = io.BytesIO()
    wb.save(b)
    before = len(_items(client, auth))
    r = client.post("/api/catalog/dataset/import?replace_items=true", headers=auth,
                    files={"file": ("x.xlsx", b.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 400, r.text
    assert len(_items(client, auth)) == before


def test_dataset_export_import_replace_roundtrip(client, auth):
    before = {i["name"] for i in _items(client, auth)}
    exp = client.get("/api/catalog/dataset.xlsx", headers=auth)
    assert exp.status_code == 200
    client.post("/api/catalog/items", headers=auth, json={"category": "accessory", "name": "Временен артикул", "unit": "бр.", "purchase_price": 1.0})
    r = client.post("/api/catalog/dataset/import?replace_items=true", headers=auth,
                    files={"file": ("gmsun-dataset.xlsx", exp.content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    after = {i["name"] for i in _items(client, auth)}
    assert after == before  # the temporary item (not in the file) was deleted, nothing else changed
    assert r.json().get("deleted", 0) >= 1


# --------------------------------------------------------------------------------------------------------- compat rules
def test_hv_series_ranges_match_datasheets(client, auth):
    db = SessionLocal()
    try:
        bosg = _db_item(db, "Bos-G Pro battery").specs
        bosa = _db_item(db, "BOS - A - 7.68").specs
        am2 = _db_item(db, "SUN-15K-SG01HP3 -EU-AM2").specs
        bm = _db_item(db, "SUN-40K-SG01HP3 -EU-BM4").specs
        em6 = _db_item(db, "SUN-60K-SG02HP3-EU-EM6").specs
        assert engineering.hv_series_range(am2, bosg)[1] == 11
        assert engineering.hv_series_range(am2, bosa)[1] == 15
        assert engineering.hv_series_range(bm, bosg)[1] == 13
        assert engineering.hv_series_range(bm, bosa)[1] == 18
        assert engineering.hv_series_range(em6, bosg)[1] == 16
        assert engineering.hv_series_range(em6, bosa)[1] == 21
    finally:
        db.close()


def test_am2_mppt_layout_is_two_plus_one():
    db = SessionLocal()
    try:
        inv = _db_item(db, "SUN-15K-SG01HP3 -EU-AM2").specs
        assert engineering.mppt_capacities(inv) == [2, 1]
    finally:
        db.close()


def test_impossible_combinations_are_blocked(client, auth):
    db = SessionLocal()
    try:
        cfg = compat._design_cfg(db)
        panel = _db_item(db, "Himo 10 485Wp")
        inv3 = _db_item(db, "SUN-10K-SG05LP3")
        inv1 = _db_item(db, "SUN-10K-SG02LP1")
        lv = _db_item(db, "RW-F16")
        hv = _db_item(db, "Bos-G Pro battery")
        hv_inv = _db_item(db, "SUN-20K-SG01HP3 -EU-AM2")
        # 3-phase inverter on a 1-phase connection
        assert compat.check_pair(panel, inv3, cfg, modules_per_inverter=20, phase=1)["status"] == "blocked"
        assert compat.check_pair(panel, inv3, cfg, modules_per_inverter=20, phase=3)["status"] in ("ok", "warn")
        assert compat.check_pair(panel, inv1, cfg, modules_per_inverter=20, phase=1)["status"] in ("ok", "warn")
        # far too many modules for one inverter
        assert compat.check_pair(panel, inv1, cfg, modules_per_inverter=200, phase=1)["status"] == "blocked"
        # LV battery on HV inverter and vice versa
        assert compat.check_battery(hv_inv, lv, 1)["status"] == "blocked"
        assert compat.check_battery(inv3, hv, 4)["status"] == "blocked"
        assert compat.check_battery(inv3, lv, 1)["status"] in ("ok", "warn")
        # an HV stack too long for the AM2 battery voltage window
        assert compat.check_battery(hv_inv, hv, 4)["status"] == "blocked"  # BOS-G Pro needs >= 5 modules in series
        assert compat.check_battery(hv_inv, hv, 5)["status"] in ("ok", "warn")
        assert compat.check_battery(hv_inv, hv, 30)["status"] == "blocked"
    finally:
        db.close()


def test_hv_rack_selection():
    db = SessionLocal()
    try:
        inv = _db_item(db, "SUN-50K-SG01HP3-EU-BM4")
        bosg = _db_item(db, "Bos-G Pro battery")

        def racks(b, n):
            acc, _ = compat.hv_accessories(db, inv, b, n)
            return sorted((it.name, q) for it, q, _r in acc if "Rack" in it.name or "Frame" in it.name)

        r8 = racks(bosg, 8)
        assert len(r8) == 1 and "до 8" in r8[0][0] and r8[0][1] == 1
        r12 = racks(bosg, 12)
        assert len(r12) == 1 and "до 12" in r12[0][0]
        assert sum(q for _n, q in racks(bosg, 16)) == 2
    finally:
        db.close()


def test_compatibility_endpoint(client, auth):
    p = _make_project(client, auth)  # phase 1
    panel = _by(client, auth, "Himo 10 485Wp", "panel")
    r = client.get(f"/api/projects/{p['id']}/compatibility", headers=auth, params={"panel_item_id": panel["id"], "panel_qty": 20})
    assert r.status_code == 200, r.text
    m = r.json()
    inv3 = _by(client, auth, "SUN-10K-SG05LP3", "inverter")
    inv1 = _by(client, auth, "SUN-10K-SG02LP1", "inverter")
    assert m["inverters"][str(inv3["id"])]["status"] == "blocked"
    assert m["inverters"][str(inv1["id"])]["status"] in ("ok", "warn")
    assert m["inverters"][str(inv3["id"])]["reasons"]


# ------------------------------------------------------------------------------------------------- labor per inverter kW
def _quote_with(client, auth, pid, **sel):
    return client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": sel}).json()


def _labor(q):
    return next(l for l in q["lines"] if l["key"] == "labor")


def test_labor_is_inverter_kw_times_rate(client, auth):
    p = client.post("/api/projects", headers=auth, json={"name": "Труд", "client_name": "К", "phase": 3, "connected_power_kw": 20, "roof_type": "tile"}).json()
    panel = _by(client, auth, "Himo 10 485Wp", "panel")
    inv = _by(client, auth, "SUN-16K-SG05LP3", "inverter")
    q = _quote_with(client, auth, p["id"], panel_item_id=panel["id"], panel_qty=22, inverter_item_id=inv["id"], inverter_qty=1)
    lab = _labor(q)
    rate = client.get("/api/settings/pricing", headers=auth).json()["value"]["labor_eur_per_inverter_kw"]
    assert lab["qty"] == pytest.approx(16.0) and lab["unit_price"] == pytest.approx(rate)  # 10.67 kWp, but 16 kW inverter
    # per-quote override of the rate
    q2 = _quote_with(client, auth, p["id"], panel_item_id=panel["id"], panel_qty=22, inverter_item_id=inv["id"], inverter_qty=1, labor_eur_per_kw=100)
    assert _labor(q2)["unit_price"] == pytest.approx(100) and _labor(q2)["qty"] == pytest.approx(16.0)
    # changing the setting updates the default rate of new quotes and the existing draft
    pr = client.get("/api/settings/pricing", headers=auth).json()["value"]
    client.put("/api/settings/pricing", headers=auth, json={"value": {**pr, "labor_eur_per_inverter_kw": 130.0}})
    try:
        q3 = client.get(f"/api/quotes/{q2['id']}", headers=auth).json()
        assert _labor(q3)["unit_price"] == pytest.approx(100)  # explicit override kept
        q4 = _quote_with(client, auth, p["id"], panel_item_id=panel["id"], panel_qty=22, inverter_item_id=inv["id"], inverter_qty=2)
        assert _labor(q4)["qty"] == pytest.approx(32.0) and _labor(q4)["unit_price"] == pytest.approx(130.0)
    finally:
        client.put("/api/settings/pricing", headers=auth, json={"value": pr})


# --------------------------------------------------------------------------------------------------------- live sync
def test_project_changes_update_the_draft_quote(client, auth):
    p = client.post("/api/projects", headers=auth, json={"name": "Синхрон", "client_name": "К", "phase": 3, "connected_power_kw": 20, "roof_type": "tile"}).json()
    pid = p["id"]
    panel = _by(client, auth, "Himo 10 485Wp", "panel")
    inv = _by(client, auth, "SUN-12K-SG05LP3", "inverter")
    sel = {"panel_item_id": panel["id"], "panel_qty": 20, "inverter_item_id": inv["id"], "inverter_qty": 1}
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"selections": sel}})
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": sel}).json()
    t0 = q["total"]
    # project change -> draft quote follows without a manual recalc
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"selections": {**sel, "panel_qty": 24}}})
    q1 = client.get(f"/api/quotes/{q['id']}", headers=auth).json()
    assert q1["selections"]["panel_qty"] == 24 and q1["total"] > t0
    # catalog price change -> draft follows
    client.patch(f"/api/catalog/items/{inv['id']}", headers=auth, json={"purchase_price": inv["purchase_price"] + 100})
    try:
        q2 = client.get(f"/api/quotes/{q['id']}", headers=auth).json()
        assert q2["total"] > q1["total"]
    finally:
        client.patch(f"/api/catalog/items/{inv['id']}", headers=auth, json={"purchase_price": inv["purchase_price"]})
    # quote-level markup edit is mirrored into the project
    client.patch(f"/api/quotes/{q['id']}", headers=auth, json={"markup_pct": 15})
    pr = client.get(f"/api/projects/{pid}", headers=auth).json()
    assert pr["params"]["selections"].get("markup_pct") == 15
    # a sent quote is frozen
    client.patch(f"/api/quotes/{q['id']}", headers=auth, json={"status": "sent"})
    frozen = client.get(f"/api/quotes/{q['id']}", headers=auth).json()["total"]
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"selections": {**sel, "panel_qty": 30}}})
    assert client.get(f"/api/quotes/{q['id']}", headers=auth).json()["total"] == frozen
