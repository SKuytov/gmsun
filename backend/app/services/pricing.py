"""Quote calculation engine.

Turns a project + the quote `selections` dict into priced lines grouped into
sections, then computes totals (discount, VAT, advance, balance).

Auto lines carry a stable `key`; on recalculation existing lines with the same
key are updated unless the user has `locked` them (manual override). Manual
lines (`source == "manual"`) are always preserved.
"""
from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, LaborOption, Layout, Project, Quote, QuoteLine, RoofTypeConfig
from . import bom, engineering
from . import procurement
from . import module_fit
from .settings import get_setting

SECTIONS: list[tuple[str, str, str]] = [
    ("modules", "Част фотоволтаични модули", "PV modules"),
    ("inverter", "Част инвертор и батерии", "Inverter & batteries"),
    ("construction", "Част конструкция", "Mounting structure"),
    ("electrical", "Част електрически компоненти", "Electrical components"),
    ("labor", "Част строително-монтажни работи", "Installation works"),
    ("other", "Транспорт и други", "Transport & other"),
]
SECTION_ORDER = {s[0]: i for i, s in enumerate(SECTIONS)}


def _item(db: Session, item_id: Any) -> CatalogItem | None:
    if not item_id:
        return None
    try:
        return db.get(CatalogItem, int(item_id))
    except (TypeError, ValueError):
        return None


def _line(key: str, section: str, name: str, unit: str, qty: float, unit_price: float, purchase: float = 0.0, item: CatalogItem | None = None, meta: dict | None = None) -> dict[str, Any]:
    return {
        "key": key,
        "section": section,
        "name": name,
        "unit": unit,
        "qty": float(qty),
        "unit_price": round(float(unit_price), 4),
        "purchase_price": round(float(purchase), 4),
        "catalog_item_id": item.id if item else None,
        "meta": meta or {},
    }


def _item_line(key: str, section: str, item: CatalogItem, qty: float, markup: float, name: str | None = None, meta: dict | None = None) -> dict[str, Any]:
    return _line(key, section, name or item.name, item.unit, qty, item.price_for(markup), item.purchase_price, item, meta)


def active_layout_summary(project: Project) -> dict[str, Any]:
    """Aggregate all layouts of a project into one summary (count, kwp, lines)."""
    total: dict[str, Any] = {"count": 0, "kwp": 0.0, "lines": [], "area_m2": 0.0}
    for lay in project.layouts:
        s = lay.summary or {}
        total["count"] += int(s.get("count") or 0)
        total["kwp"] += float(s.get("kwp") or 0.0)
        total["area_m2"] += float(s.get("area_m2") or 0.0)
        total["lines"].extend(s.get("lines") or [])
    total["kwp"] = round(total["kwp"], 3)
    return total


