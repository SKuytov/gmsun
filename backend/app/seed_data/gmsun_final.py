"""GM SUN final catalog (09.11.2026) – the only items the system may quote.

Source: ``gmsun-dataset.xlsx`` edited by GM SUN (real purchase prices, EUR ex VAT, real markups). Technical data
comes from the official manufacturer datasheets (Deye inverter/battery datasheets 2024-2026, LONGi Hi-MO 10 and
Suntech datasheets) and is marked ``specs_verified``.

Every item has a stable ``sku`` key; the catalog migration matches existing rows by sku first, then by name, so
the dataset can be re-applied safely. ``legacy_id`` is the row ID the item had in the edited workbook.
"""
from __future__ import annotations

from typing import Any

MIGRATION_KEY = "catalog_v2_gmsun_final"
SUPPLIER = "green-energy.bg"

DS = {
    "lp1_sg03": "https://www.deyeinverter.com/deyeinverter/2024/08/02/datasheet_sun-3.6-6k-sg03lp1_240802_en.pdf",
    "lp1_sg05": "https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-3.6-8k-sg05lp1-eu-am2-p_240927_en.pdf",
    "lp1_sg02": "https://deye.com/wp-content/uploads/2026/07/%E3%80%90b%E3%80%91datasheet_sun-7.6-12k-sg02lp1-eu-am2_20260706_en.pdf",
    "lp1_sg01": "https://www.deyeinverter.com/deyeinverter/2024/03/22/datasheet_sun-12-16kk-sg01lp1-eu_020322_en.pdf",
    "lp3_sg05": "https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-3-12k-sg05lp3-eu-sm2_240927_en.pdf",
    "lp3_sg04": "https://www.deyeinverter.com/deyeinverter/2024/10/21/datasheet_sun-5-12k-sg04lp3_241021_en.pdf",
    "lp3_14_20": "https://deye.com/wp-content/uploads/2026/07/%E3%80%90b%E3%80%91datasheet_sun-14-20k-sg05lp3-eu-sm2_20260706_en.pdf",
    "hp3_am2": "https://deye.com/wp-content/uploads/2026/07/%E3%80%90b%E3%80%91datasheet_sun-5-25k-sg01hp3-eu-am2_20260706_en.pdf",
    "hp3_bm": "https://deye.com/wp-content/uploads/2026/07/%E3%80%90b%E3%80%91datasheet_sun-29.9-50k-sg01hp3-eu-bm4_20260706_en.pdf",
    "hp3_em6": "https://deye.com/wp-content/uploads/2026/07/%E3%80%90b%E3%80%91datasheet_sun-60-80k-sg02hp3-eu-em6_20260706_en.pdf",
    "hp3_gm": "https://cdn.enfsolar.com/z/pp/2026/5/e45uxmga96zr/b-datasheet-sun-100125k-sg02hp3-eu-gm10-20260107-en.pdf",
    "bos_g": "https://deye.com/wp-content/uploads/2026/01/deye-bos-g-pro-series_brochure-20251219v1.0.pdf",
    "bos_a": "https://deye.com/wp-content/uploads/2026/09/deye-ess-user-manual-bos-a-euende-v07-_20260225.pdf",
    "longi_54": "https://www.longi.com/en/products/modules/hi-mo-10/",
    "suntech": "https://www.suntech-power.com/",
}


