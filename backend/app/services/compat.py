"""System compatibility: panel ↔ inverter ↔ battery ↔ installation.

Every combination the UI offers is checked against the datasheet values stored in the catalog specs. A result is
``ok`` (connect as-is), ``warn`` (works, but with a limitation – e.g. current clipping) or ``blocked`` (physically or
electrically impossible / not allowed – never auto-selected, never quoted without a red warning).

Rules (IEC 62548 / manufacturer datasheets):
* string length: Voc(Tmin) × Ns ≤ 0,97 × Vdc,max and Vmp(Tcold) × Ns ≤ MPPT max; Vmp(Tcell,max) × Ns ≥ max(MPPT min, start)
  → there must be an Ns with ns_min ≤ Ns ≤ ns_max;
* the module's Isc must not exceed the max short-circuit current of the largest MPPT input (one string per input);
* modules per inverter must fit: ns_min ≤ modules ≤ (inputs × ns_max) and kWp per inverter ≤ max PV input power;
* inverter phases = installation phases (1-phase inverter on a 3-phase site is allowed only as a warning);
* battery: hybrid inverter, same voltage class (LV 48 V / HV), same ecosystem (Deye ↔ Deye), HV series count inside the
  inverter's battery window and the BMS limits (BOS-G Pro 5–16, BOS-A 7–21), equal modules per cluster.
"""
from __future__ import annotations

import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, Project
from . import engineering
from .settings import get_setting

OK, WARN, BLOCKED = "ok", "warn", "blocked"
_RANK = {OK: 0, WARN: 1, BLOCKED: 2}


