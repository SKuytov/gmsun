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
from . import compat, bom, engineering
from . import procurement
from . import module_fit
from . import site_kind
from .settings import get_setting

SECTIONS: list[tuple[str, str, str]] = [
    ("modules", "Част фотоволтаични модули", "PV modules"),
    ("inverter", "Част инвертор и батерии", "Inverter & batteries"),
    ("construction", "Част конструкция", "Mounting structure"),
    ("electrical", "Част електрически компоненти", "Electrical components"),
    ("labor", "Част монтажни работи", "Installation works"),
    ("other", "Транспорт и други", "Transport & other"),
]
SECTION_ORDER = {s[0]: i for i, s in enumerate(SECTIONS)}


def _item(db: Session, item_id: Any, *, include_inactive: bool = False) -> CatalogItem | None:
    """Catalog item by id – deleted or deactivated items are never quoted (returns None)."""
    if not item_id:
        return None
    try:
        it = db.get(CatalogItem, int(item_id))
    except (TypeError, ValueError):
        return None
    if it is not None and not include_inactive and it.active is False:
        return None
    return it


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


def include_delivery(sel: dict[str, Any], pricing: dict[str, Any]) -> bool:
    """Delivery fee lines: the quote's own switch wins, otherwise the company setting (off by default)."""
    v = sel.get("delivery_fees")
    if isinstance(v, bool):
        return v
    return bool(pricing.get("include_delivery_fees", False))


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
    inc_delivery = include_delivery(sel, pricing)
    if inc_delivery and panel_qty > 0 and float(pricing.get("delivery_fee_equipment", 0)) > 0:
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
    # BMS / control box and rack / cabinet are two independent selections (auto | manual | none)
    from . import battery_acc

    ba = battery_acc.resolve(db, sel, inverter, battery, bq, inv_qty or 1)
    for kind, prefix in (("bms", "batt_bms"), ("rack", "batt_rack")):
        for it, q, why in ba[kind]:
            key = f"batt_auto:{it.id}" if ba["modes"].get(kind) == "auto" else f"{prefix}:{it.id}"
            lines.append(_item_line(key, "inverter", it, q, markup, meta={"auto": why, "battery_part": kind}))
    for it, q, _why in ba["other"]:
        lines.append(_item_line(f"batt_acc:{it.id}", "inverter", it, q, markup, meta={"battery_part": "other"}))
    info["battery_accessories_auto"] = [{"id": a["item_id"], "name": a["name"], "qty": a["qty"], "kind": k} for k in ("bms", "rack") for a in ba["auto"][k]]
    info["battery_parts"] = {
        "modes": ba["modes"],
        "auto": ba["auto"],
        "bms": [{"id": it.id, "name": it.name, "qty": q} for it, q, _w in ba["bms"]],
        "rack": [{"id": it.id, "name": it.name, "qty": q} for it, q, _w in ba["rack"]],
    }
    warnings.extend(ba["notes"])
    for w in ba["warnings"]:
        if w.startswith("НЕСЪВМЕСТИМО"):
            warnings.insert(0, w)
        else:
            warnings.append(w)
    sysc = compat.system_issues(db, project, panel, panel_qty, inverter, inv_qty or 1, battery, bq)
    info["compat"] = sysc
    for b in sysc["blocked"]:
        warnings.insert(0, f"НЕСЪВМЕСТИМО: {b}")
    if inc_delivery and inverter and float(pricing.get("delivery_fee_inverter", 0)) > 0:
        lines.append(_line("delivery:inverter", "inverter", "Доставка на оборудване", "бр.", 1, pricing["delivery_fee_inverter"]))

    # ------------------------------------------------------------- construction
    roof = db.get(RoofTypeConfig, project.roof_type)
    mode = sel.get("mounting_mode", "auto")
    if roof and panel_qty > 0 and mode != "none":
        eff_mode = roof.pricing_mode if mode == "auto" else mode
        stats = bom.compute_stats(layout_sum, roof, modules_override=panel_qty, strings=int((info.get("strings") or {}).get("strings") or 1))
        info["mounting_stats"] = stats.as_dict()
        info["mounting_mode"] = eff_mode
        skind = site_kind.kind_of(roof.code, roof)
        fence_base = str(((project.params or {}).get("survey") or {}).get("fence_base") or "freestanding")
        info["site_kind"] = skind
        if eff_mode == "lump":
            price = float(sel.get("lump_price_per_module") or roof.lump_price_per_module or 0)
            lump_name = fence_lump_name(fence_base) if skind == "fence" else f"Модулна алуминиева конструкция за {roof.label_bg.lower()}"
            lines.append(_line("mount:lump", "construction", lump_name, "бр.", panel_qty, price, meta={"mode": "lump"}))
        else:
            ml = bom.mounting_lines(db, roof, stats, markup, float(pricing.get("fastener_margin_pct", 0) or 0),
                                    fence_base=fence_base if skind == "fence" else None)
            if not ml:
                warnings.append("Няма дефинирани правила за монтажни материали за този тип покрив.")
            lines.extend(ml)
        if inc_delivery and float(pricing.get("delivery_fee_construction", 0)) > 0:
            lines.append(_line("delivery:construction", "construction", "Доставка на оборудване", "бр.", 1, pricing["delivery_fee_construction"]))
    elif not roof:
        warnings.append("Непознат тип покрив.")

    # --------------------------------------------------------------- electrical
    sb = _item(db, sel.get("switchboard_item_id"))
    want_ph = int((inverter.specs or {}).get("phases") or project.phase or 3) if inverter else int(project.phase or 3)
    if sb is None or (sb.specs or {}).get("phases") and int((sb.specs or {}).get("phases")) != want_ph:
        boards = db.query(CatalogItem).filter(CatalogItem.category == "switchboard", CatalogItem.active.is_(True)).order_by(CatalogItem.sort_order, CatalogItem.id).all()
        auto_sb = next((b for b in boards if int((b.specs or {}).get("phases") or 0) == want_ph), None)
        if auto_sb is not None and sel.get("auto_switchboard", True):
            if sb is not None:
                warnings.append(f"Таблото „{sb.name}“ е за друг брой фази — автоматично е избрано „{auto_sb.name}“.")
            sb = auto_sb
            info["switchboard_auto"] = auto_sb.id
    covered: set[str] = set()
    if sb:
        sb_qty = max(1, inv_qty or 1)
        lines.append(_item_line("switchboard", "electrical", sb, sb_qty, markup, name=f"{sb.name}" + (f" — по едно за всеки инвертор" if sb_qty > 1 else "")))
        covered = {str(x) for x in ((sb.specs or {}).get("covers_roles") or [])}
        info["switchboard_item_id"] = sb.id
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
    modes = cable_modes(sel)
    info["cable_modes"] = modes
    pipes = [p for p in (sel.get("pipes") or []) if isinstance(p, dict) and _num(p.get("m")) > 0 and p.get("item_id")]
    skip: set[str] = set()
    if modes["cables"] == "manual":
        skip |= MANUAL_CABLE_ROLES
    if modes["mc4"] == "kit":
        skip.add("mc4_pair")
    if modes["battery_cables"] == "kit":
        skip |= BATTERY_KIT_ROLES
    if pipes:
        skip |= {"conduit_32", "conduit_40"}
    design_cables: dict[str, list[dict[str, Any]]] = {}
    for r in design.get("roles") or []:
        rk = r["role"]
        if rk in MANUAL_CABLE_ROLES or rk == "mc4_pair" or rk in BATTERY_KIT_ROLES:
            design_cables.setdefault(rk, []).append(r)
        if rk in skip:
            if rk == "mc4_pair" or rk in BATTERY_KIT_ROLES:
                lab = "MC4 конектори — в комплекта с панелите" if rk == "mc4_pair" else f"{r['name']} — в комплекта с батерията"
                if lab not in info.setdefault("kit_included", []):
                    info["kit_included"].append(lab)
            continue
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
        if item is None and rk in covered:
            info.setdefault("covered_by_switchboard", []).append(r["name"])
            info.setdefault("covered_roles", []).append(rk)
            continue
        if item is None:
            item = engineering.find_item_for_role(all_items, r, pick)
            if item is not None and item.category == "mounting" and info.get("mounting_mode") == "lump":
                # construction priced per module already includes its fixings / earthing clamps
                info.setdefault("covered_by_construction", []).append(r["name"])
                continue
        if item is None and rk == "pv_cable":
            pvc = [c for c in all_items if c.category == "solar_cable" or (c.specs or {}).get("role") == "pv_cable"]
            if pvc:
                item = min(pvc, key=lambda c: abs(float((c.specs or {}).get("cross_section_mm2") or 6) - float(r["spec"].get("cross_section_mm2") or 6)))
                want = r["spec"].get("cross_section_mm2")
                have = (item.specs or {}).get("cross_section_mm2")
                if want and have and float(want) > float(have):
                    warnings.append(f"Изчислено е {want:g} mm² соларен кабел, а в каталога има {have:g} mm² — проверете пада на напрежение за дългите стрингове.")
        meta = {"role": rk, "auto_qty": r["qty"], "spec": r["spec"], "role_name": r["name"]}
        if item:
            name = r["name"] if rk in ("pv_cable",) else item.name
            if int(design.get("inverters") or 1) > 1 and rk in ("ac_mcb", "ac_cable", "ac_lug", "ac_rcd"):
                m = re.search(r"\(([^()]*)\)\s*$", r["name"])  # keep the purpose, e.g. "(табло AC → ГРТ)", when several AC lines coexist
                if m:
                    name = f"{name} ({m.group(1)})"
            lines.append(_item_line(key, r["section"], item, qty, markup, name=name, meta=meta))
        else:
            # the curated catalog has no article for this role → not quoted (listed for information only)
            missing.append(r["name"])
            info.setdefault("not_quoted_roles", []).append(rk)
    if missing:
        info["not_quoted"] = missing
    if modes["cables"] == "manual":
        lines.extend(_manual_cable_lines(db, sel, markup, design_cables, warnings, info))
    for i, pp in enumerate(pipes):
        it = _item(db, pp.get("item_id"))
        if it is None:
            continue
        ln = _item_line(f"pipe:{i}", "electrical", it, round(_num(pp.get("m")), 2), markup, meta={"role": "pvc_pipe", "client_hidden": True})
        ln["hidden"] = True  # bought and installed, but its price is spread over the visible electrical rows
        lines.append(ln)
    for extra in sel.get("electrical_items") or []:
        it = _item(db, extra.get("catalog_item_id") or extra.get("item_id"))
        if it:
            lines.append(_item_line(f"elec:{it.id}", "electrical", it, float(extra.get("qty") or 1), markup))

    # -------------------------------------------------------------------- labor
    labor_mode = sel.get("labor_mode") or pricing.get("labor_mode_default") or "per_inverter_kw"
    if labor_mode == "per_inverter_kw":
        rate = sel.get("labor_eur_per_kw")
        rate = float(rate) if isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate >= 0 else float(pricing.get("labor_eur_per_inverter_kw") or 0)
        inv_kw = float(((inverter.specs or {}).get("ac_power_kw") or 0) if inverter else 0) * (inv_qty or 0)
        info["labor"] = {"mode": "per_inverter_kw", "inverter_kw": round(inv_kw, 2), "rate": rate, "kwp": kwp}
        if inv_kw > 0 and rate > 0:
            lbl = f"{inv_qty} × {inv_kw / inv_qty:g} kW" if inv_qty > 1 else f"{inv_kw:g} kW"
            lines.append(_line("labor", "labor", f"Монтаж, пуск и настройка — инвертор {lbl} × {rate:g} €/kW", "kW", round(inv_kw, 3), rate,
                               meta={"mode": "per_inverter_kw", "rate": rate}))
        elif inv_kw <= 0:
            warnings.append("Трудът се изчислява по мощността на инвертора — изберете инвертор.")
        else:
            warnings.append("Не е зададена цена за труд €/kW (Настройки → Ценообразуване).")
        lo = db.get(LaborOption, int(sel["labor_option_id"])) if sel.get("labor_option_id") else None
        if lo:  # the matrix choice still gives the execution period / crew printed in the quote
            info["execution_days"], info["workers"] = lo.days, lo.workers
    elif labor_mode == "matrix" and sel.get("labor_option_id"):
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
    addons_total = 0.0
    for i, a in enumerate(sel.get("custom_addons") or []):
        if not isinstance(a, dict):
            continue
        qty, up = _num(a.get("qty")), _num(a.get("unit_price"))
        if qty <= 0 or up <= 0:
            continue
        name = (str(a.get("name") or "").strip() or "Допълнителен разход")[:500]
        unit = (str(a.get("unit") or "бр.").strip() or "бр.")[:16]
        ln = _line(f"addon:{i}", "other", name, unit, qty, up, purchase=up, meta={"addon": True, "spread": "all"})
        ln["hidden"] = True  # internal cost (e.g. pallet delivery) – spread over every visible row of the quote
        lines.append(ln)
        addons_total += qty * up
    if addons_total:
        info["addons_total"] = round(addons_total, 2)

    for ln in lines:  # articles marked "hidden in the client quote" in the catalog (e.g. PVC pipes)
        if ln.get("catalog_item_id") and not ln.get("hidden"):
            it = _item(db, ln["catalog_item_id"], include_inactive=True)
            if it is not None and (it.specs or {}).get("client_hidden"):
                ln["hidden"] = True
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


