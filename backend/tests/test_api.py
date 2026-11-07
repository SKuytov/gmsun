import pathlib

ATT = pathlib.Path.home() / ".perplexity/attachments/cb4b216045a5431e872b5d9a7c8b57e7"


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login-json", json={"email": "admin@gmsun.local", "password": "nope"})
    assert r.status_code == 401


def test_catalog_seeded(client, auth):
    items = client.get("/api/catalog/items", headers=auth).json()
    cats = {i["category"] for i in items}
    assert {"panel", "inverter", "battery", "switchboard", "solar_cable", "power_cable", "mounting"} <= cats
    meta = client.get("/api/catalog/meta", headers=auth).json()
    assert "categories" in meta


def test_sizing_inverters_single_phase(client, auth):
    inv = client.get("/api/sizing/inverters?phase=1&connected_kw=16&pv_kwp=9.1", headers=auth).json()
    assert inv
    assert all(i["item"]["specs"]["phases"] == 1 for i in inv)
    assert "SUN-16K" in inv[0]["item"]["name"]


def test_sizing_batteries_lv_compat(client, auth):
    inv = client.get("/api/sizing/inverters?phase=1&connected_kw=16", headers=auth).json()[0]
    bats = client.get(f"/api/sizing/batteries?inverter_id={inv['item']['id']}&target_kwh=32", headers=auth).json()
    assert bats
    for b in bats:
        assert b["item"]["specs"]["voltage_class"] == "LV"
    assert bats[0]["qty"] == 2


def _make_project(client, auth):
    p = client.post(
        "/api/projects",
        headers=auth,
        json={"name": "Тест", "client_name": "Клиент", "site_address": "София", "phase": 1, "connected_power_kw": 16, "roof_type": "tile", "desired_storage_kwh": 16},
    )
    assert p.status_code == 201, p.text
    return p.json()