def _design(db: Session, project: Project, sel: dict[str, Any], pricing: dict[str, Any], panel: CatalogItem | None, inverter: CatalogItem | None, battery: CatalogItem | None, bq: int, panel_qty: int, layout_sum: dict[str, Any], inverter_qty: int = 1) -> dict[str, Any]:
    """Collect roof planes + rail statistics and run the engineering engine.

    When ``panel_qty`` is smaller than the layout count (a "target power" quote on a roof with more room) the planes
    are scaled down proportionally, so strings, rails and cables follow the quoted module count."""
    pw = module_fit.module_dims_m(panel.specs)[0] if panel else 1.134
    planes: list[dict[str, Any]] = []
    lay_count = int(layout_sum.get("count") or 0)
    scale = (panel_qty / lay_count) if (lay_count > 0 and 0 < panel_qty < lay_count) else 1.0
    fit = sel.get("panel_fit") if isinstance(sel.get("panel_fit"), dict) else None
    fit_by_layout = {int(k): v for k, v in (fit or {}).get("layouts", {}).items()} if fit and panel and int(fit.get("panel_item_id") or 0) == panel.id else {}
    if fit_by_layout and sel.get("use_layout", True):
        # a module different from the one drawn in the layout: use the counts the module-fit engine placed per plane
        scale = 1.0
        for lay in project.layouts:
            n = int((fit_by_layout.get(lay.id) or {}).get("count_used") or 0)
            if n > 0:
                planes.append({"name": lay.name, "modules": n, "module_w_m": pw, "azimuth": lay.azimuth_deg, "tilt": lay.tilt_deg, "layout_id": lay.id})
        fit_total = sum(int((v or {}).get("count_max") or 0) for v in fit_by_layout.values())
        if lay_count > 0 and fit_total > 0:
            scale = min(1.0, panel_qty / lay_count * (lay_count / fit_total))  # rails follow the quoted share of the roof
    elif sel.get("use_layout", True) and lay_count:
        remaining = panel_qty if scale < 1 else None
        for lay in project.layouts:
            s = lay.summary or {}
            n = int(s.get("count") or 0)
            if n <= 0:
                continue
            if remaining is not None:
                n = min(remaining, max(0, int(round(n * scale))))
                remaining -= n
            if n > 0:
                planes.append({"name": lay.name, "modules": n, "module_w_m": pw, "azimuth": lay.azimuth_deg, "tilt": lay.tilt_deg, "layout_id": lay.id})
        if remaining and planes:  # rounding leftovers go to the largest plane
            planes.sort(key=lambda x: -x["modules"])
            planes[0]["modules"] += remaining
    if not planes and panel_qty > 0:
        planes.append({"name": "Плоскост 1", "modules": panel_qty, "module_w_m": pw})
    lines = layout_sum.get("lines") or []
    rail_lines = (sum(int(l.get("rails") or 2) for l in lines) if lines else math.ceil(panel_qty / 10) * 2)
    row_m = (sum(float(l.get("length_m") or 0) for l in lines) if lines else panel_qty * (pw + 0.02))
    if scale < 1:
        rail_lines = max(2, int(round(rail_lines * scale)))
        row_m = row_m * scale
    try:
        return engineering.full_design(
            db, project=project, panel=panel, inverter=inverter, battery=battery, battery_qty=bq, panel_qty=panel_qty,
            planes=planes, rail_lines=rail_lines, row_length_m=row_m, sel=sel, pricing=pricing, inverter_qty=inverter_qty,
        )
    except Exception as e:  # noqa: BLE001 - design must never block the quote
        return {"roles": [], "warnings": [f"Грешка в инженерния модул: {e}"], "strings": {}}