MANUAL_CABLE_ROLES = {"pv_cable", "ac_cable", "pe_cable", "bonding_cable", "rs485_cable", "ct_cable", "parallel_cable"}
BATTERY_KIT_ROLES = {"battery_cable", "battery_lug", "comm_cable"}


def _num(v: Any) -> float:
    if isinstance(v, bool):
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if math.isfinite(f) else 0.0


def cable_modes(sel: dict[str, Any]) -> dict[str, str]:
    """cables: auto | manual · mc4: kit | auto | manual · battery_cables: kit | auto.
    MC4 connectors and battery cables come with the panels / batteries (GM SUN) → "kit" = not quoted."""
    cm = sel.get("cables_mode") if sel.get("cables_mode") in ("auto", "manual") else "auto"
    mc = sel.get("mc4_mode")
    if mc not in ("kit", "auto", "manual"):
        mc = "manual" if (sel.get("mc4_item_id") or _num(sel.get("mc4_qty")) > 0) else "kit"
    bc = sel.get("battery_cables_mode") if sel.get("battery_cables_mode") in ("kit", "auto") else "kit"
    return {"cables": cm, "mc4": mc, "battery_cables": bc}


def _manual_cable_lines(db: Session, sel: dict[str, Any], markup: float, design: dict[str, list[dict[str, Any]]],
                        warnings: list[str], info: dict[str, Any]) -> list[dict[str, Any]]:
    """Cables chosen by hand (type + length per row). The engineering design is still checked: a missing solar / AC /
    PE cable or a smaller cross-section than calculated gives a warning."""
    out: list[dict[str, Any]] = []
    have: dict[str, float] = {}
    for i, c in enumerate(sel.get("cables") or []):
        if not isinstance(c, dict):
            continue
        it = _item(db, c.get("item_id"))
        m = round(_num(c.get("m")), 2)
        if it is None or m <= 0:
            continue
        sp = it.specs or {}
        role = sp.get("role")
        sec = "inverter" if it.category == "battery_accessory" else "electrical"
        out.append(_item_line(f"cable:{i}", sec, it, m, markup, meta={"role": role, "manual": True, "cross_section_mm2": sp.get("cross_section_mm2")}))
        if role:
            have[role] = max(have.get(role, 0.0), _num(sp.get("cross_section_mm2")))
    for role, label in (("pv_cable", "соларен кабел"), ("ac_cable", "AC захранващ кабел"), ("pe_cable", "заземителен проводник PE")):
        need = [r for r in design.get(role) or []]
        if not need:
            continue
        need_mm2 = max(_num((r.get("spec") or {}).get("cross_section_mm2")) for r in need)
        if role not in have:
            warnings.append(f"Ръчен избор на кабели: няма {label} (по проекта {need_mm2:g} mm²) — добавете ред в „Материали → Кабели“.")
        elif need_mm2 and have[role] and have[role] + 1e-9 < need_mm2:
            warnings.append(f"Ръчен избор на кабели: {label} {have[role]:g} mm² е под изчисленото сечение {need_mm2:g} mm² — проверете пада на напрежение и токовото натоварване.")
    info["manual_cables"] = len(out)
    return out