def test_project_layout_quote_flow(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": "Юг", "plane_w_m": 3.23, "plane_h_m": 16.9, "orientation": "landscape", "setback_m": 0.3}).json()
    lay = client.post(f"/api/projects/{pid}/layouts/{lay['id']}/autofill", headers=auth, json={}).json()
    assert lay["summary"]["count"] == 14

    items = client.get("/api/catalog/items", headers=auth).json()

    def find(cat, sub):
        return next(i for i in items if i["category"] == cat and sub in i["name"])

    sel = {
        "inverter_item_id": find("inverter", "SUN-16K-SG01LP1")["id"],
        "battery_item_id": find("battery", "RW-F16")["id"],
        "battery_qty": 1,
        "switchboard_item_id": find("switchboard", "Моно")["id"],
        "solar_cable_item_id": find("solar_cable", "KBE")["id"],
        "solar_cable_red_m": 50,
        "solar_cable_black_m": 50,
        "power_cable_item_id": find("power_cable", "4×16")["id"],
        "power_cable_m": 40,
        "labor_mode": "per_w",
    }
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": sel})
    assert q.status_code == 201, q.text
    q = q.json()
    assert q["net_total"] > 0
    # totals must equal the sum of visible lines right after creation (regression: double-appended lines)
    assert abs(q["subtotal"] - round(sum(l["total"] for l in q["lines"] if not l["hidden"]), 2)) < 0.02
    assert abs(q["total"] - round(q["net_total"] * 1.2, 2)) < 0.02
    assert abs(q["advance_amount"] - round(q["net_total"] * 0.7, 2)) < 0.02
    sections = {l["section"] for l in q["lines"]}
    assert {"modules", "inverter", "construction", "electrical", "labor"} <= sections
    labor = next(l for l in q["lines"] if l["section"] == "labor")
    assert labor["total"] == round(9100 * 0.118, 2)

    # lock a manual price and make sure recalculation keeps it
    ln = q["lines"][0]
    r = client.patch(f"/api/quotes/{q['id']}/lines/{ln['id']}", headers=auth, json={"unit_price": 123.0})
    assert r.status_code == 200
    q2 = client.post(f"/api/quotes/{q['id']}/recalculate", headers=auth).json()
    first = next(l for l in q2["lines"] if l["id"] == ln["id"])
    assert first["unit_price"] == 123.0 and first["locked"]

    # manual extra line
    before = q2["net_total"]
    q3 = client.post(f"/api/quotes/{q['id']}/lines", headers=auth, json={"section": "other", "name": "Кран", "qty": 1, "unit_price": 150}).json()
    assert abs(q3["net_total"] - before - 150) < 0.01

    # documents
    pdf = client.get(f"/api/quotes/{q['id']}/pdf", headers=auth)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    pdf_i = client.get(f"/api/quotes/{q['id']}/pdf?mode=internal", headers=auth)
    assert pdf_i.status_code == 200
    xlsx = client.get(f"/api/quotes/{q['id']}/xlsx", headers=auth)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    html = client.get(f"/api/quotes/{q['id']}/html", headers=auth)
    assert "ОФЕРТА" in html.text.upper()


def test_labor_matrix_mode(client, auth):
    p = _make_project(client, auth)
    labor = client.get("/api/catalog/labor", headers=auth).json()
    opt = next(l for l in labor if l["days"] == 2 and l["workers"] == 3)
    assert opt["price"] == 3000
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_qty": 10, "labor_mode": "matrix", "labor_option_id": opt["id"], "mounting_mode": "none"}}).json()
    lab = [l for l in q["lines"] if l["section"] == "labor"]
    assert lab and lab[0]["total"] == 3000


def test_settings_roundtrip(client, auth):
    r = client.get("/api/settings/pricing", headers=auth)
    assert r.status_code == 200
    val = r.json()["value"]
    assert val["vat_pct"] == 20
    val["default_markup_pct"] = 12
    r = client.put("/api/settings/pricing", headers=auth, json={"value": val})
    assert r.status_code == 200
    assert client.get("/api/settings/pricing", headers=auth).json()["value"]["default_markup_pct"] == 12
    val["default_markup_pct"] = 10
    client.put("/api/settings/pricing", headers=auth, json={"value": val})


def test_catalog_import_supplier_pricelist(client, auth):
    f = ATT / "Price-list-SALIM-Inverters-Batteries-Components-12.10.2026_4d09f9e0-2713-4a80-8b0b-f4d4c6514d45-Copy.xlsx"
    if not f.exists():
        import pytest

        pytest.skip("supplier price list not available")
    r = client.post("/api/catalog/import?category=inverter", headers=auth, files={"file": ("p.xlsx", f.read_bytes())})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["updated"] >= 40  # existing Deye items matched by model code, not duplicated


def test_catalog_export(client, auth):
    r = client.get("/api/catalog/export", headers=auth)
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_engineering_design_and_techfile(client, auth):
    """Automatic electrical design (IEC 62548 string check + roles BOM) and the technical file PDF."""
    p = _make_project(client, auth)
    pid = p["id"]
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"dc_run_m": 18, "ac_run_m": 15}})
    lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": "Юг", "plane_w_m": 15.0, "plane_h_m": 6.5, "orientation": "landscape", "setback_m": 0.3}).json()
    lay = client.post(f"/api/projects/{pid}/layouts/{lay['id']}/autofill", headers=auth, json={}).json()
    assert lay["summary"]["count"] >= 18
    items = client.get("/api/catalog/items", headers=auth).json()

    def find(cat, sub):
        return next(i for i in items if i["category"] == cat and sub in i["name"])

    sel = {
        "inverter_item_id": find("inverter", "SUN-16K-SG05LP3")["id"],
        "battery_item_id": find("battery", "RW-F16")["id"],
        "battery_qty": 1,
        "labor_mode": "per_w",
    }
    d = client.post(f"/api/sizing/projects/{pid}/design", headers=auth, json={"selections": sel})
    assert d.status_code == 200, d.text
    d = d.json()
    assert d["strings"]["strings"], "string design must assign strings"
    assert all(s["voc_cold_v"] <= 800 for s in d["strings"]["strings"])
    assert all(c["ok"] for c in d["strings"]["checks"]), d["strings"]["checks"]
    roles = {r["role"]: r for r in d["roles"]}
    assert sum(1 for r in d["roles"] if r["role"] == "pv_cable") == 2  # red + black
    for must in ("pv_cable", "mc4_pair", "ac_mcb", "ac_rcd", "ac_cable", "pe_cable", "battery_cable", "battery_breaker", "bonding_clamp", "dc_spd", "cable_tie_uv"):
        assert must in roles, must
    assert roles["ac_mcb"]["spec"]["rating_a"] >= 100 and roles["ac_mcb"]["spec"]["poles"] == "4P"
    assert roles["ac_cable"]["spec"]["cross_section_mm2"] >= 10
    assert roles["battery_cable"]["spec"]["cross_section_mm2"] >= 50
    # margins applied: red cable qty is the rounded-up length with the cable margin
    assert roles["pv_cable"]["qty"] >= d["dc"]["red_m"] or roles["pv_cable"]["qty"] >= d["dc"]["black_m"]

    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": sel})
    assert q.status_code == 201, q.text
    q = q.json()
    elec = [l for l in q["lines"] if l["section"] == "electrical"]
    assert len(elec) >= 15
    assert any((l["meta"] or {}).get("role") == "ac_rcd" for l in elec)
    cons = [l for l in q["lines"] if l["section"] == "construction"]
    small = [l for l in cons if (l["meta"] or {}).get("margin_pct")]
    assert small, "fastener margin must be applied to small parts"

    tf = client.get(f"/api/quotes/{q['id']}/techfile.pdf", headers=auth)
    assert tf.status_code == 200 and tf.content[:4] == b"%PDF"
    html = client.get(f"/api/quotes/{q['id']}/techfile.html", headers=auth)
    assert "Еднолинейна схема" in html.text and "<svg" in html.text
    xlsx = client.get(f"/api/quotes/{q['id']}/xlsx", headers=auth)
    assert xlsx.status_code == 200
    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert wb.sheetnames == ["Оферта"]  # client version has no purchase data
    xlsx = client.get(f"/api/quotes/{q['id']}/xlsx?internal=true", headers=auth)
    wb = load_workbook(io.BytesIO(xlsx.content))
    assert "Поръчка" in wb.sheetnames and wb["Поръчка"].max_row > 10 and "Доставчици" in wb.sheetnames