def build_lines(db: Session, project: Project, quote: Quote) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    sel = quote.selections or {}
    pricing = get_setting(db, "pricing")
    markup = float(quote.markup_pct if quote.markup_pct is not None else pricing.get("default_markup_pct", 0))
    warnings: list[str] = []
    lines: list[dict[str, Any]] = []
    info: dict[str, Any] = {}

    # ------------------------------------------------------------------ modules
    panel = _item(db, sel.get("panel_item_id"))
    layout_sum = active_layout_summary(project)
    panel_qty = int(sel.get("panel_qty") or 0)
    fit = sel.get("panel_fit") if isinstance(sel.get("panel_fit"), dict) else None
    if fit and panel and int(fit.get("panel_item_id") or 0) == panel.id and int(fit.get("count") or 0) > 0 and sel.get("use_layout", True):
        # module chosen by the recommendation engine (may differ from the module drawn in the layout)
        panel_qty = int(fit["count"])
        if int(fit.get("roof_count") or 0) > panel_qty:
            info["roof_panel_qty"] = int(fit["roof_count"])
    elif sel.get("use_layout", True) and layout_sum["count"] > 0:
        panel_qty = layout_sum["count"]
        limit = int(sel.get("panel_limit") or 0)
        if 0 < limit < panel_qty:  # quote only part of the roof (target power), the rest stays as an option
            info["roof_panel_qty"] = panel_qty
            panel_qty = limit
    if panel is None and project.layouts:
        panel = _item(db, project.layouts[0].panel_item_id)
    panel_wp = float((panel.specs or {}).get("wp", 0)) if panel else 0.0
    kwp = round(panel_qty * panel_wp / 1000.0, 3)
    info.update({"panel_qty": panel_qty, "kwp": kwp, "panel_wp": panel_wp})
    if panel and panel_qty > 0:
        lines.append(_item_line("panel", "modules", panel, panel_qty, markup, name=f"{panel.name} ({kwp * 1000:.0f} W)"))
        spare_pct = float(sel.get("module_spare_pct", pricing.get("module_spare_pct", 0)) or 0)
        spare = math.ceil(panel_qty * spare_pct / 100.0 - 1e-9) if spare_pct > 0 else 0
        if spare > 0:
            lines.append(_item_line("panel:spare", "modules", panel, spare, markup, name=f"{panel.name} — резервни модули ({spare_pct:g} %)", meta={"spare": True}))
            info["panel_spare"] = spare
    elif panel_qty > 0:
        warnings.append("Не е избран модел панел.")
    if sel.get("delivery_fees", True) and panel_qty > 0 and float(pricing.get("delivery_fee_equipment", 0)) > 0:
        lines.append(_line("delivery:modules", "modules", "Доставка на оборудване", "бр.", 1, pricing["delivery_fee_equipment"]))

    # --------------------------------------------------------- inverter/battery
    inverter = _item(db, sel.get("inverter_item_id"))
    inv_qty = max(1, int(sel.get("inverter_qty") or 1)) if inverter else 0
    if inverter:
        lines.append(_item_line("inverter", "inverter", inverter, inv_qty, markup))
        inv_sp = inverter.specs or {}
        ac = float(inv_sp.get("ac_power_kw") or 0)
        ac_tot = ac * inv_qty
        info["inverter_qty"] = inv_qty
        info["ac_kw"] = round(ac_tot, 2)
        lbl = f"{inv_qty} × {ac:g} kW = {ac_tot:g} kW" if inv_qty > 1 else f"{ac:g} kW"
        if ac and project.connected_power_kw and ac_tot > project.connected_power_kw * 1.1:
            warnings.append(f"Инверторите ({lbl}) надвишават присъединената мощност ({project.connected_power_kw:g} kW) — нужно е увеличение на присъединената мощност или ограничение на отдаваната мощност (export limit)." if inv_qty > 1 else f"Инверторът ({lbl}) надвишава присъединената мощност ({project.connected_power_kw:g} kW).")
        if ac and kwp and kwp > ac_tot * float(pricing.get("dc_ac_ratio_max", 1.35)):
            need = math.ceil(kwp / (ac * float(pricing.get("dc_ac_ratio_max", 1.35))) - 1e-9)
            warnings.append(f"Мощността на панелите ({kwp:g} kWp) е над препоръчителната за {lbl} инвертор(и) — нужни са поне {need} × {ac:g} kW или по-голям модел.")
        if ac and kwp and inv_qty > 1 and kwp < ac_tot * 0.6:
            warnings.append(f"Инверторната мощност ({lbl}) е значително по-голяма от панелите ({kwp:g} kWp) — намалете броя инвертори.")
        if int(inv_sp.get("phases", project.phase)) != project.phase:
            warnings.append("Фазите на инвертора не съответстват на инсталацията.")
    else:
        warnings.append("Не е избран инвертор.")

    battery = _item(db, sel.get("battery_item_id"))
    bq = int(sel.get("battery_qty") or 1) if battery else 0
    if battery:
        bsp = battery.specs or {}
        kwh = float(bsp.get("kwh") or 0)
        lines.append(_item_line("battery", "inverter", battery, bq, markup, name=f"{battery.name} ({kwh * bq:g} kWh)" if kwh else None))
        if inverter:
            ivc = (inverter.specs or {}).get("battery_voltage_class")
            bvc = bsp.get("voltage_class")
            if ivc and bvc and str(ivc).upper() != str(bvc).upper():
                warnings.append(f"Батерията е {bvc}, а инверторът е {ivc} — несъвместими.")
        info["storage_kwh"] = kwh * bq
    for i, acc in enumerate(sel.get("battery_accessories") or []):
        it = _item(db, acc.get("catalog_item_id"))
        if it:
            lines.append(_item_line(f"batt_acc:{it.id}", "inverter", it, float(acc.get("qty") or 1), markup))
    if sel.get("delivery_fees", True) and inverter and float(pricing.get("delivery_fee_inverter", 0)) > 0:
        lines.append(_line("delivery:inverter", "inverter", "Доставка на оборудване", "бр.", 1, pricing["delivery_fee_inverter"]))

    # ------------------------------------------------------------- construction
    roof = db.get(RoofTypeConfig, project.roof_type)
    mode = sel.get("mounting_mode", "auto")
    if roof and panel_qty > 0 and mode != "none":
        eff_mode = roof.pricing_mode if mode == "auto" else mode
        stats = bom.compute_stats(layout_sum, roof, modules_override=panel_qty, strings=int((info.get("strings") or {}).get("strings") or 1))
        info["mounting_stats"] = stats.as_dict()
        if eff_mode == "lump":
            price = float(sel.get("lump_price_per_module") or roof.lump_price_per_module or 0)
            lines.append(_line("mount:lump", "construction", f"Модулна алуминиева конструкция за {roof.label_bg.lower()}", "бр.", panel_qty, price, meta={"mode": "lump"}))
        else:
            ml = bom.mounting_lines(db, roof, stats, markup, float(pricing.get("fastener_margin_pct", 0) or 0))
            if not ml:
                warnings.append("Няма дефинирани правила за монтажни материали за този тип покрив.")
            lines.extend(ml)
        if sel.get("delivery_fees", True) and float(pricing.get("delivery_fee_construction", 0)) > 0:
            lines.append(_line("delivery:construction", "construction", "Доставка на оборудване", "бр.", 1, pricing["delivery_fee_construction"]))
    elif not roof:
        warnings.append("Непознат тип покрив.")

    # --------------------------------------------------------------- electrical
    sb = _item(db, sel.get("switchboard_item_id"))
    if sb:
        lines.append(_item_line("switchboard", "electrical", sb, 1, markup))
    else:
        warnings.append("Не е избрано електрическо табло.")
    # engineering design: strings, protections, cables, earthing, consumables
    design = _design(db, project, sel, pricing, panel, inverter, battery, bq, panel_qty, layout_sum, inverter_qty=inv_qty or 1)
    info["design"] = design
    sd = design.get("strings") or {}
    info["strings"] = {"strings": sd.get("count", 0), "modules_per_string": sd.get("modules_per_string", 0), "mppts": sd.get("mppts", 0), "inverters": sd.get("inverters", 1), "per_inverter": sd.get("per_inverter") or [], "warnings": sd.get("warnings") or []}
    warnings.extend(design.get("warnings") or [])
    auto_el = sel.get("auto_electrical", True)
    all_items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    pick = procurement.chooser(db, sel.get("strategy"), all_items) if sel.get("strategy") else None
    missing: list[str] = []
    counters: dict[str, int] = {}
    for r in design.get("roles") or []:
        rk = r["role"]
        if not auto_el and rk not in ("pv_cable", "mc4_pair", "ac_cable"):
            continue
        idx = counters.get(rk, 0)
        counters[rk] = idx + 1
        key = f"eng:{rk}:{idx}"
        qty = float(r["qty"])
        item: CatalogItem | None = None
        # user overrides from the Materials step
        if rk == "pv_cable":
            if sel.get("solar_cable_item_id"):
                item = _item(db, sel.get("solar_cable_item_id"))
            ov = sel.get("solar_cable_red_m") if (r["spec"].get("color") == "red") else sel.get("solar_cable_black_m")
            if isinstance(ov, (int, float)) and ov > 0:
                qty = float(ov)
        elif rk == "mc4_pair":
            if sel.get("mc4_item_id"):
                item = _item(db, sel.get("mc4_item_id"))
            if isinstance(sel.get("mc4_qty"), (int, float)) and sel.get("mc4_qty") > 0:
                qty = float(sel["mc4_qty"])
        elif rk == "ac_cable" and idx == 0:
            if sel.get("power_cable_item_id"):
                item = _item(db, sel.get("power_cable_item_id"))
            if isinstance(sel.get("power_cable_m"), (int, float)) and sel.get("power_cable_m") > 0:
                qty = float(sel["power_cable_m"])
        if item is None:
            item = engineering.find_item_for_role(all_items, r, pick)
        meta = {"role": rk, "auto_qty": r["qty"], "spec": r["spec"], "role_name": r["name"]}
        if item:
            name = r["name"] if rk in ("pv_cable",) else item.name
            if int(design.get("inverters") or 1) > 1 and rk in ("ac_mcb", "ac_cable", "ac_lug", "ac_rcd"):
                m = re.search(r"\(([^()]*)\)\s*$", r["name"])  # keep the purpose, e.g. "(табло AC → ГРТ)", when several AC lines coexist
                if m:
                    name = f"{name} ({m.group(1)})"
            lines.append(_item_line(key, r["section"], item, qty, markup, name=name, meta=meta))
        else:
            missing.append(r["name"])
            lines.append(_line(key, r["section"], r["name"], r["unit"], qty, 0.0, meta={**meta, "missing_item": True}))
    if missing:
        warnings.append(f"Няма артикул в каталога за {len(missing)} позиции (добавете ги в Каталог с роля): " + "; ".join(missing[:6]) + (" …" if len(missing) > 6 else ""))
    for extra in sel.get("electrical_items") or []:
        it = _item(db, extra.get("catalog_item_id") or extra.get("item_id"))
        if it:
            lines.append(_item_line(f"elec:{it.id}", "electrical", it, float(extra.get("qty") or 1), markup))

    # -------------------------------------------------------------------- labor
    labor_mode = sel.get("labor_mode", "matrix")
    if labor_mode == "matrix" and sel.get("labor_option_id"):
        lo = db.get(LaborOption, int(sel["labor_option_id"]))
        if lo:
            name = f"Монтаж, пуск и настройка — {lo.days} {'ден' if lo.days == 1 else 'дни'}, {lo.workers} {'работник' if lo.workers == 1 else 'работници'}"
            lines.append(_line("labor", "labor", name, "компл.", 1, lo.price, meta={"days": lo.days, "workers": lo.workers}))
            info["execution_days"], info["workers"] = lo.days, lo.workers
    elif labor_mode == "per_w":
        ppw = float(sel.get("install_price_per_w") or pricing.get("install_price_per_w") or 0)
        watts = kwp * 1000
        if watts > 0:
            lines.append(_line("labor", "labor", f"Монтаж, пуск и настройка на оборудване 1 × {watts:.0f} W", "W", watts, ppw))
    elif labor_mode == "manual":
        price = float(sel.get("labor_price") or 0)
        if price > 0:
            lines.append(_line("labor", "labor", "Монтаж, пуск и настройка на оборудване", "компл.", 1, price))
    else:
        warnings.append("Не е избран вариант за труд (срок/работници).")

    # -------------------------------------------------------------------- other
    tp = float(sel.get("transport_price") or 0)
    if tp > 0:
        lines.append(_line("transport", "other", sel.get("transport_name") or "Транспорт", "бр.", 1, tp))
    for extra in sel.get("extra_items") or []:
        it = _item(db, extra.get("catalog_item_id"))
        if it:
            lines.append(_item_line(f"extra:{it.id}", "other", it, float(extra.get("qty") or 1), markup))

    # price sanity
    for ln in lines:
        if ln["catalog_item_id"] and ln["unit_price"] <= 0:
            warnings.append(f"Липсва цена за „{ln['name']}“ в каталога.")

    # procurement: supplier + lead time per line, overall delivery time = slowest line
    scfg = get_setting(db, "suppliers")
    cache: dict[int, CatalogItem | None] = {}
    lead_max, bottleneck = 0, None
    for ln in lines:
        iid = ln.get("catalog_item_id")
        if not iid:
            continue
        it = cache.get(iid) if iid in cache else cache.setdefault(iid, _item(db, iid))
        if not it:
            continue
        ld = procurement.lead_time_days(it, scfg)
        ln["meta"] = {**(ln.get("meta") or {}), "lead_time_days": ld, "supplier": procurement.supplier_of(it), "supplier_sku": it.supplier_sku or it.sku}
        if ld > lead_max:
            lead_max, bottleneck = ld, ln["name"]
    info["lead_time_days"] = lead_max
    info["lead_bottleneck"] = bottleneck
    if sel.get("strategy"):
        info["strategy"] = sel["strategy"]

    return lines, warnings, info