def fence_lump_name(base: str) -> str:
    if base == "wall":
        return "Конструкция за фотоволтаична стена — конзоли с анкери към фасадата, алуминиеви шини, скоби (вертикален монтаж)"
    if base == "existing":
        return "Конструкция за соларна ограда върху съществуваща ограда — U-болтове, алуминиеви шини, скоби (вертикален монтаж)"
    return "Конструкция за соларна ограда — поцинковани стълбове с бетонни фундаменти, алуминиеви шини, скоби (вертикален монтаж)"


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
        if nl.get("hidden"):
            ln.hidden = True  # forced: pipes, internal add-on costs
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


def is_active(ln: QuoteLine) -> bool:
    """Line is part of the offer (priced, ordered, installed) – visible or hidden, but not removed."""
    return not bool(getattr(ln, "excluded", False))


def is_visible(ln: QuoteLine) -> bool:
    """Line is shown to the client (its total includes the share of hidden lines)."""
    return is_active(ln) and not ln.hidden


def base_total(ln: QuoteLine) -> float:
    return round(float(ln.qty or 0) * float(ln.unit_price or 0), 2)


def _round_line(ln: QuoteLine, share: float) -> None:
    """Spread ``share`` € over the unit price so that qty × client unit price = line total (2 decimals)."""
    base = base_total(ln)
    qty = float(ln.qty or 0)
    if abs(share) < 0.005 or qty <= 0:
        ln.client_unit_price, ln.total, ln.alloc = round(float(ln.unit_price or 0), 2), base, 0.0
        return
    cu = round(float(ln.unit_price or 0) + share / qty, 2)
    ln.client_unit_price = cu
    ln.total = round(qty * cu, 2)
    ln.alloc = round(ln.total - base, 2)


