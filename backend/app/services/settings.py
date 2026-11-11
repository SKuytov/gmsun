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
        "min_margin_pct": 10.0,
        "advance_options": [60, 70, 80],
        "default_advance_pct": 70,
        "quote_validity_days": 10,
        "show_unit_prices_client": False,
        "client_pdf_collapse_construction": True,
        "advance_basis": "net",
        "include_delivery_fees": False,  # GM SUN: delivery fees are not quoted (per-quote switch can still add them)
        "delivery_fee_equipment": 200.0,
        "delivery_fee_inverter": 60.0,
        "delivery_fee_construction": 40.0,
        "install_price_per_w": 0.118,
        "labor_eur_per_inverter_kw": 118.0,  # Труд (СМР) = inverter AC kW × this rate (default labor mode)
        "labor_mode_default": "per_inverter_kw",  # per_inverter_kw | matrix | per_w | manual
        "specific_yield_kwh_per_kwp": 1250,
        "dc_ac_ratio_max": 1.35,
        "quote_number_prefix": "",
        # --- engineering defaults (industry practice; editable) ---
        "cable_margin_pct": 15.0,  # cable reserve for routing, terminations and bends
        "fastener_margin_pct": 10.0,  # screws/clamps/clips/ties loss & breakage reserve
        "module_spare_pct": 0.0,  # spare modules ordered with the project
        "design_tmin_c": -20.0,  # minimum ambient (Voc check) – Bulgaria lowland winter
        "design_tcell_max_c": 70.0,  # max cell temperature (Vmp check)
        "voc_margin": 0.97,  # Voc(cold) must stay below this share of the inverter's max DC voltage
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
        "intro": "Благодарим Ви за интереса към GM SUN SYSTEM SOLAR. Въз основа на данните за обекта и потреблението Ви подготвихме следното предложение за доставка и монтаж на фотоволтаична централа. Всички позиции са описани в приложената спецификация и могат да бъдат уточнени според Вашите предпочитания.",
        "closing": "Оставаме на разположение за въпроси и безплатен оглед на място.",
        "order_note": "Моля, потвърдете поръчката с номер и срок на доставка. Доставката да е придружена от приемо-предавателен протокол и сертификати/декларации за съответствие на продуктите.",
        "rfq_note": "Моля, потвърдете наличност, цена и срок на доставка за посочените позиции. При липса на точен артикул предложете еквивалент със същите технически параметри.",
    },
    # Procurement: who we order from and how long it takes (working days). Item-level lead time overrides the
    # supplier default; items marked as back-order at the supplier get at least ``backorder_lead_time_days``.
    "suppliers": {
        "list": [
            {"name": "green-energy.bg", "contact": "", "email": "", "phone": "", "url": "https://green-energy.bg", "lead_time_days": 3,
             "notes": "Инвертори, батерии, модули и аксесоари – наличните на склад артикули се доставят за 1–3 работни дни."},
            {"name": "Aerocompact", "contact": "", "email": "", "phone": "", "url": "https://www.aerocompact.com", "lead_time_days": 15,
             "notes": "Монтажни системи – поръчка през дистрибутор, обичайно 2–3 седмици."},
        ],
        "default_lead_time_days": 7,
        "backorder_lead_time_days": 21,
        "delivery_address": "",  # empty → company address is used in RFQ documents
    },
    # Automatic tier classification (economy / standard / premium) and proposal engine weights.
    # Set by datafill.fill_missing() once the demo dataset has been completed (prevents re-running on every start).
    "datafill": {"done": False, "at": None, "stats": {}},
    "procurement": {
        "price_max_age_days": 120,
        "brand_tiers": {
            "premium": ["Huawei", "SMA", "Fronius", "Sungrow", "LONGi", "AIKO", "Jinko", "JA Solar", "BYD", "Aerocompact", "Victron", "Tesla"],
            "economy": ["Deye", "Solis", "Luxpower", "Felicity", "Dyness", "Tongwei", "Canadian", "Risen", "Pylontech", "Must", "Growatt"],
        },
        "tier_weights": {"price": 0.6, "brand": 0.25, "quality": 0.15},
        "tier_economy_max": 0.38,
        "tier_premium_min": 0.62,
        # Balanced strategy: how much a day of lead time "costs" when ranking alternatives (EUR/day) and the maximum
        # acceptable lead time for the Fastest strategy before falling back to the next quickest option.
        "balanced_eur_per_day": 25.0,
        "fastest_max_days": 10,
        "candidate_panels": 6,  # how many panel models to evaluate per strategy (top-N by that strategy's ranking)
        "candidate_inverters": 4,
        "max_parallel_inverters": 6,  # largest number of identical inverters the proposal engine will put in parallel
        "min_parallel_unit_kw": 8,  # smallest inverter (kW AC) that may be proposed in parallel operation
        "candidate_batteries": 3,
        # Module recommendation: mounting + labour cost per module (EUR) added to the module price when comparing
        # €/Wp between formats (makes 450 Wp modules dearer per Wp than 600 Wp ones on an open roof).
        "bos_per_module_eur": 55.0,
    },
}


def get_setting(db: Session, key: str) -> dict[str, Any]:
    row = db.get(Setting, key)
    base = dict(DEFAULT_SETTINGS.get(key, {}))
    if row and row.value:
        base.update(row.value)
    return base


def set_setting(db: Session, key: str, value: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
    row = db.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value)
        db.add(row)
    else:
        merged = dict(row.value or {})
        merged.update(value)
        row.value = merged
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return get_setting(db, key)