def _inv(sku: str, legacy_id: int, name: str, price: float, *, kw: float, phases: int, vclass: str, ds: str,
         max_dc_v: float, start_v: float, mppt: tuple[float, float], mppt_strings: list[int], i_op: list[float], i_sc: list[float],
         max_pv_kw: float, batt_v: tuple[float, float], charge_a: float, batt_inputs: int, ac_max_a: float,
         weight_kg: float | None = None, max_parallel: int = 10, note: str = "") -> dict[str, Any]:
    specs: dict[str, Any] = {
        "ac_power_kw": kw, "phases": phases, "hybrid": True, "battery_voltage_class": vclass,
        "battery_v_min": batt_v[0], "battery_v_max": batt_v[1],
        "battery_max_charge_a": charge_a, "max_charge_a": charge_a, "battery_inputs": batt_inputs,
        "battery_max_charge_kw": round(charge_a * (51.2 if vclass == "LV" else batt_v[0]) / 1000, 1) if vclass == "LV" else None,
        "max_pv_kw": max_pv_kw, "max_dc_voltage": max_dc_v, "start_voltage": start_v, "mppt_v_min": mppt[0], "mppt_v_max": mppt[1],
        "mppt_count": len(mppt_strings), "strings_per_mppt": max(mppt_strings), "mppt_strings": list(mppt_strings),
        "max_input_current_a": max(i_op), "max_isc_a": max(i_sc), "mppt_input_current_a": list(i_op), "mppt_isc_a": list(i_sc),
        "max_ac_current_a": ac_max_a, "rcd_ma": 300, "integrated_dc_switch": True, "integrated_spd": True,
        "compatible_batteries": ["Deye"], "max_parallel_units": max_parallel,
        "specs_verified": True, "spec_source": "Deye datasheet", "datasheet_url": ds,
    }
    if weight_kg:
        specs["weight_kg"] = weight_kg
    if note:
        specs["verified_note"] = note
    specs = {k: v for k, v in specs.items() if v is not None}
    return {"sku": sku, "legacy_id": legacy_id, "category": "inverter", "name": name, "manufacturer": "Deye", "unit": "бр.",
            "purchase_price": price, "markup_pct": 12.0, "warranty": "10 години", "specs": specs}


LP1 = dict(phases=1, vclass="LV", max_dc_v=500, start_v=125, mppt=(150, 425), batt_v=(40, 60), max_parallel=16)
LP3_SM2_S = dict(phases=3, vclass="LV", max_dc_v=800, start_v=160, mppt=(200, 650), batt_v=(40, 60), max_parallel=10)
LP3_SG04 = dict(phases=3, vclass="LV", max_dc_v=800, start_v=160, mppt=(200, 650), batt_v=(40, 60), max_parallel=10)
LP3_SM2_L = dict(phases=3, vclass="LV", max_dc_v=800, start_v=160, mppt=(160, 650), batt_v=(40, 60), max_parallel=10)
HP3_AM2 = dict(phases=3, vclass="HV", max_dc_v=1000, start_v=180, mppt=(150, 850), batt_v=(160, 700), max_parallel=10)
HP3_BM = dict(phases=3, vclass="HV", max_dc_v=1000, start_v=180, mppt=(150, 850), batt_v=(160, 800), max_parallel=10)
HP3_EM6 = dict(phases=3, vclass="HV", max_dc_v=1000, start_v=180, mppt=(150, 850), batt_v=(160, 1000), max_parallel=10)
HP3_GM = dict(phases=3, vclass="HV", max_dc_v=1000, start_v=180, mppt=(150, 850), batt_v=(160, 1000), max_parallel=10)