def apply_lines(db: Session, quote: Quote, new_lines: list[dict[str, Any]]) -> None:
    existing = {ln.key: ln for ln in quote.lines if ln.source == "auto"}
    seen: set[str] = set()
    for nl in new_lines:
        seen.add(nl["key"])
        ln = existing.get(nl["key"])
        if ln is None:
            ln = QuoteLine(key=nl["key"], source="auto")
            quote.lines.append(ln)  # backref sets quote_id; do not also pass quote= (would double-append)
        if ln.locked:
            # keep user's manual override but still refresh purchase price for margin reporting
            ln.purchase_price = nl["purchase_price"]
            ln.catalog_item_id = nl["catalog_item_id"]
            ln.total = round(ln.qty * ln.unit_price, 2)
            continue
        ln.section = nl["section"]
        ln.name = nl["name"]
        ln.unit = nl["unit"]
        ln.qty = nl["qty"]
        ln.unit_price = nl["unit_price"]
        ln.purchase_price = nl["purchase_price"]
        ln.catalog_item_id = nl["catalog_item_id"]
        ln.meta = nl.get("meta") or {}
        ln.total = round(ln.qty * ln.unit_price, 2)
    for key, ln in existing.items():
        if key not in seen and not ln.locked:
            quote.lines.remove(ln)
            db.delete(ln)
    # positions: by section order then existing position / insertion
    # new lines (position None) sort after the existing ones of their section, in insertion order
    ordered = sorted(quote.lines, key=lambda l: (SECTION_ORDER.get(l.section, 99), l.position if l.position is not None else 10**6, l.id or 10**9))
    for i, ln in enumerate(ordered):
        ln.position = i


