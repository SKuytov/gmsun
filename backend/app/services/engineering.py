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
from collections.abc import Callable
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
# brands whose hybrid inverters only accept their own battery systems (closed BMS protocol)
CLOSED_BATTERY_ECOSYSTEMS = {"huawei": ["huawei"], "sungrow": ["sungrow"], "goodwe": ["goodwe"], "luxpower": []}


def battery_compatibility(inverter: CatalogItem | None, battery: CatalogItem | None, qty: int = 1) -> list[str]:
    """Cross-check a battery against the inverter: voltage class, DC window, charge current and brand ecosystem."""
    if not inverter or not battery:
        return []
    inv, bs = inverter.specs or {}, battery.specs or {}
    w: list[str] = []
    ivc = (inv.get("battery_voltage_class") or "").upper()
    bvc = (bs.get("voltage_class") or "").upper()
    if inv.get("hybrid") is False:
        w.append("Избраният инвертор не е хибриден — батерията не може да се свърже към него.")
        return w
    if ivc and bvc and ivc != bvc:
        w.append(f"Клас на напрежение: инверторът е за {ivc} батерии, а батерията е {bvc}.")
    vmin, vmax, vnom = _f(inv, "battery_v_min"), _f(inv, "battery_v_max"), _f(bs, "nominal_v")
    if bvc == "HV" and _f(bs, "module_v_max"):
        lo_n, hi_n = hv_series_range(inv, bs)
        n = int(qty)
        if hi_n < lo_n:
            w.append(f"Батерийните модули не могат да се свържат към този инвертор — прозорецът {vmin:g}–{vmax:g} V не допуска нито един брой модули в серия.")
        elif n < lo_n:
            w.append(f"{n} модула в серия са под минимума за инвертора/BMS — нужни са поне {lo_n} модула (до {hi_n}).")
        elif n > hi_n:
            clusters = hv_clusters(inv, bs, n, 1)
            if not clusters:
                w.append(f"{n} модула надвишават допустимите {hi_n} в серия за този инвертор (прозорец {vmin:g}–{vmax:g} V).")
        if bs.get("recommended_inverter_kw_min") and _f(inv, "ac_power_kw") < _f(bs, "recommended_inverter_kw_min"):
            w.append(f"{battery.name} е предназначена основно за инвертори от {_f(bs, 'recommended_inverter_kw_min'):g} kW нагоре — проверете с доставчика.")
    elif vmin and vmax and vnom:
        v_sys = vnom * qty if bvc == "HV" and bs.get("stackable") else vnom
        if not (vmin <= v_sys <= vmax):
            w.append(f"Напрежението на батерията ({v_sys:g} V) е извън прозореца на инвертора {vmin:g}–{vmax:g} V.")
    inv_i = _f(inv, "battery_max_charge_a")
    bat_i = _f(bs, "max_charge_a")
    if inv_i and bat_i and bvc == "LV" and bat_i * qty < inv_i * 0.5:
        w.append(f"Токът на зареждане на батериите ({bat_i * qty:g} A общо) е доста под възможностите на инвертора ({inv_i:g} A) — помислете за повече модули или ограничете тока в настройките.")
    inv_kw = _f(inv, "battery_max_charge_kw")
    bat_kwh = _f(bs, "kwh") * qty
    if inv_kw and bat_kwh and inv_kw > bat_kwh * 1.0:
        w.append(f"Макс. мощност на зареждане на инвертора ({inv_kw:g} kW) надвишава 1C за {bat_kwh:g} kWh — задайте лимит на тока в инвертора.")
    im = (inverter.manufacturer or "").lower().split()[0] if inverter.manufacturer else ""
    bm = (battery.manufacturer or "").lower().split()[0] if battery.manufacturer else ""
    allowed = CLOSED_BATTERY_ECOSYSTEMS.get(im)
    if allowed is not None and bm and bm not in allowed and allowed:
        w.append(f"{inverter.manufacturer} инверторите работят само със собствени батерии — {battery.manufacturer} не е съвместима.")
    compat = inv.get("compatible_batteries")
    if isinstance(compat, list) and compat and bm and not any(bm in str(c).lower() for c in compat):
        w.append(f"Батерията не е в списъка със съвместими за инвертора: {', '.join(map(str, compat))}.")
    return w


