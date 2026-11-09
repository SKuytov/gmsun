"""Module recommendation engine + photo visualisation + 3D scene."""
import base64
import io

import cv2
import numpy as np

from tests.test_api import _make_project
from tests.test_multi_inverter import _big_roof_project


def test_orientation_factor_shape():
    from app.services.module_fit import orientation_factor as f

    assert f(180, 33) == 1.0
    assert f(180, 10) < f(180, 30)          # flat is worse than optimal tilt
    assert f(90, 30) < f(180, 30)           # east worse than south
    assert abs(f(90, 30) - f(270, 30)) < 1e-6  # east == west
    assert f(0, 30) < f(90, 30)             # north worst
    assert f(180, 90) < 0.8                 # vertical south facade


def test_recommend_and_apply(client, auth):
    pid, count = _big_roof_project(client, auth)
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"survey": {"roof_access": "ladder", "building_height_m": 8}}})

    r = client.post(f"/api/projects/{pid}/module-recommendations", headers=auth, json={"scope": "auto", "strategy": "balanced", "top": 6})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["scope"] == "target" and rec["target_kwp"] == 24.0 and rec["evaluated"] >= 4
    cands = rec["candidates"]
    assert len(cands) == 4 and cands[0]["rank"] == 1  # the final catalog has exactly 4 modules
    for c in cands:
        # target mode: the recommended count meets the demand (within the 95 % rule) and fits the planes
        assert c["count_used"] <= c["count_max"]
        assert c["kwp"] >= 24.0 * 0.95
        assert c["eur_per_wp_effective"] is not None and c["eur_per_wp_effective"] > c["eur_per_wp"]
        assert len(c["layouts"]) == 2 and all(l["orientation"] in ("portrait", "landscape") for l in c["layouts"])
        assert c["reasons"] or c["warnings"]
    # ladder access: large-format modules carry a handling warning
    big = [c for c in rec["candidates"] if c["height_mm"] > 2050]
    assert all(any("стълба" in w for w in c["warnings"]) for c in big)
    # scores are sorted
    assert [c["score"] for c in cands] == sorted(c["score"] for c in cands)

    # roof scope → every candidate uses the whole roof
    roof = client.post(f"/api/projects/{pid}/module-recommendations", headers=auth, json={"scope": "roof", "strategy": "economy"}).json()
    assert roof["scope"] == "roof" and all(c["count_used"] == c["count_max"] for c in roof["candidates"])
    assert roof["candidates"][0]["kwp_max"] > 60

    # strategies differ in weighting: premium's top pick has tier premium or the best quality score
    prem = client.post(f"/api/projects/{pid}/module-recommendations", headers=auth, json={"strategy": "premium"}).json()
    assert prem["candidates"][0]["quality"] >= max(c["quality"] for c in prem["candidates"]) - 1e-9 or prem["candidates"][0]["tier"] == "premium"

    # apply the balanced recommendation: layouts get the module + the needed count, selections follow
    best = cands[0]
    r = client.post(f"/api/projects/{pid}/module-recommendations/apply", headers=auth, json={"panel_item_id": best["item_id"], "scope": "auto"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["params"]["selections"]["panel_item_id"] == best["item_id"]
    total = sum(int((l.get("summary") or {}).get("count") or 0) for l in p["layouts"])
    assert total == best["count_used"] == p["params"]["selections"]["panel_qty"]
    assert all(l["panel_item_id"] == best["item_id"] for l in p["layouts"])
    # the best-oriented plane (south) is filled first
    south = next(l for l in p["layouts"] if l["name"] == "Юг")
    west = next(l for l in p["layouts"] if l["name"] == "Запад")
    assert (south["summary"]["count"] or 0) >= (west["summary"]["count"] or 0)
    assert all(l["render_path"] for l in p["layouts"])  # plan renders generated server-side

    # proposals now compare modules automatically (panel_auto default) …
    props = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={"scope": "target"}).json()
    assert props["variants"]
    for v in props["variants"]:
        assert 22.0 <= v["kwp"] <= 27.0, v["kwp"]
        assert v["selections"].get("panel_fit") and v["selections"]["panel_fit"]["count"] == v["panel_qty"]
    # … and switching it off pins the layout module
    pinned = client.post(f"/api/projects/{pid}/proposals", headers=auth, json={"scope": "target", "selections": {"panel_auto": False, "panel_item_id": best["item_id"]}}).json()
    assert all(v["selections"]["panel_item_id"] == best["item_id"] for v in pinned["variants"])

    # applying a proposal with a different module re-places the modules on the planes
    other = next((v for v in props["variants"] if v["selections"]["panel_item_id"] != best["item_id"]), None)
    if other:
        r = client.post(f"/api/projects/{pid}/proposals/apply", headers=auth, json={"selections": other["selections"], "strategy": other["strategy"]})
        assert r.status_code == 200, r.text
        p2 = r.json()
        assert all(l["panel_item_id"] == other["selections"]["panel_item_id"] for l in p2["layouts"])
        assert sum(int(l["summary"]["count"]) for l in p2["layouts"]) == other["panel_qty"]
        assert "panel_fit" not in p2["params"]["selections"]


def _synthetic_roof_photo() -> tuple[bytes, list[list[float]]]:
    W, H = 1200, 800
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (235, 205, 160)
    img[int(H * 0.62):] = (60, 120, 70)
    quad = [[250.0, 200.0], [950.0, 190.0], [1100.0, 520.0], [120.0, 540.0]]
    cv2.fillPoly(img, [np.array(quad, np.int32)], (120, 130, 140))
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes(), quad


def test_visualisation_and_scene(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": "Юг", "plane_w_m": 12.0, "plane_h_m": 6.0, "tilt_deg": 25, "azimuth_deg": 180}).json()
    lid = lay["id"]
    photo, quad = _synthetic_roof_photo()
    r = client.post(f"/api/projects/{pid}/layouts/{lid}/image", headers=auth, files={"file": ("roof.jpg", photo, "image/jpeg")})
    assert r.status_code == 200, r.text
    r = client.patch(f"/api/projects/{pid}/layouts/{lid}", headers=auth, json={"corners": quad})
    assert r.status_code == 200, r.text
    lay = client.post(f"/api/projects/{pid}/layouts/{lid}/autofill", headers=auth, json={}).json()
    assert lay["summary"]["count"] > 10
    # all three renders exist after autofill (server-side, no browser upload needed)
    assert lay["render_path"] and lay["visual_path"] and lay["rect_path"]
    for rel in (lay["render_path"], lay["visual_path"], lay["rect_path"]):
        r = client.get(f"/api/files/{rel}")
        assert r.status_code == 200 and len(r.content) > 1000, rel
    # the overlay keeps the photo size and darkens the roof where the modules are
    vis = cv2.imdecode(np.frombuffer(client.get(f"/api/files/{lay['visual_path']}").content, np.uint8), cv2.IMREAD_COLOR)
    orig = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    assert vis.shape == orig.shape
    cx, cy = 600, 360  # inside the roof quad
    assert vis[cy, cx].mean() < orig[cy, cx].mean() - 30
    assert abs(int(vis[700, 600].mean()) - int(orig[700, 600].mean())) < 6  # grass untouched
    # silver frame variant
    r = client.post(f"/api/projects/{pid}/layouts/{lid}/visualize", headers=auth, json={"frame": "silver"})
    assert r.status_code == 200 and r.json()["visual_path"]
    pr = client.get(f"/api/projects/{pid}", headers=auth).json()
    assert pr["params"]["visual"]["frame"] == "silver"

    # 3D scene
    sc = client.get(f"/api/projects/{pid}/scene", headers=auth).json()
    assert sc["modules"] == lay["summary"]["count"] and len(sc["planes"]) == 1
    pl = sc["planes"][0]
    assert pl["texture"] == lay["rect_path"] and pl["tilt"] == 25 and pl["panel"]["width_m"] > 1
    assert sc["building"]["ridge_height_m"] > sc["building"]["eave_height_m"]

    # 3D screenshot upload → stored for the documents
    png = base64.b64encode(cv2.imencode(".png", np.full((40, 60, 3), 90, np.uint8))[1].tobytes()).decode()
    r = client.post(f"/api/projects/{pid}/render3d", headers=auth, json={"png": "data:image/png;base64," + png})
    assert r.status_code == 200 and r.json()["params"]["visual"]["render3d_path"].endswith(f"render3d_{pid}.png")

    # the client PDF embeds the visualisation appendix
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={}).json()
    r = client.get(f"/api/quotes/{q['id']}/html", headers=auth)
    assert r.status_code == 200
    assert "Как ще изглежда Вашата централа" in r.text and "3D изглед" in r.text


def test_pick_compact_block():
    from app.services import module_fit as mf

    # 7 rows × 17 columns of landscape modules (1.762 × 1.134 m) — a 32 × 9 m plane
    panels = [dict(x=0.3 + c * 1.782, y=0.3 + r * 1.154, w=1.762, h=1.134, row=r) for r in range(7) for c in range(17)]
    sel = mf.pick_compact(panels, 50)
    rows = {}
    for p in sel:
        rows.setdefault(p["row"], []).append(p)
    assert len(sel) == 50
    assert sorted(len(v) for v in rows.values()) == [10] * 5  # 5 × 10 block, no stray modules
    assert sorted(rows) == list(range(min(rows), min(rows) + 5))  # consecutive rows, centred
    assert 1 <= min(rows) <= 2
    # odd counts: symmetric trimming of the outer rows, never more than one module difference per row pair
    sel = mf.pick_compact(panels, 100)
    rows = {}
    for p in sel:
        rows.setdefault(p["row"], []).append(p)
    assert len(sel) == 100 and max(len(v) for v in rows.values()) - min(len(v) for v in rows.values()) <= 1
    assert mf.pick_compact(panels, 0) == []
    assert len(mf.pick_compact(panels, 500)) == len(panels)
    # dimension fallback by power class
    assert mf.default_dims_mm(650) == (1134, 2382) and mf.default_dims_mm(575) == (1134, 2278) and mf.default_dims_mm(450) == (1134, 1762)
    w, h, est = mf.module_dims_m({"wp": 480})
    assert est and (round(w * 1000), round(h * 1000)) == (1134, 1762)
    w, h, est = mf.module_dims_m({"wp": 480, "width_mm": 1134, "height_mm": 1762})
    assert not est