def _absorb(lines: list[QuoteLine], diff: float) -> None:
    """Put a rounding difference (cents) on one line, preferring qty = 1 so the unit price stays exact."""
    diff = round(diff, 2)
    if abs(diff) < 0.005 or not lines:
        return
    ones = [l for l in lines if abs(float(l.qty or 0) - 1.0) < 1e-9]
    tgt = max(ones or lines, key=lambda l: (l.total, -(l.id or 0)))
    tgt.total = round(tgt.total + diff, 2)
    tgt.alloc = round((tgt.alloc or 0) + diff, 2)
    q = float(tgt.qty or 0)
    if q > 0:
        tgt.client_unit_price = round(tgt.total / q, 2) if ones else round(tgt.total / q, 4)


def distribute_hidden(quote: Quote) -> float:
    """Hidden lines stay in the price: their value is spread over the visible lines **of the same section**
    proportionally to each visible line's value (equal split if those are all zero). A section without any
    visible line passes its hidden value to all visible lines of the quote. Section totals and the grand total are
    therefore exactly the same as with every line visible. Returns the distributed amount."""
    active = [l for l in quote.lines if is_active(l)]
    visible = [l for l in active if not l.hidden]
    hidden = [l for l in active if l.hidden]
    for l in active:
        l.alloc = 0.0
        l.client_unit_price = round(float(l.unit_price or 0), 2)
        l.total = base_total(l)
    for l in quote.lines:
        if not is_active(l):
            l.alloc, l.client_unit_price, l.total = 0.0, round(float(l.unit_price or 0), 2), base_total(l)
    if not hidden or not visible:
        return 0.0
    share: dict[int, float] = {}
    by_sec: dict[str, float] = {}
    whole = 0.0  # add-on costs (meta.spread = "all") go over every visible row of the quote
    for l in hidden:
        if (getattr(l, "meta", None) or {}).get("spread") == "all":
            whole += base_total(l)
        else:
            by_sec[l.section] = by_sec.get(l.section, 0.0) + base_total(l)

    def spread(targets: list[QuoteLine], amount: float) -> None:
        targets = [t for t in targets if float(t.qty or 0) > 0] or targets
        w = [max(base_total(t), 0.0) for t in targets]
        tw = sum(w)
        for t, wi in zip(targets, w):
            share[id(t)] = share.get(id(t), 0.0) + amount * (wi / tw if tw > 0 else 1.0 / len(targets))

    for sec, amount in by_sec.items():
        tg = [l for l in visible if l.section == sec]
        spread(tg or visible, amount)
    if abs(whole) > 1e-9:
        spread(visible, whole)
    expected: dict[str, float] = {}
    for l in visible:
        _round_line(l, share.get(id(l), 0.0))
        expected[l.section] = expected.get(l.section, 0.0) + base_total(l) + share.get(id(l), 0.0)
    for sec, exp in expected.items():
        sl = [l for l in visible if l.section == sec]
        _absorb(sl, exp - sum(l.total for l in sl))
    grand = round(sum(base_total(l) for l in active), 2)
    _absorb(visible, grand - sum(l.total for l in visible))
    return round(sum(base_total(l) for l in hidden), 2)


