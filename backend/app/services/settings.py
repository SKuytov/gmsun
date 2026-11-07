from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Setting

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "company": {
        "name": "GM SUN SYSTEM SOLAR Ltd",
        "address": "ул. Седянка 14, 7500 Силистра, България",
        "eik": "",
        "vat_no": "",
        "phone": "",
        "email": "m_v_stefanov_@abv.bg",
        "website": "",
        "signatory": "инж. Мирослав Стефанов",
        "logo_path": None,
        "bank": "",
        "iban": "",
    },
    "pricing": {
        "currency": "EUR",
        "vat_pct": 20.0,
        "default_markup_pct": 10.0,
        "advance_options": [60, 70, 80],
        "default_advance_pct": 70,
        "quote_validity_days": 10,
        "show_unit_prices_client": False,
        "client_pdf_collapse_construction": True,
        "advance_basis": "net",
        "delivery_fee_equipment": 200.0,
        "delivery_fee_inverter": 60.0,
        "delivery_fee_construction": 40.0,
        "install_price_per_w": 0.118,
        "specific_yield_kwh_per_kwp": 1250,
        "dc_ac_ratio_max": 1.35,
        "quote_number_prefix": "",
        # --- engineering defaults (industry practice; editable) ---
        "cable_margin_pct": 15.0,  # cable reserve for routing, terminations and bends
        "fastener_margin_pct": 10.0,  # screws/clamps/clips/ties loss & breakage reserve
        "module_spare_pct": 0.0,  # spare modules ordered with the project
        "design_tmin_c": -20.0,  # minimum ambient (Voc check) – Bulgaria lowland winter
        "design_tcell_max_c": 70.0,  # max cell temperature (Vmp check)
        "dc_vdrop_max_pct": 1.0,  # DC voltage drop target
        "ac_vdrop_max_pct": 1.0,  # AC voltage drop target inverter -> board
        "dc_run_default_m": 15.0,  # one-way array -> inverter distance
        "ac_run_default_m": 10.0,  # one-way inverter -> main board distance
        "dc_box_distance_m": 10.0,  # array SPD required beyond this (IEC 61643-32)
    },
    "texts": {
        "quote_title": "ДОСТАВКА И МОНТАЖ НА ОБОРУДВАНЕ ЗА ФОТОВОЛТАИЧНА ЦЕНТРАЛА",
        "warranty": "1. Гаранция на носеща конструкция: 60 месеца.\n2. Гаранция на инвертор и батерии: 10 години (производител).\n3. Гаранция на фотоволтаични модули: 15 години продуктова, 30 години линейна за мощност.",
        "notes": "1. Офертата е валидна за оборудването, описано в нея.\n2. Разположението на модулите ще бъде по предварително уточнена схема.\n3. Всички цени са в EUR.",
        "payment": "1. Аванс при подписване на договор.\n2. Остатък след монтаж и пуск на централата.",
    },
}


def get_setting(db: Session, key: str) -> dict[str, Any]:
    row = db.get(Setting, key)
    base = dict(DEFAULT_SETTINGS.get(key, {}))
    if row and row.value:
        base.update(row.value)
    return base


def set_setting(db: Session, key: str, value: dict[str, Any]) -> dict[str, Any]:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        merged = dict(row.value or {})
        merged.update(value)
        row.value = merged
    db.commit()
    db.refresh(row)
    return get_setting(db, key)
