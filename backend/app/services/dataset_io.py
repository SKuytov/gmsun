"""Whole-dataset Excel round trip.

Export: one workbook with a sheet per editable table (or a .zip with one workbook per table). Row 1 carries the
stable technical column keys (small grey text), row 2 the Bulgarian labels, data starts at row 3. Import accepts
exactly those files back (.xlsx or .zip of .xlsx), matches rows by primary key (``id`` / ``code`` / supplier name /
setting path), updates only cells that are filled in and creates rows that have no key. Empty cells never erase
data; the literal ``-`` (dash) clears a field on purpose.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Callable

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from ..models import CATEGORIES, MOUNTING_BASES, TIERS, CatalogItem, LaborOption, MountingRule, RoofTypeConfig
from .settings import DEFAULT_SETTINGS, get_setting, set_setting
from .workbooks import BORDER, F_BODY, F_HEAD, FILL_HEAD, MUTED, NAVY

CLEAR = "-"
F_KEY = Font(name="Calibri", size=8, color=MUTED, italic=True)
F_TITLE = Font(name="Calibri", size=14, bold=True, color=NAVY)
FILL_RO = PatternFill("solid", fgColor="F3F4F6")
FILL_REQ = PatternFill("solid", fgColor="FFFBEB")

Column = tuple[str, str, str]  # key, Bulgarian label, kind: text|int|num|bool|json|ro(readonly)

SPEC_COLUMNS: list[Column] = [
    ("stock_status", "Наличност (instock/backorder/outofstock)", "text"),
    ("price_source", "Източник на цената", "text"),
    ("wp", "Мощност Wp (панел)", "num"), ("voc", "Voc V", "num"), ("isc", "Isc A", "num"), ("vmp", "Vmp V", "num"), ("imp", "Imp A", "num"),
    ("efficiency", "КПД %", "num"), ("width_mm", "Ширина mm", "num"), ("height_mm", "Височина mm", "num"), ("weight_kg", "Тегло kg", "num"),
    ("bifaciality", "Бифациалност", "num"),
    ("ac_power_kw", "AC мощност kW (инвертор)", "num"), ("phases", "Фази", "int"), ("hybrid", "Хибриден (да/не)", "bool"),
    ("battery_voltage_class", "Клас батерия LV/HV", "text"), ("max_pv_kw", "Макс. PV kW", "num"), ("mppt_count", "Брой MPPT", "int"),
    ("kwh", "Капацитет kWh (батерия)", "num"), ("voltage_class", "Клас напрежение LV/HV", "text"), ("nominal_v", "Номинално V", "num"),
    ("cycles", "Цикли", "int"), ("chemistry", "Химия", "text"), ("max_parallel", "Макс. паралел", "int"),
    ("product_url", "Линк към продукта", "text"), ("datasheet_url", "Линк към datasheet", "text"),
]
SPEC_KEYS = {k for k, _, _ in SPEC_COLUMNS}

CATALOG_COLUMNS: list[Column] = [
    ("id", "ID (не променяйте)", "ro"), ("active", "Активен (да/не)", "bool"), ("category", "Категория", "text"), ("sku", "Код (SKU)", "text"),
    ("name", "Наименование", "text"), ("manufacturer", "Производител", "text"), ("description", "Описание", "text"), ("unit", "Мярка", "text"),
    ("purchase_price", "Доставна цена EUR (без ДДС)", "num"), ("markup_pct", "Надценка % (празно = по подразбиране)", "num"),
    ("sell_price", "Фиксирана продажна цена EUR", "num"), ("warranty", "Гаранция", "text"), ("supplier", "Доставчик", "text"),
    ("supplier_sku", "Код при доставчика", "text"), ("lead_time_days", "Срок на доставка (работни дни)", "int"),
    ("tier", "Клас (economy/standard/premium)", "text"), ("sort_order", "Подредба", "int"),
    *SPEC_COLUMNS,
    ("specs_json", "Всички спецификации (JSON, за напреднали)", "json"),
]
LABOR_COLUMNS: list[Column] = [("id", "ID (не променяйте)", "ro"), ("active", "Активен (да/не)", "bool"), ("days", "Дни", "int"), ("workers", "Работници", "int"),
                               ("price", "Цена EUR (без ДДС)", "num"), ("description", "Описание", "text")]
ROOF_COLUMNS: list[Column] = [("code", "Код (ключ, не променяйте)", "ro"), ("active", "Активен (да/не)", "bool"), ("label_bg", "Наименование BG", "text"),
                              ("label_en", "Наименование EN", "text"), ("pricing_mode", "Ценообразуване (detailed/lump)", "text"),
                              ("lump_price_per_module", "Цена конструкция EUR/модул (lump)", "num"), ("rails_per_module", "Релси на модул", "int"),
                              ("rail_stock_length_m", "Дължина релса m", "num"), ("fixation_spacing_m", "Стъпка закрепване m", "num"),
                              ("waste_pct", "Фира %", "num"), ("default_tilt_deg", "Наклон по подразбиране °", "num"), ("notes", "Бележки", "text"),
                              ("sort_order", "Подредба", "int")]
RULE_COLUMNS: list[Column] = [("id", "ID (не променяйте)", "ro"), ("active", "Активен (да/не)", "bool"), ("roof_type", "Тип покрив (код)", "text"),
                              ("catalog_item_id", "ID артикул", "int"), ("catalog_item_name", "Артикул (информативно)", "ro"), ("name", "Име на правилото", "text"),
                              ("basis", "База (" + "/".join(MOUNTING_BASES) + ")", "text"), ("factor", "Коефициент", "num"), ("round_up", "Закръгляне нагоре (да/не)", "bool"),
                              ("notes", "Бележки", "text"), ("sort_order", "Подредба", "int")]
SUPPLIER_COLUMNS: list[Column] = [("name", "Доставчик (ключ)", "text"), ("contact", "Лице за контакт", "text"), ("email", "E-mail", "text"), ("phone", "Телефон", "text"),
                                  ("url", "Уебсайт", "text"), ("lead_time_days", "Срок на доставка по подразбиране (дни)", "int"), ("notes", "Бележки", "text")]
SETTING_COLUMNS: list[Column] = [("path", "Настройка (ключ, не променяйте)", "ro"), ("value", "Стойност", "text"), ("type", "Тип", "ro"), ("hint", "Описание", "ro")]

SETTING_HINTS = {
    "company.name": "Име на фирмата в документите", "company.address": "Адрес", "company.eik": "ЕИК", "company.vat_no": "ДДС номер",
    "company.phone": "Телефон", "company.email": "E-mail", "company.website": "Уебсайт", "company.signatory": "Подписващ офертите",
    "company.bank": "Банка", "company.iban": "IBAN",
    "pricing.vat_pct": "ДДС %", "pricing.default_markup_pct": "Надценка по подразбиране %", "pricing.min_margin_pct": "Минимален марж % (проверка на офертата)",
    "procurement.price_max_age_days": "Макс. възраст на цена (дни) преди предупреждение", "texts.order_note": "Текст в поръчките към доставчици", "pricing.default_advance_pct": "Аванс по подразбиране %",
    "pricing.quote_validity_days": "Валидност на офертата (дни)", "pricing.delivery_fee_equipment": "Такса доставка оборудване EUR",
    "pricing.delivery_fee_inverter": "Такса доставка инвертор EUR", "pricing.delivery_fee_construction": "Такса доставка конструкция EUR",
    "pricing.install_price_per_w": "Монтаж EUR/W (ориентир)", "pricing.specific_yield_kwh_per_kwp": "Специфичен добив kWh/kWp/год.",
    "pricing.dc_ac_ratio_max": "Макс. DC/AC", "pricing.cable_margin_pct": "Резерв кабели %", "pricing.fastener_margin_pct": "Резерв крепежи %",
    "pricing.module_spare_pct": "Резервни модули %", "pricing.design_tmin_c": "Мин. температура °C (Voc)", "pricing.design_tcell_max_c": "Макс. темп. клетка °C", "pricing.voc_margin": "Резерв Voc спрямо макс. DC (0–1)",
    "pricing.dc_vdrop_max_pct": "Макс. пад DC %", "pricing.ac_vdrop_max_pct": "Макс. пад AC %", "pricing.dc_run_default_m": "DC трасе по подразбиране m",
    "pricing.ac_run_default_m": "AC трасе по подразбиране m", "pricing.dc_box_distance_m": "Разстояние за DC SPD m",
    "suppliers.default_lead_time_days": "Срок по подразбиране (дни)", "suppliers.backorder_lead_time_days": "Срок при backorder (дни)",
    "suppliers.delivery_address": "Адрес за доставка в RFQ", "procurement.balanced_eur_per_day": "Цена на ден закъснение EUR (балансирано)",
    "procurement.fastest_max_days": "Макс. срок за 'най-бързо' (дни)", "procurement.tier_economy_max": "Праг economy (0–1)",
    "procurement.tier_premium_min": "Праг premium (0–1)", "procurement.max_parallel_inverters": "Макс. брой инвертори в паралел (предложения)", "procurement.min_parallel_unit_kw": "Мин. мощност на инвертор за паралелна работа, kW",
}
SETTING_SKIP = {"company.logo_path", "pricing.advance_options", "pricing.currency", "pricing.show_unit_prices_client", "pricing.include_delivery_fees", "pricing.client_pdf_collapse_construction",
                "pricing.advance_basis", "pricing.quote_number_prefix", "suppliers.list", "procurement.brand_tiers", "procurement.tier_weights",
                "procurement.candidate_panels", "procurement.candidate_inverters", "procurement.candidate_batteries"}

TABLES: dict[str, dict[str, Any]] = {
    "catalog_items": {"title": "Артикули", "file": "01_artikuli_catalog_items.xlsx", "columns": CATALOG_COLUMNS, "key": "id"},
    "labor_options": {"title": "Труд", "file": "02_trud_labor_options.xlsx", "columns": LABOR_COLUMNS, "key": "id"},
    "roof_types": {"title": "Типове покриви", "file": "03_pokrivi_roof_types.xlsx", "columns": ROOF_COLUMNS, "key": "code"},
    "mounting_rules": {"title": "Правила конструкция", "file": "04_pravila_mounting_rules.xlsx", "columns": RULE_COLUMNS, "key": "id"},
    "suppliers": {"title": "Доставчици", "file": "05_dostavchici_suppliers.xlsx", "columns": SUPPLIER_COLUMNS, "key": "name"},
    "settings": {"title": "Настройки", "file": "06_nastroyki_settings.xlsx", "columns": SETTING_COLUMNS, "key": "path"},
}
TITLE_TO_TABLE = {v["title"]: k for k, v in TABLES.items()}


# ------------------------------------------------------------------------------------------------- export
def _bool_out(v: Any) -> str | None:
    if v is None:
        return None
    return "да" if bool(v) else "не"


def _rows_catalog(db: Session) -> list[dict[str, Any]]:
    out = []
    for it in db.query(CatalogItem).order_by(CatalogItem.category, CatalogItem.sort_order, CatalogItem.id).all():
        sp = dict(it.specs or {})
        row = {k: getattr(it, k) for k, _, _ in CATALOG_COLUMNS if hasattr(it, k)}
        for k in SPEC_KEYS:
            row[k] = sp.get(k)
        row["specs_json"] = json.dumps(sp, ensure_ascii=False, sort_keys=True) if sp else None
        out.append(row)
    return out


def _rows_labor(db: Session) -> list[dict[str, Any]]:
    return [{k: getattr(o, k) for k, _, _ in LABOR_COLUMNS} for o in db.query(LaborOption).order_by(LaborOption.days, LaborOption.workers).all()]


def _rows_roofs(db: Session) -> list[dict[str, Any]]:
    return [{k: getattr(o, k) for k, _, _ in ROOF_COLUMNS} for o in db.query(RoofTypeConfig).order_by(RoofTypeConfig.sort_order, RoofTypeConfig.code).all()]


def _rows_rules(db: Session) -> list[dict[str, Any]]:
    out = []
    for r in db.query(MountingRule).order_by(MountingRule.roof_type, MountingRule.sort_order, MountingRule.id).all():
        row = {k: getattr(r, k) for k, _, _ in RULE_COLUMNS if hasattr(r, k)}
        row["catalog_item_name"] = r.item.name if r.item else None
        out.append(row)
    return out


def _rows_suppliers(db: Session) -> list[dict[str, Any]]:
    return [{k: s.get(k) for k, _, _ in SUPPLIER_COLUMNS} for s in (get_setting(db, "suppliers").get("list") or [])]


def _rows_settings(db: Session) -> list[dict[str, Any]]:
    out = []
    for group in ("company", "pricing", "suppliers", "procurement", "texts"):
        cfg = get_setting(db, group)
        for k, default in DEFAULT_SETTINGS.get(group, {}).items():
            path = f"{group}.{k}"
            if path in SETTING_SKIP or isinstance(default, (dict, list)):
                continue
            v = cfg.get(k, default)
            typ = "число" if isinstance(default, (int, float)) and not isinstance(default, bool) else "да/не" if isinstance(default, bool) else "текст"
            out.append({"path": path, "value": v, "type": typ, "hint": SETTING_HINTS.get(path, "")})
    return out


ROW_SOURCES: dict[str, Callable[[Session], list[dict[str, Any]]]] = {
    "catalog_items": _rows_catalog, "labor_options": _rows_labor, "roof_types": _rows_roofs, "mounting_rules": _rows_rules,
    "suppliers": _rows_suppliers, "settings": _rows_settings,
}


def _write_sheet(ws: Worksheet, table: str, rows: list[dict[str, Any]]) -> None:
    cols: list[Column] = TABLES[table]["columns"]
    ws.title = TABLES[table]["title"]
    ws.freeze_panes = "B3"
    for ci, (key, label, kind) in enumerate(cols, 1):
        k = ws.cell(row=1, column=ci, value=key)
        k.font = F_KEY
        k.alignment = Alignment(horizontal="left")
        h = ws.cell(row=2, column=ci, value=label)
        h.font = F_HEAD
        h.fill = FILL_HEAD
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        h.border = BORDER
        width = {"id": 8, "code": 16, "active": 9, "category": 16, "sku": 22, "name": 58, "manufacturer": 16, "description": 30, "unit": 7,
                 "purchase_price": 14, "warranty": 24, "supplier": 22, "lead_time_days": 11, "tier": 12, "specs_json": 60, "product_url": 40,
                 "datasheet_url": 40, "path": 34, "value": 60, "hint": 40, "notes": 40, "label_bg": 30, "label_en": 30, "catalog_item_name": 44}.get(key, 13)
        ws.column_dimensions[get_column_letter(ci)].width = width
    ws.row_dimensions[1].height = 12
    ws.row_dimensions[2].height = 42
    for ri, row in enumerate(rows, 3):
        for ci, (key, _label, kind) in enumerate(cols, 1):
            v = row.get(key)
            if kind == "bool":
                v = _bool_out(v)
            elif kind == "num" and v is not None:
                v = float(v)
            elif v is not None and not isinstance(v, (int, float, str)):
                v = str(v)
            c = ws.cell(row=ri, column=ci, value=v)
            c.font = F_BODY
            c.border = BORDER
            c.alignment = Alignment(vertical="top", wrap_text=key in ("notes", "hint") or (key == "value" and isinstance(v, str) and len(v) > 60))
            if kind == "ro":
                c.fill = FILL_RO
            if kind == "num":
                c.number_format = "#,##0.00"
    n = max(len(rows), 1)
    # drop-down validation for enumerated columns
    enums = {"category": CATEGORIES, "tier": TIERS, "basis": MOUNTING_BASES, "pricing_mode": ["detailed", "lump"],
             "stock_status": ["instock", "backorder", "outofstock"]}
    for ci, (key, _l, kind) in enumerate(cols, 1):
        letter = get_column_letter(ci)
        if key in enums and table != "settings":
            dv = DataValidation(type="list", formula1='"' + ",".join(enums[key]) + '"', allow_blank=True)
            dv.error = "Невалидна стойност"
            ws.add_data_validation(dv)
            dv.add(f"{letter}3:{letter}{n + 200}")
        elif kind == "bool":
            dv = DataValidation(type="list", formula1='"да,не"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{letter}3:{letter}{n + 200}")
    ws.auto_filter.ref = f"A2:{get_column_letter(len(cols))}{n + 2}"
    ws.cell(row=2, column=1).comment = Comment("Ред 1 = технически ключ (не го променяйте). Празна клетка = без промяна; '-' изтрива стойността. "
                                               "Редове без ID/код се създават като нови.", "gmsun")


def _instructions_sheet(wb: Workbook, db: Session, tables: list[str]) -> None:
    ws = wb.create_sheet("Инструкции", 0)
    company = get_setting(db, "company")
    ws["A1"] = f"{company.get('name') or 'gmsun'} — пълен набор данни за редакция"
    ws["A1"].font = F_TITLE
    ws["A2"] = f"Експортирано: {datetime.now(timezone.utc).astimezone().strftime('%d.%m.%Y %H:%M')} · gmsun"
    ws["A2"].font = F_KEY
    lines = [
        "Как се работи с файла",
        "1. Редактирайте само белите клетки. Сивите колони (ID, код, информативни) са ключове — не ги променяйте и не ги изтривайте.",
        "2. Ред 1 съдържа техническия ключ на колоната, ред 2 — името ѝ на български. Не променяйте тези два реда.",
        "3. Празна клетка = полето НЕ се променя при импорт. За да изтриете стойност, напишете тире „-“.",
        "4. Нов артикул/ред: добавете го на нов ред с празно ID — системата ще го създаде (за артикули са нужни поне Категория и Наименование).",
        "5. Цените са доставни, в EUR, без ДДС. Срокът на доставка е в работни дни. Класът е economy / standard / premium.",
        "6. Стойности, отбелязани с „Източник на цената = indicative“, са ориентировъчни и трябва да бъдат заменени с реални оферти от доставчиците.",
        "7. Импорт: Каталог → „Импорт на всички таблици“ — качете този .xlsx (или .zip с един .xlsx на таблица). Системата показва колко реда са обновени/създадени и евентуални грешки.",
        "8. Да/не колоните приемат: да, не, yes, no, true, false, 1, 0.",
        "",
        "Таблици в този файл",
    ]
    for i, t in enumerate(lines, 4):
        ws.cell(row=i, column=1, value=t).font = Font(name="Calibri", size=11 if i == 4 or t == "Таблици в този файл" else 10, bold=i == 4 or t == "Таблици в този файл", color=NAVY if (i == 4 or t == "Таблици в този файл") else "111827")
    r = 4 + len(lines)
    descr = {"catalog_items": "Всички артикули: модули, инвертори, батерии, конструкция, електро материали, услуги — с цени, срокове, доставчици и спецификации.",
             "labor_options": "Варианти за труд: дни × работници → цена.", "roof_types": "Типове покриви/терени и параметри за конструкцията.",
             "mounting_rules": "Правила колко бройки от кой артикул се слагат на модул/релса/ред за всеки тип покрив.",
             "suppliers": "Доставчици, контакти и срок на доставка по подразбиране.", "settings": "Фирмени данни, ценови параметри, инженерни настройки и текстове в документите."}
    for t in tables:
        ws.cell(row=r, column=1, value=f"• {TABLES[t]['title']} — {descr[t]}").font = F_BODY
        r += 1
    ws.column_dimensions["A"].width = 150
    for row in ws.iter_rows(min_row=4, max_row=r):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")


def export_workbook(db: Session, tables: list[str] | None = None) -> bytes:
    tables = tables or list(TABLES)
    wb = Workbook()
    wb.remove(wb.active)
    for t in tables:
        _write_sheet(wb.create_sheet(), t, ROW_SOURCES[t](db))
    _instructions_sheet(wb, db, tables)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def export_zip(db: Session) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        for t, meta in TABLES.items():
            z.writestr(meta["file"], export_workbook(db, [t]))
        z.writestr("README.txt", "gmsun — пълен набор данни. Редактирайте .xlsx файловете и качете целия .zip (или отделен .xlsx) през Каталог → Импорт на всички таблици.\n"
                   "Празна клетка = без промяна, '-' изтрива стойността, редове без ID се създават. Цени: EUR без ДДС; срокове: работни дни.\n")
    return bio.getvalue()


# ------------------------------------------------------------------------------------------------- import
_TRUE = {"да", "yes", "true", "1", "y", "д", "x"}
_FALSE = {"не", "no", "false", "0", "n", "н"}


class _Skip(Exception):
    pass


def _parse(kind: str, v: Any, key: str = "") -> Any:
    """Return parsed value, or raise _Skip when the cell is empty (= keep). CLEAR → None."""
    if v is None or (isinstance(v, str) and not v.strip()):
        raise _Skip()
    if isinstance(v, str):
        v = v.strip()
        if v == CLEAR:
            return None
    if kind in ("ro",):
        return v
    if kind == "bool":
        s = str(v).strip().lower()
        if s in _TRUE:
            return True
        if s in _FALSE:
            return False
        raise ValueError(f"'{v}' не е да/не")
    if kind == "int":
        return int(round(float(str(v).replace(",", ".").replace(" ", ""))))
    if kind == "num":
        return float(str(v).replace(",", ".").replace(" ", ""))
    if kind == "json":
        return json.loads(v) if isinstance(v, str) else v
    return str(v)


def _read_sheet(ws: Worksheet) -> tuple[str | None, list[str], list[tuple[int, dict[str, Any]]]]:
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return None, [], []
    keys = [str(k).strip() if k is not None else "" for k in rows[0]]
    table = TITLE_TO_TABLE.get(ws.title)
    if table is None:  # detect by key signature
        ks = set(keys)
        if {"category", "name", "purchase_price"} <= ks:
            table = "catalog_items"
        elif {"days", "workers", "price"} <= ks:
            table = "labor_options"
        elif {"code", "label_bg"} <= ks:
            table = "roof_types"
        elif {"roof_type", "basis", "factor"} <= ks:
            table = "mounting_rules"
        elif {"path", "value"} <= ks:
            table = "settings"
        elif {"name", "lead_time_days"} <= ks and "category" not in ks:
            table = "suppliers"
    data = []
    for i, r in enumerate(rows[2:], 3):
        if r is None or all(v is None or (isinstance(v, str) and not v.strip()) for v in r):
            continue
        data.append((i, {keys[j]: r[j] for j in range(min(len(keys), len(r))) if keys[j]}))
    return table, keys, data


def _apply_columns(obj: Any, row: dict[str, Any], cols: list[Column], skip: set[str]) -> tuple[bool, list[str]]:
    changed, errs = False, []
    for key, label, kind in cols:
        if key in skip or kind == "ro" or key not in row:
            continue
        try:
            v = _parse(kind, row[key], key)
        except _Skip:
            continue
        except Exception as e:  # noqa: BLE001
            errs.append(f"{label}: {e}")
            continue
        cur = getattr(obj, key, None)
        if isinstance(cur, str) and isinstance(v, str) and cur.strip() == v.strip():
            continue
        if cur != v:
            setattr(obj, key, v)
            changed = True
    return changed, errs


def _import_catalog(db: Session, data: list[tuple[int, dict[str, Any]]], rep: dict[str, Any]) -> None:
    by_id = {c.id: c for c in db.query(CatalogItem).all()}
    today = datetime.now(timezone.utc).date().isoformat()
    for rownum, row in data:
        rid = row.get("id")
        it = None
        if rid not in (None, ""):
            try:
                it = by_id.get(int(float(rid)))
            except (TypeError, ValueError):
                rep["errors"].append(f"ред {rownum}: невалидно ID '{rid}'")
                continue
            if it is None:
                rep["errors"].append(f"ред {rownum}: няма артикул с ID {rid}")
                continue
        else:
            cat, name = (row.get("category") or "").strip() if isinstance(row.get("category"), str) else row.get("category"), row.get("name")
            if not cat or not name:
                rep["errors"].append(f"ред {rownum}: новият артикул изисква Категория и Наименование")
                continue
            it = CatalogItem(category=str(cat), name=str(name).strip(), specs={})
            db.add(it)
            rep["created"] += 1
            rep.setdefault("_new", []).append(it)
        cat_v = row.get("category")
        if isinstance(cat_v, str) and cat_v.strip() and cat_v.strip() not in CATEGORIES:
            rep["errors"].append(f"ред {rownum}: непозната категория '{cat_v}'")
            continue
        tier_v = row.get("tier")
        if isinstance(tier_v, str) and tier_v.strip() and tier_v.strip() not in (*TIERS, CLEAR):
            rep["errors"].append(f"ред {rownum}: непознат клас '{tier_v}'")
            continue
        if it.id is not None:
            rep.setdefault("_seen", set()).add(it.id)
        old_price, old_lead = it.purchase_price, it.lead_time_days
        base_cols = [c for c in CATALOG_COLUMNS if c[0] not in SPEC_KEYS and c[0] != "specs_json"]
        changed, errs = _apply_columns(it, row, base_cols, set())
        sp = dict(it.specs or {})
        for key, label, kind in SPEC_COLUMNS:
            if key not in row:
                continue
            try:
                v = _parse(kind, row[key], key)
            except _Skip:
                continue
            except Exception as e:  # noqa: BLE001
                errs.append(f"{label}: {e}")
                continue
            if v is None:
                if key in sp:
                    sp.pop(key)
                    changed = True
            elif sp.get(key) != v:
                sp[key] = v
                changed = True
        if "specs_json" in row:
            try:
                extra = _parse("json", row["specs_json"])
                if isinstance(extra, dict):
                    for k, v in extra.items():
                        if k not in SPEC_KEYS and sp.get(k) != v:
                            sp[k] = v
                            changed = True
            except _Skip:
                pass
            except Exception as e:  # noqa: BLE001
                errs.append(f"JSON: {e}")
        if it.purchase_price != old_price and it.purchase_price:
            sp["price_source"] = "excel-import"
            sp["price_updated_at"] = today
            sp.pop("price_note", None)
        if it.lead_time_days != old_lead and it.lead_time_days is not None:
            sp["lead_source"] = "excel-import"
        if errs:
            rep["errors"].append(f"ред {rownum} ({it.name[:40]}): " + "; ".join(errs))
        if changed:
            it.specs = sp
            if it.id is not None:
                rep["updated"] += 1
        elif it.id is not None:
            rep["skipped"] += 1


def _import_simple(db: Session, model: Any, cols: list[Column], key: str, data: list[tuple[int, dict[str, Any]]], rep: dict[str, Any],
                   required: tuple[str, ...], validate: Callable[[dict[str, Any]], str | None] | None = None) -> None:
    existing = {getattr(o, key): o for o in db.query(model).all()}
    for rownum, row in data:
        kv = row.get(key)
        if isinstance(kv, float) and key == "id":
            kv = int(kv)
        if isinstance(kv, str):
            kv = kv.strip() or None
        obj = existing.get(kv) if kv not in (None, "") else None
        if kv not in (None, "") and obj is None and key == "id":
            rep["errors"].append(f"ред {rownum}: няма запис с ID {kv}")
            continue
        if validate:
            msg = validate(row)
            if msg:
                rep["errors"].append(f"ред {rownum}: {msg}")
                continue
        is_new = obj is None
        if is_new:
            missing = [r for r in required if row.get(r) in (None, "")]
            if missing:
                rep["errors"].append(f"ред {rownum}: липсват задължителни полета {', '.join(missing)}")
                continue
            obj = model()
            if key == "code":
                obj.code = str(kv)
            db.add(obj)
        changed, errs = _apply_columns(obj, row, cols, {key})
        if errs:
            rep["errors"].append(f"ред {rownum}: " + "; ".join(errs))
        if is_new:
            rep["created"] += 1
        elif changed:
            rep["updated"] += 1
        else:
            rep["skipped"] += 1


def _import_suppliers(db: Session, data: list[tuple[int, dict[str, Any]]], rep: dict[str, Any]) -> None:
    cfg = get_setting(db, "suppliers")
    lst = [dict(s) for s in (cfg.get("list") or [])]
    by_name = {s.get("name"): s for s in lst}
    for rownum, row in data:
        name = (str(row.get("name") or "")).strip()
        if not name:
            rep["errors"].append(f"ред {rownum}: липсва име на доставчик")
            continue
        s = by_name.get(name)
        is_new = s is None
        if is_new:
            s = {"name": name, "contact": "", "email": "", "phone": "", "url": "", "lead_time_days": cfg.get("default_lead_time_days", 7), "notes": ""}
            lst.append(s)
            by_name[name] = s
        changed = False
        for key, label, kind in SUPPLIER_COLUMNS:
            if key == "name" or key not in row:
                continue
            try:
                v = _parse(kind, row[key])
            except _Skip:
                continue
            except Exception as e:  # noqa: BLE001
                rep["errors"].append(f"ред {rownum}: {label}: {e}")
                continue
            if s.get(key) != v:
                s[key] = v if v is not None else ("" if kind == "text" else None)
                changed = True
        rep["created" if is_new else "updated" if changed else "skipped"] += 1
    set_setting(db, "suppliers", {"list": lst})


def _import_settings(db: Session, data: list[tuple[int, dict[str, Any]]], rep: dict[str, Any]) -> None:
    updates: dict[str, dict[str, Any]] = {}
    for rownum, row in data:
        path = str(row.get("path") or "").strip()
        if "." not in path:
            rep["errors"].append(f"ред {rownum}: невалиден ключ '{path}'")
            continue
        group, k = path.split(".", 1)
        default = DEFAULT_SETTINGS.get(group, {}).get(k, None)
        if group not in DEFAULT_SETTINGS or (k not in DEFAULT_SETTINGS[group]):
            rep["errors"].append(f"ред {rownum}: непозната настройка '{path}'")
            continue
        try:
            kind = "bool" if isinstance(default, bool) else "num" if isinstance(default, float) else "int" if isinstance(default, int) else "text"
            v = _parse(kind, row.get("value"))
        except _Skip:
            rep["skipped"] += 1
            continue
        except Exception as e:  # noqa: BLE001
            rep["errors"].append(f"ред {rownum}: {path}: {e}")
            continue
        if v is None:
            v = "" if isinstance(default, str) or default is None else default
        if get_setting(db, group).get(k) != v:
            updates.setdefault(group, {})[k] = v
            rep["updated"] += 1
        else:
            rep["skipped"] += 1
    for group, vals in updates.items():
        set_setting(db, group, vals, commit=False)  # the whole import is one transaction


def _import_sheet(db: Session, ws: Worksheet, report: dict[str, Any]) -> None:
    table, keys, data = _read_sheet(ws)
    if table is None:
        if ws.title != "Инструкции":
            report["ignored_sheets"].append(ws.title)
        return
    rep = report["tables"].setdefault(table, {"title": TABLES[table]["title"], "rows": 0, "created": 0, "updated": 0, "skipped": 0, "errors": []})
    rep["rows"] += len(data)
    if table == "catalog_items":
        _import_catalog(db, data, rep)
    elif table == "labor_options":
        _import_simple(db, LaborOption, LABOR_COLUMNS, "id", data, rep, ("days", "workers", "price"))
    elif table == "roof_types":
        _import_simple(db, RoofTypeConfig, ROOF_COLUMNS, "code", data, rep, ("code", "label_bg", "label_en"),
                       lambda r: None if (r.get("pricing_mode") in (None, "", "detailed", "lump", CLEAR)) else f"невалиден режим '{r.get('pricing_mode')}'")
    elif table == "mounting_rules":
        roofs = {r.code for r in db.query(RoofTypeConfig.code).all()}
        _import_simple(db, MountingRule, RULE_COLUMNS, "id", data, rep, ("roof_type", "name", "basis"),
                       lambda r: (f"непозната база '{r.get('basis')}'" if (isinstance(r.get("basis"), str) and r["basis"].strip() and r["basis"].strip() not in MOUNTING_BASES)
                                  else f"непознат тип покрив '{r.get('roof_type')}'" if (isinstance(r.get("roof_type"), str) and r["roof_type"].strip() and r["roof_type"].strip() not in roofs) else None))
    elif table == "suppliers":
        _import_suppliers(db, data, rep)
    elif table == "settings":
        _import_settings(db, data, rep)
    db.flush()


def import_dataset(db: Session, data: bytes, filename: str = "", replace_items: bool = False) -> dict[str, Any]:
    """Apply an edited dataset. With ``replace_items`` every catalog item that is NOT a row of the Items sheet is
    deleted afterwards (the file becomes the complete catalog). Replacing is refused when the Items sheet is missing
    or has row errors, so a broken file can never wipe the catalog."""
    report: dict[str, Any] = {"files": [], "tables": {}, "ignored_sheets": [], "created": 0, "updated": 0, "skipped": 0, "errors": 0}
    blobs: list[tuple[str, bytes]] = []
    if filename.lower().endswith(".zip") or data[:2] == b"PK" and not filename.lower().endswith(".xlsx") and b"[Content_Types].xml" not in data[:4000]:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in sorted(z.namelist()):
                if n.lower().endswith(".xlsx") and not n.startswith("__MACOSX"):
                    blobs.append((n, z.read(n)))
        if not blobs:
            raise ValueError("В .zip архива няма .xlsx файлове")
    else:
        blobs.append((filename or "upload.xlsx", data))
    for name, blob in blobs:
        wb = load_workbook(io.BytesIO(blob), data_only=True, read_only=False)
        report["files"].append(name)
        for ws in wb.worksheets:
            _import_sheet(db, ws, report)
    if replace_items:
        cat = report["tables"].get("catalog_items")
        if not cat:
            db.rollback()
            raise ValueError("Режим „замени“: във файла няма лист Артикули — нищо не е изтрито.")
        if cat["errors"]:
            db.rollback()
            raise ValueError("Режим „замени“: листът Артикули има грешки — поправете ги, нищо не е променено. " + "; ".join(cat["errors"][:5]))
        db.flush()
        keep = set(cat.get("_seen") or set()) | {it.id for it in (cat.get("_new") or [])}
        if not keep:
            db.rollback()
            raise ValueError("Режим „замени“: листът Артикули е празен — нищо не е изтрито.")
        from .catalog_final import remove_items

        others = [r for r in db.query(CatalogItem).all() if r.id not in keep]
        res = remove_items(db, others, keep)
        report["deleted"] = res["deleted"]
    for t in report["tables"].values():
        t.pop("_seen", None)
        t.pop("_new", None)
    db.commit()
    for t in report["tables"].values():
        report["created"] += t["created"]
        report["updated"] += t["updated"]
        report["skipped"] += t["skipped"]
        report["errors"] += len(t["errors"])
    return report
