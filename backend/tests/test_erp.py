"""Orders / deliveries / readiness, completeness check, project documents, datasheet library, dashboard."""
import io

from tests.test_api import _make_project


def _quote(client, auth):
    p = _make_project(client, auth)
    pid = p["id"]
    lay = client.post(f"/api/projects/{pid}/layouts", headers=auth, json={"name": "Юг", "plane_w_m": 3.23, "plane_h_m": 16.9, "orientation": "landscape", "setback_m": 0.3}).json()
    client.post(f"/api/projects/{pid}/layouts/{lay['id']}/autofill", headers=auth, json={})
    items = client.get("/api/catalog/items", headers=auth).json()

    def find(cat, sub):
        return next(i for i in items if i["category"] == cat and sub in i["name"])

    sel = {"inverter_item_id": find("inverter", "SUN-16K-SG01LP1")["id"], "battery_item_id": find("battery", "RW-F16")["id"], "battery_qty": 1,
           "switchboard_item_id": find("switchboard", "Моно")["id"], "labor_mode": "per_w", "transport_price": 120}
    q = client.post(f"/api/projects/{pid}/quotes", headers=auth, json={"selections": sel})
    assert q.status_code == 201, q.text
    return pid, q.json()


def test_orders_receive_readiness(client, auth):
    pid, q = _quote(client, auth)
    r = client.post(f"/api/quotes/{q['id']}/orders/generate", headers=auth, json={})
    assert r.status_code == 200, r.text
    pos = r.json()
    assert pos, "no orders generated"
    assert all(po["number"].startswith("PO-") for po in pos)
    # labor / transport are never ordered, materials are
    names = [l["name"] for po in pos for l in po["lines"]]
    assert not any("Монтаж" in n or "Транспорт" in n for n in names)
    assert any("SUN-16K" in n for n in names)
    # quote + project moved to accepted
    assert client.get(f"/api/quotes/{q['id']}", headers=auth).json()["status"] == "accepted"
    assert client.get(f"/api/projects/{pid}", headers=auth).json()["status"] == "accepted"

    ready = client.get(f"/api/projects/{pid}/readiness", headers=auth).json()
    assert ready["items_total"] > 5 and ready["pct_received"] == 0 and ready["not_ordered"] == []
    assert ready["earliest_start"]

    po = pos[0]
    # send it, then receive one line partially
    r = client.patch(f"/api/orders/{po['id']}", headers=auth, json={"status": "sent", "supplier_ref": "INV-77"})
    assert r.status_code == 200 and r.json()["status"] == "sent" and r.json()["ordered_at"]
    assert client.get(f"/api/projects/{pid}", headers=auth).json()["status"] == "ordered"
    line = next(l for l in po["lines"] if l["qty_ordered"] >= 2)
    r = client.post(f"/api/orders/{po['id']}/lines/{line['id']}/receive", headers=auth, json={"qty": 1, "note": "първа част"})
    assert r.status_code == 200, r.text
    d = r.json()
    l2 = next(l for l in d["lines"] if l["id"] == line["id"])
    assert l2["status"] == "partial" and l2["qty_received"] == 1 and len(l2["receipts"]) == 1
    assert d["status"] == "partial"
    # receive everything
    d = client.post(f"/api/orders/{po['id']}/receive-all", headers=auth, json={}).json()
    assert d["status"] == "received" and all(l["status"] == "received" for l in d["lines"])
    # overdue filter + deliveries list
    aw = client.get("/api/orders", headers=auth).json()
    assert "open_lines" in aw and "suppliers" in aw
    # order workbook + archived as document
    r = client.get(f"/api/orders/{po['id']}/xlsx", headers=auth)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    docs = client.get(f"/api/projects/{pid}/documents", headers=auth).json()["documents"]
    assert any(doc["kind"] == "order" for doc in docs)
    # regenerate keeps non-draft orders, replaces drafts
    r = client.post(f"/api/quotes/{q['id']}/orders/generate", headers=auth, json={})
    nums = [po["number"] for po in client.get(f"/api/projects/{pid}/orders", headers=auth).json()]
    assert po["number"] in nums
    # delete rule
    assert client.delete(f"/api/orders/{po['id']}", headers=auth).status_code == 409


