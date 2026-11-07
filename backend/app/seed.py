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


DEYE_LP3_SM2 = {
    # Deye SUN-xK-SG05LP3-EU-SM2 three-phase LV hybrid (datasheets 2024-09-27 + user manuals 2026-03)
    # kw: (max_pv_kw, max_pv_access_kw, mppt_v_min, start_v, i_op_per_mppt, isc_per_mppt, strings_per_mppt, max_charge_a, max_ac_a, ac_breaker_a, batt_breaker_a, batt_cable_mm2, ac_cable_mm2, pe_mm2, batt_inputs, weight_kg, dims)
    3: (4.5, 6.0, 200, 200, 20, 30, 1, 70, 5.0, 63, 90, 42, 6, 10, 1, 35.2, "386×660×250"),
    4: (6.0, 8.0, 200, 200, 20, 30, 1, 95, 6.7, 63, 120, 42, 6, 10, 1, 35.2, "386×660×250"),
    5: (7.5, 10.0, 200, 200, 20, 30, 1, 120, 8.4, 63, 150, 42, 6, 10, 1, 35.2, "386×660×250"),
    6: (9.0, 12.0, 200, 200, 20, 30, 1, 135, 10.0, 63, 200, 42, 6, 10, 1, 35.2, "386×660×250"),
    8: (12.0, 16.0, 200, 200, 20, 30, 1, 190, 13.4, 63, 250, 42, 6, 10, 1, 35.2, "386×660×250"),
    10: (15.0, 20.0, 200, 200, 26, 39, 2, 210, 16.7, 63, 300, 42, 6, 10, 1, 35.2, "386×660×250"),
    12: (18.0, 24.0, 200, 200, 26, 39, 2, 240, 20.0, 63, 300, 42, 6, 10, 1, 35.2, "386×660×250"),
    14: (22.4, 28.0, 160, 160, 36, 54, 2, 260, 23.4, 100, 400, 50, 10, 16, 2, 50.6, "456×750×268.5"),
    15: (24.0, 30.0, 160, 160, 36, 54, 2, 280, 25.0, 100, 400, 50, 10, 16, 2, 50.6, "456×750×268.5"),
    16: (25.6, 32.0, 160, 160, 36, 54, 2, 300, 26.7, 100, 400, 50, 10, 16, 2, 50.6, "456×750×268.5"),
    18: (28.8, 36.0, 160, 160, 36, 54, 2, 330, 30.0, 100, 500, 70, 10, 16, 2, 50.6, "456×750×268.5"),
    20: (32.0, 40.0, 160, 160, 36, 54, 2, 350, 33.4, 100, 500, 70, 10, 16, 2, 50.6, "456×750×268.5"),
}


