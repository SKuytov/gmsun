"""Catalog import/export (xlsx). Understands the supplier price-list format
used in the project (section header rows, model / warranty / price columns)
as well as a plain table with a header row."""
from __future__ import annotations

import io
import re
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from ..models import CatalogItem

HEADER_ALIASES = {
    "name": ["name", "model", "модел", "наименование", "артикул", "mодел"],
    "price": ["price", "цена", "eur", "eur w/t vat", "purchase", "доставна"],
    "sell_price": ["sell", "продажна", "клиентска"],
    "warranty": ["warranty", "гаранция"],
    "sku": ["sku", "код", "part", "артикулен"],
    "unit": ["unit", "мярка", "ед."],
    "manufacturer": ["manufacturer", "производител", "brand", "марка"],
    "category": ["category", "категория"],
}


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def model_key(name: str) -> str:
    """Normalized model key used to match imported rows against existing items.

    Deye inverters: 'SUN-16K-SG01LP1-EU' style code. Batteries / others: alnum tokens
    of the name without the manufacturer prefix (e.g. 'RW-F16' -> 'RWF16').
    """
    n = (name or "").upper()
    m = re.search(r"SUN-\d+(?:\.\d+)?K-[A-Z0-9]+(?:-[A-Z0-9]+)*", n)
    if m:
        return re.sub(r"-EU$", "", m.group()).replace("-", "")
    m = re.search(r"\b(RW-[A-Z]?\d+(?:\.\d+)?|SE-[A-Z]\d+(?:\.\d+)?(?:\s?(?:MAX|PRO|C))?|BOS-[A-Z]\d*|GB-[A-Z]\d*|GE-[A-Z]\d*|AI-W\d+(?:\.\d+)?)", n)
    if m:
        return re.sub(r"[^A-Z0-9]", "", m.group())
    n = re.sub(r"^(DEYE|LONGI|KBE|VATAN|LEADER)\s+", "", n.strip())
    return re.sub(r"[^A-Z0-9]", "", n)[:40]


def _match_item(db: Session, cat: str, name_s: str) -> CatalogItem | None:
    item = db.query(CatalogItem).filter(CatalogItem.name == name_s, CatalogItem.category == cat).first()
    if item:
        return item
    key = model_key(name_s)
    if not key or len(key) < 4:
        return None
    for it in db.query(CatalogItem).filter(CatalogItem.category == cat).all():
        if (it.specs or {}).get("model_key") == key or model_key(it.name) == key:
            return it
    return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("€", "").replace("eur", "").replace(" ", "").replace(",", ".")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def infer_specs_from_name(category: str, name: str) -> dict[str, Any]:
    n = name.upper()
    sp: dict[str, Any] = {}
    if category == "inverter":
        m = re.search(r"SUN-(\d+(?:\.\d+)?)K", n)
        if m:
            sp["ac_power_kw"] = float(m.group(1))
            sp["max_pv_kw"] = round(float(m.group(1)) * 1.3, 1)
        if "LP1" in n or "MONO" in n or "МОНО" in n:
            sp["phases"] = 1
        elif "LP3" in n or "HP3" in n or "ТРИФ" in n or "THREE" in n:
            sp["phases"] = 3
        if "HP3" in n or "HIGH" in n or "ВИСОКО" in n:
            sp["battery_voltage_class"] = "HV"
        elif "LP" in n or "LOW" in n or "НИСКО" in n:
            sp["battery_voltage_class"] = "LV"
        sp["hybrid"] = True
    elif category == "battery":
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*K?WH", n)
        if m:
            sp["kwh"] = float(m.group(1).replace(",", "."))
        if " HV" in n or "HV " in n or "BOS-G" in n or "BOS-A" in n or "BOS-B" in n or "GB-W" in n:
            sp["voltage_class"] = "HV"
        elif " LV" in n or "RW-" in n or "SE-" in n or "SE -" in n or "LOW" in n:
            sp["voltage_class"] = "LV"
    elif category == "panel":
        m = re.search(r"(\d{3})\s*W", n)
        if m:
            sp["wp"] = float(m.group(1))
    elif category == "power_cable":
        m = re.search(r"(\d)\s*[Xх×]\s*(\d+(?:[.,]\d+)?)", n)
        if m:
            sp["cores"] = int(m.group(1))
            sp["cross_section_mm2"] = float(m.group(2).replace(",", "."))
    return sp


