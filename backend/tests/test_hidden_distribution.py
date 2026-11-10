"""Hidden quote lines keep their value: it is spread over the visible lines of the same section so that the section
totals and the grand total stay exactly the same. Deleted engine lines are removed from the price (and restorable)."""
from types import SimpleNamespace

from app.services import pricing

from .test_api import _make_project


def _sections(q):
    out = {}
    for l in q["lines"]:
        if not l["hidden"] and not l["excluded"]:
            out[l["section"]] = round(out.get(l["section"], 0) + l["total"], 2)
    return out


def _quote(client, auth):
    p = _make_project(client, auth)
    items = client.get("/api/catalog/items", headers=auth).json()
    inv = next(i for i in items if i["category"] == "inverter" and "SUN-16K-SG01LP1" in i["name"])
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_qty": 20, "inverter_item_id": inv["id"], "labor_mode": "per_w"}})
    assert q.status_code == 201, q.text
    return q.json()


def test_hide_keeps_totals_and_section_totals(client, auth):
    q = _quote(client, auth)
    net0, tot0, sec0 = q["net_total"], q["total"], _sections(q)
    el = [l for l in q["lines"] if l["section"] == "electrical"]
    assert len(el) >= 3
    victim = max(el, key=lambda l: l["total"])
    r = client.patch(f"/api/quotes/{q['id']}/lines/{victim['id']}", headers=auth, json={"hidden": True})
    assert r.status_code == 200, r.text
    q1 = r.json()
    assert q1["net_total"] == net0 and q1["total"] == tot0
    assert _sections(q1) == sec0
    vis = [l for l in q1["lines"] if l["section"] == "electrical" and not l["hidden"]]
    assert abs(sum(l["alloc"] for l in vis) - victim["total"]) < 0.011
    for l in vis:  # what the client sees is self-consistent: qty × unit price = total
        assert l["client_unit_price"] is not None
        if abs(l["qty"] - 1) < 1e-9 or l["alloc"] == 0:
            assert abs(round(l["qty"] * l["client_unit_price"], 2) - l["total"]) < 0.011
    # cost (and therefore margin) still counts the hidden item – it is still bought
    assert abs(q1["cost_total"] - q["cost_total"]) < 0.011
    # unhide → original prices back
    q2 = client.patch(f"/api/quotes/{q['id']}/lines/{victim['id']}", headers=auth, json={"hidden": False}).json()
    assert all(l["alloc"] == 0 for l in q2["lines"])
    assert q2["net_total"] == net0
    # survives the automatic recalculation
    q3 = client.post(f"/api/quotes/{q['id']}/recalculate", headers=auth).json()
    assert q3["net_total"] == net0


def test_hidden_whole_section_goes_to_other_sections(client, auth):
    q = _quote(client, auth)
    net0 = q["net_total"]
    con = [l for l in q["lines"] if l["section"] == "construction"]
    for l in con:
        q = client.patch(f"/api/quotes/{q['id']}/lines/{l['id']}", headers=auth, json={"hidden": True}).json()
    assert q["net_total"] == net0
    assert "construction" not in _sections(q)
    assert all(s["code"] != "construction" for s in q["sections"])


def test_delete_removes_and_restore(client, auth):
    q = _quote(client, auth)
    net0 = q["net_total"]
    ln = next(l for l in q["lines"] if l["section"] == "electrical" and l["source"] == "auto")
    q1 = client.delete(f"/api/quotes/{q['id']}/lines/{ln['id']}", headers=auth).json()
    gone = next(l for l in q1["lines"] if l["id"] == ln["id"])
    assert gone["excluded"] and not gone["hidden"]
    assert abs(q1["net_total"] - (net0 - ln["total"])) < 0.011
    q2 = client.post(f"/api/quotes/{q['id']}/recalculate", headers=auth).json()
    assert next(l for l in q2["lines"] if l["id"] == ln["id"])["excluded"]  # recalculation does not bring it back
    q3 = client.patch(f"/api/quotes/{q['id']}/lines/{ln['id']}", headers=auth, json={"excluded": False}).json()
    back = next(l for l in q3["lines"] if l["id"] == ln["id"])
    assert not back["excluded"] and not back["locked"]
    assert q3["net_total"] == net0


def _ln(i, sec, qty, up, hidden=False):
    return SimpleNamespace(id=i, section=sec, qty=qty, unit_price=up, hidden=hidden, excluded=False, alloc=0.0, client_unit_price=None, total=0.0)


def test_rounding_is_exact_without_qty_one_lines():
    lines = [_ln(1, "electrical", 150, 0.06), _ln(2, "electrical", 75, 1.09), _ln(3, "electrical", 13, 2.37), _ln(4, "electrical", 7, 3.33, hidden=True)]
    q = SimpleNamespace(lines=lines, discount_pct=0, vat_pct=20, advance_pct=70, selections={})
    pricing.compute_totals(q)
    expected = round(150 * 0.06 + 75 * 1.09 + 13 * 2.37 + 7 * 3.33, 2)
    assert q.subtotal == expected
    assert round(sum(l.total for l in lines if not l.hidden), 2) == expected


LONG = ("Доставка, монтаж, пускане в експлоатация, конфигуриране и настройка на оборудването до постигане на пълна "
        "функционална готовност, включително доставка и монтаж на всички необходими допълнителни и непредвидени "
        "електрически компоненти, материали и принадлежности, необходими за нормалната и надеждна работа на системата")


def test_long_custom_text_on_line(client, auth):
    q = _quote(client, auth)
    assert len(LONG) > 255
    ln = q["lines"][0]
    r = client.patch(f"/api/quotes/{q['id']}/lines/{ln['id']}", headers=auth, json={"name": LONG, "unit": "комплект за обекта"})
    assert r.status_code == 200, r.text
    got = next(l for l in r.json()["lines"] if l["id"] == ln["id"])
    assert got["name"] == LONG and got["locked"]
    assert got["unit"] == "комплект за обект"[:16] or len(got["unit"]) <= 16
    r = client.post(f"/api/quotes/{q['id']}/lines", headers=auth, json={"section": "other", "name": LONG * 2, "qty": 1, "unit_price": 10})
    assert r.status_code == 201 or r.status_code == 200, r.text
    assert any(l["name"] == LONG * 2 for l in r.json()["lines"])
    from app.services.pricing import SECTIONS
    assert dict((c, t) for c, t, _ in SECTIONS)["labor"] == "Част монтажни работи"
    assert client.get(f"/api/quotes/{q['id']}/pdf?mode=client", headers=auth).status_code == 200