def compute_totals(quote: Quote) -> None:
    distribute_hidden(quote)
    subtotal = round(sum(ln.total for ln in quote.lines if is_visible(ln)), 2)
    quote.subtotal = subtotal
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
        lns = [l for l in quote.lines if l.section == code and is_visible(l)]
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
    # hidden lines are still bought and installed → their cost counts; removed (excluded) lines do not
    cost = sum(float(l.qty) * float(l.purchase_price or 0) for l in quote.lines if is_active(l) and l.catalog_item_id)
    # lines without catalog item (labor, delivery) are treated as pass-through revenue (no cost tracked)
    margin = quote.net_total - cost - sum(base_total(l) for l in quote.lines if is_active(l) and not l.catalog_item_id and l.section in ("labor",))
    return round(cost, 2), round(margin, 2)


def next_quote_number(db: Session, project: Project, prefix: str = "") -> str:
    from datetime import date

    d = date.today()
    base = f"{prefix}{d:%y%m%d}"
    n = db.query(Quote).filter(Quote.number.like(f"{base}-%")).count() + 1
    return f"{base}-{n:02d}PV"


def estimate_yield(kwp: float, specific_yield: float, azimuth_deg: float = 180.0, tilt_deg: float = 20.0, bifaciality: float = 0.0) -> float:
    """Annual yield estimate: kWp × specific yield × orientation factor.

    Vertical modules (tilt ≥ 75°, solar fence / PV wall): front side south 0.70, east/west 0.58, north 0.30 of the
    optimum; a bifacial module also produces from the rear side (opposite azimuth) × bifaciality × 0.8 (rear
    irradiance / albedo) – an east–west bifacial fence reaches ~0.9 of an optimally tilted south array."""
    if kwp <= 0:
        return 0.0
    az = abs(((azimuth_deg - 180) + 180) % 360 - 180)  # 0 = south
    if tilt_deg >= 75:
        def vert(a: float) -> float:
            return 0.70 - 0.12 * (a / 90.0) if a <= 90 else 0.58 - 0.28 * ((a - 90) / 90.0)

        f = vert(az) + max(0.0, min(float(bifaciality or 0), 100.0)) / 100.0 * vert(180.0 - az) * 0.8
        return round(kwp * specific_yield * f, 0)
    # simple orientation factor: south 1.0, east/west ~0.85, north ~0.6; tilt optimum ~30°
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