INVERTERS: list[dict[str, Any]] = [
    # ---- single-phase LV (48 V battery)
    _inv("DEYE-SUN-5K-SG03LP1-EU", 92, "SUN-5K-SG03LP1-EU", 595, kw=5, ds=DS["lp1_sg03"], mppt_strings=[1, 1], i_op=[13, 13], i_sc=[17, 17], max_pv_kw=6.5, charge_a=120, batt_inputs=1, ac_max_a=25, weight_kg=20.5, **LP1),
    _inv("DEYE-SUN-6K-SG05LP1-EU-AM2-P", 93, "SUN-6K-SG05LP1-AM2-PLUS", 620, kw=6, ds=DS["lp1_sg05"], mppt_strings=[1, 1], i_op=[18, 18], i_sc=[27, 27], max_pv_kw=9.6, charge_a=135, batt_inputs=1, ac_max_a=30, weight_kg=24.9, **LP1),
    _inv("DEYE-SUN-8K-SG05LP1-EU-AM2-P", 94, "SUN-8K-SG05LP1-EU-AM2-P/PLUS", 835, kw=8, ds=DS["lp1_sg05"], mppt_strings=[2, 2], i_op=[32, 32], i_sc=[48, 48], max_pv_kw=12.8, charge_a=190, batt_inputs=1, ac_max_a=40, weight_kg=24.9, **LP1),
    _inv("DEYE-SUN-10K-SG02LP1-EU-AM3", 95, "SUN-10K-SG02LP1-EU", 1150, kw=10, ds=DS["lp1_sg02"], mppt_strings=[2, 2, 2], i_op=[26, 26, 26], i_sc=[44, 44, 44], max_pv_kw=16.0, charge_a=220, batt_inputs=1, ac_max_a=50, weight_kg=35.6, **LP1),
    _inv("DEYE-SUN-12K-SG02LP1-EU-AM3", 96, "SUN-12K-SG02LP1-EU", 1215, kw=12, ds=DS["lp1_sg02"], mppt_strings=[2, 2, 2], i_op=[26, 26, 26], i_sc=[44, 44, 44], max_pv_kw=19.2, charge_a=250, batt_inputs=1, ac_max_a=60, weight_kg=35.6, **LP1),
    _inv("DEYE-SUN-14K-SG01LP1-EU", 97, "SUN-14K-SG01LP1-EU", 1390, kw=14, ds=DS["lp1_sg01"], mppt_strings=[2, 2, 2], i_op=[26, 26, 26], i_sc=[44, 44, 44], max_pv_kw=18.2, charge_a=250, batt_inputs=2, ac_max_a=70, weight_kg=52, **LP1),
    _inv("DEYE-SUN-16K-SG01LP1-EU", 98, "SUN-16K-SG01LP1-EU", 1550, kw=16, ds=DS["lp1_sg01"], mppt_strings=[2, 2, 2], i_op=[26, 26, 26], i_sc=[44, 44, 44], max_pv_kw=20.8, charge_a=290, batt_inputs=2, ac_max_a=80, weight_kg=52, **LP1),
    # ---- three-phase LV (48 V battery)
    _inv("DEYE-SUN-5K-SG05LP3-EU-SM2", 113, "SUN-5K-SG05LP3-EU  (low voltage)", 1080, kw=5, ds=DS["lp3_sg05"], mppt_strings=[1, 1], i_op=[20, 20], i_sc=[30, 30], max_pv_kw=7.5, charge_a=120, batt_inputs=1, ac_max_a=8.4, weight_kg=35.2, **LP3_SM2_S),
    _inv("DEYE-SUN-6K-SG04LP3-EU", 114, "SUN-6K-SG04LP3-EU  (low voltage)", 1100, kw=6, ds=DS["lp3_sg04"], mppt_strings=[1, 1], i_op=[13, 13], i_sc=[17, 17], max_pv_kw=9.0, charge_a=150, batt_inputs=1, ac_max_a=10, weight_kg=38, **LP3_SG04),
    _inv("DEYE-SUN-8K-SG04LP3-EU", 115, "SUN-8K-SG04LP3-EU  (low voltage)", 1200, kw=8, ds=DS["lp3_sg04"], mppt_strings=[1, 1], i_op=[13, 13], i_sc=[17, 17], max_pv_kw=12.0, charge_a=190, batt_inputs=1, ac_max_a=13.4, weight_kg=38, **LP3_SG04),
    _inv("DEYE-SUN-10K-SG05LP3-EU-SM2", 116, "SUN-10K-SG05LP3-EU  (low voltage)", 1450, kw=10, ds=DS["lp3_sg05"], mppt_strings=[1, 1], i_op=[20, 20], i_sc=[30, 30], max_pv_kw=15.0, charge_a=210, batt_inputs=1, ac_max_a=16.7, weight_kg=35.2, **LP3_SM2_S),
    _inv("DEYE-SUN-12K-SG05LP3-EU-SM2", 117, "SUN-12K-SG05LP3-EU  (low voltage)", 1500, kw=12, ds=DS["lp3_sg05"], mppt_strings=[1, 1], i_op=[20, 20], i_sc=[30, 30], max_pv_kw=18.0, charge_a=240, batt_inputs=1, ac_max_a=20, weight_kg=35.2, **LP3_SM2_S),
    _inv("DEYE-SUN-14K-SG05LP3-EU-SM2", 124, "SUN-14K-SG05LP3-EU  (low voltage)", 1520, kw=14, ds=DS["lp3_14_20"], mppt_strings=[2, 2], i_op=[36, 36], i_sc=[54, 54], max_pv_kw=22.4, charge_a=260, batt_inputs=2, ac_max_a=23.4, weight_kg=51.9, **LP3_SM2_L),
    _inv("DEYE-SUN-15K-SG05LP3-EU-SM2", 347, "SUN-15K-SG05LP3-EU  (low voltage)", 1560, kw=15, ds=DS["lp3_14_20"], mppt_strings=[2, 2], i_op=[36, 36], i_sc=[54, 54], max_pv_kw=24.0, charge_a=280, batt_inputs=2, ac_max_a=25, weight_kg=51.9, **LP3_SM2_L),
    _inv("DEYE-SUN-16K-SG05LP3-EU-SM2", 357, "SUN-16K-SG05LP3-EU  (low voltage)", 1600, kw=16, ds=DS["lp3_14_20"], mppt_strings=[2, 2], i_op=[36, 36], i_sc=[54, 54], max_pv_kw=25.6, charge_a=300, batt_inputs=2, ac_max_a=26.7, weight_kg=51.9, **LP3_SM2_L),
    _inv("DEYE-SUN-18K-SG05LP3-EU-SM2", 358, "SUN-18K-SG05LP3-EU  (low voltage)", 1720, kw=18, ds=DS["lp3_14_20"], mppt_strings=[2, 2], i_op=[36, 36], i_sc=[54, 54], max_pv_kw=28.8, charge_a=330, batt_inputs=2, ac_max_a=30, weight_kg=51.9, **LP3_SM2_L),
    _inv("DEYE-SUN-20K-SG05LP3-EU-SM2", 388, "SUN-20K-SG05LP3-EU  (low voltage)", 1850, kw=20, ds=DS["lp3_14_20"], mppt_strings=[2, 2], i_op=[36, 36], i_sc=[54, 54], max_pv_kw=32.0, charge_a=350, batt_inputs=2, ac_max_a=33.4, weight_kg=51.9, **LP3_SM2_L),
    # ---- three-phase HV (high-voltage battery stack)
    _inv("DEYE-SUN-15K-SG01HP3-EU-AM2", 477, "SUN-15K-SG01HP3 -EU-AM2 (high voltage)", 1100, kw=15, ds=DS["hp3_am2"], mppt_strings=[2, 1], i_op=[26, 20], i_sc=[39, 30], max_pv_kw=24.0, charge_a=37, batt_inputs=1, ac_max_a=25, weight_kg=30.5, **HP3_AM2),
    _inv("DEYE-SUN-20K-SG01HP3-EU-AM2", 482, "SUN-20K-SG01HP3 -EU-AM2 (high voltage)", 1320, kw=20, ds=DS["hp3_am2"], mppt_strings=[2, 2], i_op=[26, 26], i_sc=[39, 39], max_pv_kw=32.0, charge_a=50, batt_inputs=1, ac_max_a=33.4, weight_kg=30.5, **HP3_AM2),
    _inv("DEYE-SUN-25K-SG01HP3-EU-AM2", 483, "SUN-25K-SG01HP3 -EU-AM2 (high voltage)", 1430, kw=25, ds=DS["hp3_am2"], mppt_strings=[2, 2], i_op=[26, 26], i_sc=[39, 39], max_pv_kw=40.0, charge_a=50, batt_inputs=1, ac_max_a=41.7, weight_kg=30.5, **HP3_AM2),
    _inv("DEYE-SUN-30K-SG02HP3-EU-BM3", 484, "SUN-30K-SG02HP3-EU           (high voltage)", 2080, kw=30, ds=DS["hp3_bm"], mppt_strings=[2, 2, 2], i_op=[36, 36, 36], i_sc=[55, 55, 55], max_pv_kw=48.0, charge_a=100, batt_inputs=2, ac_max_a=50, weight_kg=80, **HP3_BM,
         note="Заряден ток 50+50 A (2 батерийни входа)."),
    _inv("DEYE-SUN-35K-SG01HP3-EU-BM3", 487, "SUN-35K-SG01HP3 -EU-BM3 (high voltage)", 2900, kw=35, ds=DS["hp3_bm"], mppt_strings=[2, 2, 2], i_op=[36, 36, 36], i_sc=[55, 55, 55], max_pv_kw=56.0, charge_a=100, batt_inputs=2, ac_max_a=58.4, weight_kg=80, **HP3_BM,
         note="Заряден ток 50+50 A (2 батерийни входа)."),
    _inv("DEYE-SUN-40K-SG01HP3-EU-BM4", 489, "SUN-40K-SG01HP3 -EU-BM4 (high voltage)", 3100, kw=40, ds=DS["hp3_bm"], mppt_strings=[2, 2, 2, 2], i_op=[36, 36, 36, 36], i_sc=[55, 55, 55, 55], max_pv_kw=64.0, charge_a=100, batt_inputs=2, ac_max_a=66.7, weight_kg=80, **HP3_BM,
         note="Заряден ток 50+50 A (2 батерийни входа)."),
    _inv("DEYE-SUN-50K-SG01HP3-EU-BM4", 545, "SUN-50K-SG01HP3-EU-BM4 (high voltage)", 3100, kw=50, ds=DS["hp3_bm"], mppt_strings=[2, 2, 2, 2], i_op=[36, 36, 36, 36], i_sc=[55, 55, 55, 55], max_pv_kw=80.0, charge_a=100, batt_inputs=2, ac_max_a=83.4, weight_kg=80, **HP3_BM,
         note="Заряден ток 50+50 A (2 батерийни входа). Доставната цена (3100 €) е същата като за 40K — проверете."),
    _inv("DEYE-SUN-60K-SG02HP3-EU-EM6", 577, "SUN-60K-SG02HP3-EU-EM6 (high voltage)", 4150, kw=60, ds=DS["hp3_em6"], mppt_strings=[2] * 6, i_op=[36] * 6, i_sc=[54] * 6, max_pv_kw=96.0, charge_a=160, batt_inputs=2, ac_max_a=100, weight_kg=105, **HP3_EM6,
         note="Заряден ток 80+80 A."),
    _inv("DEYE-SUN-70K-SG02HP3-EU-EM6", 578, "SUN-70K-SG02HP3-EU-EM6 (high voltage)", 4280, kw=70, ds=DS["hp3_em6"], mppt_strings=[2] * 6, i_op=[36] * 6, i_sc=[54] * 6, max_pv_kw=112.0, charge_a=160, batt_inputs=2, ac_max_a=116.7, weight_kg=105, **HP3_EM6,
         note="Заряден ток 80+80 A."),
    _inv("DEYE-SUN-80K-SG02HP3-EU-EM6", 579, "SUN-80K-SG02HP3-EU-EM6 (high voltage)", 4350, kw=80, ds=DS["hp3_em6"], mppt_strings=[2] * 6, i_op=[36] * 6, i_sc=[54] * 6, max_pv_kw=128.0, charge_a=160, batt_inputs=2, ac_max_a=133.4, weight_kg=105, **HP3_EM6,
         note="Заряден ток 80+80 A."),
    _inv("DEYE-SUN-100K-SG02HP3-EU-GM8", 580, "SUN-100K-SG02HP3-EU-GM8", 5830, kw=100, ds=DS["hp3_gm"], mppt_strings=[2] * 8, i_op=[42] * 8, i_sc=[63] * 8, max_pv_kw=160.0, charge_a=200, batt_inputs=2, ac_max_a=166.7, **HP3_GM,
         note="Заряден ток 100+100 A."),
    _inv("DEYE-SUN-100K-SG02HP3-EU-GM10", 581, "SUN-100K-SG02HP3-EU-GM10", 6060, kw=100, ds=DS["hp3_gm"], mppt_strings=[2] * 10, i_op=[42] * 10, i_sc=[63] * 10, max_pv_kw=160.0, charge_a=200, batt_inputs=2, ac_max_a=166.7, **HP3_GM,
         note="Заряден ток 100+100 A."),
    _inv("DEYE-SUN-125K-SG02HP3-EU-GM10", 610, "SUN-125K-SG02HP3-EU-GM10", 6100, kw=125, ds=DS["hp3_gm"], mppt_strings=[2] * 10, i_op=[42] * 10, i_sc=[63] * 10, max_pv_kw=200.0, charge_a=200, batt_inputs=2, ac_max_a=204.6, **HP3_GM,
         note="Заряден ток 100+100 A."),
]


