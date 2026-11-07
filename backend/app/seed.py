"""Initial data: admin user, roof types, mounting rules, labor matrix and a
catalog seeded from the supplier price list (Deye hybrid inverters and
batteries), the LONGi Hi-MO X10 module and the real quote (KSS) items.

Prices from the supplier list were blank in the copy we received, so only the
items that appear with prices in the KSS quote carry values; everything else
is 0 and flagged in the UI until the admin enters prices.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .auth import hash_password
from .config import get_settings
from .models import CatalogItem, LaborOption, MountingRule, RoofTypeConfig, User


def _inv(name: str, kw: float, phases: int, vclass: str, price: float = 0.0, **extra) -> dict:
    specs = {
        "ac_power_kw": kw,
        "phases": phases,
        "battery_voltage_class": vclass,
        "hybrid": True,
        "max_pv_kw": round(kw * 1.3, 1),
        "mppt_count": 2 if kw <= 16 else (3 if kw <= 50 else 4),
        "strings_per_mppt": 1 if kw <= 8 else 2,
        "max_dc_voltage": 500 if (vclass == "LV" and phases == 1) else (800 if vclass == "LV" else 1000),
        "mppt_v_min": 125 if vclass == "LV" and phases == 1 else (160 if vclass == "LV" else 180),
        "battery_v_nominal": 48 if vclass == "LV" else None,
        "max_battery_parallel": 16 if vclass == "LV" else None,
        "specs_verified": False,
    }
    specs.update(extra)
    return {"category": "inverter", "name": name, "manufacturer": "Deye", "warranty": "10 години", "purchase_price": price, "specs": specs}


def _bat(name: str, kwh: float, vclass: str, price: float = 0.0, **extra) -> dict:
    specs = {"kwh": kwh, "voltage_class": vclass, "nominal_v": 51.2 if vclass == "LV" else None, "max_parallel": 16 if vclass == "LV" else 12}
    specs.update(extra)
    return {"category": "battery", "name": name, "manufacturer": "Deye", "warranty": "10 години", "purchase_price": price, "specs": specs}


CATALOG: list[dict] = [
    # ----- panels (green-energy.bg supplies LONGi) -----
    {
        "category": "panel", "name": "LONGi Hi-MO X10 LR8-66HVD-650M 650 Wp", "manufacturer": "LONGi Solar", "sku": "LR8-66HVD-650M",
        "purchase_price": 91.0, "warranty": "15 г. продуктова / 30 г. линейна",
        "specs": {"wp": 650, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 32.5, "voc": 49.72, "isc": 16.54, "vmp": 40.98, "imp": 15.86, "efficiency": 24.1, "max_system_v": 1500, "temp_coeff_pmax": -0.26, "cell": "HPBC 2.0", "datasheet": "https://green-energy.bg/"},
    },
    {
        "category": "panel", "name": "LONGi Hi-MO X10 LR8-66HVD-660M 660 Wp", "manufacturer": "LONGi Solar", "sku": "LR8-66HVD-660M",
        "purchase_price": 0.0, "warranty": "15 г. продуктова / 30 г. линейна",
        "specs": {"wp": 660, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 32.5, "voc": 50.3, "isc": 16.6, "vmp": 41.5, "imp": 15.9, "efficiency": 24.4, "max_system_v": 1500, "specs_verified": False},
    },
    {
        "category": "panel", "name": "LONGi Hi-MO 9 LR7-72HYD-640M 640 Wp (bifacial)", "manufacturer": "LONGi Solar", "sku": "LR7-72HYD-640M",
        "purchase_price": 0.0, "warranty": "15 г. продуктова / 30 г. линейна",
        "specs": {"wp": 640, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 33.5, "voc": 49.0, "isc": 16.6, "vmp": 40.6, "imp": 15.8, "efficiency": 23.7, "max_system_v": 1500, "specs_verified": False},
    },
    # ----- single-phase hybrid inverters (LV) -----
    _inv("Deye SUN-5K-SG03LP1-EU", 5, 1, "LV"),
    _inv("Deye SUN-6K-SG05LP1-AM2-PLUS", 6, 1, "LV"),
    _inv("Deye SUN-8K-SG05LP1-EU-AM2-P/PLUS", 8, 1, "LV"),
    _inv("Deye SUN-10K-SG02LP1-EU", 10, 1, "LV"),
    _inv("Deye SUN-12K-SG02LP1-EU", 12, 1, "LV"),
    _inv("Deye SUN-14K-SG01LP1-EU", 14, 1, "LV"),
    _inv("Deye SUN-16K-SG01LP1-EU", 16, 1, "LV", price=1550.0),
    # ----- three-phase hybrid inverters LV -----
    _inv("Deye SUN-5K-SG05LP3-EU (low voltage)", 5, 3, "LV"),
    _inv("Deye SUN-6K-SG04LP3-EU (low voltage)", 6, 3, "LV"),
    _inv("Deye SUN-8K-SG04LP3-EU (low voltage)", 8, 3, "LV"),
    _inv("Deye SUN-10K-SG05LP3-EU (low voltage)", 10, 3, "LV"),
    _inv("Deye SUN-12K-SG05LP3-EU (low voltage)", 12, 3, "LV"),
    _inv("Deye SUN-14K-SG05LP3-EU (low voltage)", 14, 3, "LV"),
    _inv("Deye SUN-15K-SG05LP3-EU (low voltage)", 15, 3, "LV"),
    _inv("Deye SUN-16K-SG05LP3-EU (low voltage)", 16, 3, "LV"),
    _inv("Deye SUN-18K-SG05LP3-EU (low voltage)", 18, 3, "LV"),
    _inv("Deye SUN-20K-SG05LP3-EU (low voltage)", 20, 3, "LV"),
    # ----- three-phase hybrid inverters HV -----
    _inv("Deye SUN-15K-SG01HP3-EU-AM2 (high voltage)", 15, 3, "HV", battery_v_min=160, battery_v_max=700),
    _inv("Deye SUN-20K-SG01HP3-EU-AM2 (high voltage)", 20, 3, "HV", battery_v_min=160, battery_v_max=700),
    _inv("Deye SUN-25K-SG01HP3-EU-AM2 (high voltage)", 25, 3, "HV", battery_v_min=160, battery_v_max=700),
    _inv("Deye SUN-30K-SG02HP3-EU (high voltage)", 30, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-35K-SG01HP3-EU-BM3 (high voltage)", 35, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-40K-SG01HP3-EU-BM4 (high voltage)", 40, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-50K-SG01HP3-EU-BM4 (high voltage)", 50, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-60K-SG02HP3-EU-EM6 (high voltage)", 60, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-70K-SG02HP3-EU-EM6 (high voltage)", 70, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-80K-SG02HP3-EU-EM6 (high voltage)", 80, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-100K-SG02HP3-EU-GM8", 100, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-100K-SG02HP3-EU-GM10", 100, 3, "HV", battery_v_min=160, battery_v_max=800),
    _inv("Deye SUN-125K-SG02HP3-EU-GM10", 125, 3, "HV", battery_v_min=160, battery_v_max=800),
    # ----- batteries HV -----
    _bat("Deye BOS-G 5.12 kWh HV battery module", 5.12, "HV", price=666.67, nominal_v=51.2, min_modules=4, max_parallel=12,
         accessories=[{"name": "BMS за до 12 батерии", "qty": 1}, {"name": "Frame (Rack) за до 12 батерии + 1 BMS", "qty": 1}]),
    _bat("Deye BOS-G Pro 5.12 kWh HV battery module", 5.12, "HV", nominal_v=51.2, min_modules=4, max_parallel=16),
    _bat("Deye BOS-A 7.68 kWh HV battery", 7.68, "HV", nominal_v=76.8, min_modules=3, max_parallel=14),
    _bat("Deye GB-W-Pack12-2-A3 12 kWh HV battery pack", 12.0, "HV", nominal_v=120, max_parallel=6),
    _bat("Deye BOS-B-PACK16-A3 16 kWh HV battery module", 16.0, "HV", nominal_v=160, max_parallel=6),
    {"category": "battery_accessory", "name": "Deye BMS за до 12 батерии (BOS-G)", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 589.74, "specs": {"for": "BOS-G"}},
    {"category": "battery_accessory", "name": "Deye Frame (Rack) за до 12 батерии + 1 BMS", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 282.05, "specs": {"for": "BOS-G"}},
    {"category": "battery_accessory", "name": "Deye Frame (Rack) за до 8 батерии + 1 BMS", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 256.41, "specs": {"for": "BOS-G"}},
    {"category": "battery_accessory", "name": "Deye BMS за до 16 батерии (BOS-G Pro)", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-G Pro"}},
    {"category": "battery_accessory", "name": "Deye High Voltage Control Box for BOS-A", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-A"}},
    {"category": "battery_accessory", "name": "Deye BOS-A-Rack11", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-A"}},
    {"category": "battery_accessory", "name": "Deye BOS-A-Rack14", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-A"}},
    {"category": "battery_accessory", "name": "Deye GB-W-PDU-2", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "GB-W"}},
    {"category": "battery_accessory", "name": "Deye GB-W-Base", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "GB-W"}},
    {"category": "battery_accessory", "name": "Deye BMS BOS-B-PDU-2-A", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-B"}},
    {"category": "battery_accessory", "name": "Deye Accessory pack BOS-B-PACK16-A3", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": 0.0, "specs": {"for": "BOS-B"}},
    # ----- batteries LV -----
    _bat("Deye SE-G5.1 Pro-B 5.12 kWh LV", 5.12, "LV"),
    _bat("Deye SE-F5 Pro C 5.12 kWh LV", 5.12, "LV"),
    _bat("Deye RW-F10.2 10.2 kWh LV IP65", 10.2, "LV"),
    _bat("Deye RW-F10.6 10.6 kWh LV IP20", 10.6, "LV"),
    _bat("Deye SE-F12 C 12 kWh LV IP21", 12.0, "LV"),
    _bat("Deye SE-F12 MAX 12 kWh LV IP65 (heating)", 12.0, "LV"),
    _bat("Deye RW-F16 16 kWh LV", 16.0, "LV", price=1480.0),
    _bat("Deye SE-F16 C 16 kWh LV IP21", 16.0, "LV"),
    _bat("Deye SE-F16 MAX 16 kWh LV IP65", 16.0, "LV"),
    _bat("Deye GE-F60 60 kWh (без инвертор)", 60.0, "HV", max_parallel=10),
    # ----- accessories -----
    {"category": "accessory", "name": "Deye LSW-3 Wi-Fi dongle", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "Deye LS4G-3 4G dongle", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "Оптимизатор Deye SUN-XL02-A", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "SDM630-Modbus трифазен смарт електромер", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 3}},
    {"category": "accessory", "name": "SDM630MCT трифазен електромер за токов трансформатор", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 3}},
    {"category": "accessory", "name": "SDM230-Modbus монофазен смарт електромер", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 1}},
    {"category": "accessory", "name": "Зарядна станция Deye SUN-EVSE22K01-EU-AC", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    # ----- switchboards -----
    {"category": "switchboard", "name": "Монофазно електрическо табло (AC/DC защити, 400×300×200)", "purchase_price": 90.0, "specs": {"phases": 1}},
    {"category": "switchboard", "name": "Трифазно електрическо табло (AC/DC защити, 600×600×200)", "purchase_price": 110.0, "specs": {"phases": 3}},
    # ----- solar cables -----
    {"category": "solar_cable", "name": "KBE 6 mm² H1Z2Z2-K", "manufacturer": "KBE", "unit": "м", "purchase_price": 1.2, "specs": {"cross_section_mm2": 6}},
    {"category": "solar_cable", "name": "Vatan 6 mm² H1Z2Z2-K", "manufacturer": "Vatan", "unit": "м", "purchase_price": 0.88, "specs": {"cross_section_mm2": 6}},
    {"category": "solar_cable", "name": "Leader 6 mm² H1Z2Z2-K", "manufacturer": "Leader", "unit": "м", "purchase_price": 0.78, "specs": {"cross_section_mm2": 6}},
    # ----- power cables -----
    {"category": "power_cable", "name": "Захранващ кабел 3×6 mm²", "unit": "м", "purchase_price": 1.9, "specs": {"cores": 3, "cross_section_mm2": 6, "phases": 1}},
    {"category": "power_cable", "name": "Захранващ кабел 4×6 mm²", "unit": "м", "purchase_price": 2.0, "specs": {"cores": 4, "cross_section_mm2": 6, "phases": 3}},
    {"category": "power_cable", "name": "Усукан проводник 4×16 mm²", "unit": "м", "purchase_price": 2.4, "specs": {"cores": 4, "cross_section_mm2": 16, "phases": 3}},
    {"category": "power_cable", "name": "Захранващ кабел 5×10 mm²", "unit": "м", "purchase_price": 4.2, "specs": {"cores": 5, "cross_section_mm2": 10, "phases": 3}},
    {"category": "power_cable", "name": "Захранващ кабел 5×16 mm²", "unit": "м", "purchase_price": 6.5, "specs": {"cores": 5, "cross_section_mm2": 16, "phases": 3}},
    # ----- electrical small parts -----
    {"category": "electrical", "name": "Конектор MC4 комплект", "unit": "бр.", "purchase_price": 1.2},
    {"category": "electrical", "name": "Гофрирана тръба ф32 + крепежи", "unit": "м", "purchase_price": 1.22},
    {"category": "electrical", "name": "Заземителен проводник 6 mm² жълто-зелен", "unit": "м", "purchase_price": 0.9},
    # ----- mounting (Aerocompact CompactPITCH, quote 64845) -----
    {"category": "mounting", "sku": "705100-3550", "name": "X50-3550 монтажна шина 3550 mm", "manufacturer": "Aerocompact", "purchase_price": 24.92, "specs": {"length_m": 3.55}},
    {"category": "mounting", "sku": "705202", "name": "XPCN съединител за шина X40/X50", "manufacturer": "Aerocompact", "purchase_price": 1.85},
    {"category": "mounting", "sku": "705310", "name": "XM-F кука за керемиден покрив (регулируема)", "manufacturer": "Aerocompact", "purchase_price": 12.29},
    {"category": "mounting", "sku": "705309", "name": "XM-FSP опорна плоча за кука", "manufacturer": "Aerocompact", "purchase_price": 1.76},
    {"category": "mounting", "sku": "705308-8004", "name": "XM-FCMR покривна ламарина среден размер, червена", "manufacturer": "Aerocompact", "purchase_price": 8.02},
    {"category": "mounting", "sku": "701544", "name": "SDS-W 8×100 самонарезен винт за дърво", "manufacturer": "Aerocompact", "purchase_price": 0.26},
    {"category": "mounting", "sku": "701590", "name": "GSC 10×30 фиксиращ винт", "manufacturer": "Aerocompact", "purchase_price": 0.23},
    {"category": "mounting", "sku": "707011", "name": "CLM10 средна скоба Click 30-46", "manufacturer": "Aerocompact", "purchase_price": 1.54},
    {"category": "mounting", "sku": "707003", "name": "CLE10 крайна скоба Click 30-46", "manufacturer": "Aerocompact", "purchase_price": 1.54},
    {"category": "mounting", "sku": "705205", "name": "XCL50 капачка лява за шина X50", "manufacturer": "Aerocompact", "purchase_price": 0.46},
    {"category": "mounting", "sku": "705206", "name": "XCR50 капачка дясна за шина X50", "manufacturer": "Aerocompact", "purchase_price": 0.46},
    {"category": "mounting", "sku": "701902", "name": "CLP-M кабелна клипса за модул", "manufacturer": "Aerocompact", "purchase_price": 0.26},
    {"category": "mounting", "sku": "706457", "name": "CLP-R кабелна клипса за шина", "manufacturer": "Aerocompact", "purchase_price": 0.16},
    {"category": "mounting", "name": "Трапецовиден държач за LT ламарина (къса шина) с EPDM", "purchase_price": 4.5},
    {"category": "mounting", "name": "Самопробивен винт 6.3×25 с EPDM шайба (ламарина)", "purchase_price": 0.12},
    {"category": "mounting", "name": "Държач за сандвич панел (изолационен винт M10)", "purchase_price": 5.8},
    {"category": "mounting", "name": "Триъгълна конструкция за плосък покрив 15° (комплект за 1 модул)", "purchase_price": 38.0},
    {"category": "mounting", "name": "Баластен блок 30 кг", "purchase_price": 6.0},
    {"category": "mounting", "name": "Защитна подложка за хидроизолация", "purchase_price": 1.5},
    {"category": "mounting", "name": "Наземна конструкция — стоманена поцинкована (на модул)", "purchase_price": 55.0},
    {"category": "mounting", "name": "Бетонен фундамент / забит профил (на опора)", "purchase_price": 28.0},
    # ----- services / transport -----
    {"category": "transport", "name": "Транспорт до обекта", "unit": "бр.", "purchase_price": 0.0, "sell_price": 120.0},
    {"category": "service", "name": "Проектиране и документация за присъединяване", "unit": "бр.", "purchase_price": 0.0, "sell_price": 350.0},
    {"category": "service", "name": "Монтаж и настройка на мониторинг (Wi-Fi/4G)", "unit": "бр.", "purchase_price": 0.0, "sell_price": 60.0},
]

ROOF_TYPES: list[dict] = [
    {"code": "tile", "label_bg": "Покрив с керемиди", "label_en": "Tile roof", "pricing_mode": "detailed", "lump_price_per_module": 124.0, "rails_per_module": 2, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 25.0, "sort_order": 1,
     "notes": "Куки за керемиди върху ребрата (стъпка ~0.7 m), шини X50, скоби Click."},
    {"code": "flat_concrete", "label_bg": "Плосък бетонен покрив", "label_en": "Flat concrete roof", "pricing_mode": "detailed", "lump_price_per_module": 95.0, "rails_per_module": 2, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 15.0, "sort_order": 2,
     "notes": "Триъгълници 15° с баласт, без пробиване на хидроизолацията."},
    {"code": "lt_sheet", "label_bg": "LT ламарина", "label_en": "Trapezoidal metal sheet", "pricing_mode": "detailed", "lump_price_per_module": 70.0, "rails_per_module": 2, "fixation_spacing_m": 1.0, "waste_pct": 8.0, "default_tilt_deg": 10.0, "sort_order": 3,
     "notes": "Къси трапецовидни държачи с EPDM върху гребена на ламарината."},
    {"code": "sandwich", "label_bg": "Сандвич панел", "label_en": "Sandwich panel roof", "pricing_mode": "detailed", "lump_price_per_module": 78.0, "rails_per_module": 2, "fixation_spacing_m": 1.0, "waste_pct": 8.0, "default_tilt_deg": 10.0, "sort_order": 4,
     "notes": "Държачи към носещата конструкция през панела (изолационни винтове)."},
    {"code": "ground", "label_bg": "Наземна конструкция", "label_en": "Ground mount", "pricing_mode": "detailed", "lump_price_per_module": 83.0, "rails_per_module": 2, "fixation_spacing_m": 2.5, "waste_pct": 5.0, "default_tilt_deg": 30.0, "sort_order": 5,
     "notes": "Стоманени маси, фундаменти/забити профили. Разстояние между редовете за избягване на засенчване."},
]

# (roof_type, item name, basis, factor, round_up)
MOUNTING_RULES: list[tuple[str, str, str, float, bool]] = [
    # tile roof — Aerocompact CompactPITCH XM-F
    ("tile", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("tile", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("tile", "XM-F кука за керемиден покрив (регулируема)", "per_fixation", 1, True),
    ("tile", "XM-FSP опорна плоча за кука", "per_fixation", 0.75, True),
    ("tile", "XM-FCMR покривна ламарина среден размер, червена", "per_fixation", 1, True),
    ("tile", "SDS-W 8×100 самонарезен винт за дърво", "per_fixation", 2, True),
    ("tile", "GSC 10×30 фиксиращ винт", "per_fixation", 1.1, True),
    ("tile", "CLM10 средна скоба Click 30-46", "per_mid_clamp", 1, True),
    ("tile", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("tile", "XCL50 капачка лява за шина X50", "per_line", 1, True),
    ("tile", "XCR50 капачка дясна за шина X50", "per_line", 1, True),
    ("tile", "CLP-M кабелна клипса за модул", "per_module", 1, True),
    ("tile", "CLP-R кабелна клипса за шина", "per_module", 1, True),
    # LT sheet
    ("lt_sheet", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("lt_sheet", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("lt_sheet", "Трапецовиден държач за LT ламарина (къса шина) с EPDM", "per_fixation", 1, True),
    ("lt_sheet", "Самопробивен винт 6.3×25 с EPDM шайба (ламарина)", "per_fixation", 4, True),
    ("lt_sheet", "CLM10 средна скоба Click 30-46", "per_mid_clamp", 1, True),
    ("lt_sheet", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("lt_sheet", "CLP-M кабелна клипса за модул", "per_module", 1, True),
    # sandwich
    ("sandwich", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("sandwich", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("sandwich", "Държач за сандвич панел (изолационен винт M10)", "per_fixation", 1, True),
    ("sandwich", "CLM10 средна скоба Click 30-46", "per_mid_clamp", 1, True),
    ("sandwich", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("sandwich", "CLP-M кабелна клипса за модул", "per_module", 1, True),
    # flat concrete — ballasted triangles
    ("flat_concrete", "Триъгълна конструкция за плосък покрив 15° (комплект за 1 модул)", "per_module", 1, True),
    ("flat_concrete", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("flat_concrete", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("flat_concrete", "Баластен блок 30 кг", "per_module", 3, True),
    ("flat_concrete", "Защитна подложка за хидроизолация", "per_module", 2, True),
    ("flat_concrete", "CLM10 средна скоба Click 30-46", "per_mid_clamp", 1, True),
    ("flat_concrete", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("flat_concrete", "CLP-M кабелна клипса за модул", "per_module", 1, True),
    # ground
    ("ground", "Наземна конструкция — стоманена поцинкована (на модул)", "per_module", 1, True),
    ("ground", "Бетонен фундамент / забит профил (на опора)", "per_fixation", 1, True),
    ("ground", "CLM10 средна скоба Click 30-46", "per_mid_clamp", 1, True),
    ("ground", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("ground", "CLP-M кабелна клипса за модул", "per_module", 1, True),
]

LABOR: list[tuple[int, int, float]] = [
    (1, 2, 1100.0), (1, 3, 1500.0), (2, 2, 1600.0), (2, 3, 3000.0), (3, 2, 2300.0), (3, 3, 3300.0), (3, 4, 4200.0),
    (4, 3, 4300.0), (5, 3, 5200.0), (5, 4, 6800.0), (7, 4, 9200.0), (10, 4, 12800.0),
]


def seed(db: Session) -> None:
    s = get_settings()
    if not db.query(User).first():
        db.add(User(email=s.admin_email, name="Администратор", password_hash=hash_password(s.admin_password), role="admin"))
    if not db.query(RoofTypeConfig).first():
        for rt in ROOF_TYPES:
            db.add(RoofTypeConfig(**rt))
    if not db.query(LaborOption).first():
        for d, w, p in LABOR:
            db.add(LaborOption(days=d, workers=w, price=p))
    db.flush()
    if not db.query(CatalogItem).first():
        for i, it in enumerate(CATALOG):
            row = CatalogItem(sort_order=i, **it)
            db.add(row)
        db.flush()
        by_name = {c.name: c for c in db.query(CatalogItem).all()}
        for i, (roof, name, basis, factor, ru) in enumerate(MOUNTING_RULES):
            item = by_name.get(name)
            db.add(MountingRule(roof_type=roof, catalog_item_id=item.id if item else None, name=name, basis=basis, factor=factor, round_up=ru, sort_order=i))
    db.commit()