def compute_totals(quote: Quote) -> None:
    subtotal = 0.0
    for ln in quote.lines:
        ln.total = round(float(ln.qty) * float(ln.unit_price), 2)
        if not ln.hidden:
            subtotal += ln.total
    quote.subtotal = round(subtotal, 2)
    quote.discount_amount = round(subtotal * float(quote.discount_pct or 0) / 100.0, 2)
    quote.net_total = round(quote.subtotal - quote.discount_amount, 2)
    quote.vat_amount = round(quote.net_total * float(quote.vat_pct or 0) / 100.0, 2)
    quote.total = round(quote.net_total + quote.vat_amount, 2)
    basis = quote.net_total if (quote.selections or {}).get("advance_basis", "net") == "net" else quote.total
    quote.advance_amount = round(basis * float(quote.advance_pct or 0) / 100.0, 2)
    quote.balance_amount = round(basis - quote.advance_amount, 2)


def recalculate(db: Session, quote: Quote) -> tuple[list[str], dict[str, Any]]:
    project = quote.project
    lines, warnings, info = build_lines(db, project, quote)
    apply_lines(db, quote, lines)
    compute_totals(quote)
    if info.get("execution_days"):
        quote.execution_days = info["execution_days"]
        quote.workers = info.get("workers")
    sel = dict(quote.selections or {})
    sel["_info"] = info
    sel["_warnings"] = warnings
    quote.selections = sel
    return warnings, info