def _inv_lp3(kw: int, price: float = 0.0) -> dict:
    (max_pv, access, mppt_min, start, i_op, i_sc, spm, chg, ac_max, brk, bbrk, bcab, accab, pe, binp, wt, dims) = DEYE_LP3_SM2[kw]
    ds = "https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-3-12k-sg05lp3-eu-sm2_240927_en.pdf" if kw <= 12 else "https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-14-20k-sg05lp3-eu-sm2_240927_en.pdf"
    specs = {
        "ac_power_kw": kw, "phases": 3, "battery_voltage_class": "LV", "hybrid": True,
        "max_pv_kw": max_pv, "max_pv_access_kw": access, "mppt_count": 2, "strings_per_mppt": spm,
        "max_dc_voltage": 800, "start_voltage": start, "mppt_v_min": mppt_min, "mppt_v_max": 650, "rated_dc_v": 550,
        "max_input_current_a": i_op, "max_isc_a": i_sc,
        "battery_v_nominal": 48, "battery_v_min": 40, "battery_v_max": 60, "max_charge_a": chg, "max_charge_kw": round(chg * 51.2 / 1000, 1), "battery_inputs": binp, "max_battery_parallel": 16,
        "max_ac_current_a": ac_max, "ac_breaker_a": brk, "rcd_ma": 300, "ac_cable_mm2": accab, "pe_cable_mm2": pe,
        "battery_breaker_a": bbrk, "battery_cable_mm2": bcab, "ct_lead_m": 4, "ct_count": 3,
        "integrated_dc_switch": True, "integrated_spd": True, "efficiency_max": 97.6, "ip": "IP65",
        "weight_kg": wt, "dims_mm": dims, "clearance_cm": "50 страни/горе/долу, 100 отпред",
        "datasheet": ds, "specs_verified": True,
        "verified_note": "battery breaker 14-20K по таблица на Deye — проверете в ръководството за конкретната ревизия" if kw >= 14 else "",
    }
    return {"category": "inverter", "sku": f"SUN-{kw}K-SG05LP3-EU-SM2", "name": f"Deye SUN-{kw}K-SG05LP3-EU-SM2 (трифазен, LV, {kw} kW)", "manufacturer": "Deye", "warranty": "10 години", "purchase_price": price, "specs": specs}


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
        "specs": {"wp": 650, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 33.5, "cells": 132, "voc": 49.72, "isc": 16.54, "vmp": 40.98, "imp": 15.86, "efficiency": 24.06, "max_system_v": 1500, "max_series_fuse_a": 35, "temp_coeff_pmax": -0.26, "temp_coeff_voc": -0.20, "temp_coeff_isc": 0.05, "cell": "HPBC 2.0", "frame_mm": 30, "datasheet": "https://eu.longi.com/longi-solar-panels-datasheets/lr8-66hvd-640-670m", "specs_verified": True},
    },
    {
        "category": "panel", "name": "LONGi Hi-MO X10 LR8-66HVD-660M 660 Wp", "manufacturer": "LONGi Solar", "sku": "LR8-66HVD-660M",
        "purchase_price": 0.0, "warranty": "15 г. продуктова / 30 г. линейна",
        "specs": {"wp": 660, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 33.5, "cells": 132, "voc": 50.1, "isc": 16.62, "vmp": 41.36, "imp": 15.96, "efficiency": 24.4, "max_system_v": 1500, "max_series_fuse_a": 35, "temp_coeff_pmax": -0.26, "temp_coeff_voc": -0.20, "datasheet": "https://eu.longi.com/longi-solar-panels-datasheets/lr8-66hvd-640-670m", "specs_verified": False},
    },
    {
        "category": "panel", "name": "LONGi Hi-MO 9 LR7-72HYD-640M 640 Wp (bifacial)", "manufacturer": "LONGi Solar", "sku": "LR7-72HYD-640M",
        "purchase_price": 0.0, "warranty": "15 г. продуктова / 30 г. линейна",
        "specs": {"wp": 640, "width_mm": 1134, "height_mm": 2382, "thickness_mm": 30, "weight_kg": 33.5, "voc": 49.0, "isc": 16.6, "vmp": 40.6, "imp": 15.8, "efficiency": 23.7, "max_system_v": 1500, "max_series_fuse_a": 35, "temp_coeff_pmax": -0.28, "temp_coeff_voc": -0.22, "specs_verified": False},
    },
    # ----- single-phase hybrid inverters (LV) -----
    _inv("Deye SUN-5K-SG03LP1-EU", 5, 1, "LV"),
    _inv("Deye SUN-6K-SG05LP1-AM2-PLUS", 6, 1, "LV"),
    _inv("Deye SUN-8K-SG05LP1-EU-AM2-P/PLUS", 8, 1, "LV"),
    _inv("Deye SUN-10K-SG02LP1-EU", 10, 1, "LV"),
    _inv("Deye SUN-12K-SG02LP1-EU", 12, 1, "LV"),
    _inv("Deye SUN-14K-SG01LP1-EU", 14, 1, "LV"),
    _inv("Deye SUN-16K-SG01LP1-EU", 16, 1, "LV", price=1550.0),
    # ----- three-phase hybrid inverters LV (verified datasheet values) -----
    *[_inv_lp3(k) for k in (3, 4, 5, 6, 8, 10, 12, 14, 15, 16, 18, 20)],
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
    _bat("Deye SE-G5.1 Pro-B 5.12 kWh LV (19\" rack)", 5.12, "LV", ah=100, max_charge_a=100, rec_charge_a=50, dims_mm="440×133×540", weight_kg=45, ip="IP20", usable_kwh=4.6, built_in_breaker=True, max_parallel=16, datasheet="https://deye.com/product/se-g5-1-pro-b/", specs_verified=True),
    _bat("Deye SE-F5 Pro C 5.12 kWh LV", 5.12, "LV", ah=100),
    _bat("Deye RW-M6.1-B 6.14 kWh LV IP65 (стенен)", 6.14, "LV", ah=120, max_charge_a=100, rec_charge_a=60, dims_mm="510×740×145", weight_kg=58, ip="IP65", built_in_breaker=True, max_parallel=16, datasheet="https://deyeinverters.net/en/products/batteries/deye-6-14kwh-low-voltage-lithium-solar-battery-rw-m6-1-b", specs_verified=True),
    _bat("Deye RW-F10.2 10.2 kWh LV IP65", 10.2, "LV", ah=200),
    _bat("Deye RW-F10.6 10.6 kWh LV IP20", 10.6, "LV", ah=208),
    _bat("Deye SE-F12 C 12 kWh LV IP21", 12.0, "LV", ah=240),
    _bat("Deye SE-F12 MAX 12 kWh LV IP65 (heating)", 12.0, "LV", ah=240),
    _bat("Deye RW-F16 16 kWh LV (314 Ah)", 16.0, "LV", price=1480.0, ah=314, usable_kwh=14.4, max_charge_a=160, peak_a=300, built_in_breaker=True, built_in_breaker_a=125, dims_mm="480×830×235", weight_kg=122, ip="IP20", max_parallel=16, datasheet="https://deye.com/product/rw-f16/", specs_verified=True),
    _bat("Deye SE-F16 C 16 kWh LV IP21", 16.0, "LV", ah=314),
    _bat("Deye SE-F16 MAX 16 kWh LV IP65", 16.0, "LV", ah=314),
    _bat("Deye GE-F60 60 kWh (без инвертор)", 60.0, "HV", max_parallel=10),
    # ----- accessories -----
    {"category": "accessory", "name": "Deye LSW-3 Wi-Fi dongle", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "Deye LS4G-3 4G dongle", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "Оптимизатор Deye SUN-XL02-A", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    {"category": "accessory", "name": "SDM630-Modbus трифазен смарт електромер", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 3, "role": "smart_meter"}},
    {"category": "accessory", "name": "SDM630MCT трифазен електромер за токов трансформатор", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 3}},
    {"category": "accessory", "name": "SDM230-Modbus монофазен смарт електромер", "manufacturer": "Eastron", "warranty": "2 години", "purchase_price": 0.0, "specs": {"phases": 1, "role": "smart_meter"}},
    {"category": "accessory", "name": "Зарядна станция Deye SUN-EVSE22K01-EU-AC", "manufacturer": "Deye", "warranty": "2 години", "purchase_price": 0.0},
    # ----- switchboards -----
    {"category": "switchboard", "name": "Монофазно електрическо табло (AC/DC защити, 400×300×200)", "purchase_price": 90.0, "specs": {"phases": 1}},
    {"category": "switchboard", "name": "Трифазно електрическо табло (AC/DC защити, 600×600×200)", "purchase_price": 110.0, "specs": {"phases": 3}},
    # ----- solar cables (role pv_cable) -----
    {"category": "solar_cable", "name": "KBE 6 mm² H1Z2Z2-K", "manufacturer": "KBE", "unit": "м", "purchase_price": 1.2, "specs": {"cross_section_mm2": 6, "role": "pv_cable"}},
    {"category": "solar_cable", "name": "Vatan 6 mm² H1Z2Z2-K", "manufacturer": "Vatan", "unit": "м", "purchase_price": 0.88, "specs": {"cross_section_mm2": 6, "role": "pv_cable"}},
    {"category": "solar_cable", "name": "Leader 6 mm² H1Z2Z2-K", "manufacturer": "Leader", "unit": "м", "purchase_price": 0.78, "specs": {"cross_section_mm2": 6, "role": "pv_cable"}},
    {"category": "solar_cable", "name": "Соларен кабел 10 mm² H1Z2Z2-K", "unit": "м", "purchase_price": 1.65, "specs": {"cross_section_mm2": 10, "role": "pv_cable", "price_source": "indicative"}},
    # ----- power cables (role ac_cable) -----
    {"category": "power_cable", "name": "Кабел СВТ 3×6 mm²", "unit": "м", "purchase_price": 1.9, "specs": {"cores": 3, "cross_section_mm2": 6, "phases": 1, "role": "ac_cable"}},
    {"category": "power_cable", "name": "Кабел СВТ 3×10 mm²", "unit": "м", "purchase_price": 3.1, "specs": {"cores": 3, "cross_section_mm2": 10, "phases": 1, "role": "ac_cable", "price_source": "indicative"}},
    {"category": "power_cable", "name": "Кабел СВТ 5×6 mm²", "unit": "м", "purchase_price": 3.0, "specs": {"cores": 5, "cross_section_mm2": 6, "phases": 3, "role": "ac_cable", "price_source": "indicative"}},
    {"category": "power_cable", "name": "Кабел СВТ 5×10 mm²", "unit": "м", "purchase_price": 4.2, "specs": {"cores": 5, "cross_section_mm2": 10, "phases": 3, "role": "ac_cable"}},
    {"category": "power_cable", "name": "Кабел СВТ 5×16 mm²", "unit": "м", "purchase_price": 6.5, "specs": {"cores": 5, "cross_section_mm2": 16, "phases": 3, "role": "ac_cable"}},
    {"category": "power_cable", "name": "Кабел СВТ 5×25 mm²", "unit": "м", "purchase_price": 10.5, "specs": {"cores": 5, "cross_section_mm2": 25, "phases": 3, "role": "ac_cable", "price_source": "indicative"}},
    {"category": "power_cable", "name": "Кабел СВТ 4×6 mm²", "unit": "м", "purchase_price": 2.0, "specs": {"cores": 4, "cross_section_mm2": 6, "phases": 3}},
    {"category": "power_cable", "name": "Усукан проводник 4×16 mm²", "unit": "м", "purchase_price": 2.4, "specs": {"cores": 4, "cross_section_mm2": 16, "phases": 3}},
    # ----- DC protection -----
    {"category": "dc_protection", "name": "Конектор MC4 комплект (мъжки+женски) 1500 V", "manufacturer": "Stäubli/съвм.", "unit": "бр.", "purchase_price": 1.2, "specs": {"role": "mc4_pair"}},
    {"category": "dc_protection", "name": "Предпазител gPV 25 A 1000 V DC 10×38", "unit": "бр.", "purchase_price": 3.2, "specs": {"role": "dc_fuse", "rating_a": 25, "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Предпазител gPV 30 A 1000 V DC 10×38", "unit": "бр.", "purchase_price": 3.4, "specs": {"role": "dc_fuse", "rating_a": 30, "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Държач за предпазител 10×38 1000 V DC 1P (DIN)", "unit": "бр.", "purchase_price": 4.5, "specs": {"role": "dc_fuse_holder", "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Катоден отводител DC тип 2, 1000 V, 40 kA (Y, сменяеми модули)", "unit": "бр.", "purchase_price": 48.0, "specs": {"role": "dc_spd", "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Разединител DC 1000 V 32 A 4P (DIN)", "unit": "бр.", "purchase_price": 26.0, "specs": {"role": "dc_isolator", "rating_a": 32, "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Табло DC IP65 8–12 модула, с DIN шина и салници", "unit": "бр.", "purchase_price": 32.0, "specs": {"role": "dc_enclosure", "price_source": "indicative"}},
    {"category": "dc_protection", "name": "Кабелен салник M20 IP68", "unit": "бр.", "purchase_price": 0.45, "specs": {"role": "cable_gland", "price_source": "indicative"}},
    # ----- AC protection -----
    {"category": "ac_protection", "name": "Автоматичен прекъсвач 2P 32 A C 6 kA", "unit": "бр.", "purchase_price": 9.5, "specs": {"role": "ac_mcb", "rating_a": 32, "poles": "2P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Автоматичен прекъсвач 2P 63 A C 6 kA", "unit": "бр.", "purchase_price": 16.0, "specs": {"role": "ac_mcb", "rating_a": 63, "poles": "2P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Автоматичен прекъсвач 4P 32 A C 6 kA", "unit": "бр.", "purchase_price": 19.0, "specs": {"role": "ac_mcb", "rating_a": 32, "poles": "4P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Автоматичен прекъсвач 4P 63 A C 6 kA", "unit": "бр.", "purchase_price": 28.0, "specs": {"role": "ac_mcb", "rating_a": 63, "poles": "4P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Автоматичен прекъсвач 4P 100 A C 10 kA", "unit": "бр.", "purchase_price": 68.0, "specs": {"role": "ac_mcb", "rating_a": 100, "poles": "4P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Дефектнотокова защита 2P 63 A 300 mA тип A", "unit": "бр.", "purchase_price": 38.0, "specs": {"role": "ac_rcd", "rating_a": 63, "poles": "2P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Дефектнотокова защита 4P 63 A 300 mA тип A", "unit": "бр.", "purchase_price": 62.0, "specs": {"role": "ac_rcd", "rating_a": 63, "poles": "4P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Дефектнотокова защита 4P 100 A 300 mA тип A", "unit": "бр.", "purchase_price": 118.0, "specs": {"role": "ac_rcd", "rating_a": 100, "poles": "4P", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Катоден отводител AC тип 2, 1P+N 275 V 20 kA", "unit": "бр.", "purchase_price": 32.0, "specs": {"role": "ac_spd", "phases": 1, "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Катоден отводител AC тип 2, 3P+N 275 V 20 kA", "unit": "бр.", "purchase_price": 58.0, "specs": {"role": "ac_spd", "phases": 3, "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Табло за резервирани товари 12–24 модула IP40", "unit": "бр.", "purchase_price": 28.0, "specs": {"role": "ac_enclosure", "price_source": "indicative"}},
    {"category": "ac_protection", "name": "Кабелен накрайник / обувка 6–16 mm²", "unit": "бр.", "purchase_price": 0.25, "specs": {"role": "ac_lug", "price_source": "indicative"}},
    # ----- battery DC side -----
    {"category": "battery_accessory", "name": "Батериен кабел 50 mm² H07V-K (червен/черен)", "unit": "м", "purchase_price": 7.8, "specs": {"role": "battery_cable", "cross_section_mm2": 50, "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "Батериен кабел 70 mm² H07V-K (червен/черен)", "unit": "м", "purchase_price": 10.9, "specs": {"role": "battery_cable", "cross_section_mm2": 70, "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "Кабелна обувка тръбна 50 mm² M10", "unit": "бр.", "purchase_price": 0.9, "specs": {"role": "battery_lug", "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "DC прекъсвач батерия 250 A 2P 125 V DC (MCCB)", "unit": "бр.", "purchase_price": 48.0, "specs": {"role": "battery_breaker", "rating_a": 250, "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "DC прекъсвач батерия 400 A 2P 125 V DC (MCCB)", "unit": "бр.", "purchase_price": 95.0, "specs": {"role": "battery_breaker", "rating_a": 400, "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "DC прекъсвач батерия 500 A 2P 125 V DC (MCCB)", "unit": "бр.", "purchase_price": 130.0, "specs": {"role": "battery_breaker", "rating_a": 500, "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "Шинен разпределител DC 500 A (+/−) за паралелни батерии", "unit": "бр.", "purchase_price": 45.0, "specs": {"role": "battery_busbar", "price_source": "indicative"}},
    {"category": "battery_accessory", "name": "Комуникационен кабел CAN RJ45 2 m (батерия ↔ инвертор)", "unit": "бр.", "purchase_price": 4.0, "specs": {"role": "comm_cable", "price_source": "indicative"}},
    # ----- earthing -----
    {"category": "grounding", "name": "Заземителен проводник ПВ-А1 16 mm² жълто-зелен", "unit": "м", "purchase_price": 2.3, "specs": {"role": "pe_cable", "cross_section_mm2": 16, "price_source": "indicative"}},
    {"category": "grounding", "name": "Заземителен проводник 6 mm² жълто-зелен", "unit": "м", "purchase_price": 0.9, "specs": {"role": "bonding_cable", "cross_section_mm2": 6}},
    {"category": "grounding", "name": "Заземителна шина PE 7×16 mm² за табло", "unit": "бр.", "purchase_price": 3.5, "specs": {"role": "earth_bar", "price_source": "indicative"}},
    {"category": "grounding", "name": "Заземителен кол 1,5 m Ø16 поцинкован + клема", "unit": "бр.", "purchase_price": 16.0, "specs": {"role": "earth_rod", "price_source": "indicative"}},
    {"category": "grounding", "name": "Поцинкована шина 30×4 mm", "unit": "м", "purchase_price": 2.6, "specs": {"role": "earth_strip", "price_source": "indicative"}},
    # ----- cable management & consumables -----
    {"category": "cable_management", "name": "Гофрирана тръба UV ф32 (двуслойна, черна)", "unit": "м", "purchase_price": 1.22, "specs": {"role": "conduit_32"}},
    {"category": "cable_management", "name": "Гофрирана тръба UV ф40 (двуслойна, черна)", "unit": "м", "purchase_price": 1.6, "specs": {"role": "conduit_40", "price_source": "indicative"}},
    {"category": "cable_management", "name": "Скоба за тръба ф32/ф40 с дюбел", "unit": "бр.", "purchase_price": 0.18, "specs": {"role": "conduit_clip", "price_source": "indicative"}},
    {"category": "cable_management", "name": "Кабелна връзка UV 4,8×200 mm черна", "unit": "бр.", "purchase_price": 0.05, "specs": {"role": "cable_tie_uv", "price_source": "indicative"}},
    {"category": "cable_management", "name": "Кабелен накрайник за жило 6 mm² (изолиран)", "unit": "бр.", "purchase_price": 0.06, "specs": {"role": "end_sleeve", "price_source": "indicative"}},
    {"category": "cable_management", "name": "Комплект табели PV (DC опасност, двойно захранване, инвертор, табло)", "unit": "компл.", "purchase_price": 9.0, "specs": {"role": "labels", "price_source": "indicative"}},
    # ----- monitoring / metering -----
    {"category": "monitoring", "name": "Кабел за удължаване на CT 2×0,75 mm² екраниран", "unit": "м", "purchase_price": 0.55, "specs": {"role": "ct_cable", "price_source": "indicative"}},
    {"category": "monitoring", "name": "Кабел RS485 екраниран 2×0,5 mm²", "unit": "м", "purchase_price": 0.5, "specs": {"role": "rs485_cable", "price_source": "indicative"}},
    # ----- mounting: AEROCOMPACT CompactPITCH (tile) — codes from quote 64845 / Aerocompact catalogue -----
    {"category": "mounting", "sku": "705100-3550", "name": "X50-3550 монтажна шина 3550 mm", "manufacturer": "Aerocompact", "purchase_price": 24.92, "specs": {"length_m": 3.55, "system": "CompactPITCH"}},
    {"category": "mounting", "sku": "705100-4400", "name": "X50-4400 монтажна шина 4400 mm", "manufacturer": "Aerocompact", "purchase_price": 31.0, "specs": {"length_m": 4.4, "system": "CompactPITCH", "price_source": "indicative"}},
    {"category": "mounting", "sku": "705100-5850", "name": "X50-5850 монтажна шина 5850 mm", "manufacturer": "Aerocompact", "purchase_price": 41.0, "specs": {"length_m": 5.85, "system": "CompactPITCH", "price_source": "indicative"}},
    {"category": "mounting", "sku": "705202", "name": "XPCN съединител за шина X40/X50", "manufacturer": "Aerocompact", "purchase_price": 1.85, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "705310", "name": "XM-F кука за керемиден покрив (регулируема)", "manufacturer": "Aerocompact", "purchase_price": 12.29, "specs": {"system": "CompactPITCH", "screws": "2× SDS-W 8×100 или 3× SDS-W 6×100", "datasheet": "https://shop.sonepar.at/asset_external/downloads/pim/402002/MD21_120160400.pdf"}},
    {"category": "mounting", "sku": "705309", "name": "XM-FSP опорна плоча за кука", "manufacturer": "Aerocompact", "purchase_price": 1.76, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "705308-8004", "name": "XM-FCMR покривна ламарина среден размер, червена", "manufacturer": "Aerocompact", "purchase_price": 8.02},
    {"category": "mounting", "sku": "701544", "name": "SDS-W 8×100 самонарезен винт за дърво (A2)", "manufacturer": "Aerocompact", "purchase_price": 0.26, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "701590", "name": "GSC 10×30 фиксиращ винт (кука↔шина)", "manufacturer": "Aerocompact", "purchase_price": 0.23, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "707011", "name": "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "manufacturer": "Aerocompact", "purchase_price": 1.54, "specs": {"small_part": True, "torque_nm": 15}},
    {"category": "mounting", "sku": "707003", "name": "CLE10 крайна скоба Click 30-46", "manufacturer": "Aerocompact", "purchase_price": 1.54, "specs": {"small_part": True, "torque_nm": 15, "edge_distance_mm": 40}},
    {"category": "mounting", "sku": "705205", "name": "XCL50 капачка лява за шина X50", "manufacturer": "Aerocompact", "purchase_price": 0.46, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "705206", "name": "XCR50 капачка дясна за шина X50", "manufacturer": "Aerocompact", "purchase_price": 0.46, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "701902", "name": "CLP-M кабелна клипса за модул", "manufacturer": "Aerocompact", "purchase_price": 0.26, "specs": {"small_part": True}},
    {"category": "mounting", "sku": "706457", "name": "CLP-R кабелна клипса за шина", "manufacturer": "Aerocompact", "purchase_price": 0.16, "specs": {"small_part": True}},
    {"category": "mounting", "name": "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "manufacturer": "Aerocompact", "purchase_price": 1.9, "specs": {"small_part": True, "role": "bonding_clamp", "torque_nm": 10, "price_source": "indicative"}},
    # ----- CompactMETAL (trapezoidal sheet) -----
    {"category": "mounting", "name": "CompactMETAL TL25 трапецовиден мост 250 mm с EPDM", "manufacturer": "Aerocompact", "purchase_price": 4.5, "specs": {"system": "CompactMETAL", "datasheet": "https://www.aerocompact.com/en/products/pitched-roofs/compactmetal-tm", "price_source": "indicative"}},
    {"category": "mounting", "name": "MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", "manufacturer": "Aerocompact", "purchase_price": 0.12, "specs": {"small_part": True, "price_source": "indicative"}},
    {"category": "mounting", "name": "CLE10 Plus крайна скоба Click (за къси шини)", "manufacturer": "Aerocompact", "sku": "707080", "purchase_price": 2.35, "specs": {"small_part": True, "price_source": "indicative"}},
    # ----- sandwich / corrugated: hanger bolts to purlins -----
    {"category": "mounting", "name": "Шпилка (hanger bolt) M10×250 A2 с EPDM уплътнение и адаптер за шина (сандвич панел)", "purchase_price": 5.8, "specs": {"price_source": "indicative"}},
    {"category": "mounting", "name": "Уплътнителна EPDM шайба/маншон за шпилка M10", "purchase_price": 0.4, "specs": {"small_part": True, "price_source": "indicative"}},
    # ----- CompactFLAT S10 (flat roof, 10° south) -----
    {"category": "mounting", "name": "CompactFLAT S10 основа (базов профил) за 1 модул 10°", "manufacturer": "Aerocompact", "purchase_price": 38.0, "specs": {"system": "CompactFLAT", "price_source": "indicative"}},
    {"category": "mounting", "name": "Баластен блок бетон 40×20×10 cm (≈18 kg)", "purchase_price": 3.2, "specs": {"weight_kg": 18, "price_source": "indicative"}},
    {"category": "mounting", "name": "Защитна подложка (строителна защита) за хидроизолация", "purchase_price": 1.5},
    {"category": "mounting", "name": "Ветрозащитен дефлектор CompactFLAT (заден лист)", "manufacturer": "Aerocompact", "purchase_price": 9.5, "specs": {"price_source": "indicative"}},
    # ----- ground mount -----
    {"category": "mounting", "name": "Наземна конструкция — стоманена поцинкована (на модул)", "purchase_price": 55.0},
    {"category": "mounting", "name": "Бетонен фундамент / забит профил (на опора)", "purchase_price": 28.0},
    {"category": "mounting", "name": "Болт M10×30 A2 с гайка и шайби (наземна конструкция)", "purchase_price": 0.35, "specs": {"small_part": True, "price_source": "indicative"}},
    # ----- services / transport -----
    {"category": "transport", "name": "Транспорт до обекта", "unit": "бр.", "purchase_price": 0.0, "sell_price": 120.0},
    {"category": "service", "name": "Проектиране и документация за присъединяване", "unit": "бр.", "purchase_price": 0.0, "sell_price": 350.0},
    {"category": "service", "name": "Монтаж и настройка на мониторинг (Wi-Fi/4G)", "unit": "бр.", "purchase_price": 0.0, "sell_price": 60.0},
]

ROOF_TYPES: list[dict] = [
    {"code": "tile", "label_bg": "Покрив с керемиди", "label_en": "Tile roof", "pricing_mode": "detailed", "lump_price_per_module": 124.0, "rails_per_module": 2, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 25.0, "sort_order": 1,
     "notes": "Куки за керемиди върху ребрата (стъпка ~0.7 m), шини X50, скоби Click."},
    {"code": "flat_concrete", "label_bg": "Плосък бетонен покрив", "label_en": "Flat concrete roof", "pricing_mode": "detailed", "lump_price_per_module": 95.0, "rails_per_module": 2, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 15.0, "sort_order": 2,
     "notes": "CompactFLAT S10 с баласт, без пробиване на хидроизолацията. Баластът се потвърждава с ветрово/снегово изчисление."},
    {"code": "lt_sheet", "label_bg": "LT ламарина", "label_en": "Trapezoidal metal sheet", "pricing_mode": "detailed", "lump_price_per_module": 70.0, "rails_per_module": 2, "fixation_spacing_m": 1.0, "waste_pct": 8.0, "default_tilt_deg": 10.0, "sort_order": 3,
     "notes": "CompactMETAL TL25 мостове с EPDM върху гребена на ламарината, 4 винта MSS 6×25 на мост."},
    {"code": "sandwich", "label_bg": "Сандвич панел", "label_en": "Sandwich panel roof", "pricing_mode": "detailed", "lump_price_per_module": 78.0, "rails_per_module": 2, "fixation_spacing_m": 1.0, "waste_pct": 8.0, "default_tilt_deg": 10.0, "sort_order": 4,
     "notes": "Шпилки M10 през панела към столиците с EPDM уплътнение."},
    {"code": "ground", "label_bg": "Наземна конструкция", "label_en": "Ground mount", "pricing_mode": "detailed", "lump_price_per_module": 83.0, "rails_per_module": 2, "fixation_spacing_m": 2.5, "waste_pct": 5.0, "default_tilt_deg": 30.0, "sort_order": 5,
     "notes": "Стоманени маси, фундаменти/забити профили. Разстояние между редовете за избягване на засенчване."},
]

# (roof_type, item name, basis, factor, round_up)
# Quantities follow the racking configurator logic (Aerocompact report, quote 64845):
# one hook per fixation point, 2 SDS-W screws + 1 GSC set screw per hook, support plate
# on ~75 % of hooks (depends on rafter height), clamps per rail run, 2 cable clips/module.
# Small parts additionally receive the fastener reserve from Settings (default 10 %).
MOUNTING_RULES: list[tuple[str, str, str, float, bool]] = [
    # tile roof — Aerocompact CompactPITCH XM-F
    ("tile", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("tile", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("tile", "XM-F кука за керемиден покрив (регулируема)", "per_fixation", 1, True),
    ("tile", "XM-FSP опорна плоча за кука", "per_fixation", 0.75, True),
    ("tile", "XM-FCMR покривна ламарина среден размер, червена", "per_fixation", 1, True),
    ("tile", "SDS-W 8×100 самонарезен винт за дърво (A2)", "per_fixation", 2, True),
    ("tile", "GSC 10×30 фиксиращ винт (кука↔шина)", "per_fixation", 1, True),
    ("tile", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    ("tile", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("tile", "XCL50 капачка лява за шина X50", "per_line", 1, True),
    ("tile", "XCR50 капачка дясна за шина X50", "per_line", 1, True),
    ("tile", "CLP-M кабелна клипса за модул", "per_module", 2, True),
    ("tile", "CLP-R кабелна клипса за шина", "per_module", 1, True),
    # trapezoidal sheet — CompactMETAL TL25 bridges (4 MSS screws each), rails on bridges
    ("lt_sheet", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("lt_sheet", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("lt_sheet", "CompactMETAL TL25 трапецовиден мост 250 mm с EPDM", "per_fixation", 1, True),
    ("lt_sheet", "MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", "per_fixation", 4, True),
    ("lt_sheet", "GSC 10×30 фиксиращ винт (кука↔шина)", "per_fixation", 1, True),
    ("lt_sheet", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    ("lt_sheet", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("lt_sheet", "XCL50 капачка лява за шина X50", "per_line", 1, True),
    ("lt_sheet", "XCR50 капачка дясна за шина X50", "per_line", 1, True),
    ("lt_sheet", "CLP-M кабелна клипса за модул", "per_module", 2, True),
    # sandwich panel — hanger bolts into purlins
    ("sandwich", "X50-3550 монтажна шина 3550 mm", "per_rail", 1, True),
    ("sandwich", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
    ("sandwich", "Шпилка (hanger bolt) M10×250 A2 с EPDM уплътнение и адаптер за шина (сандвич панел)", "per_fixation", 1, True),
    ("sandwich", "Уплътнителна EPDM шайба/маншон за шпилка M10", "per_fixation", 1, True),
    ("sandwich", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    ("sandwich", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("sandwich", "XCL50 капачка лява за шина X50", "per_line", 1, True),
    ("sandwich", "XCR50 капачка дясна за шина X50", "per_line", 1, True),
    ("sandwich", "CLP-M кабелна клипса за модул", "per_module", 2, True),
    # flat concrete — CompactFLAT S10 ballasted (ballast per module to be confirmed by wind/snow calc)
    ("flat_concrete", "CompactFLAT S10 основа (базов профил) за 1 модул 10°", "per_module", 1, True),
    ("flat_concrete", "Ветрозащитен дефлектор CompactFLAT (заден лист)", "per_module", 1, True),
    ("flat_concrete", "Баластен блок бетон 40×20×10 cm (≈18 kg)", "per_module", 4, True),
    ("flat_concrete", "Защитна подложка (строителна защита) за хидроизолация", "per_module", 2, True),
    ("flat_concrete", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    ("flat_concrete", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("flat_concrete", "CLP-M кабелна клипса за модул", "per_module", 2, True),
    # ground mount
    ("ground", "Наземна конструкция — стоманена поцинкована (на модул)", "per_module", 1, True),
    ("ground", "Бетонен фундамент / забит профил (на опора)", "per_fixation", 1, True),
    ("ground", "Болт M10×30 A2 с гайка и шайби (наземна конструкция)", "per_module", 4, True),
    ("ground", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    ("ground", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    ("ground", "CLP-M кабелна клипса за модул", "per_module", 2, True),
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
    # Catalog seeding is additive: items/rules that already exist (by name) are never touched, so user edits and
    # imported prices survive upgrades, while new role-tagged items (protection, earthing, …) appear after a restart.
    if not s.seed_demo and db.query(CatalogItem).first() is None:
        db.commit()
        return
    existing_names = {c.name for c in db.query(CatalogItem.name).all()}
    for i, it in enumerate(CATALOG):
        if it["name"] in existing_names:
            continue
        db.add(CatalogItem(sort_order=i, **it))
    db.flush()
    by_name = {c.name: c for c in db.query(CatalogItem).all()}
    existing_rules = {(r.roof_type, r.name) for r in db.query(MountingRule.roof_type, MountingRule.name).all()}
    for i, (roof, name, basis, factor, ru) in enumerate(MOUNTING_RULES):
        if (roof, name) in existing_rules:
            continue
        item = by_name.get(name)
        db.add(MountingRule(roof_type=roof, catalog_item_id=item.id if item else None, name=name, basis=basis, factor=factor, round_up=ru, sort_order=i))
    db.commit()