def hv_series_range(inv: dict[str, Any], bs: dict[str, Any]) -> tuple[int, int]:
    """Modules allowed in ONE series string (cluster) of an HV stack on this inverter.

    n × module_v_max must not exceed the inverter's battery_v_max, n × module_v_min must not fall below its
    battery_v_min, and the BMS limits series_min / series_max apply (Deye BOS-G Pro 5–16, BOS-A 7–21)."""
    vmin, vmax = _f(inv, "battery_v_min"), _f(inv, "battery_v_max")
    mvmin, mvmax = _f(bs, "module_v_min"), _f(bs, "module_v_max")
    lo = int(_f(bs, "series_min", 1)) or 1
    hi = int(_f(bs, "series_max", 99)) or 99
    if vmin and mvmin:
        lo = max(lo, math.ceil(vmin / mvmin - 1e-9))
    if vmax and mvmax:
        hi = min(hi, math.floor(vmax / mvmax + 1e-9))
    return lo, hi


def hv_clusters(inv: dict[str, Any], bs: dict[str, Any], qty: int, n_inverters: int = 1) -> list[int] | None:
    """Split ``qty`` HV modules into equal-ish series clusters, one per battery input (inverter battery_inputs × units).
    Returns the module count per cluster or None if impossible."""
    lo, hi = hv_series_range(inv, bs)
    if qty <= 0 or hi < lo:
        return None
    max_clusters = max(1, int(_f(inv, "battery_inputs", 1))) * max(1, int(n_inverters))
    k = max(1, math.ceil(qty / hi))
    while k <= max_clusters:
        base, rem = divmod(qty, k)
        if base >= lo and base + (1 if rem else 0) <= hi:
            if rem == 0:
                return [base] * k
            # Deye requires the same module count on every cluster of a parallel HV system
        k += 1
    return None


def split_planes(planes: list[dict[str, Any]], n_inverters: int) -> list[list[dict[str, Any]]]:
    """Distribute roof planes over ``n_inverters`` inverters.

    Whole planes are assigned to the least-loaded inverter when there are at least as many planes as inverters
    (one orientation per inverter where possible); otherwise every plane is split evenly, so each inverter gets
    the same module count ±1."""
    n_inverters = max(1, int(n_inverters))
    active = [p for p in planes if int(p.get("modules") or 0) > 0]
    if n_inverters == 1:
        return [active]
    groups: list[list[dict[str, Any]]] = [[] for _ in range(n_inverters)]
    loads = [0] * n_inverters
    if len(active) >= n_inverters:
        for p in sorted(active, key=lambda x: -int(x["modules"])):
            k = loads.index(min(loads))
            groups[k].append(dict(p))
            loads[k] += int(p["modules"])
        # a very unbalanced split (one inverter > 1.6× the average) is worse than splitting planes – fall through
        avg = sum(loads) / n_inverters
        if max(loads) <= avg * 1.6 and min(loads) > 0:
            return groups
        groups = [[] for _ in range(n_inverters)]
    for p in active:
        n = int(p["modules"])
        base, rem = divmod(n, n_inverters)
        for k in range(n_inverters):
            cnt = base + (1 if k < rem else 0)
            if cnt > 0:
                groups[k].append({**p, "modules": cnt, "name": f"{p.get('name') or 'Плоскост'}" + (f" ({k + 1}/{n_inverters})" if n_inverters > 1 else "")})
    return groups