def sections_view(quote: Quote, lang: str = "bg") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for code, bg, en in SECTIONS:
        lns = [l for l in quote.lines if l.section == code and not l.hidden]
        if not lns:
            continue
        out.append(
            {
                "code": code,
                "title": bg if lang == "bg" else en,
                "total": round(sum(l.total for l in lns), 2),
                "lines": [l.id for l in lns],
            }
        )
    return out


def cost_and_margin(quote: Quote) -> tuple[float, float]:
    cost = sum(float(l.qty) * float(l.purchase_price or 0) for l in quote.lines if not l.hidden and l.catalog_item_id)
    # lines without catalog item (labor, delivery) are treated as pass-through revenue (no cost tracked)
    margin = quote.net_total - cost - sum(l.total for l in quote.lines if not l.hidden and not l.catalog_item_id and l.section in ("labor",))
    return round(cost, 2), round(margin, 2)


def next_quote_number(db: Session, project: Project, prefix: str = "") -> str:
    from datetime import date

    d = date.today()
    base = f"{prefix}{d:%y%m%d}"
    n = db.query(Quote).filter(Quote.number.like(f"{base}-%")).count() + 1
    return f"{base}-{n:02d}PV"


def estimate_yield(kwp: float, specific_yield: float, azimuth_deg: float = 180.0, tilt_deg: float = 20.0) -> float:
    """Annual yield estimate: kWp × specific yield × orientation factor."""
    if kwp <= 0:
        return 0.0
    # simple orientation factor: south 1.0, east/west ~0.85, north ~0.6; tilt optimum ~30°
    az = abs(((azimuth_deg - 180) + 180) % 360 - 180)  # 0 = south
    f_az = 1.0 - 0.15 * (az / 90.0) if az <= 90 else 0.85 - 0.25 * ((az - 90) / 90.0)
    f_tilt = 1.0 - 0.0001 * (tilt_deg - 30) ** 2
    return round(kwp * specific_yield * max(f_az, 0.5) * max(f_tilt, 0.7), 0)


def quote_dict(db: Session, quote: Quote) -> dict[str, Any]:
    cost, margin = cost_and_margin(quote)
    sel = quote.selections or {}
    return {
        "warnings": sel.get("_warnings", []),
        "sections": sections_view(quote),
        "cost_total": cost,
        "margin": margin,
    }
