"""BMS / control box and rack / cabinet are two independent selections (auto | manual | none) with engineering checks."""
from __future__ import annotations


def _by(client, auth, sub, cat):
    return next(i for i in client.get("/api/catalog/items", params={"category": cat}, headers=auth).json() if sub in i["name"])


def _project(client, auth):
    p = client.post("/api/projects", headers=auth, json={"name": "HV", "client_name": "К", "site_address": "Русе", "phase": 3, "connected_power_kw": 20, "roof_type": "tile"})
    assert p.status_code == 201, p.text
    return p.json()


def _sel(client, auth, **extra):
    inv = _by(client, auth, "SUN-20K-SG01HP3 -EU-AM2", "inverter")
    bat = _by(client, auth, "Bos-G Pro battery", "battery")
    return {"panel_qty": 26, "inverter_item_id": inv["id"], "battery_item_id": bat["id"], "battery_qty": 5, **extra}


def _parts(q):
    return {l["key"].split(":")[0]: l for l in q["lines"] if l["key"].startswith(("batt_auto", "batt_bms", "batt_rack", "batt_acc"))}, [l for l in q["lines"] if l["key"].startswith("batt_")]


def test_auto_bms_and_rack_by_default(client, auth):
    p = _project(client, auth)
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": _sel(client, auth)}).json()
    _k, rows = _parts(q)
    names = sorted(r["name"] for r in rows)
    assert any("BMS" in n for n in names) and any("Rack" in n for n in names)


def test_manual_rack_auto_bms_and_none(client, auth):
    p = _project(client, auth)
    rack12 = _by(client, auth, "за до 12 батерии + 1 BMS", "battery_accessory")
    bms = _by(client, auth, "BMS за до 16", "battery_accessory")
    sel = _sel(client, auth, battery_rack={"mode": "manual", "items": [{"item_id": rack12["id"], "qty": 1}]})
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": sel}).json()
    rows = [l for l in q["lines"] if l["key"].startswith("batt_")]
    assert any(l["key"] == f"batt_rack:{rack12['id']}" and l["qty"] == 1 for l in rows)
    assert any(l["key"] == f"batt_auto:{bms['id']}" for l in rows)  # BMS stays automatic
    assert not any("до 8" in l["name"] for l in rows)  # auto rack replaced by the manual one
    # BMS off → no BMS line, explicit warning
    sel["battery_bms"] = {"mode": "none", "items": []}
    r = client.patch(f"/api/quotes/{q['id']}", headers=auth, json={"selections": sel})
    assert r.status_code == 200, r.text
    q = r.json()
    assert not any("BMS за до 16" in l["name"] for l in q["lines"])
    assert any("HV батериите не работят без него" in w for w in q.get("warnings") or [])


def test_endpoint_options_and_checks(client, auth):
    rack8 = _by(client, auth, "за до 8 батерии + 1 BMS", "battery_accessory")
    bos_a_rack = _by(client, auth, "BOS-A-Rack11", "battery_accessory")
    sel = _sel(client, auth, battery_qty=10, battery_rack={"mode": "manual", "items": [{"item_id": rack8["id"], "qty": 1}, {"item_id": bos_a_rack["id"], "qty": 1}]})
    r = client.post("/api/sizing/battery-parts", headers=auth, json={"selections": sel})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["hv"] is True
    opts = {o["item_id"]: o for o in d["options"]["rack"]}
    assert opts[rack8["id"]]["compatible"] and not opts[bos_a_rack["id"]]["compatible"]
    assert all(o["role"] in ("hv_bms", "bms", "control_box") for o in d["options"]["bms"])
    # wrong-family rack rejected, the remaining 8-slot rack is too small for 10 modules
    assert [x["item_id"] for x in d["resolved"]["rack"]] == [rack8["id"]]
    assert any(w.startswith("НЕСЪВМЕСТИМО") for w in d["warnings"])
    assert any("побира 8" in w for w in d["warnings"])
    # cables are sized by the engine – never offered as "other" accessories
    assert not any(o["role"] in ("battery_cable", "battery_lug", "comm_cable") for o in d["options"]["other"])


def test_legacy_manual_list_still_works(client, auth):
    """Old selections: auto off + BMS / rack inside battery_accessories (with item_id or catalog_item_id)."""
    p = _project(client, auth)
    rack12 = _by(client, auth, "за до 12 батерии + 1 BMS", "battery_accessory")
    bms = _by(client, auth, "BMS за до 16", "battery_accessory")
    sel = _sel(client, auth, battery_auto_accessories=False, battery_accessories=[{"catalog_item_id": rack12["id"], "qty": 1}, {"item_id": bms["id"], "qty": 1}])
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": sel}).json()
    keys = {l["key"] for l in q["lines"]}
    assert f"batt_rack:{rack12['id']}" in keys and f"batt_bms:{bms['id']}" in keys