def _lv_bat(sku: str, legacy_id: int, name: str, price: float, kwh: float, charge_a: float, parallel: int, ip: str, verified: bool = True) -> dict[str, Any]:
    return {"sku": sku, "legacy_id": legacy_id, "category": "battery", "name": name, "manufacturer": "Deye", "unit": "бр.",
            "purchase_price": price, "markup_pct": 12.0, "warranty": "10 години",
            "specs": {"kwh": kwh, "voltage_class": "LV", "nominal_v": 51.2, "chemistry": "LiFePO4", "max_charge_a": charge_a, "max_parallel": parallel,
                      "stackable": False, "ip": ip, "family": "lv", "specs_verified": verified, "spec_source": "Deye datasheet"}}


BATTERIES_LV: list[dict[str, Any]] = [
    _lv_bat("DEYE-SE-G5.1-PRO-B", 99, "SE - G5.1 Pro-B - 5KWh", 620, 5.12, 100, 64, "IP20"),
    _lv_bat("DEYE-RW-F10.2", 100, "RW-F10.2 (Deye) - 10.2KWh с IP65", 1435.9, 10.24, 198, 32, "IP65"),
    _lv_bat("DEYE-RW-F10.6", 101, "RW-F 10.6 (Deye) - 10.6KWh с IP20", 1384.62, 10.6, 200, 32, "IP20", verified=False),
    _lv_bat("DEYE-SE-F5-PRO-C", 102, "SE-F5 Pro C (5.12kwh low valtage)", 620, 5.12, 100, 32, "IP20"),
    _lv_bat("DEYE-RW-F16", 103, "RW-F16 - 16 kWh  LV Battery", 1550, 16.0, 160, 32, "IP65"),
    _lv_bat("DEYE-SE-F12-C", 104, "SE - F12 C   IP21", 1295, 11.8, 230, 32, "IP21"),
    _lv_bat("DEYE-SE-F12-MAX", 105, "SE-F12 MAX (IP 65, heating function)", 1365, 11.8, 230, 32, "IP65"),
    _lv_bat("DEYE-SE-F16-C", 111, "SE - F16 C   IP21", 1450, 16.0, 160, 32, "IP21"),
    _lv_bat("DEYE-SE-F16-MAX", 112, "SE - F16 MAX IP65", 1600, 16.0, 160, 32, "IP65"),
]