def test_completeness_and_fixes(client, auth):
    pid, q = _quote(client, auth)
    r = client.get(f"/api/quotes/{q['id']}/completeness", headers=auth)
    assert r.status_code == 200, r.text
    c = r.json()
    codes = {i["code"]: i for i in c["items"]}
    assert codes["modules"]["level"] == "ok" and codes["inverter"]["level"] == "ok" and codes["labor"]["level"] == "ok"
    assert codes["survey"]["level"] == "warn"           # no survey yet
    assert codes["grid_docs"]["level"] == "warn" and codes["grid_docs"]["fix"]["type"] == "add_item"
    assert 0 <= c["score"] <= 100
    # survey: tall building without internet → scaffold + 4G router findings
    client.patch(f"/api/projects/{pid}", headers=auth, json={"params": {"survey": {"building_height_m": 9, "roof_access": "scaffold", "internet": "none", "roof_condition": "good", "surveyed_at": "2026-11-07"}}})
    c = client.get(f"/api/quotes/{q['id']}/completeness", headers=auth).json()
    codes = {i["code"]: i for i in c["items"]}
    assert codes["survey"]["level"] == "ok"
    assert codes["scaffold"]["level"] == "warn" and codes["scaffold"]["fix"]["qty"] >= 1
    assert codes["internet"]["level"] == "warn"
    # apply the one-click fixes → lines appear in the quote and the findings turn ok/disappear
    fixes = [codes[k]["fix"] for k in ("scaffold", "internet", "grid_docs", "commissioning") if codes.get(k) and codes[k]["fix"]]
    c2 = client.post(f"/api/quotes/{q['id']}/completeness/apply", headers=auth, json={"fixes": fixes}).json()
    codes2 = {i["code"]: i for i in c2["items"]}
    assert "scaffold" not in codes2 or codes2["scaffold"]["level"] != "warn"
    assert "internet" not in codes2
    assert codes2["grid_docs"]["level"] == "ok"
    q2 = client.get(f"/api/quotes/{q['id']}", headers=auth).json()
    names = " ".join(l["name"] for l in q2["lines"] if not l["hidden"])
    assert "Скеле" in names and "4G" in names and "присъединяване" in names
    assert q2["net_total"] > q["net_total"]


def test_documents_upload_and_package(client, auth):
    pid, q = _quote(client, auth)
    # upload a "photo" (tiny PNG) and a contract
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (3000, 1000), (200, 50, 50)).save(buf, "PNG")
    r = client.post(f"/api/projects/{pid}/documents", headers=auth, files={"file": ("roof.png", buf.getvalue(), "image/png")}, data={"kind": "photo", "title": "Покрив юг"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["kind"] == "photo" and d["filename"].endswith(".jpg") and d["url"].startswith("/api/files/projects/")
    r = client.post(f"/api/projects/{pid}/documents", headers=auth, files={"file": ("dogovor.pdf", b"%PDF-1.4 test", "application/pdf")}, data={"kind": "contract"})
    assert r.status_code == 201
    lst = client.get(f"/api/projects/{pid}/documents", headers=auth).json()
    assert {x["kind"] for x in lst["documents"]} >= {"photo", "contract"}
    # generated documents are archived automatically (same content → one version)
    client.get(f"/api/quotes/{q['id']}/xlsx", headers=auth)
    client.get(f"/api/quotes/{q['id']}/xlsx", headers=auth)
    lst = client.get(f"/api/projects/{pid}/documents?kind=bom", headers=auth).json()
    assert len(lst["documents"]) == 1
    # download + delete
    did = lst["documents"][0]["id"]
    assert client.get(f"/api/documents/{did}/download", headers=auth).status_code == 200
    assert client.delete(f"/api/documents/{did}", headers=auth).status_code == 204
    # client package zip: quote + techfile (+ merged)
    r = client.get(f"/api/quotes/{q['id']}/client-package.zip", headers=auth)
    assert r.status_code == 200, r.text
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert any(n.startswith("01_Oferta") for n in names) and any(n.startswith("02_Tehnichesko") for n in names)
    assert any(n.startswith("00_Palno") for n in names)


def test_datasheet_library_and_dashboard(client, auth):
    st = client.get("/api/catalog/datasheets/status", headers=auth).json()
    assert st["items_with_url"] > 50 and st["library_total"] > 10
    lib = client.get("/api/catalog/datasheets/library", headers=auth).json()
    assert lib["items"] and lib["library"]
    d = client.get("/api/dashboard", headers=auth).json()
    assert "pipeline" in d and "deliveries" in d and "catalog" in d and "datasheets" in d
    assert d["catalog"]["items"] > 100
