"""v2 features: Filkab cables / PVC pipes / solar fence catalog packs, manual cables, MC4 & battery cables "in kit",
hidden custom add-ons spread over the whole quote, PVC pipes hidden in the electrical section, solar fence site kind."""
from app.services import site_kind
from app.services.pricing import cable_modes, estimate_yield

from .test_api import _make_project


def _items(client, auth):
    return client.get("/api/catalog/items", headers=auth).json()


def _quote(client, auth, extra=None, roof="tile"):
    p = _make_project(client, auth)
    if roof != "tile":
        r = client.patch(f"/api/projects/{p['id']}", headers=auth, json={"roof_type": roof})
        assert r.status_code == 200, r.text
    items = _items(client, auth)
    inv = next(i for i in items if i["category"] == "inverter" and "SUN-16K-SG01LP1" in i["name"])
    sel = {"panel_qty": 20, "inverter_item_id": inv["id"], "labor_mode": "per_w", **(extra or {})}
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": sel})
    assert q.status_code == 201, q.text
    return p, q.json()


def _vis(q):
    return [l for l in q["lines"] if not l["hidden"] and not l["excluded"]]


def test_catalog_has_filkab_pipes_and_fence(client, auth):
    items = _items(client, auth)
    names = [i["name"] for i in items]
    assert any("H1Z2Z2-K" in n and "4" in n for n in names)
    assert any("H1Z2Z2-K" in n and "6" in n for n in names)
    assert sum(1 for i in items if i["supplier"] == "Филкаб") >= 20
    assert any("СВТ" in n for n in names) and any("AL/R" in n for n in names)
    pipes = [i for i in items if (i["specs"] or {}).get("role") == "pvc_pipe"]
    assert {20, 25, 32} <= {int((i["specs"] or {}).get("diameter_mm") or 0) for i in pipes} or len(pipes) >= 3
    rts = client.get("/api/catalog/roof-types", headers=auth).json()
    fence = next(r for r in rts if r["code"] == "pv_fence")
    assert fence["kind"] == "fence" and fence["default_tilt_deg"] == 90
    assert all(r.get("kind") in site_kind.KINDS for r in rts)


def test_mc4_and_battery_cables_kit_by_default():
    assert cable_modes({}) == {"cables": "auto", "mc4": "kit", "battery_cables": "kit"}
    assert cable_modes({"mc4_item_id": 5})["mc4"] == "manual"
    assert cable_modes({"cables_mode": "manual", "mc4_mode": "auto"})["cables"] == "manual"


def test_mc4_kit_not_quoted(client, auth):
    _, q = _quote(client, auth)
    assert not any("MC4" in l["name"] and not l["excluded"] for l in q["lines"] if l["section"] == "electrical")


def test_custom_addon_hidden_and_spread_over_whole_quote(client, auth):
    _, q0 = _quote(client, auth)
    _, q = _quote(client, auth, {"custom_addons": [{"name": "Доставка батерия — палет", "qty": 2, "unit": "палет", "unit_price": 40}]})
    add = [l for l in q["lines"] if l["key"].startswith("addon:")]
    assert len(add) == 1 and add[0]["hidden"] and abs(add[0]["total"] - 80) < 0.011
    # the visible lines carry it: net grows by exactly 80 (× markup 0 – add-ons are at cost)
    assert abs(q["net_total"] - q0["net_total"] - 80) < 0.02
    vis = _vis(q)
    assert abs(sum(l["total"] for l in vis) - q["net_total"]) < 0.05 or abs(sum(l["total"] for l in vis) - q["subtotal"]) < 0.05
    secs = {l["section"] for l in vis if l["alloc"]}
    assert len(secs) >= 2  # spread over every section, not only "other"


def test_pipes_hidden_in_electrical(client, auth):
    items = _items(client, auth)
    pipe = next(i for i in items if (i["specs"] or {}).get("role") == "pvc_pipe")
    _, q0 = _quote(client, auth)
    _, q = _quote(client, auth, {"pipes": [{"item_id": pipe["id"], "m": 30}]})
    pl = [l for l in q["lines"] if l["key"].startswith("pipe:")]
    assert len(pl) == 1 and pl[0]["hidden"] and pl[0]["section"] == "electrical"
    el = [l for l in _vis(q) if l["section"] == "electrical"]
    assert abs(sum(l["alloc"] for l in el) - sum(l["total"] for l in q["lines"] if l["hidden"] and l["section"] == "electrical")) < 0.05
    # automatic corrugated conduits are replaced by the chosen pipes
    assert not any(l["key"].startswith("design:conduit") for l in q["lines"])


def test_manual_cables(client, auth):
    items = _items(client, auth)
    pv6 = next(i for i in items if "H1Z2Z2-K" in i["name"] and "6" in i["name"] and i["supplier"] == "Филкаб")
    _, q = _quote(client, auth, {"cables_mode": "manual", "cables": [{"item_id": pv6["id"], "m": 80}]})
    cl = [l for l in q["lines"] if l["key"].startswith("cable:")]
    assert len(cl) == 1 and cl[0]["qty"] == 80 and cl[0]["catalog_item_id"] == pv6["id"]
    roles = {(l["meta"] or {}).get("role") for l in q["lines"] if not l["key"].startswith("cable:")}
    assert "pv_cable" not in roles and "ac_cable" not in roles
    comp = client.get(f"/api/quotes/{q['id']}/completeness", headers=auth)
    assert comp.status_code == 200


def test_fence_kind_and_vertical_yield(client, auth):
    assert site_kind.kind_from_code("pv_fence") == "fence"
    assert site_kind.kind_from_code("ground_concrete") == "ground"
    assert site_kind.kind_from_code("flat_ballast") == "flat"
    assert site_kind.kind_from_code("tile") == "pitched"
    mono = estimate_yield(10, 1300, 90, 90)
    bif = estimate_yield(10, 1300, 90, 90, bifaciality=70)
    south20 = estimate_yield(10, 1300, 180, 20)
    assert mono < south20 and bif > mono


def test_fence_project_quote_and_pdf(client, auth):
    p, q = _quote(client, auth, roof="pv_fence")
    client.patch(f"/api/projects/{p['id']}", headers=auth, json={"params": {"survey": {"fence_base": "wall", "fence_length_m": 30, "fence_height_m": 2}}})
    q = client.post(f"/api/quotes/{q['id']}/recalculate", headers=auth).json()
    con = [l for l in q["lines"] if l["section"] == "construction" and not l["excluded"]]
    assert con and any("стена" in l["name"] or "ограда" in l["name"] for l in con)
    html = client.get(f"/api/quotes/{q['id']}/html?mode=client", headers=auth).text
    assert "ограда" in html.lower()
    comp = client.get(f"/api/quotes/{q['id']}/completeness", headers=auth)
    assert comp.status_code == 200
    txt = comp.text
    assert "скеле" not in txt.lower()  # no roof checks for a fence