BATTERIES_HV: list[dict[str, Any]] = [
    {"sku": "DEYE-BOS-G-PRO-5.12", "legacy_id": 611, "category": "battery", "name": "Bos-G Pro battery 5,12KWh", "manufacturer": "Deye", "unit": "бр.",
     "purchase_price": 665, "markup_pct": 12.0, "warranty": "10 години",
     "specs": {"kwh": 5.12, "voltage_class": "HV", "nominal_v": 51.2, "module_v_min": 44.0, "module_v_max": 58.4, "series_min": 5, "series_max": 16,
               "stackable": True, "family": "bos_g", "chemistry": "LiFePO4", "max_charge_a": 100, "max_parallel": 16, "ip": "IP20",
               "specs_verified": True, "spec_source": "Deye BOS-G Pro brochure", "datasheet_url": DS["bos_g"]}},
    {"sku": "DEYE-BOS-A-7.68", "legacy_id": 633, "category": "battery", "name": "BOS - A - 7.68 KWh HV Battery", "manufacturer": "Deye", "unit": "бр.",
     "purchase_price": 930, "markup_pct": 12.0, "warranty": "10 години",
     "specs": {"kwh": 7.68, "voltage_class": "HV", "nominal_v": 38.4, "module_v_min": 33.6, "module_v_max": 43.8, "series_min": 7, "series_max": 21,
               "stackable": True, "family": "bos_a", "chemistry": "LiFePO4", "max_charge_a": 100, "max_parallel": 16, "ip": "IP20",
               "recommended_inverter_kw_min": 50,
               "specs_verified": True, "spec_source": "Deye BOS-A manual", "datasheet_url": DS["bos_a"]}},
]


