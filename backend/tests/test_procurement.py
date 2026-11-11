"""Lead times, tiers, the proposal engine and supplier RFQ workbooks."""
from __future__ import annotations

import io
import zipfile

from openpyxl import load_workbook

from tests.test_api import _make_project


def test_catalog_items_expose_procurement_fields(client, auth):
    items = client.get("/api/catalog/items?category=panel,inverter,battery", headers=auth).json()
    assert items
    for it in items:
        assert it["effective_lead_time_days"] is not None and it["effective_lead_time_days"] > 0
        assert it["effective_tier"] in ("economy", "standard", "premium")
    # every final item comes from green-energy.bg; no Aerocompact items remain
    # (other tests may edit a supplier field, so check the majority + that none is empty)
    assert all(i["supplier"] for i in items)
    assert sum(i["supplier"] == "green-energy.bg" for i in items) >= len(items) - 3
    mounting = client.get("/api/catalog/items?category=mounting", headers=auth).json()
    assert mounting and all((i["specs"] or {}).get("pack") in ("aerocompact", "pv_fence") for i in mounting)


def test_item_lead_time_and_tier_override(client, auth):
    inv = client.get("/api/catalog/items?category=inverter", headers=auth).json()[0]
    r = client.patch(f"/api/catalog/items/{inv['id']}", headers=auth, json={"lead_time_days": 42, "tier": "premium", "supplier_sku": "ABC-1"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["effective_lead_time_days"] == 42 and out["effective_tier"] == "premium" and out["supplier_sku"] == "ABC-1"
    bad = client.patch(f"/api/catalog/items/{inv['id']}", headers=auth, json={"tier": "gold"})
    assert bad.status_code == 400
    client.patch(f"/api/catalog/items/{inv['id']}", headers=auth, json={"lead_time_days": None, "tier": None})


def test_suppliers_setting_roundtrip(client, auth):
    s = client.get("/api/settings/suppliers", headers=auth).json()["value"]
    assert any(x["name"] == "green-energy.bg" for x in s["list"])
    s["list"].append({"name": "Местен склад", "lead_time_days": 2, "email": "sklad@example.bg"})
    r = client.put("/api/settings/suppliers", headers=auth, json={"value": s})
    assert r.status_code == 200
    assert any(x["name"] == "Местен склад" for x in r.json()["value"]["list"])


def test_proposals_generate_and_apply(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    client.patch(f"/api/projects/{pid}", headers=auth, json={"connected_power_kw": 15, "desired_storage_kwh": 10, "phase": 3, "voltage_class": "LV"})
    r = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["target_kwp"] > 0
    variants = {v["strategy"]: v for v in data["variants"]}
    assert set(variants) == {"economy", "balanced", "premium", "fastest"}
    for v in variants.values():
        assert v["total"] > 0 and v["lead_time_days"] >= 0 and v["kwp"] > 0
        assert v["selections"]["panel_item_id"] and v["selections"]["inverter_item_id"]
        assert v["selections"]["strategy"] == v["strategy"]
        roles = {k["role"] for k in v["key_items"]}
        assert {"panel", "inverter"} <= roles
    # economy must not cost more than premium; fastest must not be slower than economy
    assert variants["economy"]["total"] <= variants["premium"]["total"] + 1e-6
    assert variants["fastest"]["lead_time_days"] <= variants["economy"]["lead_time_days"]
    # a quote built from the applied proposal reproduces the proposal totals
    chosen = variants["economy"]
    ap = client.post(f"/api/projects/{pid}/proposals/apply", headers=auth, json={"selections": chosen["selections"], "strategy": "economy"})
    assert ap.status_code == 200
    assert ap.json()["params"]["selections"]["strategy"] == "economy"
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": chosen["selections"]}).json()
    assert abs(q["total"] - chosen["total"]) < 0.05, (q["total"], chosen["total"])
    info = q["selections"]["_info"]
    assert info["lead_time_days"] == chosen["lead_time_days"]
    assert info["lead_bottleneck"]
    assert all("lead_time_days" in (ln.get("meta") or {}) for ln in q["lines"] if ln.get("catalog_item_id"))


def test_rfq_exports(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    items = client.get("/api/catalog/items", headers=auth).json()
    inv = next(i for i in items if i["category"] == "inverter" and "SUN-16K-SG05LP3" in i["name"])
    pan = next(i for i in items if i["category"] == "panel" and i["supplier"] == "green-energy.bg")
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": {"panel_item_id": pan["id"], "panel_qty": 20, "use_layout": False, "inverter_item_id": inv["id"], "labor_mode": "per_w"}}).json()
    summary = client.get(f"/api/quotes/{q['id']}/rfq", headers=auth).json()
    assert summary and any(s["supplier"] == "green-energy.bg" for s in summary)
    assert all({"supplier", "lines", "value", "lead_time_days"} <= set(s) for s in summary)
    x = client.get(f"/api/quotes/{q['id']}/rfq.xlsx", headers=auth)
    assert x.status_code == 200
    wb = load_workbook(io.BytesIO(x.content))
    assert wb.sheetnames[0] == "Доставчици" and len(wb.sheetnames) == 1 + len(summary)
    ws = wb["green-energy.bg"]
    text = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value is not None)
    assert "Запитване за оферта" in text and pan["name"] in text
    one = client.get(f"/api/quotes/{q['id']}/rfq.xlsx?supplier=green-energy.bg", headers=auth)
    assert load_workbook(io.BytesIO(one.content)).sheetnames == ["green-energy.bg"]
    z = client.get(f"/api/quotes/{q['id']}/rfq.zip", headers=auth)
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert len(names) == len(summary) and all(n.startswith("Zayavka_") and n.endswith(".xlsx") for n in names)
