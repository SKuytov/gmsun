"""Complete demo dataset (datafill) and whole-dataset Excel round trip."""
import io
import zipfile

from openpyxl import load_workbook


def test_seeded_dataset_is_complete(client, auth):
    # other tests may have imported unpriced supplier rows in the meantime → complete them first (as the admin button does)
    r = client.post("/api/catalog/dataset/fill-missing", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["unpriced_left"] == []
    items = client.get("/api/catalog/items?include_inactive=true", headers=auth).json()
    assert len(items) > 500
    missing_price = [i for i in items if not i["purchase_price"]]
    assert missing_price == [], [i["name"] for i in missing_price][:10]
    for key in ("lead_time_days", "tier", "supplier", "sku", "manufacturer"):
        assert all(i.get(key) not in (None, "") for i in items), key
    # indicative prices are marked as such
    marked = [i for i in items if (i["specs"] or {}).get("price_source") == "indicative"]
    assert len(marked) > 100
    # the seed itself already completed the dataset: a second run has nothing left to fill (idempotent, never overwrites)
    r = client.post("/api/catalog/dataset/fill-missing", headers=auth)
    assert r.json()["price"] == 0 and r.json()["lead_time"] == 0 and r.json()["tier"] == 0


def test_dataset_export_and_import_roundtrip(client, auth):
    r = client.get("/api/catalog/dataset.xlsx", headers=auth)
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Инструкции", "Артикули", "Труд", "Типове покриви", "Правила конструкция", "Доставчици", "Настройки"} <= set(wb.sheetnames)
    ws = wb["Артикули"]
    keys = [c.value for c in ws[1]]
    assert "purchase_price" in keys and "lead_time_days" in keys and "kwh" in keys
    # unchanged file → nothing updated, no errors
    rep = client.post("/api/catalog/dataset/import", headers=auth, files={"file": ("gmsun-dataset.xlsx", r.content)}).json()
    assert rep["errors"] == 0 and rep["updated"] == 0 and rep["created"] == 0

    # edit a price + lead time, add a new item, clear a warranty with '-'
    col = {k: i + 1 for i, k in enumerate(keys)}
    first = 3
    item_id = ws.cell(row=first, column=col["id"]).value
    ws.cell(row=first, column=col["purchase_price"]).value = 1234.5
    ws.cell(row=first, column=col["lead_time_days"]).value = 42
    ws.cell(row=first, column=col["warranty"]).value = "-"
    new_row = ws.max_row + 1
    ws.cell(row=new_row, column=col["category"]).value = "accessory"
    ws.cell(row=new_row, column=col["name"]).value = "Тестов артикул от Excel"
    ws.cell(row=new_row, column=col["purchase_price"]).value = "12,5"
    ws.cell(row=new_row, column=col["active"]).value = "да"
    # labour sheet edit
    wl = wb["Труд"]
    lkeys = {c.value: i + 1 for i, c in enumerate(wl[1])}
    wl.cell(row=3, column=lkeys["price"]).value = 999
    # settings edit
    wsett = wb["Настройки"]
    for row in wsett.iter_rows(min_row=3):
        if row[0].value == "pricing.default_markup_pct":
            row[1].value = 17.5
    bio = io.BytesIO()
    wb.save(bio)
    rep = client.post("/api/catalog/dataset/import", headers=auth, files={"file": ("gmsun-dataset.xlsx", bio.getvalue())}).json()
    assert rep["errors"] == 0, rep
    assert rep["created"] == 1 and rep["updated"] >= 3
    it = client.get(f"/api/catalog/items/{item_id}", headers=auth).json()
    assert it["purchase_price"] == 1234.5 and it["lead_time_days"] == 42 and it["warranty"] is None
    assert it["specs"]["price_source"] == "excel-import"
    items = client.get("/api/catalog/items", headers=auth).json()
    new = [i for i in items if i["name"] == "Тестов артикул от Excel"]
    assert new and new[0]["purchase_price"] == 12.5
    assert client.get("/api/catalog/labor", headers=auth).json()[0]["price"] == 999
    assert client.get("/api/settings/pricing", headers=auth).json()["value"]["default_markup_pct"] == 17.5


def test_dataset_zip_roundtrip(client, auth):
    r = client.get("/api/catalog/dataset.zip", headers=auth)
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        names = z.namelist()
    assert sum(n.endswith(".xlsx") for n in names) == 6
    rep = client.post("/api/catalog/dataset/import", headers=auth, files={"file": ("gmsun-dataset.zip", r.content)}).json()
    assert rep["errors"] == 0 and len(rep["files"]) == 6 and rep["created"] == 0


def test_dataset_import_reports_errors(client, auth):
    r = client.get("/api/catalog/dataset.xlsx", headers=auth)
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Артикули"]
    keys = {c.value: i + 1 for i, c in enumerate(ws[1])}
    ws.cell(row=3, column=keys["tier"]).value = "gold"
    ws.cell(row=4, column=keys["purchase_price"]).value = "abc"
    bio = io.BytesIO()
    wb.save(bio)
    rep = client.post("/api/catalog/dataset/import", headers=auth, files={"file": ("x.xlsx", bio.getvalue())}).json()
    assert rep["errors"] == 2
    assert any("gold" in e for e in rep["tables"]["catalog_items"]["errors"])