def _acc(sku: str, legacy_id: int, name: str, price: float, role: str, family: str, **spec: Any) -> dict[str, Any]:
    return {"sku": sku, "legacy_id": legacy_id, "category": "battery_accessory", "name": name, "manufacturer": "Deye", "unit": "бр.",
            "purchase_price": price, "markup_pct": 12.0, "warranty": "10 години",
            "specs": {"role": role, "family": family, "specs_verified": True, "spec_source": "Deye", **spec}}


BATTERY_ACCESSORIES: list[dict[str, Any]] = [
    _acc("DEYE-BOS-G-HRACK", 619, "Frame(Rack):  за до 12 батерии + 1 BMS", 250, "hv_rack", "bos_g", capacity=12),
    _acc("DEYE-BOS-G-LRACK", 620, "Frame(Rack):  за до 8 батерии + 1 BMS", 235, "hv_rack", "bos_g", capacity=8),
    _acc("DEYE-BOS-G-PDU", 630, "BMS за до 16 батерии", 620, "hv_bms", "bos_g", max_series=16),
    _acc("DEYE-BOS-A-PDU-2", 63, "High Voltage Control Box for BOS-A", 750, "hv_bms", "bos_a", max_series=21),
    _acc("DEYE-BOS-A-RACK11", 64, "BOS-A-Rack11", 250, "hv_rack", "bos_a", capacity=10),
    _acc("DEYE-BOS-A-RACK14", 65, "BOS-A-Rack14", 297.44, "hv_rack", "bos_a", capacity=13),
]