def _worst(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def _f(d: dict[str, Any] | None, k: str, default: float = 0.0) -> float:
    try:
        v = (d or {}).get(k)
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _design_cfg(db: Session) -> dict[str, Any]:
    pr = get_setting(db, "pricing")
    return {"design_tmin_c": pr.get("design_tmin_c", -20), "design_tcell_max_c": pr.get("design_tcell_max_c", 70), "voc_margin": pr.get("voc_margin", 0.97)}


def string_window(panel: CatalogItem, inverter: CatalogItem, cfg: dict[str, Any]) -> dict[str, Any]:
    ps, inv = panel.specs or {}, inverter.specs or {}
    voc, vmp = _f(ps, "voc"), _f(ps, "vmp")
    b_voc = abs(_f(ps, "temp_coeff_voc", -0.25)) / 100.0
    b_p = abs(_f(ps, "temp_coeff_pmax", -0.30)) / 100.0
    tmin, tmax = float(cfg.get("design_tmin_c", -20)), float(cfg.get("design_tcell_max_c", 70))
    vdc = _f(inv, "max_dc_voltage", 1000)
    mppt_max = _f(inv, "mppt_v_max", vdc * 0.85)
    mppt_min = max(_f(inv, "mppt_v_min", 150), _f(inv, "start_voltage", 0))
    voc_cold = voc * (1 + b_voc * (25 - tmin))
    vmp_cold = vmp * (1 + b_p * (25 - tmin))
    vmp_hot = vmp * (1 - b_p * (tmax - 25))
    margin = float(cfg.get("voc_margin") or 0.97)
    ns_max = int(min(math.floor(vdc * margin / voc_cold) if voc_cold else 0, math.floor(mppt_max / vmp_cold) if vmp_cold else 0))
    ns_abs = int(math.floor(vdc / voc_cold)) if voc_cold else 0
    if ns_max < 1 <= ns_abs:
        ns_max = ns_abs
    ns_min = int(math.ceil(mppt_min / vmp_hot)) if vmp_hot else 1
    caps = engineering.mppt_capacities(inv, _f(ps, "isc") or None)
    return {"ns_min": max(1, ns_min), "ns_max": ns_max, "inputs": sum(caps), "mppt_strings": caps, "voc_cold": round(voc_cold, 2), "vmp_hot": round(vmp_hot, 2)}


def check_pair(panel: CatalogItem | None, inverter: CatalogItem | None, cfg: dict[str, Any], *, modules_per_inverter: int = 0, phase: int | None = None) -> dict[str, Any]:
    """Panel ↔ inverter (and optionally the module count per inverter and the site phases)."""
    status, reasons = OK, []
    if not panel or not inverter:
        return {"status": OK, "reasons": [], "window": None}
    ps, inv = panel.specs or {}, inverter.specs or {}
    if not ps.get("voc") or not ps.get("vmp") or not inv.get("max_dc_voltage"):
        return {"status": WARN, "reasons": ["Липсват електрически данни (Voc/Vmp или Vdc max) — съвместимостта не може да се провери."], "window": None}
    win = string_window(panel, inverter, cfg)
    if win["ns_max"] < 1 or win["ns_max"] < win["ns_min"]:
        status = BLOCKED
        reasons.append(f"Няма допустима дължина на стринг: нужни са ≥ {win['ns_min']} модула за MPPT минимума, а Voc/MPPT max позволява ≤ {win['ns_max']}.")
    isc, imp = _f(ps, "isc"), _f(ps, "imp")
    nominal = engineering.mppt_capacities(inv)
    caps = win["mppt_strings"]
    if isc and sum(caps) <= 0:
        status = BLOCKED
        reasons.append(f"Isc на модула {isc:g} A надвишава макс. Isc на всеки MPPT вход.")
    elif isc and caps != nominal:
        status = _worst(status, WARN)
        reasons.append(f"Isc {isc:g} A: входовете се намаляват от {sum(nominal)} на {sum(caps)} (ток на късо съединение на MPPT).")
    i_op = [float(x) for x in (inv.get("mppt_input_current_a") or []) if x] or ([_f(inv, "max_input_current_a")] * len(nominal) if inv.get("max_input_current_a") else [])
    if imp and i_op and len(i_op) >= len(nominal):
        # strings a tracker carries without clipping (the string planner spreads strings over trackers first)
        soft = [min(caps[m], int((i_op[m] + 1e-6) // imp)) if caps[m] > 0 else 0 for m in range(len(nominal))]
        single = [m + 1 for m in range(len(nominal)) if caps[m] > 0 and imp > i_op[m] + 1e-6]
        win["strings_no_clip"] = sum(soft)
        if single:
            status = _worst(status, WARN)
            reasons.append(f"MPPT {', '.join(map(str, single))}: Imp {imp:g} A на модула > работния ток на входа — лек clipping при пълно слънце (допустимо).")
        elif modules_per_inverter > 0 and win["ns_max"] >= 1:
            need = math.ceil(modules_per_inverter / win["ns_max"])
            n_trk = len([c for c in caps if c > 0])
            if need < n_trk and modules_per_inverter // n_trk >= win["ns_min"]:
                need = n_trk  # same rule as the string planner: use every tracker when the strings stay long enough
            if need > sum(soft):
                status = _worst(status, WARN)
                reasons.append(f"{need} стринга × Imp {imp:g} A: някои MPPT носят паралелни стрингове над работния си ток — лек clipping при пълно слънце (допустимо).")
    if phase and int(_f(inv, "phases", phase)) != int(phase):
        if int(_f(inv, "phases", phase)) == 3 and int(phase) == 1:
            status = BLOCKED
            reasons.append("Трифазен инвертор на монофазна инсталация — невъзможно.")
        else:
            status = _worst(status, WARN)
            reasons.append("Монофазен инвертор на трифазна инсталация — допустимо, но с асиметрия (проверете изискванията на ЕРП).")
    if modules_per_inverter > 0 and status != BLOCKED:
        cap = win["inputs"] * win["ns_max"]
        if modules_per_inverter < win["ns_min"]:
            status = BLOCKED
            reasons.append(f"{modules_per_inverter} модула на инвертор са под минималния стринг ({win['ns_min']}).")
        elif modules_per_inverter > cap:
            status = BLOCKED
            reasons.append(f"{modules_per_inverter} модула на инвертор надвишават капацитета {win['inputs']} входа × {win['ns_max']} = {cap}.")
        kwp = modules_per_inverter * _f(ps, "wp") / 1000.0
        pv_max = _f(inv, "max_pv_kw")
        if pv_max and kwp > pv_max + 1e-6:
            status = BLOCKED
            reasons.append(f"{kwp:.2f} kWp на инвертор > макс. PV вход {pv_max:g} kWp.")
    return {"status": status, "reasons": reasons, "window": win}


def check_battery(inverter: CatalogItem | None, battery: CatalogItem | None, qty: int = 1, n_inverters: int = 1) -> dict[str, Any]:
    status, reasons = OK, []
    rng: dict[str, Any] | None = None
    if not inverter or not battery:
        return {"status": OK, "reasons": [], "range": None}
    inv, bs = inverter.specs or {}, battery.specs or {}
    if inv.get("hybrid") is False:
        return {"status": BLOCKED, "reasons": ["Инверторът не е хибриден."], "range": None}
    ivc, bvc = str(inv.get("battery_voltage_class") or "").upper(), str(bs.get("voltage_class") or "").upper()
    if ivc and bvc and ivc != bvc:
        return {"status": BLOCKED, "reasons": [f"Инверторът е за {ivc} батерии, а батерията е {bvc}."], "range": None}
    compat = inv.get("compatible_batteries")
    bm = (battery.manufacturer or "").lower().split()[0] if battery.manufacturer else ""
    if isinstance(compat, list) and compat and bm and not any(bm in str(c).lower() for c in compat):
        return {"status": BLOCKED, "reasons": [f"Батерията не е съвместима (позволени: {', '.join(map(str, compat))})."], "range": None}
    if bvc == "HV" and bs.get("module_v_max"):
        lo, hi = engineering.hv_series_range(inv, bs)
        max_clusters = max(1, int(_f(inv, "battery_inputs", 1))) * max(1, int(n_inverters))
        rng = {"min": lo, "max_per_cluster": hi, "max": hi * max_clusters, "clusters_max": max_clusters}
        if hi < lo:
            return {"status": BLOCKED, "reasons": ["Батерийният прозорец на инвертора не допуска модулите в серия."], "range": rng}
        if qty:
            cl = engineering.hv_clusters(inv, bs, int(qty), n_inverters)
            if cl is None:
                status = BLOCKED
                if qty < lo:
                    reasons.append(f"Минимум {lo} модула в серия (избрани {qty}).")
                else:
                    reasons.append(f"{qty} модула не могат да се разпределят по равно в до {max_clusters} клъстера по {lo}–{hi} модула.")
            else:
                rng["clusters"] = cl
        if _f(bs, "recommended_inverter_kw_min") and _f(inv, "ac_power_kw") < _f(bs, "recommended_inverter_kw_min"):
            status = _worst(status, WARN)
            reasons.append(f"Батерията е предназначена основно за инвертори ≥ {_f(bs, 'recommended_inverter_kw_min'):g} kW.")
    else:
        maxp = int(_f(bs, "max_parallel", 16)) or 16
        rng = {"min": 1, "max": maxp}
        if qty and qty > maxp:
            status = BLOCKED
            reasons.append(f"Максимум {maxp} модула в паралел (избрани {qty}).")
        inv_i, bat_i = _f(inv, "battery_max_charge_a"), _f(bs, "max_charge_a")
        if qty and inv_i and bat_i and bat_i * qty < inv_i * 0.5:
            status = _worst(status, WARN)
            reasons.append(f"Токът на зареждане {bat_i * qty:g} A е под 50 % от {inv_i:g} A на инвертора — ограничете тока в настройките.")
        if bat_i and inv_i:
            rng["recommended"] = max(1, math.ceil(inv_i * 0.5 / bat_i))
    return {"status": status, "reasons": reasons, "range": rng}


def _active(db: Session, cat: str) -> list[CatalogItem]:
    return db.query(CatalogItem).filter(CatalogItem.category == cat, CatalogItem.active.is_(True)).order_by(CatalogItem.sort_order, CatalogItem.id).all()


def _get(db: Session, iid: Any) -> CatalogItem | None:
    try:
        return db.get(CatalogItem, int(iid)) if iid else None
    except (TypeError, ValueError):
        return None


def matrix(db: Session, project: Project, *, panel_item_id: Any = None, inverter_item_id: Any = None, inverter_qty: int = 1,
           panel_qty: int = 0, battery_item_id: Any = None, battery_qty: int = 0) -> dict[str, Any]:
    """Status of every active inverter / panel / battery against the current selection (for the UI)."""
    cfg = _design_cfg(db)
    panel, inverter, battery = _get(db, panel_item_id), _get(db, inverter_item_id), _get(db, battery_item_id)
    n_inv = max(1, int(inverter_qty or 1))
    per_inv = int(math.ceil(panel_qty / n_inv)) if panel_qty else 0
    phase = int(project.phase or 3)
    out: dict[str, Any] = {"inverters": {}, "panels": {}, "batteries": {}}
    for inv in _active(db, "inverter"):
        qty = n_inv
        r = check_pair(panel, inv, cfg, modules_per_inverter=per_inv, phase=phase) if panel else check_pair(None, None, cfg)
        if panel and panel_qty and r["status"] == BLOCKED and (inverter is None or inv.id != inverter.id):
            # another model may work with a different number of units in parallel – report the smallest one
            max_units = max(1, int(_f(inv.specs, "max_parallel_units", 1)))
            for n in range(1, min(16, max_units) + 1):
                rr = check_pair(panel, inv, cfg, modules_per_inverter=int(math.ceil(panel_qty / n)), phase=phase)
                if rr["status"] != BLOCKED:
                    r, qty = rr, n
                    break
        if not panel and int(_f(inv.specs, "phases", phase)) == 3 and phase == 1:
            r = {"status": BLOCKED, "reasons": ["Трифазен инвертор на монофазна инсталация — невъзможно."], "window": None}
        if battery:
            b = check_battery(inv, battery, battery_qty or 0, n_inv)
            if b["status"] != OK:
                r = {**r, "status": _worst(r["status"], b["status"] if b["status"] == WARN else WARN),
                     "reasons": r["reasons"] + [f"Батерия: {x}" for x in b["reasons"]]}
        out["inverters"][inv.id] = {"status": r["status"], "reasons": r["reasons"], "window": r.get("window"), "qty": qty}
    for p in _active(db, "panel"):
        r = check_pair(p, inverter, cfg, modules_per_inverter=per_inv if inverter else 0, phase=None)
        out["panels"][p.id] = {"status": r["status"], "reasons": r["reasons"], "window": r.get("window")}
    for b in _active(db, "battery"):
        r = check_battery(inverter, b, battery_qty if battery and b.id == battery.id else 0, n_inv) if inverter else {"status": OK, "reasons": [], "range": None}
        out["batteries"][b.id] = r
    out["selected"] = system_issues(db, project, panel, panel_qty, inverter, n_inv, battery, battery_qty)
    return out


def system_issues(db: Session, project: Project, panel: CatalogItem | None, panel_qty: int, inverter: CatalogItem | None, inv_qty: int,
                  battery: CatalogItem | None, battery_qty: int) -> dict[str, Any]:
    """Blocking problems and warnings for the selected system (used by the quote)."""
    cfg = _design_cfg(db)
    blocked: list[str] = []
    warns: list[str] = []
    n_inv = max(1, int(inv_qty or 1))
    if inverter:
        mx = int(_f(inverter.specs, "max_parallel_units", 10)) or 10
        if n_inv > mx:
            blocked.append(f"{n_inv} × {inverter.name}: максимум {mx} инвертора в паралел.")
    if panel and inverter:
        r = check_pair(panel, inverter, cfg, modules_per_inverter=int(math.ceil(panel_qty / n_inv)) if panel_qty else 0, phase=int(project.phase or 3))
        (blocked if r["status"] == BLOCKED else warns).extend(r["reasons"])
    elif inverter:
        ph = int(_f(inverter.specs, "phases", project.phase or 3))
        if ph == 3 and int(project.phase or 3) == 1:
            blocked.append("Трифазен инвертор на монофазна инсталация — невъзможно.")
    if battery and inverter:
        b = check_battery(inverter, battery, int(battery_qty or 0), n_inv)
        (blocked if b["status"] == BLOCKED else warns).extend(b["reasons"])
    return {"blocked": blocked, "warnings": warns, "ok": not blocked}


def best_battery_qty(inverter: CatalogItem, battery: CatalogItem, wanted: int, n_inv: int = 1) -> int | None:
    """Closest allowed battery quantity to ``wanted`` (for auto-correction)."""
    if check_battery(inverter, battery, wanted, n_inv)["status"] != BLOCKED:
        return wanted
    for d in range(1, 40):
        for q in (wanted + d, wanted - d):
            if q >= 1 and check_battery(inverter, battery, q, n_inv)["status"] != BLOCKED:
                return q
    return None


def hv_accessories(db: Session, inverter: CatalogItem | None, battery: CatalogItem, qty: int, n_inv: int = 1) -> tuple[list[tuple[CatalogItem, int, str]], list[str]]:
    """HV stack: one BMS (control box / PDU) per series cluster and the cheapest racks that hold the modules."""
    bs = battery.specs or {}
    fam = bs.get("family")
    notes: list[str] = []
    if str(bs.get("voltage_class") or "").upper() != "HV" or not fam or qty <= 0:
        return [], notes
    clusters = engineering.hv_clusters(inverter.specs or {}, bs, qty, n_inv) if inverter else None
    if clusters is None:
        hi = int(_f(bs, "series_max", 16)) or 16
        k = max(1, math.ceil(qty / hi))
        base, rem = divmod(qty, k)
        clusters = [base + (1 if i < rem else 0) for i in range(k)]
    acc = [a for a in _active(db, "battery_accessory") if (a.specs or {}).get("family") == fam]
    bms = sorted([a for a in acc if (a.specs or {}).get("role") == "hv_bms"], key=lambda a: a.purchase_price or 0)
    racks = [a for a in acc if (a.specs or {}).get("role") == "hv_rack" and int(_f(a.specs, "capacity")) > 0]
    out: dict[int, list[Any]] = {}
    if bms:
        b = next((x for x in bms if int(_f(x.specs, "max_series", 99)) >= max(clusters)), bms[-1])
        out[b.id] = [b, len(clusters), "BMS / контролна кутия за всеки клъстер"]
    else:
        notes.append("Няма BMS / контролна кутия в каталога за тази батерия.")
    if racks:
        for n in clusters:
            combo = _rack_combo(racks, n)
            for r in combo:
                if r.id in out:
                    out[r.id][1] += 1
                else:
                    out[r.id] = [r, 1, "стелаж"]
    else:
        notes.append("Няма стелаж в каталога за тази батерия.")
    if len(clusters) > 1:
        notes.append(f"Батериите са разделени на {len(clusters)} клъстера × {clusters[0]} модула (равен брой — изискване на Deye).")
    return [(v[0], v[1], v[2]) for v in out.values()], notes


def _rack_combo(racks: list[CatalogItem], n: int) -> list[CatalogItem]:
    """Cheapest multiset of racks (≤ 3 pieces) with capacity ≥ n."""
    best: tuple[float, list[CatalogItem]] | None = None
    rs = sorted(racks, key=lambda r: _f(r.specs, "capacity"))
    for a in rs:
        for combo in ([a],) + tuple([a, b] for b in rs) + tuple([a, b, c] for b in rs for c in rs):
            if sum(_f(x.specs, "capacity") for x in combo) >= n:
                cost = sum(float(x.purchase_price or 0) for x in combo) + len(combo) * 1e-3
                if best is None or cost < best[0]:
                    best = (cost, list(combo))
    return best[1] if best else []
