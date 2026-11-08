"""Roof with room for ~83 kWp but a 20 kW grid connection (the user's test case).

* ``scope=target``/auto → proposals for the needed power, the rest of the roof is reported as an option;
* ``scope=roof``      → every module is used and the inverters are multiplied (e.g. 4 × 20 kW), with AC combiner,
  main breaker, per-inverter protections and per-inverter string design.
"""
import math

from tests.test_api import _make_project


def _big_roof_project(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    client.patch(f"/api/projects/{pid}", headers=auth, json={"connected_power_kw": 20, "desired_storage_kwh": 0, "phase": 3, "voltage_class": "LV"})
    # ~190 modules: two big planes
    for name, w, h in (("Юг", 30.0, 9.0), ("Запад", 20.0, 9.0)):
        lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": name, "plane_w_m": w, "plane_h_m": h, "orientation": "portrait", "setback_m": 0.3}).json()
        client.post(f"/api/projects/{pid}/layouts/{lay['id']}/autofill", headers=auth, json={}).json()
    p = client.get(f"/api/projects/{pid}", headers=auth).json()
    count = sum(int((l.get("summary") or {}).get("count") or 0) for l in p["layouts"])
    assert count >= 120, count
    return pid, count


def test_inverter_count_rule():
    from app.services.sizing import inverter_count

    assert inverter_count(20, 20) == 1
    assert inverter_count(20, 83, max_pv_kw=26) == 4          # 83/26 → 4 units, DC/AC 1.04
    assert inverter_count(50, 83, max_pv_kw=65) == 2          # 2 × 50 kW, DC/AC 0.83
    assert inverter_count(12, 83, max_pv_kw=15.6) == 6        # 6 × 12 kW, DC/AC 1.15
    assert inverter_count(5, 83, max_pv_kw=6.5) == 0          # would need 13 units → excluded
    assert inverter_count(16, 14.3, max_pv_kw=20.8) == 1


def test_sizing_endpoint_returns_qty(client, auth):
    r = client.get("/api/sizing/inverters", headers=auth, params={"phase": 3, "connected_kw": 20, "pv_kwp": 83, "voltage_class": "LV"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows and all(row["qty"] >= 1 for row in rows)
    # every suggestion covers the array: per-unit PV ≤ 1.35 × AC (i.e. the model is multiplied as needed)
    for row in rows:
        ac = float(row["item"]["specs"]["ac_power_kw"])
        assert 83 / row["qty"] <= ac * 1.36 + 1e-6, (row["item"]["name"], row["qty"])
        assert abs(row["ac_total_kw"] - ac * row["qty"]) < 1e-6
    # a 20 kW class model is proposed as 4 units
    twenty = [row for row in rows if 19 <= float(row["item"]["specs"]["ac_power_kw"]) <= 20]
    assert twenty and all(row["qty"] == 4 for row in twenty), [(t["item"]["name"], t["qty"]) for t in twenty]


def test_proposals_target_vs_roof(client, auth):
    pid, count = _big_roof_project(client, auth)

    # ---- default (auto): the roof is far bigger than the 20 kW connection → size for the demand, keep the roof as an option
    r = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={})
    assert r.status_code == 200, r.text
    auto = r.json()
    assert auto["scope"] == "target" and auto["demand_basis"] == "connected_power"
    # roof capacity = the planes filled with the base module (auto-fill), at least what is drawn by hand
    assert auto["roof_panel_qty"] >= count and auto["roof_kwp"] > 60
    assert 20 <= auto["target_kwp"] <= 27
    assert auto["notes"] and "целия покрив" in auto["notes"][0]
    for v in auto["variants"]:
        assert v["panel_qty"] < count and v["kwp"] <= 27.5, (v["strategy"], v["panel_qty"], v["kwp"])
        sel = v["selections"]
        # the automatic panel pick stores a per-plane fit; a manual panel keeps the plain panel_limit
        if "panel_fit" in sel:
            assert sel["panel_fit"]["count"] == v["panel_qty"], (v["strategy"], sel["panel_fit"])
            # roof capacity is re-computed for the recommended module, so it may differ from the hand-drawn count
            assert v["roof_panel_qty"] == sel["panel_fit"]["roof_count"] > v["panel_qty"]
        else:
            assert sel["panel_limit"] == v["panel_qty"]
            assert v["roof_panel_qty"] == count
        assert v["ac_kw"] <= 20 * 1.1 + 1e-6, (v["strategy"], v["ac_kw"])
        assert not any("надвишава присъединената" in w for w in v["warnings"]), v["warnings"]

    # ---- whole roof: several inverters in parallel, complete AC side
    r = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={"scope": "roof"})
    assert r.status_code == 200, r.text
    roof = r.json()
    assert roof["scope"] == "roof" and roof["target_basis"] == "layout"
    assert any("присъединената мощност" in n for n in roof["notes"])
    assert roof["variants"]
    for v in roof["variants"]:
        fit = v["selections"].get("panel_fit")
        if fit:
            assert v["panel_qty"] == fit["count"] == fit["roof_count"] > 0
        else:
            assert v["panel_qty"] == count
        n = v["inverter_qty"]
        inv = next(k for k in v["key_items"] if k["role"] == "inverter")
        assert inv["qty"] == n
        kwp = v["kwp"]
        assert 0.75 <= kwp / v["ac_kw"] <= 1.36, (v["strategy"], inv["name"], n, kwp, v["ac_kw"])
        assert "panel_limit" not in v["selections"]
    # a single large string inverter is a valid answer too, but at least one strategy must land on a parallel set
    multi = [v for v in roof["variants"] if v["inverter_qty"] >= 2]
    assert multi, [(v["strategy"], v["inverter_qty"]) for v in roof["variants"]]

    # ---- the quote built from a multi-inverter proposal carries N inverters, N breakers, a combiner and a main breaker
    chosen = multi[0]
    n = chosen["inverter_qty"]
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": chosen["selections"]}).json()
    assert abs(q["total"] - chosen["total"]) < 0.05
    lines = q["lines"]
    inv_line = next(l for l in lines if l["key"] == "inverter")
    assert inv_line["qty"] == n
    by_role = {}
    for l in lines:
        role = (l.get("meta") or {}).get("role")
        if role:
            by_role.setdefault(role, []).append(l)
    assert "ac_combiner" in by_role and by_role["ac_combiner"][0]["qty"] == 1
    assert "parallel_cable" in by_role and by_role["parallel_cable"][0]["qty"] == n - 1
    mcbs = by_role["ac_mcb"]
    assert any(l["qty"] == n for l in mcbs), [(l["name"], l["qty"]) for l in mcbs]
    main = [l for l in mcbs if "Главен" in (l["meta"].get("role_name") or "")]
    assert "ГРТ" in main[0]["name"]
    assert main and main[0]["qty"] == 1
    i_inv = float(next(l for l in mcbs if l["qty"] == n)["meta"]["spec"]["rating_a"])
    i_main = float(main[0]["meta"]["spec"]["rating_a"])
    assert i_main >= i_inv * n * 0.9  # main breaker sized for the sum of the inverters
    assert by_role["ac_rcd"][0]["qty"] == n
    assert len(by_role["ac_cable"]) >= 2  # per-inverter feeders + combiner → main board
    assert not any(l.get("meta", {}).get("missing_item") for l in by_role["ac_combiner"] + by_role["parallel_cable"] + mcbs)
    info = q["selections"]["_info"]
    assert info["inverter_qty"] == n
    st = info["strings"]
    assert st["inverters"] == n and len(st["per_inverter"]) == n
    assert sum(p["modules"] for p in st["per_inverter"]) == chosen["panel_qty"]
    # no inverter gets more strings than it has inputs
    design = info["design"]["strings"]
    per_inv_inputs = design["inputs_per_inverter"]
    for p in st["per_inverter"]:
        assert p["strings"] <= per_inv_inputs, (p, per_inv_inputs)
    # the module split is balanced (±1 string worth of modules)
    mods = [p["modules"] for p in st["per_inverter"]]
    assert max(mods) - min(mods) <= max(1, math.ceil(count / n) * 0.35)


def test_single_inverter_design_unchanged(client, auth):
    """A 14 kWp roof with a 16 kW hybrid keeps a single inverter and the classic AC side (no combiner)."""
    p = _make_project(client, auth)
    pid = p["id"]
    client.patch(f"/api/projects/{pid}", headers=auth, json={"connected_power_kw": 15, "phase": 3})
    lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": "Юг", "plane_w_m": 3.23, "plane_h_m": 16.9, "orientation": "landscape", "setback_m": 0.3}).json()
    client.post(f"/api/projects/{pid}/layouts/{lay['id']}/autofill", headers=auth, json={})
    r = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={}).json()
    assert r["scope"] == "roof"
    for v in r["variants"]:
        assert v["inverter_qty"] == 1
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": r["variants"][0]["selections"]}).json()
    roles = {(l.get("meta") or {}).get("role") for l in q["lines"]}
    assert "ac_combiner" not in roles and "parallel_cable" not in roles