OTHER: list[dict[str, Any]] = [
    {"sku": "EASTRON-SDM630MCT", "legacy_id": 66, "category": "monitoring", "name": "Трифазен електромер за токов трансформатор SDM630MCT", "manufacturer": "Eastron",
     "unit": "бр.", "purchase_price": 123.08, "markup_pct": 12.0, "warranty": "2 години",
     "specs": {"role": "smart_meter", "phases": 3, "ct": True, "protocol": "Modbus RS485", "specs_verified": True, "spec_source": "Eastron"}},
    {"sku": "DEYE-SUN-EVSE22K01-EU-AC", "legacy_id": 67, "category": "accessory", "name": "SUN-EVSE22K01-EU-AC", "manufacturer": "Deye",
     "unit": "бр.", "purchase_price": 300, "markup_pct": 12.0, "warranty": "2 години",
     "description": "Трифазна зарядна станция за електромобили 22 kW (по избор).",
     "specs": {"role": "ev_charger", "phases": 3, "power_kw": 22, "optional": True, "specs_verified": True, "spec_source": "Deye"}},
    {"sku": "KBE-SOLAR-6MM2", "legacy_id": 68, "category": "solar_cable", "name": "KBE", "manufacturer": "KBE",
     "unit": "м", "purchase_price": 0.95, "markup_pct": 15.0, "description": "Соларен кабел 6 mm² (H1Z2Z2-K).",
     "specs": {"role": "pv_cable", "cross_section_mm2": 6, "specs_verified": True, "spec_source": "KBE"}},
    {"sku": "GMSUN-ACDC-BOARD-1P", "legacy_id": 325, "category": "switchboard", "name": "Оборудвано AC/DC ел табло Монофазно", "manufacturer": "GM SUN",
     "unit": "бр.", "purchase_price": 160, "markup_pct": 15.0,
     "description": "Окомплектовано AC/DC табло: DC и AC защити (прекъсвачи, ДТЗ, катодни отводители), клеми и заземителна шина.",
     "specs": {"role": "switchboard", "phases": 1, "covers_roles": ["ac_mcb", "ac_rcd", "ac_spd", "dc_spd", "dc_isolator", "dc_fuse", "dc_fuse_holder", "dc_enclosure", "ac_enclosure", "earth_bar", "labels", "cable_gland"]}},
    {"sku": "GMSUN-ACDC-BOARD-3P", "legacy_id": 326, "category": "switchboard", "name": "Оборудвано AC/DC ел табло Трифазно", "manufacturer": "GM SUN",
     "unit": "бр.", "purchase_price": 220, "markup_pct": 15.0,
     "description": "Окомплектовано AC/DC табло: DC и AC защити (прекъсвачи, ДТЗ, катодни отводители), клеми и заземителна шина.",
     "specs": {"role": "switchboard", "phases": 3, "covers_roles": ["ac_mcb", "ac_rcd", "ac_spd", "dc_spd", "dc_isolator", "dc_fuse", "dc_fuse_holder", "dc_enclosure", "ac_enclosure", "earth_bar", "labels", "cable_gland"]}},
]


def _panel(sku: str, legacy_id: int, name: str, mfr: str, price: float, **spec: Any) -> dict[str, Any]:
    return {"sku": sku, "legacy_id": legacy_id, "category": "panel", "name": name, "manufacturer": mfr, "unit": "бр.",
            "purchase_price": price, "markup_pct": 15.0, "warranty": spec.pop("warranty", "15 г. продукт / 30 г. мощност"),
            "specs": {**spec, "specs_verified": True, "spec_source": f"{mfr} datasheet"}}


