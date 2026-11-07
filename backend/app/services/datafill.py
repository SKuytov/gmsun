"""Fill empty catalog fields with clearly-marked indicative values.

The goal is a *complete* demo dataset: every item gets a purchase price, supplier, lead time, tier, SKU,
manufacturer and warranty, so proposals, quotes and RFQs work out of the box. Every value written here is
tagged in ``specs`` (``price_source = "indicative"``, ``lead_source = "indicative"`` …) and only *empty*
fields are touched — real supplier data entered later (UI, Excel import, supplier sync) is never overwritten.

Price model (net EUR, November 2026 EU wholesale level, rounded):
  * PV modules      — €/Wp by brand (AIKO ABC ≈ 0.165, LONGi ≈ 0.14, TOPCon mainstream ≈ 0.12–0.13)
  * inverters       — a + b·kW curves per brand / topology, calibrated on priced catalogue items and public
                      distributor prices (Deye SUN‑12K‑SG04LP3 ≈ 1 450–1 650 €, SUN‑50K HV ≈ 3 600–3 800 €,
                      Sungrow SH10RT ≈ 950–1 250 €, SG110CX ≈ 4 200–4 550 €, Huawei 215KTL ≈ 4 500–8 000 €,
                      Solis S5‑GR3P10K ≈ 830–1 075 €)
  * batteries       — €/kWh by segment (Deye LV ≈ 105–115, Dyness DL5.0C ≈ 115, HV modules ≈ 140–160,
                      Sungrow HV ≈ 230–265, C&I cabinets ≈ 155–190, MWh containers ≈ 150)
  * accessories, monitoring, services — fixed typical prices
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem
from . import procurement
from .settings import get_setting, set_setting

INDICATIVE_NOTE = "Ориентировъчна стойност — актуализирайте с реалната оферта на доставчика."

# ------------------------------------------------------------------------------------------------- helpers
_KWH_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*k\s*wh", re.I)
_KW_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*k\s*w(?![h])", re.I)
_WP_RE = re.compile(r"(\d{3,4})\s*W(?:p)?\b", re.I)
_MODEL_RE = re.compile(r"\b([A-Z]{1,6}[A-Z0-9]*(?:[-/.][A-Z0-9]+){1,6})\b")

BRANDS = [
    "Deye", "Huawei", "Sungrow", "Solis", "GoodWe", "Luxpower", "LONGi Solar", "AIKO", "Jinko Solar", "JA Solar",
    "Tongwei Solar", "Ulica Solar", "Risen Energy", "DAH Solar", "Suntech", "Dyness", "KSTAR", "K-Star", "Dunext",
    "FOX", "CATL", "Sunwoda", "Atess", "Sofar", "Eastron", "Aerocompact", "Victron", "Pylontech", "BYD", "Fronius",
    "SMA", "Growatt", "Felicity", "Canadian Solar", "Trina", "EASUN", "Must", "Leader", "KBE", "Vatan", "Stäubli",
    "Hager", "Schneider", "ABB", "Eaton", "Phoenix Contact", "Weidmüller", "OBO", "Dehn", "Citel", "Noark", "Chint",
]
_BRAND_ALIASES = {"kstar": "KSTAR", "k-star": "KSTAR", "luxpowertek": "Luxpower", "luxpower": "Luxpower", "longi": "LONGi Solar",
                  "jinko": "Jinko Solar", "tongwei": "Tongwei Solar", "ulica": "Ulica Solar", "risen": "Risen Energy",
                  "dah": "DAH Solar", "fox": "FOX", "catl": "CATL", "dunext": "Dunext", "sunwoda": "Sunwoda", "atess": "Atess"}


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_kwh(name: str) -> float | None:
    m = _KWH_RE.search(name or "")
    return _num(m.group(1)) if m else None


def parse_kw(name: str) -> float | None:
    m = _KW_RE.search(name or "")
    return _num(m.group(1)) if m else None


def guess_manufacturer(name: str) -> str | None:
    low = (name or "").lower()
    hits: list[tuple[int, str]] = []
    for key, brand in _BRAND_ALIASES.items():
        m = re.search(rf"\b{re.escape(key)}\b", low)
        if m:
            hits.append((m.start(), brand))
    for b in BRANDS:
        pos = low.find(b.lower())
        if pos >= 0:
            hits.append((pos, b))
    if "powerstack" in low:
        hits.append((0, "Sungrow"))
    return min(hits)[1] if hits else None


def guess_model_code(name: str) -> str | None:
    cands = [m for m in _MODEL_RE.findall(name or "")
             if any(ch.isdigit() for ch in m) and len(m) >= 6 and len(re.split(r"[-/.]", m)[0]) >= 2]
    return cands[0] if cands else None


def _round_price(v: float) -> float:
    if v >= 10000:
        return float(round(v / 100) * 100)
    if v >= 1000:
        return float(round(v / 10) * 10)
    if v >= 100:
        return float(round(v))
    return float(round(v, 2))


# ------------------------------------------------------------------------------------------------- price model
def _panel_price(it: CatalogItem, sp: dict) -> float | None:
    wp = sp.get("wp") or (float(m.group(1)) if (m := _WP_RE.search(it.name or "")) else None)
    if not wp:
        return None
    man = (it.manufacturer or "").lower()
    name = (it.name or "").lower()
    rate = 0.13
    if "aiko" in man:
        rate = 0.165
    elif "longi" in man:
        rate = 0.14 if ("hvd" in name or "x10" in name) else 0.135 if "hgd" in name else 0.125
    elif "jinko" in man or "ja solar" in man:
        rate = 0.15
    elif "tongwei" in man or "ulica" in man or "risen" in man or "suntech" in man:
        rate = 0.12
    elif "dah" in man:
        rate = 0.125
    if "full-black" in name or "full black" in name or "fullblack" in name:
        rate += 0.01
    return wp * rate


def _inverter_price(it: CatalogItem, sp: dict) -> float | None:
    kw = sp.get("ac_power_kw") or parse_kw(it.name)
    man = (it.manufacturer or "").lower()
    name = (it.name or "").upper()
    hybrid = bool(sp.get("hybrid")) or any(k in name for k in ("LP1", "LP3", "HP3", "SH", "EH", "SNA", "TRIP", "ХИБРИД", "HYBRID"))
    phases = sp.get("phases") or (1 if ("LP1" in name or "1P" in name or "RS" in name or "L1" in name or "МОНОФАЗ" in name) else 3)
    hv = "HP3" in name or (sp.get("battery_voltage_class") or "").upper() == "HV"
    if not kw:
        if "215" in name or "255" in name:
            kw = 255 if "255" in name else 215
        else:
            return None
    if "deye" in man:
        if hv or kw >= 25:
            return 870 + 57 * kw            # SUN‑xK‑SG01HP3 / SG02HP3 (HV commercial)
        if phases == 1:
            return 450 + 85 * kw            # SUN‑xK‑SG0xLP1 (1‑ph LV hybrid)
        return 550 + 70 * kw                # SUN‑xK‑SG05LP3 / SG04LP3 (3‑ph LV hybrid)
    if "sungrow" in man:
        if "HX" in name:
            return 2500 + 22 * kw           # SG250HX / SG350HX utility string
        if "CX" in name:
            return 1200 + 32 * kw           # SG33–150CX commercial
        if hybrid or "SH" in name:
            return 300 + 90 * kw            # SH‑RT / SH‑RS / SH‑T residential hybrid
        return 250 + 60 * kw                # SG‑RS / SG‑RT grid
    if "huawei" in man:
        if kw >= 100:
            return 1500 + 25 * kw           # SUN2000‑185/215/330KTL
        if phases == 1 and kw <= 6:
            return 450 + 90 * kw            # SUN2000‑xKTL‑L1
        return 400 + 70 * kw
    if "solis" in man:
        if kw >= 100:
            return 1200 + 32 * kw
        if hybrid:
            return 350 + 120 * kw if phases == 1 else 400 + 110 * kw
        return 150 + 70 * kw if phases == 1 else 200 + 60 * kw
    if "luxpower" in man:
        if "TRIP" in name:
            return 1800.0
        if "SNA2" in name or "LT" in name:
            return 1500.0
        return 350 + 110 * kw
    if "goodwe" in man:
        return 400 + 100 * kw if hybrid else 250 + 70 * kw
    return 400 + 90 * kw if hybrid else 250 + 65 * kw


def _battery_kwh(it: CatalogItem, sp: dict) -> float | None:
    if sp.get("kwh"):
        return float(sp["kwh"])
    kwh = parse_kwh(it.name)
    if kwh:
        return kwh
    name = re.sub(r"\s*-\s*", "-", (it.name or "").upper())  # "SE - F12" → "SE-F12"
    known = {"ST255CS": 257.0, "ST510CS": 510.0, "DH200F": 215.0, "DH200Y": 232.0, "LUNA2000-215": 215.0, "LUNA2000-241": 241.0,
             "GE-F60": 60.0, "GE-F120": 120.0, "RW-F16": 16.0, "RW-F10.2": 10.24, "RW-F10.6": 10.6, "RW-M6.1": 6.14,
             "SE-G5.1": 5.12, "SE-F5": 5.12, "SE-F12": 12.0, "SE-F16": 16.0, "BOS-G": 5.12, "BOS-A": 7.68, "BOS-B": 16.0,
             "DL5.0C": 5.12, "POWERBRICK MAX": 16.0, "POWERBRICK PLUS": 16.07, "PGEM MAX": 16.08, "PSHIELD MAX": 16.0,
             "LYNX HOME U": 5.4, "POTISBANK-L5.0": 5.12, "ATRIX": 5.12, "EVO 10-10": 10.0, "ICON 100KW/215KWH": 215.0,
             "BC107DE2": 107.0, "GB-W-PACK": 12.0, "ENERC": 4073.0, "ENERX": 5644.0, "ENERONE+": 407.0, "GM215": 215.0,
             "POWERMOUNT-P96": 96.0, "POWERMOUNT-P72": 72.0, "POWERHILL-P12": 12.0, "STACK 100": 15.0, "SBH": 5.0, "SBR": 3.2,
             "HI-MO ONE": 10.0, "ONENEXUS H2": 10.0, "ONENEXUS M5": 5.0, "ONENEXUS M20": 20.0, "G5.1": 5.12}
    for k, v in known.items():
        if k in name:
            return v
    return None


def _battery_price(it: CatalogItem, sp: dict) -> float | None:
    kwh = _battery_kwh(it, sp)
    if not kwh:
        return None
    man = (it.manufacturer or "").lower()
    name = (it.name or "").upper()
    hv = (sp.get("voltage_class") or "").upper() == "HV" or any(k in name for k in ("BOS-", "GB-W", "HV", "SBR", "SBH", "LUNA", "ONENEXUS H"))
    if kwh >= 1000:
        rate = 150.0                                  # MWh containers (CATL EnerC/EnerX …)
    elif kwh >= 50:
        rate = 190.0 if ("liquid" in name.lower() or "течно" in (it.name or "").lower()) else 175.0  # C&I cabinets
    elif "sungrow" in man:
        rate = 265.0 if "SBR" in name else 230.0
    elif "huawei" in man or "goodwe" in man:
        rate = 225.0
    elif "longi" in man:
        rate = 200.0 if hv else 170.0
    elif hv:
        rate = 160.0 if kwh < 8 else 150.0           # Deye BOS‑G Pro / BOS‑A / GB‑W / BOS‑B
    elif "deye" in man:
        rate = 115.0 if kwh < 8 else 105.0           # Deye LV: RW‑F16 ≈ 1 630 € real price → ≈ 102 €/kWh
    elif "dyness" in man or "dah" in man or "sunwoda" in man or "luxpower" in man:
        rate = 118.0
    else:
        rate = 140.0
    return kwh * rate


def _fixed_price(it: CatalogItem) -> float | None:
    n = (it.name or "").lower()
    cat = it.category
    table: list[tuple[str, float]] = [
        ("lsw-3", 35), ("ls4g-3", 60), ("smart-plug", 45), ("smart-tx01", 70), ("smart-ct01", 40), ("sun-xl02", 45),
        ("sdm630mct", 110), ("sdm630", 95), ("sdm230", 60), ("evse22k", 650), ("wallbox", 650), ("smartguard", 900),
        ("emma", 450), ("sec1000", 650), ("optimizer 600", 55), ("optimizer 450", 45), ("idc 30e", 3500), ("idc 180e", 15000),
        ("cda24d", 3500), ("evd-80", 18000), ("bms за до 16", 650), ("bms за до 12", 550), ("bms", 550),
        ("rack11", 240), ("rack14", 265), ("control box", 450), ("pdu", 300), ("gb-w-base", 120), ("accessory pack", 80),
        ("транспорт", 120), ("проектиране", 650), ("мониторинг", 120),
    ]
    for key, price in table:
        if key in n:
            return float(price)
    if cat == "mounting":
        return 28.0                                   # generic per‑module mounting kit (green‑energy.bg systems)
    if cat == "other":
        kw = parse_kw(it.name)
        if not kw and (m := re.search(r"(\d{1,3})K\b", it.name or "")):
            kw = float(m.group(1))
        if kw:
            return kw * 600.0                         # equipment bundles ≈ 0.60 €/Wp
    return None


def estimate_price(it: CatalogItem) -> float | None:
    sp = it.specs or {}
    if it.category == "panel":
        return _panel_price(it, sp)
    if it.category == "inverter":
        return _inverter_price(it, sp)
    if it.category in ("battery", "battery_accessory"):
        fixed = _fixed_price(it)
        if fixed is not None and it.category == "battery_accessory" and not parse_kwh(it.name):
            return fixed
        return _battery_price(it, sp) or fixed
    return _fixed_price(it)


# ------------------------------------------------------------------------------------------------- lead time / warranty
def estimate_lead_days(it: CatalogItem, suppliers_cfg: dict) -> int:
    sp = it.specs or {}
    status = (sp.get("stock_status") or "").lower()
    sup = procurement.supplier_of(it)
    if status == "backorder":
        return int(suppliers_cfg.get("backorder_lead_time_days") or 21)
    if status == "outofstock":
        return 30
    kwh = _battery_kwh(it, sp) if it.category in ("battery", "battery_accessory") else None
    kw = (sp.get("ac_power_kw") or parse_kw(it.name)) if it.category == "inverter" else None
    if (kwh and kwh >= 50) or (kw and kw >= 100):
        return 60                                      # C&I cabinets / utility inverters are made to order
    if kw and kw >= 25:
        return 20
    for s in suppliers_cfg.get("list") or []:
        if s.get("name") == sup and s.get("lead_time_days") is not None:
            return int(s["lead_time_days"])
    if sup == "Aerocompact":
        return 15
    if (it.manufacturer or "").lower() == "deye" and it.category in ("inverter", "battery", "battery_accessory", "accessory", "monitoring"):
        return 10
    return int(suppliers_cfg.get("default_lead_time_days") or 7)


def estimate_warranty(it: CatalogItem) -> str | None:
    man = (it.manufacturer or "").lower()
    cat = it.category
    sp = it.specs or {}
    if cat == "panel":
        return "15 г. продуктова / 30 г. линейна мощност"
    if cat == "inverter":
        kw = sp.get("ac_power_kw") or parse_kw(it.name) or 0
        if kw >= 25:
            return "5 години (производител)"
        return "10 години (производител)" if any(b in man for b in ("deye", "huawei", "sungrow", "goodwe", "luxpower", "solis")) else "5 години (производител)"
    if cat in ("battery", "battery_accessory"):
        return "10 години / 6 000 цикъла" if (_battery_kwh(it, sp) or 0) < 50 else "5 години (производител), 10 г. по договор"
    if cat == "mounting":
        return "25 години (алуминиеви компоненти)" if "aerocompact" in (procurement.supplier_of(it) or "").lower() else "10 години"
    if cat in ("transport", "service", "labor"):
        return None
    return "2 години"


def default_supplier(it: CatalogItem) -> str:
    sup = procurement.supplier_of(it)
    if sup and sup not in ("Неразпределени",):
        return sup
    if (it.manufacturer or "").lower() == "deye" or it.category in ("inverter", "battery", "battery_accessory", "panel", "monitoring"):
        return "Deye дистрибутор (BG)"
    if it.category in ("transport", "service"):
        return "GM SUN SYSTEM SOLAR"
    return "Електро склад (местен)"


def make_sku(it: CatalogItem) -> str:
    sp = it.specs or {}
    if sp.get("supplier_product_id") and (it.supplier or sp.get("supplier")) == "green-energy.bg":
        return f"GE-{sp['supplier_product_id']}"
    code = guess_model_code(it.name)
    if code:
        return code
    prefix = {"panel": "PV", "inverter": "INV", "battery": "BAT", "battery_accessory": "BAC", "mounting": "MNT", "ac_protection": "ACP",
              "dc_protection": "DCP", "solar_cable": "CBL", "power_cable": "CBL", "grounding": "GND", "cable_management": "CMG",
              "switchboard": "SWB", "accessory": "ACC", "monitoring": "MON", "transport": "TRN", "service": "SRV", "other": "OTH"}.get(it.category, "ITM")
    return f"GMS-{prefix}-{it.id:04d}"


# ------------------------------------------------------------------------------------------------- main entry
def fill_missing(db: Session, *, prices: bool = True, lead: bool = True, tiers: bool = True, meta: bool = True) -> dict[str, Any]:
    suppliers_cfg = get_setting(db, "suppliers")
    items = db.query(CatalogItem).all()
    stats = {"price": 0, "lead_time": 0, "tier": 0, "supplier": 0, "sku": 0, "manufacturer": 0, "warranty": 0, "unpriced_left": []}

    # 1) manufacturer, supplier, sku, warranty
    for it in items:
        sp = dict(it.specs or {})
        changed = False
        if meta and not it.manufacturer:
            g = guess_manufacturer(it.name)
            it.manufacturer = g or "Generic"
            stats["manufacturer"] += 1
            changed = True
        if meta and not it.supplier:
            it.supplier = default_supplier(it)
            stats["supplier"] += 1
            changed = True
        if meta and not it.sku:
            it.sku = make_sku(it)
            stats["sku"] += 1
            changed = True
        if meta and not it.supplier_sku and sp.get("supplier_product_id"):
            it.supplier_sku = str(sp["supplier_product_id"])
        if meta and not it.warranty:
            w = estimate_warranty(it)
            if w:
                it.warranty = w
                stats["warranty"] += 1
                changed = True
        if meta and it.category == "inverter" and not sp.get("ac_power_kw"):
            kw = parse_kw(it.name) or (255.0 if "255" in (it.name or "") else None)
            if kw:
                sp["ac_power_kw"] = kw
                sp.setdefault("phases", 1 if re.search(r"1P|LP1|L1|монофаз", it.name or "", re.I) else 3)
                sp["spec_source"] = sp.get("spec_source") or "name-derived"
                changed = True
        if meta and it.category in ("battery", "battery_accessory") and not sp.get("kwh"):
            kwh = _battery_kwh(it, sp) if it.category == "battery" else parse_kwh(it.name)
            if kwh:
                sp["kwh"] = kwh
                sp["spec_source"] = sp.get("spec_source") or "name-derived"
                changed = True
        if meta and not sp.get("stock_status") and it.category not in ("transport", "service"):
            sp["stock_status"] = "instock"
            changed = True
        if changed:
            it.specs = sp

    # 2) prices
    if prices:
        for it in items:
            if it.purchase_price and it.purchase_price > 0:
                continue
            est = estimate_price(it)
            if est is None or est <= 0:
                stats["unpriced_left"].append(f"{it.id}: {it.name}")
                continue
            sp = dict(it.specs or {})
            it.purchase_price = _round_price(est)
            sp["price_source"] = "indicative"
            sp["price_note"] = INDICATIVE_NOTE
            sp["price_estimated_at"] = datetime.now(timezone.utc).date().isoformat()
            it.specs = sp
            stats["price"] += 1
    db.flush()

    # 3) lead times
    if lead:
        for it in items:
            if it.lead_time_days is not None:
                continue
            it.lead_time_days = estimate_lead_days(it, suppliers_cfg)
            sp = dict(it.specs or {})
            sp["lead_source"] = "indicative"
            it.specs = sp
            stats["lead_time"] += 1
    db.flush()

    # 4) tiers — freeze the automatic classification so it is visible/editable in Excel
    if tiers:
        active = [i for i in items if i.active]
        cls = procurement.classify(active, get_setting(db, "procurement"))
        for it in items:
            if it.tier:
                continue
            c = cls.get(it.id)
            it.tier = "standard" if it.category in ("transport", "service", "labor", "other", "mounting") else ((c or {}).get("tier") or "standard")
            stats["tier"] += 1
    db.commit()
    set_setting(db, "datafill", {"done": True, "at": datetime.now(timezone.utc).isoformat(), "stats": {k: v for k, v in stats.items() if k != "unpriced_left"}})
    return stats
