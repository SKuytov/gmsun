"""Electrical & system engineering engine.

Turns panel/inverter/battery specs + the layout into a complete, standards-based
design and a *role-based* bill of materials:

* String design (IEC 62548 / IEC 60364-7-712):
    - Voc at the design minimum cell temperature must stay below the inverter's
      maximum DC voltage; Vmp at the design maximum cell temperature must stay
      above the MPPT minimum; Vmp(cold) below the MPPT maximum.
    - One string per MPPT when possible, equal string lengths per MPPT,
      per-plane strings (no mixing of roof planes in one string).
    - Per MPPT current check (operating current and Isc).
* Over-current protection (IEC 62548 §6.5): string fuses only when
  (Ns-1) x Isc x 1.25 > module max series fuse; fuse 1.5 x Isc <= In <= 2.4 x Isc.
* DC cable: design current 1.25 x Isc, voltage drop at Imp (target <= 1 %),
  lengths from the actual cable run (one-way distance array -> inverter) plus the
  string span, with the configurable cable reserve (industry practice 10-15 %).
* AC protection from the inverter manual (breaker, RCD type A 300 mA, SPD T2),
  cable size with voltage-drop check (target <= 1 %).
* Battery DC breaker / cable from the inverter manual table.
* Earthing & bonding (IEC 62548 §7): 6 mm2 bonding along the rails with one
  bonding clamp per rail line, PE from the inverter per manual.
* Cable management consumables with the fastener/consumable reserve.

Every quantity is returned together with the formula inputs so the PDF
technical file can show how it was derived, and so the user can override any
line in the quote.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem

# standard ratings
MCB_STD = [10, 13, 16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 160]
RCD_STD = [25, 40, 63, 80, 100, 125]
FUSE_STD = [10, 12, 15, 16, 20, 25, 30, 32]
DC_BREAKER_STD = [63, 80, 100, 125, 160, 200, 250, 300, 400, 500, 630]
CABLE_STD = [2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120]
# IEC 60364-5-52, reference method E/F (free air / tray) approx. current carrying capacity, Cu, 70°C PVC/90°C XLPE mixed-conservative
CABLE_IZ = {2.5: 25, 4: 34, 6: 43, 10: 60, 16: 80, 25: 106, 35: 131, 50: 159, 70: 202, 95: 245, 120: 284}
SIGMA_CU = 56.0  # m/(Ω·mm²)


def _f(d: dict[str, Any] | None, k: str, default: float = 0.0) -> float:
    try:
        v = (d or {}).get(k)
        return float(v) if v is not None and v != "" else default
    except (TypeError, ValueError):
        return default


def _std(value: float, table: list[float | int]) -> float | int:
    for v in table:
        if v >= value - 1e-9:
            return v
    return table[-1]


def _round_up(v: float, step: float = 1.0) -> float:
    return math.ceil(v / step - 1e-9) * step


# ----------------------------------------------------------------------------- strings
def string_design(panel: CatalogItem | None, inverter: CatalogItem | None, planes: list[dict[str, Any]], design: dict[str, Any]) -> dict[str, Any]:
    """planes: [{name, modules, span_m, azimuth, tilt}] -> string table + checks."""
    out: dict[str, Any] = {"strings": [], "warnings": [], "checks": []}
    n_total = sum(int(p.get("modules") or 0) for p in planes)
    if not panel or not inverter or n_total <= 0:
        return out
    ps, inv = panel.specs or {}, inverter.specs or {}
    voc, vmp, isc, imp = _f(ps, "voc"), _f(ps, "vmp"), _f(ps, "isc"), _f(ps, "imp")
    wp = _f(ps, "wp")
    b_voc = abs(_f(ps, "temp_coeff_voc", -0.25)) / 100.0
    b_pmax = abs(_f(ps, "temp_coeff_pmax", -0.30)) / 100.0
    max_fuse = _f(ps, "max_series_fuse_a", 25)
    tmin = _f(design, "design_tmin_c", -20)
    tmax = _f(design, "design_tcell_max_c", 70)
    max_dc_v = _f(inv, "max_dc_voltage", 1000)
    start_v = _f(inv, "start_voltage", 0)
    mppt_min = _f(inv, "mppt_v_min", 150)
    mppt_max = _f(inv, "mppt_v_max", max_dc_v * 0.85)
    mppts = max(1, int(_f(inv, "mppt_count", 2)))
    spm = max(1, int(_f(inv, "strings_per_mppt", 1)))
    i_op = _f(inv, "max_input_current_a", 0)  # per MPPT operating current
    i_sc_max = _f(inv, "max_isc_a", i_op * 1.5 if i_op else 0)

    voc_cold = voc * (1 + b_voc * (25 - tmin))
    vmp_cold = vmp * (1 + b_pmax * (25 - tmin))
    vmp_hot = vmp * (1 - b_pmax * (tmax - 25))
    ns_max = int(min(math.floor(max_dc_v / voc_cold) if voc_cold else 99, math.floor(mppt_max / vmp_cold) if vmp_cold else 99))
    ns_min = int(math.ceil(max(mppt_min, start_v) / vmp_hot)) if vmp_hot else 1
    out.update(
        {
            "voc_stc": voc, "vmp_stc": vmp, "isc": isc, "imp": imp,
            "voc_cold": round(voc_cold, 1), "vmp_cold": round(vmp_cold, 1), "vmp_hot": round(vmp_hot, 1),
            "tmin_c": tmin, "tcell_max_c": tmax, "ns_max": ns_max, "ns_min": ns_min,
            "mppts": mppts, "strings_per_mppt": spm, "inputs": mppts * spm,
            "inv_max_dc_v": max_dc_v, "inv_mppt_min": mppt_min, "inv_mppt_max": mppt_max, "inv_i_op": i_op, "inv_i_sc": i_sc_max,
        }
    )
    if ns_max < 1 or ns_max < ns_min:
        out["warnings"].append("Няма допустима дължина на стринг за тази комбинация панел/инвертор (проверете Voc/MPPT).")
        return out

    # ---- allocate strings per plane
    strings: list[dict[str, Any]] = []
    active_planes = [p for p in planes if int(p.get("modules") or 0) > 0]
    for pi, pl in enumerate(planes):
        n = int(pl.get("modules") or 0)
        if n <= 0:
            continue
        s_need = math.ceil(n / ns_max)
        s = s_need
        # single plane: use every MPPT when the strings stay >= ns_min (better MPP tracking, lower current per input)
        if len(active_planes) == 1 and s < mppts and n // mppts >= ns_min:
            s = mppts
        base, rem = divmod(n, s)
        for k in range(s):
            cnt = base + (1 if k < rem else 0)
            strings.append({"plane": pl.get("name") or f"Плоскост {pi + 1}", "plane_index": pi, "modules": cnt, "span_m": round(cnt * _f(pl, "module_w_m", 1.134) + (cnt - 1) * 0.02, 2), "azimuth": pl.get("azimuth"), "tilt": pl.get("tilt")})
    # ---- assign to MPPT inputs: one string per MPPT first, then second strings
    inputs = mppts * spm
    if len(strings) > inputs:
        out["warnings"].append(f"{len(strings)} стринга надвишават входовете на инвертора ({mppts} MPPT × {spm}). Намалете стринговете или изберете по-голям инвертор.")
    for i, st in enumerate(strings):
        st["id"] = f"S{i + 1}"
        st["mppt"] = (i % mppts) + 1
        st["input"] = (i // mppts) + 1
        st["voc_cold_v"] = round(st["modules"] * voc_cold, 1)
        st["vmp_stc_v"] = round(st["modules"] * vmp, 1)
        st["vmp_hot_v"] = round(st["modules"] * vmp_hot, 1)
        st["kwp"] = round(st["modules"] * wp / 1000, 3)
        if st["modules"] < ns_min:
            out["warnings"].append(f"Стринг {st['id']} ({st['modules']} модула): Vmp при {tmax:g} °C = {st['vmp_hot_v']} V е под MPPT минимума {mppt_min:g} V.")
        if st["modules"] > ns_max:
            out["warnings"].append(f"Стринг {st['id']} ({st['modules']} модула): Voc при {tmin:g} °C = {st['voc_cold_v']} V надвишава {max_dc_v:g} V.")
    # equal lengths per MPPT & current check
    per_mppt: dict[int, list[dict[str, Any]]] = {}
    for st in strings:
        per_mppt.setdefault(st["mppt"], []).append(st)
    fuses_required = False
    for m, sts in per_mppt.items():
        if len({s["modules"] for s in sts}) > 1:
            out["warnings"].append(f"MPPT {m}: паралелни стрингове с различна дължина ({', '.join(str(s['modules']) for s in sts)}). Изравнете ги.")
        if len({s["plane_index"] for s in sts}) > 1:
            out["warnings"].append(f"MPPT {m}: паралелни стрингове от различни плоскости — препоръчва се отделен MPPT за всяка ориентация.")
        if i_op and len(sts) * imp > i_op + 1e-6:
            out["warnings"].append(f"MPPT {m}: работен ток {len(sts) * imp:.1f} A надвишава {i_op:g} A на входа (ограничение на мощността).")
        if i_sc_max and len(sts) * isc > i_sc_max + 1e-6:
            out["warnings"].append(f"MPPT {m}: Isc {len(sts) * isc:.1f} A надвишава максимално допустимия {i_sc_max:g} A.")
        if (len(sts) - 1) * isc * 1.25 > max_fuse:
            fuses_required = True
    out["strings"] = strings
    out["count"] = len(strings)
    out["modules_per_string"] = max((s["modules"] for s in strings), default=0)
    out["fuses_required"] = fuses_required
    fuse_a = _std(1.5 * isc, FUSE_STD) if isc else 0
    out["fuse_a"] = fuse_a if fuse_a <= max(max_fuse, 1) and fuse_a <= 2.4 * isc + 1e-9 else fuse_a
    out["fuse_rule"] = f"1,5×Isc={1.5 * isc:.1f} A ≤ In ≤ 2,4×Isc={2.4 * isc:.1f} A; ≤ макс. предпазител на модула {max_fuse:g} A"
    out["max_series_fuse_a"] = max_fuse
    out["checks"] = [
        {"ok": all(s["modules"] <= ns_max for s in strings), "text": f"Voc при {tmin:g} °C: {out['modules_per_string'] * voc_cold:.0f} V ≤ {max_dc_v:g} V (макс. DC)"},
        {"ok": all(s["modules"] >= ns_min for s in strings), "text": f"Vmp при {tmax:g} °C: {min((s['modules'] for s in strings), default=0) * vmp_hot:.0f} V ≥ {mppt_min:g} V (MPPT мин.)"},
        {"ok": len(strings) <= inputs, "text": f"{len(strings)} стринга на {inputs} входа ({mppts} MPPT)"},
        {"ok": not fuses_required, "text": "Стрингови предпазители: " + ("необходими" if fuses_required else "не са необходими — (Ns−1)×Isc×1,25 ≤ макс. предпазител на модула")},
    ]
    return out


# ----------------------------------------------------------------------------- full design
def full_design(
    db: Session,
    *,
    project: Any,
    panel: CatalogItem | None,
    inverter: CatalogItem | None,
    battery: CatalogItem | None,
    battery_qty: int,
    panel_qty: int,
    planes: list[dict[str, Any]],
    rail_lines: int,
    row_length_m: float,
    sel: dict[str, Any],
    pricing: dict[str, Any],
) -> dict[str, Any]:
    params = project.params or {}
    design = {
        "design_tmin_c": _f(params, "design_tmin_c", _f(pricing, "design_tmin_c", -20)),
        "design_tcell_max_c": _f(pricing, "design_tcell_max_c", 70),
    }
    cable_margin = _f(pricing, "cable_margin_pct", 15) / 100.0
    fast_margin = _f(pricing, "fastener_margin_pct", 10) / 100.0
    dc_run = _f(params, "dc_run_m", _f(pricing, "dc_run_default_m", 15))
    ac_run = _f(params, "ac_run_m", _f(pricing, "ac_run_default_m", 10))
    batt_run = _f(params, "battery_run_m", 2)
    backup_run = _f(params, "backup_run_m", 3)
    dc_box_dist = _f(pricing, "dc_box_distance_m", 10)
    dc_vdrop_max = _f(pricing, "dc_vdrop_max_pct", 1.0)
    ac_vdrop_max = _f(pricing, "ac_vdrop_max_pct", 1.0)
    project_phase = int(getattr(project, "phase", 3) or 3)
    inv_phase = int(_f(inverter.specs or {}, "phases", project_phase)) if inverter else project_phase
    phase = inv_phase  # the inverter decides the AC topology (poles, cores); the project phase is only cross-checked
    phase_warning = f"Инверторът е {inv_phase}-фазен, а обектът е заявен като {project_phase}-фазен — проверете присъединяването." if inverter and inv_phase != project_phase else None

    inv = (inverter.specs if inverter else {}) or {}
    ps = (panel.specs if panel else {}) or {}
    bs = (battery.specs if battery else {}) or {}
    sd = string_design(panel, inverter, planes, design)
    strings = sd.get("strings") or []
    n_str = len(strings)
    warnings: list[str] = list(sd.get("warnings") or [])
    if phase_warning:
        warnings.append(phase_warning)
    roles: list[dict[str, Any]] = []

    def role(key: str, name: str, qty: float, unit: str = "бр.", section: str = "electrical", **spec: Any) -> None:
        if qty <= 0:
            return
        roles.append({"role": key, "name": name, "qty": qty, "unit": unit, "section": section, "spec": spec})

    # ------------------------------------------------------------------ DC side
    isc, imp, vmp = _f(ps, "isc"), _f(ps, "imp"), _f(ps, "vmp")
    dc: dict[str, Any] = {"run_m": dc_run}
    if n_str:
        i_design = 1.25 * isc
        mm2 = 6.0
        for s in strings:
            L = dc_run + s["span_m"]  # one-way length incl. string span
            u = s["modules"] * vmp
            vd = (2 * L * imp) / (SIGMA_CU * mm2 * u) * 100 if u else 0
            s["cable_one_way_m"] = round(L, 1)
            s["vdrop_pct"] = round(vd, 2)
        worst = max(s["vdrop_pct"] for s in strings)
        while worst > dc_vdrop_max and mm2 < 16:
            mm2 = _std(mm2 + 0.1, CABLE_STD)
            for s in strings:
                u = s["modules"] * vmp
                s["vdrop_pct"] = round((2 * (dc_run + s["span_m"]) * imp) / (SIGMA_CU * mm2 * u) * 100, 2) if u else 0
            worst = max(s["vdrop_pct"] for s in strings)
        red = sum(dc_run + s["span_m"] + 2 for s in strings)
        black = sum(dc_run + 2 for s in strings)
        dc.update(
            {
                "cable_mm2": mm2, "design_current_a": round(i_design, 1), "cable_iz_a": CABLE_IZ.get(mm2), "vdrop_worst_pct": worst, "vdrop_limit_pct": dc_vdrop_max,
                "red_m_raw": round(red, 1), "black_m_raw": round(black, 1), "margin_pct": cable_margin * 100,
                "red_m": _round_up(red * (1 + cable_margin), 5), "black_m": _round_up(black * (1 + cable_margin), 5),
            }
        )
        role("pv_cable", f"Соларен кабел червен (+) {mm2:g} mm² H1Z2Z2-K", dc["red_m"], unit="м", cross_section_mm2=mm2, color="red")
        role("pv_cable", f"Соларен кабел черен (−) {mm2:g} mm² H1Z2Z2-K", dc["black_m"], unit="м", cross_section_mm2=mm2, color="black")
        box_mode = sel.get("dc_box", "auto")
        dc_box = (dc_run > dc_box_dist) if box_mode == "auto" else box_mode in ("yes", True)
        dc["box"] = dc_box
        dc["box_reason"] = (
            f"разстояние масив–инвертор {dc_run:g} m > {dc_box_dist:g} m → DC защита (SPD T2) при масива съгласно IEC 61643-32" if (dc_box and box_mode == "auto") else ("по избор" if dc_box else "не е необходима — вградени DC прекъсвач и SPD T2 в инвертора" if inv.get("integrated_spd", True) else "не е избрана")
        )
        # MC4 pairs: 1 pair at the string ends + 1 pair at the inverter (or box) per string, +1 spare
        mc4 = 2 * n_str + (2 * n_str if dc_box else 0) + 1
        dc["mc4_pairs"] = mc4
        role("mc4_pair", "Конектор MC4 комплект (мъжки+женски)", mc4)
        if sd.get("fuses_required") or (dc_box and sel.get("dc_box_fuses", False)):
            role("dc_fuse", f"Предпазител gPV {sd['fuse_a']} A 1000 V DC 10×38", 2 * n_str, rating_a=sd["fuse_a"])
            role("dc_fuse_holder", "Държач за предпазител 10×38 1000 V DC (1P)", 2 * n_str)
        if dc_box:
            mppts_used = len({s["mppt"] for s in strings})
            role("dc_spd", "Катоден отводител DC тип 2, 1000 V (Y-схема)", mppts_used)
            role("dc_isolator", "Разединител DC 1000 V 32 A, 4P (2 стринга)", math.ceil(n_str / 2), rating_a=32)
            role("dc_enclosure", "Табло DC IP65 (за SPD/предпазители/разединител)", 1)
            role("cable_gland", "Кабелен салник M20 IP68 (соларен кабел)", 2 * n_str + 2 * mppts_used)
        dc["dc_switch_integrated"] = bool(inv.get("integrated_dc_switch", True))
        if inverter and not inv.get("integrated_dc_switch", True):
            role("dc_isolator", "Разединител DC 1000 V 32 A, 4P при инвертора", math.ceil(n_str / 2), rating_a=32)
    # ---------------------------------------------------------------- AC side
    ac: dict[str, Any] = {"run_m": ac_run, "phase": phase}
    if inverter:
        p_kw = _f(inv, "ac_power_kw")
        i_max = _f(inv, "max_ac_current_a") or (p_kw * 1000 / (math.sqrt(3) * 400) if phase == 3 else p_kw * 1000 / 230) * 1.1
        brk = int(_f(inv, "ac_breaker_a") or _std(1.25 * i_max, MCB_STD))
        rcd = int(_std(brk, RCD_STD))
        poles = "4P" if phase == 3 else "2P"
        mm2 = _f(inv, "ac_cable_mm2")
        if not mm2:
            mm2 = next((c for c in CABLE_STD if CABLE_IZ[c] >= brk), 16)
        u = 400 if phase == 3 else 230
        pf = 1.0

        def vdrop(a: float) -> float:
            if phase == 3:
                return (math.sqrt(3) * ac_run * i_max * pf) / (SIGMA_CU * a * u) * 100
            return (2 * ac_run * i_max * pf) / (SIGMA_CU * a * u) * 100

        vd = vdrop(mm2)
        while vd > ac_vdrop_max and mm2 < 70:
            mm2 = _std(mm2 + 0.1, CABLE_STD)
            vd = vdrop(mm2)
        cores = 5 if phase == 3 else 3
        ac_len_raw = ac_run + 3  # inverter + board terminations
        ac.update(
            {
                "i_max_a": round(i_max, 1), "breaker_a": brk, "breaker_poles": poles, "rcd_a": rcd, "rcd_ma": int(_f(inv, "rcd_ma", 300)), "rcd_type": "A",
                "cable_mm2": mm2, "cores": cores, "cable_m_raw": ac_len_raw, "cable_m": _round_up(ac_len_raw * (1 + cable_margin), 1), "vdrop_pct": round(vd, 2), "vdrop_limit_pct": ac_vdrop_max,
                "spd_integrated": bool(inv.get("integrated_spd", True)),
            }
        )
        role("ac_mcb", f"Автоматичен прекъсвач {poles} {brk} A, крива C, 6 kA (вход мрежа)", 1, rating_a=brk, poles=poles)
        role("ac_rcd", f"Дефектнотокова защита {poles} {rcd} A / 300 mA тип A", 1, rating_a=rcd, poles=poles)
        role("ac_spd", f"Катоден отводител AC тип 2, {'3P+N' if phase == 3 else '1P+N'} 275 V", 1, phases=phase)
        role("ac_cable", f"Кабел СВТ {cores}×{mm2:g} mm² (инвертор → ГРТ)", ac["cable_m"], unit="м", cross_section_mm2=mm2, cores=cores)
        role("ac_lug", f"Кабелен накрайник / накрайник за жило {mm2:g} mm²", 2 * cores)
        # backup (load) output — optional sub-board
        if sel.get("backup_output"):
            role("ac_mcb", f"Автоматичен прекъсвач {poles} {brk} A, крива C (изход резервирани товари)", 1, rating_a=brk, poles=poles)
            role("ac_cable", f"Кабел СВТ {cores}×{mm2:g} mm² (инвертор → табло резервирани товари)", _round_up((backup_run + 3) * (1 + cable_margin), 1), unit="м", cross_section_mm2=mm2, cores=cores)
            role("ac_enclosure", "Табло за резервирани товари (подтабло)", 1)
            ac["backup"] = True
        # metering
        metering = sel.get("metering", "ct")
        ac["metering"] = metering
        ct_leads = _f(inv, "ct_lead_m", 4)
        if metering == "smart_meter":
            role("smart_meter", "Смарт електромер Modbus RS485 (Eastron SDM630 / SDM230)", 1, phases=phase)
            role("rs485_cable", "Кабел RS485 екраниран 2×0,5 mm² (инвертор → електромер)", _round_up((ac_run + 2) * (1 + cable_margin), 1), unit="м")
        elif ac_run + 1 > ct_leads:
            role("ct_cable", "Кабел за удължаване на токови трансформатори 2×0,75 mm² екраниран", _round_up(3 * (ac_run + 2 - ct_leads) * (1 + cable_margin), 1) if phase == 3 else _round_up((ac_run + 2 - ct_leads) * (1 + cable_margin), 1), unit="м")
        role("labels", "Комплект предупредителни табели PV (DC, двойно захранване, инвертор, табло) по IEC 62548", 1)
    # --------------------------------------------------------------- battery
    bat: dict[str, Any] = {}
    if battery and battery_qty > 0 and inverter:
        inputs = int(_f(inv, "battery_inputs", 1))
        brk_a = int(_f(inv, "battery_breaker_a") or _std(_f(inv, "max_charge_a", 100) * 1.25, DC_BREAKER_STD))
        mm2 = _f(inv, "battery_cable_mm2") or next((c for c in CABLE_STD if CABLE_IZ[c] >= _f(inv, "max_charge_a", 100) * 1.25), 70)
        kwh = _f(bs, "kwh")
        parallel = battery_qty > inputs
        bat.update(
            {
                "qty": battery_qty, "kwh": round(kwh * battery_qty, 2), "inputs": inputs, "breaker_a": brk_a, "cable_mm2": mm2, "run_m": batt_run,
                "built_in_breaker": bool(bs.get("built_in_breaker")), "busbar": parallel, "max_charge_a": _f(inv, "max_charge_a"),
            }
        )
        per_cable = batt_run + 0.5
        n_cables = battery_qty if not parallel else battery_qty + inputs
        bat["cable_m"] = _round_up(2 * per_cable * n_cables * (1 + cable_margin), 1)
        role("battery_cable", f"Батериен кабел {mm2:g} mm² гъвкав (червен/черен) H07V-K", bat["cable_m"], unit="м", section="inverter", cross_section_mm2=mm2)
        role("battery_lug", f"Кабелна обувка тръбна {mm2:g} mm² M8/M10", 4 * n_cables, section="inverter")
        role("battery_breaker", f"DC прекъсвач/разединител батерия {brk_a} A, 2P, 125 V DC", min(battery_qty, inputs) if not parallel else inputs, section="inverter", rating_a=brk_a)
        if parallel:
            role("battery_busbar", f"Шинен разпределител DC {_std(brk_a * 1.2, DC_BREAKER_STD)} A (+/−) за паралелни батерии", 1, section="inverter")
        role("comm_cable", "Комуникационен кабел CAN/RS485 RJ45 (батерия ↔ инвертор/батерия)", battery_qty, section="inverter")
        if battery_qty > int(_f(bs, "max_parallel", 16)):
            warnings.append(f"Батерии в паралел ({battery_qty}) надвишават допустимото за модела ({int(_f(bs, 'max_parallel'))}).")
    # -------------------------------------------------------------- earthing
    grd: dict[str, Any] = {}
    if panel_qty:
        pe_mm2 = _f(inv, "pe_cable_mm2", 16) if inverter else 16
        bonding_m = row_length_m + dc_run + 5
        grd.update({"pe_mm2": pe_mm2, "pe_m": _round_up((ac_run + 2) * (1 + cable_margin), 1), "bonding_mm2": 6, "bonding_m_raw": round(bonding_m, 1), "bonding_m": _round_up(bonding_m * (1 + cable_margin), 5), "bonding_clamps": rail_lines})
        role("pe_cable", f"Заземителен проводник ПВ-А1 {pe_mm2:g} mm² жълто-зелен (инвертор → заземителна шина)", grd["pe_m"], unit="м", cross_section_mm2=pe_mm2)
        role("bonding_cable", "Заземителен проводник 6 mm² жълто-зелен (изравняване на потенциалите на конструкцията)", grd["bonding_m"], unit="м", cross_section_mm2=6)
        role("bonding_clamp", "Клема за заземяване на шина (WCL8-10 / еквивалент)", int(math.ceil(rail_lines * (1 + fast_margin))), section="construction")
        role("earth_bar", "Заземителна шина / клеморед PE в таблото", 1)
        if sel.get("earth_rod", getattr(project, "roof_type", "") == "ground"):
            role("earth_rod", "Заземителен кол 1,5 m поцинкован + клема за кол", 1 if panel_qty <= 40 else 2)
            role("earth_strip", "Поцинкована шина 30×4 mm за заземител", 10 if panel_qty <= 40 else 20, unit="м")
            grd["earth_rod"] = True
    # ---------------------------------------------------- cable management
    mgmt: dict[str, Any] = {}
    if panel_qty and n_str:
        ties = int(math.ceil((4 * panel_qty + 2 * rail_lines + 10 * n_str) * (1 + fast_margin)))
        conduit_dc = _round_up(dc_run * math.ceil(2 * n_str / 4) * (1 + cable_margin), 1)  # ≤4 PV cables per ф32 conduit
        conduit_ac = _round_up((ac_run + (batt_run if bat else 0)) * (1 + cable_margin), 1)
        clips = int(math.ceil((conduit_dc + conduit_ac) * 2 * (1 + fast_margin)))
        mgmt.update({"ties": ties, "conduit_dc_m": conduit_dc, "conduit_ac_m": conduit_ac, "conduit_clips": clips})
        role("cable_tie_uv", "Кабелна връзка UV-устойчива 4,8×200 mm (черна)", ties)
        role("conduit_32", "Гофрирана тръба UV ф32 (DC кабели)", conduit_dc, unit="м")
        role("conduit_40", "Гофрирана тръба UV ф40 (AC/батерийни кабели)", conduit_ac, unit="м")
        role("conduit_clip", "Скоба за гофрирана тръба ф32/ф40", clips)
        role("end_sleeve", f"Кабелен накрайник за жило 6 mm² (DC)", 4 * n_str)
    # --------------------------------------------------------------------
    return {
        "strings": sd,
        "dc": dc,
        "ac": ac,
        "battery": bat,
        "grounding": grd,
        "management": mgmt,
        "margins": {"cable_pct": cable_margin * 100, "fastener_pct": fast_margin * 100, "module_spare_pct": _f(pricing, "module_spare_pct", 0)},
        "roles": roles,
        "warnings": warnings,
    }


# ----------------------------------------------------------------------- catalog matching
def find_item_for_role(items: list[CatalogItem], r: dict[str, Any]) -> CatalogItem | None:
    """Pick the catalog item with specs.role == role; for rated parts the smallest
    rating >= required; for cables the smallest cross-section >= required."""
    spec = r.get("spec") or {}
    cands = [it for it in items if it.active and (it.specs or {}).get("role") == r["role"]]
    if not cands:
        return None
    need_a = _f(spec, "rating_a")
    need_mm2 = _f(spec, "cross_section_mm2")
    poles = spec.get("poles")
    phases = spec.get("phases")
    cores = spec.get("cores")

    def ok(it: CatalogItem) -> bool:
        s = it.specs or {}
        if poles and s.get("poles") and str(s.get("poles")).upper() != str(poles).upper():
            return False
        if phases and s.get("phases") and int(s.get("phases")) != int(phases):
            return False
        if cores and s.get("cores") and int(s.get("cores")) != int(cores):
            return False
        if need_a and _f(s, "rating_a") and _f(s, "rating_a") < need_a - 1e-9:
            return False
        if need_mm2 and _f(s, "cross_section_mm2") and _f(s, "cross_section_mm2") < need_mm2 - 1e-9:
            return False
        return True

    good = [it for it in cands if ok(it)]
    if not good:
        return None
    good.sort(key=lambda it: (_f(it.specs, "rating_a") or 0, _f(it.specs, "cross_section_mm2") or 0, it.purchase_price or 0))
    return good[0]