def string_design(panel: CatalogItem | None, inverter: CatalogItem | None, planes: list[dict[str, Any]], design: dict[str, Any], n_inverters: int = 1) -> dict[str, Any]:
    """planes: [{name, modules, span_m, azimuth, tilt}] -> string table + checks.

    With ``n_inverters`` > 1 the array is split over identical inverters (see ``split_planes``); every inverter is
    designed on its own and the tables are merged (``strings[i]["inverter"]`` = 1..N, ``per_inverter`` summaries)."""
    n_inverters = max(1, int(n_inverters or 1))
    if n_inverters == 1:
        out = _string_design_single(panel, inverter, planes, design)
        for st in out.get("strings") or []:
            st["inverter"] = 1
        out["inverters"] = 1
        return out
    groups = split_planes(planes, n_inverters)
    merged: dict[str, Any] = {"strings": [], "warnings": [], "checks": [], "per_inverter": [], "inverters": n_inverters}
    fuses_required = False
    parts_w: list[list[str]] = []
    parts_c: list[list[dict[str, Any]]] = []
    for k, grp in enumerate(groups, 1):
        part = _string_design_single(panel, inverter, grp, design)
        if k == 1:
            for key in ("voc_stc", "vmp_stc", "isc", "imp", "voc_cold", "vmp_cold", "vmp_hot", "tmin_c", "tcell_max_c", "ns_max", "ns_min", "mppts", "strings_per_mppt",
                        "inv_max_dc_v", "inv_mppt_min", "inv_mppt_max", "inv_i_op", "inv_i_sc", "fuse_a", "fuse_rule", "max_series_fuse_a"):
                if key in part:
                    merged[key] = part[key]
            merged["inputs_per_inverter"] = part.get("inputs", 0)
        offset = len(merged["strings"])
        for st in part.get("strings") or []:
            st["inverter"] = k
            st["id"] = f"S{offset + int(st['id'][1:])}" if str(st.get("id", "")).startswith("S") else st.get("id")
            st["id_local"] = f"И{k}-{st['id']}"
            merged["strings"].append(st)
        parts_w.append(list(part.get("warnings") or []))
        parts_c.append(list(part.get("checks") or []))
        fuses_required = fuses_required or bool(part.get("fuses_required"))
        merged["per_inverter"].append({"inverter": k, "modules": sum(int(p.get("modules") or 0) for p in grp), "strings": part.get("count", 0),
                                       "modules_per_string": part.get("modules_per_string", 0), "planes": [p.get("name") for p in grp],
                                       "kwp": round(sum(float(st.get("kwp") or 0) for st in part.get("strings") or []), 3)})
    # warnings/checks identical for every inverter are reported once, the rest with the inverter number
    common_w = set(parts_w[0]).intersection(*parts_w[1:]) if parts_w else set()
    merged["warnings"].extend(w for w in parts_w[0] if w in common_w) if parts_w else None
    for k, ws in enumerate(parts_w, 1):
        merged["warnings"].extend(f"Инвертор {k}: {w}" for w in ws if w not in common_w)
    common_c = {(c["text"], bool(c.get("ok"))) for c in parts_c[0]} if parts_c else set()
    for cs in parts_c[1:]:
        common_c &= {(c["text"], bool(c.get("ok"))) for c in cs}
    merged["checks"].extend(c for c in parts_c[0] if (c["text"], bool(c.get("ok"))) in common_c) if parts_c else None
    for k, cs in enumerate(parts_c, 1):
        merged["checks"].extend({**c, "text": f"Инвертор {k}: {c['text']}"} for c in cs if (c["text"], bool(c.get("ok"))) not in common_c)
    merged["count"] = len(merged["strings"])
    merged["modules_per_string"] = max((s["modules"] for s in merged["strings"]), default=0)
    merged["inputs"] = merged.get("inputs_per_inverter", 0) * n_inverters
    merged["fuses_required"] = fuses_required
    return merged


VOC_MARGIN = 0.97  # Voc(cold) design headroom against the inverter's max DC voltage


def mppt_capacities(inv: dict[str, Any], isc: float | None = None) -> list[int]:
    """Strings per MPPT tracker. ``mppt_strings`` (datasheet, e.g. [2, 1] for Deye SUN-15K-SG01HP3-EU-AM2) wins over
    the symmetric ``mppt_count`` × ``strings_per_mppt``. With the module ``isc`` an MPPT only takes as many parallel
    strings as its max. short-circuit current allows (k × Isc ≤ Isc,max of the tracker); it may become 0."""
    mppts = max(1, int(_f(inv, "mppt_count", 2)))
    spm = max(1, int(_f(inv, "strings_per_mppt", 1)))
    caps = [spm] * mppts
    lst = inv.get("mppt_strings")
    if isinstance(lst, list) and lst:
        try:
            c = [max(1, int(x)) for x in lst]
            if len(c) == mppts or not inv.get("mppt_count"):
                caps = c
        except (TypeError, ValueError):
            pass
    if isc and isc > 0:
        i_sc = [float(x) for x in (inv.get("mppt_isc_a") or []) if x]
        if not i_sc and inv.get("max_isc_a"):
            i_sc = [_f(inv, "max_isc_a")] * len(caps)
        if len(i_sc) >= len(caps):
            caps = [min(c, int(math.floor(i_sc[m] / isc + 1e-9))) for m, c in enumerate(caps)]
    return caps


