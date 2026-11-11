"""GM SUN does not quote delivery fees: off by default, per-quote switch can still add them, migration cleans drafts."""
from app.db import SessionLocal
from app.models import Quote, Setting
from app.services import delivery_off

from .test_api import _make_project


def _inv(client, auth):
    return next(i for i in client.get("/api/catalog/items", params={"category": "inverter"}, headers=auth).json() if "SUN-16K-SG01LP1" in i["name"])


def _delivery(q):
    return [l for l in q["lines"] if l["key"].startswith("delivery:")]


def test_no_delivery_fees_by_default_and_opt_in(client, auth):
    p = _make_project(client, auth)
    q = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_qty": 20, "inverter_item_id": _inv(client, auth)["id"]}}).json()
    assert _delivery(q) == []
    sel = {k: v for k, v in q["selections"].items() if not k.startswith("_")}
    q2 = client.patch(f"/api/quotes/{q['id']}", headers=auth, json={"selections": {**sel, "delivery_fees": True}}).json()
    assert len(_delivery(q2)) >= 2 and q2["net_total"] > q["net_total"]


def test_migration_removes_delivery_from_drafts_only(client, auth):
    p = _make_project(client, auth)
    inv = _inv(client, auth)["id"]
    draft = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_qty": 20, "inverter_item_id": inv, "delivery_fees": True}}).json()
    sent = client.post(f"/api/projects/{p['id']}/quotes", headers=auth, json={"selections": {"panel_qty": 20, "inverter_item_id": inv, "delivery_fees": True}}).json()
    assert _delivery(draft) and _delivery(sent)
    db = SessionLocal()
    try:
        db.get(Quote, sent["id"]).status = "sent"
        mig = db.get(Setting, "migrations")
        mig.value = {k: v for k, v in (mig.value or {}).items() if k != delivery_off.MIGRATION_KEY}
        db.commit()
        res = delivery_off.migrate(db)
        assert res and res["quotes"] >= 1
        assert delivery_off.migrate(db) is None  # once
    finally:
        db.close()
    d = client.get(f"/api/quotes/{draft['id']}", headers=auth).json()
    s = client.get(f"/api/quotes/{sent['id']}", headers=auth).json()
    assert _delivery(d) == [] and "delivery_fees" not in d["selections"]
    assert _delivery(s) and s["net_total"] == sent["net_total"]  # frozen document untouched