def import_catalog_xlsx(db: Session, data: bytes, default_category: str, default_markup_price_is_purchase: bool = True) -> dict[str, Any]:
    wb = load_workbook(io.BytesIO(data), data_only=True)
    created = updated = skipped = 0
    section_category = default_category
    section_specs: dict[str, Any] = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        # detect header row
        col: dict[str, int] = {}
        header_idx = -1
        for i, row in enumerate(rows[:15]):
            cells = [_norm(c) for c in row]
            hits = {}
            for field, aliases in HEADER_ALIASES.items():
                for j, c in enumerate(cells):
                    if c and any(c == a or c.startswith(a) for a in aliases) and field not in hits:
                        hits[field] = j
            if "name" in hits and ("price" in hits or "warranty" in hits):
                col, header_idx = hits, i
                break
        if "name" not in col:
            continue
        for row in rows[header_idx + 1 :]:
            name = row[col["name"]] if col["name"] < len(row) else None
            if not name or not str(name).strip():
                continue
            name_s = str(name).strip()
            price = _to_float(row[col["price"]]) if "price" in col and col["price"] < len(row) else None
            warranty = row[col["warranty"]] if "warranty" in col and col["warranty"] < len(row) else None
            other_empty = price is None and not warranty
            # section header rows (e.g. "Монофазни хибридни инвертори DEYE ...")
            if other_empty and len(name_s) > 12 and not re.search(r"\d", name_s.split()[0]):
                low = name_s.lower()
                if "инвертор" in low or "inverter" in low:
                    section_category = "inverter"
                    section_specs = {}
                    if "моно" in low or "mono" in low:
                        section_specs["phases"] = 1
                    if "триф" in low or "three" in low:
                        section_specs["phases"] = 3
                    if "високо" in low or "high" in low:
                        section_specs["battery_voltage_class"] = "HV"
                    elif "ниско" in low or "low" in low:
                        section_specs["battery_voltage_class"] = "LV"
                elif "батери" in low or "batter" in low:
                    section_category = "battery"
                    section_specs = {"voltage_class": "HV" if " hv" in low or "високо" in low else ("LV" if " lv" in low or "ниско" in low else None)}
                    section_specs = {k: v for k, v in section_specs.items() if v}
                elif "аксесоар" in low or "accesso" in low:
                    section_category, section_specs = "accessory", {}
                elif "зарядн" in low or "charger" in low or "evse" in low:
                    section_category, section_specs = "accessory", {}
                elif "кабел" in low or "cable" in low:
                    section_category, section_specs = "solar_cable", {}
                elif "панел" in low or "module" in low or "модул" in low:
                    section_category, section_specs = "panel", {}
                continue
            cat = section_category
            if "category" in col and col["category"] < len(row) and row[col["category"]]:
                cat = _norm(row[col["category"]])
            specs = dict(section_specs)
            specs.update(infer_specs_from_name(cat, name_s))
            item = _match_item(db, cat, name_s)
            specs.setdefault("model_key", model_key(name_s))
            sku = row[col["sku"]] if "sku" in col and col["sku"] < len(row) else None
            unit = row[col["unit"]] if "unit" in col and col["unit"] < len(row) else None
            manu = row[col["manufacturer"]] if "manufacturer" in col and col["manufacturer"] < len(row) else None
            sell = _to_float(row[col["sell_price"]]) if "sell_price" in col and col["sell_price"] < len(row) else None
            if item is None:
                item = CatalogItem(category=cat, name=name_s, unit=str(unit or ("м" if "cable" in cat else "бр.")))
                db.add(item)
                created += 1
            else:
                updated += 1
            if price is not None:
                item.purchase_price = price
            if sell is not None:
                item.sell_price = sell
            if warranty:
                item.warranty = str(warranty)
            if sku:
                item.sku = str(sku)
            if manu:
                item.manufacturer = str(manu)
            elif "deye" in name_s.lower() or re.match(r"SUN-", name_s, re.I):
                item.manufacturer = item.manufacturer or "Deye"
            merged = dict(item.specs or {})
            for k, v in specs.items():
                merged.setdefault(k, v)
            item.specs = merged
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def export_catalog_xlsx(db: Session) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Catalog"
    ws.append(["category", "sku", "name", "manufacturer", "unit", "purchase_price", "markup_pct", "sell_price", "warranty", "active", "specs"])
    for it in db.query(CatalogItem).order_by(CatalogItem.category, CatalogItem.sort_order, CatalogItem.name).all():
        ws.append([it.category, it.sku, it.name, it.manufacturer, it.unit, it.purchase_price, it.markup_pct, it.sell_price, it.warranty, it.active, str(it.specs or {})])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