def _assign_mppts(strings: list[dict[str, Any]], mppts: int, spm: int, caps: list[int] | None = None,
                  imp: float = 0.0, i_ops: list[float] | None = None) -> None:
    """Assign strings to MPPT trackers/inputs in place.

    Rules (in order): strings of the same plane share an MPPT (same orientation in parallel) as long as the tracker's
    operating current allows it (``imp`` × strings ≤ ``i_ops[m-1]``), different planes get separate MPPTs while any are
    free, a plane with more strings than the tracker takes spills over to the next free MPPT, and only when every MPPT
    is used do planes get mixed or trackers get overloaded (the caller warns about that). MPPT ``m`` takes at most
    ``caps[m-1]`` strings (default ``spm`` each); anything beyond the hardware inputs is still numbered so the warning
    can be shown.
    """
    caps = list(caps) if caps else [spm] * mppts
    mppts = len(caps)
    cap = {m: caps[m - 1] for m in range(1, mppts + 1)}
    # current-limited capacity: how many parallel strings a tracker carries without clipping
    soft = dict(cap)
    if imp and i_ops:
        for m in cap:
            lim = i_ops[m - 1] if len(i_ops) >= m else 0
            if lim:
                soft[m] = max(1, min(cap[m], int((lim + 1e-6) // imp)))
    free = dict(cap)
    by_plane: dict[int, list[dict[str, Any]]] = {}
    for st in strings:
        by_plane.setdefault(int(st.get("plane_index") or 0), []).append(st)

    def _place(pending: list[dict[str, Any]], limit: dict[int, int]) -> list[dict[str, Any]]:
        while pending:
            used = {k: cap[k] - free[k] for k in cap}
            room = {k: max(0, limit[k] - used[k]) for k in cap}
            # a fully free tracker that takes the whole plane, then any fully free one (biggest first), then the most room
            whole = [k for k in cap if used[k] == 0 and room[k] >= len(pending)]
            m = min(whole, key=lambda k: (cap[k], k)) if whole else None
            if m is None:
                fully = [k for k in cap if used[k] == 0 and room[k] > 0]
                m = max(fully, key=lambda k: (room[k], -k)) if fully else None
            if m is None:
                cand = [k for k in cap if room[k] > 0]
                m = max(cand, key=lambda k: room[k]) if cand else None
            if m is None:
                break
            take, pending = pending[: room[m]], pending[room[m]:]
            for st in take:
                st["mppt"] = m
                st["input"] = cap[m] - free[m] + 1
                free[m] -= 1
        return pending

    def _run(limit: dict[int, int]) -> None:
        free.clear()
        free.update(cap)
        # largest planes first so they get whole trackers
        for _pi, sts in sorted(by_plane.items(), key=lambda kv: -len(kv[1])):
            pending = _place(list(sts), limit)
            pending = _place(pending, cap)  # no current headroom left anywhere: use the remaining physical inputs
            # hardware exhausted: number the rest round-robin so the UI can show them
            for j, st in enumerate(pending):
                st["mppt"] = (j % mppts) + 1
                st["input"] = cap[st["mppt"]] + 1 + j // mppts

    def _mixed() -> bool:
        seen: dict[int, set[int]] = {}
        for st in strings:
            seen.setdefault(st["mppt"], set()).add(int(st.get("plane_index") or 0))
        return any(len(v) > 1 for v in seen.values())

    if soft != cap:
        _run(soft)
        if not _mixed():
            return
        # spreading for current would put different orientations on one tracker: mild clipping is the lesser evil
        _run(cap)
        if _mixed():
            _run(soft)
        return
    _run(cap)


def _string_design_single(panel: CatalogItem | None, inverter: CatalogItem | None, planes: list[dict[str, Any]], design: dict[str, Any]) -> dict[str, Any]:
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
    caps = mppt_capacities(inv, isc)
    if sum(caps) <= 0:
        out["warnings"].append(f"Isc на модула ({isc:g} A) надвишава макс. ток на късо съединение на всички MPPT входове — панелът не може да се свърже към този инвертор.")
        return out
    mppts = len(caps)
    spm = max(caps)
    i_op = _f(inv, "max_input_current_a", 0)  # per MPPT operating current
    i_sc_max = _f(inv, "max_isc_a", i_op * 1.5 if i_op else 0)
    # asymmetric MPPTs (e.g. Sungrow SH10RT 13.5 A / 27 A, Deye 2×26 A + 1×13 A): per-input lists from the datasheet
    i_op_list = [float(x) for x in (inv.get("mppt_input_current_a") or []) if x]
    i_sc_list = [float(x) for x in (inv.get("mppt_isc_a") or []) if x]
    if not ps.get("specs_verified") and ps.get("spec_source"):
        out["warnings"].append(f"Характеристиките на панела са извлечени автоматично ({ps.get('spec_source')}) и не са проверени — сверете с datasheet-а.")
    if not inv.get("specs_verified") and inv.get("spec_source"):
        out["warnings"].append(f"Характеристиките на инвертора са извлечени автоматично ({inv.get('spec_source')}) и не са проверени — сверете с datasheet-а.")

    voc_cold = voc * (1 + b_voc * (25 - tmin))
    vmp_cold = vmp * (1 + b_pmax * (25 - tmin))
    vmp_hot = vmp * (1 - b_pmax * (tmax - 25))
    # design headroom: keep Voc(cold) <= VOC_MARGIN x Vdc,max (datasheet tolerance, colder-than-record mornings)
    voc_margin = float(design.get("voc_margin") or VOC_MARGIN)
    ns_max = int(min(math.floor(max_dc_v * voc_margin / voc_cold) if voc_cold else 99, math.floor(mppt_max / vmp_cold) if vmp_cold else 99))
    ns_max_abs = int(math.floor(max_dc_v / voc_cold)) if voc_cold else 99
    if ns_max < 1 <= ns_max_abs:
        ns_max = ns_max_abs
    ns_min = int(math.ceil(max(mppt_min, start_v) / vmp_hot)) if vmp_hot else 1
    out.update(
        {
            "voc_stc": voc, "vmp_stc": vmp, "isc": isc, "imp": imp,
            "voc_cold": round(voc_cold, 1), "vmp_cold": round(vmp_cold, 1), "vmp_hot": round(vmp_hot, 1),
            "tmin_c": tmin, "tcell_max_c": tmax, "ns_max": ns_max, "ns_min": ns_min,
            "mppts": mppts, "strings_per_mppt": spm, "mppt_strings": caps, "inputs": sum(caps),
            "inv_max_dc_v": max_dc_v, "inv_mppt_min": mppt_min, "inv_mppt_max": mppt_max, "inv_i_op": i_op, "inv_i_sc": i_sc_max,
        }
    )
    if ns_max < 1 or ns_max < ns_min:
        out["warnings"].append("Няма допустима дължина на стринг за тази комбинация панел/инвертор (проверете Voc/MPPT).")
        return out

    # ---- allocate strings per plane
    strings: list[dict[str, Any]] = []
    active_planes = [p for p in planes if int(p.get("modules") or 0) > 0]
    inputs = sum(caps)
    for pi, pl in enumerate(planes):
        n = int(pl.get("modules") or 0)
        if n <= 0:
            continue
        s_need = math.ceil(n / ns_max)
        s = s_need
        # single plane: use every MPPT when the strings stay >= ns_min (better MPP tracking, lower current per input)
        if len(active_planes) == 1 and s < mppts and n // mppts >= ns_min:
            s = mppts
        # prefer a string count that divides the plane evenly (equal lengths in parallel) when an input is spare
        # (only when the extra string still fits on the plane's own MPPT – mixing planes on one tracker is worse)
        room = inputs if len(active_planes) == 1 else spm
        if n % s and s + 1 <= room and n % (s + 1) == 0 and n // (s + 1) >= ns_min:
            s += 1
        base, rem = divmod(n, s)
        for k in range(s):
            cnt = base + (1 if k < rem else 0)
            strings.append({"plane": pl.get("name") or f"Плоскост {pi + 1}", "plane_index": pi, "modules": cnt, "span_m": round(cnt * _f(pl, "module_w_m", 1.134) + (cnt - 1) * 0.02, 2), "azimuth": pl.get("azimuth"), "tilt": pl.get("tilt")})
    # ---- assign to MPPT inputs: keep each plane on its own MPPT(s); parallel strings of one plane share an MPPT
    if len(strings) > inputs:
        lay_txt = f"{mppts} MPPT × {spm}" if len(set(caps)) == 1 else " + ".join(str(c) for c in caps) + f" на {mppts} MPPT"
        out["warnings"].append(f"{len(strings)} стринга надвишават входовете на инвертора ({lay_txt}). Намалете стринговете или изберете по-голям инвертор.")
    _assign_mppts(strings, mppts, spm, caps, imp=imp, i_ops=i_op_list or ([i_op] * mppts if i_op else None))
    for i, st in enumerate(strings):
        st["id"] = f"S{i + 1}"
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
        i_op_m = i_op_list[m - 1] if len(i_op_list) >= m else i_op
        i_sc_m = i_sc_list[m - 1] if len(i_sc_list) >= m else (i_sc_max if not i_op_list or len(i_op_list) < m else i_op_m * 1.5)
        if i_op_m and len(sts) * imp > i_op_m + 1e-6:
            out["warnings"].append(f"MPPT {m}: работен ток {len(sts) * imp:.1f} A надвишава {i_op_m:g} A на входа (ограничение на мощността).")
        if i_sc_m and len(sts) * isc > i_sc_m + 1e-6:
            out["warnings"].append(f"MPPT {m}: Isc {len(sts) * isc:.1f} A надвишава максимално допустимия {i_sc_m:g} A.")
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
    inverter_qty: int = 1,
) -> dict[str, Any]:
    params = project.params or {}
    n_inv = max(1, int(inverter_qty or 1)) if inverter else 1
    design = {
        "design_tmin_c": _f(params, "design_tmin_c", _f(pricing, "design_tmin_c", -20)),
        "design_tcell_max_c": _f(pricing, "design_tcell_max_c", 70),
        "voc_margin": _f(pricing, "voc_margin", VOC_MARGIN),
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
    sd = string_design(panel, inverter, planes, design, n_inverters=n_inv)
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
        combiner_run = 3.0  # inverters are mounted next to the AC combiner board when several run in parallel
        ac_len_raw = (ac_run + 3) if n_inv == 1 else (combiner_run + 2)  # per-inverter feeder incl. terminations
        ac.update(
            {
                "inverters": n_inv, "i_max_a": round(i_max, 1), "breaker_a": brk, "breaker_poles": poles, "rcd_a": rcd, "rcd_ma": int(_f(inv, "rcd_ma", 300)), "rcd_type": "A",
                "cable_mm2": mm2, "cores": cores, "cable_m_raw": ac_len_raw * n_inv, "cable_m": _round_up(ac_len_raw * n_inv * (1 + cable_margin), 1), "vdrop_pct": round(vd, 2), "vdrop_limit_pct": ac_vdrop_max,
                "spd_integrated": bool(inv.get("integrated_spd", True)), "p_total_kw": round(p_kw * n_inv, 2),
            }
        )
        per_inv = f" ×{n_inv} инвертора" if n_inv > 1 else ""
        role("ac_mcb", f"Автоматичен прекъсвач {poles} {brk} A, крива C, 6 kA (изход инвертор{per_inv})" if n_inv > 1 else f"Автоматичен прекъсвач {poles} {brk} A, крива C, 6 kA (вход мрежа)", n_inv, rating_a=brk, poles=poles)
        role("ac_rcd", f"Дефектнотокова защита {poles} {rcd} A / 300 mA тип A" + (" (на инвертор)" if n_inv > 1 else ""), n_inv, rating_a=rcd, poles=poles)
        role("ac_cable", f"Кабел СВТ {cores}×{mm2:g} mm² (инвертор → {'табло AC комбиниране' if n_inv > 1 else 'ГРТ'})", ac["cable_m"], unit="м", cross_section_mm2=mm2, cores=cores)
        role("ac_lug", f"Кабелен накрайник / накрайник за жило {mm2:g} mm²", 2 * cores * n_inv, cross_section_mm2=mm2)
        if n_inv > 1:
            # AC combiner: one main breaker for the sum of the inverters + feeder to the main board sized for the total current
            i_tot = i_max * n_inv
            brk_main = int(_std(1.25 * i_tot, MCB_STD)) if 1.25 * i_tot <= MCB_STD[-1] else int(math.ceil(1.25 * i_tot / 50) * 50)
            mm2_main = next((c for c in CABLE_STD if CABLE_IZ[c] >= brk_main), CABLE_STD[-1])

            def vdrop_main(a: float) -> float:
                if phase == 3:
                    return (math.sqrt(3) * ac_run * i_tot * pf) / (SIGMA_CU * a * u) * 100
                return (2 * ac_run * i_tot * pf) / (SIGMA_CU * a * u) * 100

            vdm = vdrop_main(mm2_main)
            while vdm > ac_vdrop_max and mm2_main < CABLE_STD[-1]:
                mm2_main = _std(mm2_main + 0.1, CABLE_STD)
                vdm = vdrop_main(mm2_main)
            main_len = _round_up((ac_run + 3) * (1 + cable_margin), 1)
            ac.update({"combiner": True, "i_total_a": round(i_tot, 1), "main_breaker_a": brk_main, "main_cable_mm2": mm2_main, "main_cable_m": main_len, "main_vdrop_pct": round(vdm, 2)})
            role("ac_combiner", f"Табло AC за паралелни инвертори ({n_inv} входа, главен прекъсвач {brk_main} A) IP65", 1, inverters=n_inv, rating_a=brk_main)
            role("ac_mcb", f"Главен прекъсвач {poles} {brk_main} A (табло AC → ГРТ)", 1, rating_a=brk_main, poles=poles)
            role("ac_cable", f"Кабел СВТ {cores}×{mm2_main:g} mm² (табло AC комбиниране → ГРТ)", main_len, unit="м", cross_section_mm2=mm2_main, cores=cores)
            role("ac_lug", f"Кабелна обувка {mm2_main:g} mm² (табло AC → ГРТ)", 2 * cores, cross_section_mm2=mm2_main)
            role("parallel_cable", "Кабел за паралелна комуникация между инвертори (CAN/RS485, RJ45 екраниран)", n_inv - 1)
            if brk_main > 160:
                warnings.append(f"Общ AC ток {i_tot:.0f} A — главното табло/присъединяването трябва да бъдат проверени от проектант (NN ≥ {brk_main} A).")
        role("ac_spd", f"Катоден отводител AC тип 2, {'3P+N' if phase == 3 else '1P+N'} 275 V", 1, phases=phase)
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
        inputs = int(_f(inv, "battery_inputs", 1)) * n_inv
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
        if n_inv > 1:
            bat["per_inverter"] = round(battery_qty / n_inv, 2)
            if battery_qty % n_inv:
                warnings.append(f"{battery_qty} батерии не се делят поравно на {n_inv} инвертора — при отделни батерийни банки изравнете броя (напр. {math.ceil(battery_qty / n_inv) * n_inv}).")
        if battery_qty > int(_f(bs, "max_parallel", 16)) * n_inv:
            warnings.append(f"Батерии в паралел ({battery_qty}) надвишават допустимото за модела ({int(_f(bs, 'max_parallel'))} на инвертор).")
        warnings.extend(battery_compatibility(inverter, battery, battery_qty))
    # -------------------------------------------------------------- earthing
    grd: dict[str, Any] = {}
    if panel_qty:
        pe_mm2 = _f(inv, "pe_cable_mm2", 16) if inverter else 16
        bonding_m = row_length_m + dc_run + 5
        pe_len = (ac_run + 2) if n_inv == 1 else (3 + 2) * n_inv + (ac_run + 2)
        grd.update({"pe_mm2": pe_mm2, "pe_m": _round_up(pe_len * (1 + cable_margin), 1), "bonding_mm2": 6, "bonding_m_raw": round(bonding_m, 1), "bonding_m": _round_up(bonding_m * (1 + cable_margin), 5), "bonding_clamps": rail_lines})
        role("pe_cable", f"Заземителен проводник ПВ-А1 {pe_mm2:g} mm² жълто-зелен (инвертор → заземителна шина)", grd["pe_m"], unit="м", cross_section_mm2=pe_mm2)
        role("bonding_cable", "Заземителен проводник 6 mm² жълто-зелен (изравняване на потенциалите на конструкцията)", grd["bonding_m"], unit="м", cross_section_mm2=6)
        role("bonding_clamp", "Клема за заземяване на шина (WCL8-10 / еквивалент)", int(math.ceil(rail_lines * (1 + fast_margin))), section="construction")
        role("earth_bar", "Заземителна шина / клеморед PE в таблото", 1)
        from .site_kind import kind_from_code

        if sel.get("earth_rod", kind_from_code(getattr(project, "roof_type", "")) in ("ground", "fence")):
            role("earth_rod", "Заземителен кол 1,5 m поцинкован + клема за кол", 1 if panel_qty <= 40 else 2)
            role("earth_strip", "Поцинкована шина 30×4 mm за заземител", 10 if panel_qty <= 40 else 20, unit="м")
            grd["earth_rod"] = True
    # ---------------------------------------------------- cable management
    mgmt: dict[str, Any] = {}
    if panel_qty and n_str:
        ties = int(math.ceil((4 * panel_qty + 2 * rail_lines + 10 * n_str) * (1 + fast_margin)))
        conduit_dc = _round_up(dc_run * math.ceil(2 * n_str / 4) * (1 + cable_margin), 1)  # ≤4 PV cables per ф32 conduit
        conduit_ac = _round_up((ac_run + (batt_run if bat else 0) + (3 * n_inv if n_inv > 1 else 0)) * (1 + cable_margin), 1)
        clips = int(math.ceil((conduit_dc + conduit_ac) * 2 * (1 + fast_margin)))
        mgmt.update({"ties": ties, "conduit_dc_m": conduit_dc, "conduit_ac_m": conduit_ac, "conduit_clips": clips})
        role("cable_tie_uv", "Кабелна връзка UV-устойчива 4,8×200 mm (черна)", ties)
        role("conduit_32", "Гофрирана тръба UV ф32 (DC кабели)", conduit_dc, unit="м")
        role("conduit_40", "Гофрирана тръба UV ф40 (AC/батерийни кабели)", conduit_ac, unit="м")
        role("conduit_clip", "Скоба за гофрирана тръба ф32/ф40", clips)
        role("end_sleeve", f"Кабелен накрайник за жило 6 mm² (DC)", 4 * n_str)
    # --------------------------------------------------------------------
    return {
        "inverters": n_inv,
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
def find_item_for_role(items: list[CatalogItem], r: dict[str, Any], chooser: Callable[[list[CatalogItem]], CatalogItem] | None = None) -> CatalogItem | None:
    """Pick the catalog item with specs.role == role; for rated parts the smallest
    rating >= required; for cables the smallest cross-section >= required.

    ``chooser`` (optional) decides between technically equivalent items (same rating / cross-section), e.g. the
    cheapest, the fastest to deliver or the premium brand – see ``procurement.chooser``."""
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
    # generic items (no declared rating / cross-section) are treated as an exact match, but a declared exact match wins
    def _key(it: CatalogItem):
        ra, mm = _f(it.specs, "rating_a"), _f(it.specs, "cross_section_mm2")
        undeclared = bool((need_a and not ra) or (need_mm2 and not mm))
        return (ra or (need_a or 0), mm or (need_mm2 or 0), undeclared, it.purchase_price or 0)

    good.sort(key=_key)
    if chooser is not None:
        top = good[0]
        same = [it for it in good if _key(it)[:3] == _key(top)[:3]]
        if len(same) > 1:
            return chooser(same)
    return good[0]
