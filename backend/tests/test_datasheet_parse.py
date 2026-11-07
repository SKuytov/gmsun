"""Datasheet / supplier-portfolio parsing (green-energy.bg import)."""
from app.services import datasheet_parse as dp
from app.services.supplier_sync import _sanitize_battery, build_items, expand_models, gmsun_category, price_eur, title_wp

PANEL_TXT = """ULICA SOLAR N-TYPE TOPCON BIFACIAL
Electrical Characteristics (STC)
Model UL-570M-144HV UL-575M-144HV UL-580M-144HV
Maximum Power (Pmax) [W] 570 575 580
Open Circuit Voltage (Voc) [V] 51.2 51.4 51.6
Short Circuit Current (Isc) [A] 14.1 14.2 14.3
Voltage at Maximum Power (Vmp) [V] 42.6 42.8 43.0
Current at Maximum Power (Imp) [A] 13.38 13.44 13.49
Module Efficiency [%] 22.07 22.26 22.45
Temperature Coefficient of Pmax -0.29 %/°C
Temperature Coefficient of Voc -0.25 %/°C
Temperature Coefficient of Isc 0.045 %/°C
Maximum System Voltage 1500 V
Maximum Series Fuse Rating 25 A
Dimensions 2278 x 1134 x 35 mm
Weight 32.5 kg
"""


def test_parse_panel_multi_column_datasheet():
    cols = dp.parse_panel(PANEL_TXT)
    assert [c["wp"] for c in cols] == [570, 575, 580]
    c = cols[1]
    assert (c["voc"], c["isc"], c["vmp"], c["imp"]) == (51.4, 14.2, 42.8, 13.44)
    assert (c["width_mm"], c["height_mm"], c["thickness_mm"], c["weight_kg"]) == (1134, 2278, 35, 32.5)
    assert c["max_system_v"] == 1500 and c["max_series_fuse_a"] == 25
    assert c["temp_coeff_voc"] == -0.25 and c["temp_coeff_pmax"] == -0.29
    assert c["specs_verified"] is False and c["spec_source"].startswith("datasheet")


def test_parse_panel_ignores_ocr_garbage_and_noct_columns():
    txt = PANEL_TXT + "\nElectrical Characteristics (NOCT)\nMaximum Power (Pmax) [W] 425 428 432\nOpen Circuit Voltage (Voc) [V] 48.1 48.3 48.5\n"
    cols = dp.parse_panel(txt)
    assert [c["wp"] for c in cols] == [570, 575, 580]  # STC kept, NOCT ignored
    assert cols[0]["voc"] == 51.2
    ocr = "Model 570 425 575 428 580 432 jbouiel oo LO \\ 500\nMaximum Power (Pmax) [W] 570 425 575 428 580 432\nOpen Circuit Voltage (Voc) [V] 51.2 48.1 51.4 48.3 51.6 48.5\n"
    cols = dp.parse_panel(ocr)
    assert all(400 <= c["wp"] <= 800 for c in cols)
    assert all(c.get("voc") is None or 30 <= c["voc"] <= 70 for c in cols)


def test_bulgarian_description_parser():
    sp = dp.parse_bg_description(
        "inverter",
        "Максимална PV входна мощност: 15 000Wp\nМакс. входно DC напрежение: 1.100 V\nНоминална изходна мощност: 10 kW\n2 независими MPP тракера\nДиапазон на батерията: 40-60 V",
    )
    assert sp["max_pv_kw"] == 15.0
    assert sp["max_dc_voltage"] == 1100
    assert sp["ac_power_kw"] == 10
    assert sp["mppt_count"] == 2
    assert (sp["battery_v_min"], sp["battery_v_max"], sp["battery_voltage_class"], sp["hybrid"]) == (40, 60, "LV", True)


def test_model_expansion_and_kw():
    assert expand_models("Deye SUN-14/15/16/18/20K-SG05LP3-EU-SM2") == [f"SUN-{k}K-SG05LP3-EU-SM2" for k in (14, 15, 16, 18, 20)]
    assert expand_models("SUNGROW SG 15 RT / SG 17 RT / SG 20 RT") == ["SG15RT", "SG17RT", "SG20RT"]
    assert dp.model_kw("SUN-12K-SG04LP3-EU") == 12
    assert dp.model_kw("SG10RT") == 10
    assert dp.model_kw("SH5.0RT") == 5
    assert dp.model_kw("S6-EH3P(10KW)") == 10
    assert title_wp("Фотоволтаичен панел - Ulica solar 575 Wp N TYPE TOPCON BIFACIAL") == [575]


def test_sanitize_battery_drops_cell_voltage():
    sp = {"kwh": 16.0, "nominal_v": 3.2, "voltage_class": "LV"}
    _sanitize_battery(sp, "Deye RW-F16")
    assert sp["nominal_v"] == 51.2 and sp["voltage_class"] == "LV" and sp["ah"] == 312


def _product(**kw):
    base = {
        "id": 1,
        "name": "Фотоволтаичен панел - Ulica solar 575 Wp N TYPE TOPCON BIFACIAL",
        "permalink": "https://green-energy.bg/produkt/fotovoltaichen-panel-ulica-solar-575-wp-n-type-topcon-bifacial/",
        "sku": "",
        "description": "<p>Датшийт: <a href='https://green-energy.bg/wp-content/uploads/2024/02/ulica.pdf'>PDF</a></p>",
        "short_description": "",
        "categories": [{"name": "Фотоволтаични панели", "slug": "fotovoltaichni-paneli"}],
        "images": [{"src": "https://green-energy.bg/wp-content/uploads/img.jpg"}],
        "prices": {"price": "0", "regular_price": "0", "currency_code": "BGN", "currency_minor_unit": 2},
        "attributes": [],
    }
    base.update(kw)
    return base


def test_build_items_from_store_product():
    p = _product()
    assert gmsun_category(p) == "panel"
    assert price_eur(p) == (0.0, 0.0)
    items = build_items([p], datasheet_text=lambda url: PANEL_TXT if url.endswith("ulica.pdf") else "")
    assert len(items) == 1
    it = items[0]
    assert it["category"] == "panel" and it["manufacturer"]
    sp = it["specs"]
    assert sp["supplier"] == "green-energy.bg"
    assert sp["product_url"].startswith("https://green-energy.bg/produkt/")
    assert sp["datasheet_url"].endswith("ulica.pdf")
    assert sp["image_url"].endswith("img.jpg")
    assert sp["wp"] == 575 and sp["voc"] == 51.4  # the 575 W column was picked from the 570/575/580 sheet
    assert sp["specs_verified"] is False

    inv = _product(
        id=2,
        name="Deye SUN-14/15/16/18/20K-SG05LP3-EU-SM2 трифазен хибриден инвертор",
        categories=[{"name": "Хибридни инвертори", "slug": "hibridni-invertori"}],
        prices={"price": "391166", "regular_price": "391166", "currency_code": "BGN", "currency_minor_unit": 2},
        description="",
    )
    items = build_items([inv])
    assert len(items) == 5, [i["name"] for i in items]
    kws = sorted(i["specs"]["ac_power_kw"] for i in items)
    assert kws == [14, 15, 16, 18, 20]
    assert all(i["category"] == "inverter" and i["specs"]["phases"] == 3 for i in items)
    assert abs(items[0]["purchase_price"] - 3911.66 / 1.95583) < 0.01