PANELS: list[dict[str, Any]] = [
    _panel("LONGI-LR7-54HVH-485M", 69, "Longi Solar Himo 10 485Wp, HVH", "LONGi", 67.42, wp=485, voc=40.40, isc=15.23, vmp=33.40, imp=14.53,
           efficiency=23.8, width_mm=1134, height_mm=1800, thickness_mm=30, weight_kg=21.6, temp_coeff_voc=-0.20, temp_coeff_pmax=-0.26, max_series_fuse_a=30,
           model="LR7-54HVH-485M", cell="HPBC 2.0 (back-contact)", datasheet_url=DS["longi_54"]),
    _panel("LONGI-LR7-72HVH-650M", 322, "Longi Solar Himo 10 - 650Wp, HVH", "LONGi", 83.2, wp=650, voc=53.9, isc=15.29, vmp=44.56, imp=14.59,
           efficiency=24.1, width_mm=1134, height_mm=2382, thickness_mm=30, weight_kg=31.8, temp_coeff_voc=-0.20, temp_coeff_pmax=-0.26, max_series_fuse_a=30,
           model="LR7-72HVH-650M", cell="HPBC 2.0 (back-contact)", datasheet_url=DS["longi_54"]),
    _panel("SUNTECH-STP455S-H48-NKH", 323, "Suntech STP455S-H48-Nkh", "Suntech", 55.51, wp=455, voc=35.92, isc=16.09, vmp=29.49, imp=15.43,
           efficiency=22.8, width_mm=1134, height_mm=1762, thickness_mm=30, temp_coeff_voc=-0.25, temp_coeff_pmax=-0.29, max_series_fuse_a=35,
           model="STP455S-H48/Nkh", datasheet_url=DS["suntech"]),
    _panel("SUNTECH-STP455S-I54-NTH-B", 324, "Suntech STP455 S-I54-Nth+ Black Frame", "Suntech", 56.88, wp=455, voc=39.57, isc=14.52, vmp=32.90, imp=13.83,
           efficiency=22.8, width_mm=1134, height_mm=1762, thickness_mm=30, temp_coeff_voc=-0.24, temp_coeff_pmax=-0.29, max_series_fuse_a=25,
           model="STP455S-I54/Nth+", datasheet_url=DS["suntech"]),
]

ITEMS: list[dict[str, Any]] = INVERTERS + BATTERIES_LV + BATTERIES_HV + BATTERY_ACCESSORIES + OTHER + PANELS

# Labor matrix (days × workers → EUR ex VAT) – kept for the execution time and the matrix pricing mode.
LABOR: list[tuple[int, int, float]] = [
    (1, 2, 1100.0), (1, 3, 1500.0), (2, 2, 1600.0), (2, 3, 3000.0), (3, 2, 2300.0), (3, 3, 3300.0), (3, 4, 4200.0),
    (4, 3, 4300.0), (5, 3, 5200.0), (5, 4, 6800.0), (7, 4, 9200.0), (10, 4, 12800.0),
]

# Construction is priced per module (lump) – there are no individual mounting articles in the final catalog.
ROOF_LUMP: dict[str, float] = {
    "tile": 124, "tile_xt": 118, "tile_xtr": 128, "plain_tile": 126, "lt_sheet": 62, "lt_sheet_ts": 58, "standing_seam": 72,
    "sandwich": 84, "fibre_cement": 80, "flat_concrete": 95, "flat_ew": 88, "flat_bifacial": 120, "ground_ballast": 125, "ground": 83,
}

SETTINGS: dict[str, dict[str, Any]] = {
    "company": {"name": "GM SUN SYSTEM SOLAR Ltd", "address": "ул. Седянка 14, 7500 Силистра, България", "email": "m_v_stefanov_@abv.bg", "signatory": "инж. Мирослав Стефанов"},
    "pricing": {
        "vat_pct": 20.0, "default_markup_pct": 10.0, "min_margin_pct": 10.0, "default_advance_pct": 70, "quote_validity_days": 10,
        "delivery_fee_equipment": 200.0, "delivery_fee_inverter": 60.0, "delivery_fee_construction": 40.0, "install_price_per_w": 0.118,
        "labor_eur_per_inverter_kw": 118.0, "labor_mode_default": "per_inverter_kw",
        "specific_yield_kwh_per_kwp": 1250, "dc_ac_ratio_max": 1.35, "cable_margin_pct": 15.0, "fastener_margin_pct": 10.0, "module_spare_pct": 0.0,
        "design_tmin_c": -20.0, "design_tcell_max_c": 70.0, "voc_margin": 0.97, "dc_vdrop_max_pct": 1.0, "ac_vdrop_max_pct": 1.0,
        "dc_run_default_m": 15.0, "ac_run_default_m": 10.0, "dc_box_distance_m": 10.0,
    },
    "procurement": {"price_max_age_days": 120, "tier_economy_max": 0.38, "tier_premium_min": 0.62, "balanced_eur_per_day": 25, "fastest_max_days": 10,
                    "max_parallel_inverters": 6, "min_parallel_unit_kw": 8, "bos_per_module_eur": 55},
}
