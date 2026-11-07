"""Heuristic datasheet (PDF text) → gmsun spec extraction.

Used by the supplier importer (green-energy.bg) and by the catalog "upload
datasheet" action.  The parser works on the text produced by
``pdftotext -layout`` (poppler): each spec row becomes a line
``label  v1  v2  v3 ...`` where columns are separated by 2+ spaces.

Datasheets list several models (power classes) side by side.  The parser
returns one spec dict per column; the caller picks the column that matches the
product (by Wp or kW) or imports every column.

Everything produced here is marked ``specs_verified: False`` and the list of
successfully parsed fields is stored under ``parsed_fields`` so the UI can show
what still has to be checked by an engineer.  The engineering engine keeps its
own conservative fall-backs for every missing key.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any, Callable

NUM = r"[-+]?\d+(?:[.,]\d+)?"
_num_re = re.compile(NUM)


def pdf_to_text(path: str) -> str:
    """Extract layout-preserving text with poppler's pdftotext (empty string if unavailable)."""
    if not shutil.which("pdftotext"):
        return ""
    try:
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=120)
        return out.stdout.decode("utf-8", "ignore")
    except Exception:  # pragma: no cover - external tool
        return ""


# ----------------------------------------------------------------------------- helpers
def _nums(s: str) -> list[float]:
    vals = []
    s = s.replace("\u2212", "-").replace("~", "-").replace("–", "-").replace("−", "-")
    s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)  # 1,500 V -> 1500
    s = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " ", s)  # 160-650 is a range, not a negative number
    for t in _num_re.findall(s):
        try:
            vals.append(float(t.replace(",", ".")))
        except ValueError:
            pass
    return vals


def _cells(line: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\s{2,}|\t|\|", line.strip()) if p.strip()]
    return parts


def _is_label(cell: str) -> bool:
    """A cell that is mostly letters (a parameter name), not a value."""
    letters = len(re.findall(r"[A-Za-zА-Яа-я]", cell))
    digits = len(re.findall(r"\d", cell))
    return letters >= 3 and letters > digits * 2


def _split_label(line: str) -> tuple[str, list[str]]:
    """Return (label, value cells) for the *first* parameter in a line.

    Kept for backwards compatibility – the table scanner uses :func:`_pairs`.
    """
    pairs = _pairs(line)
    return pairs[0] if pairs else ("", [])


def _pairs(line: str) -> list[tuple[str, list[str]]]:
    """Split a layout line into (label, values) pairs.

    ``Bifaciality  70±5%  Temperature Coefficient of Isc  +0.050%/℃`` yields two
    pairs; leading garbage cells (``±``, ``4-9×14``) are skipped; ``Weight 21 kg``
    (single-space) is split at the first number.  A cell that mixes a label and
    its values ("Short-circuit Current (Isc) A 14.23 11.48 …", typical for OCR
    output) is split at the first number as well.
    """
    cells = _cells(line)
    if not cells:
        return []
    split_rx = re.compile(r"^(.*?[A-Za-zА-Яа-я)\]:%])\s*:?\s+(" + NUM + r".*)$")
    out: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(cells):
        c = cells[i]
        label: str | None = None
        vals: list[str] = []
        if _is_label(c):
            label = c
            m = re.match(r"^(.*?[\])):])\s*(" + NUM + r".*)$", c)  # "Pmax [W] 700"
            if m and _is_label(m.group(1)):
                label, vals = m.group(1), [m.group(2).strip()]
            else:
                m = split_rx.match(c)  # "Temperature coefficients of Pmax -0.30%/°C" (OCR, single spaces)
                if m and _is_label(m.group(1)) and _is_label_like(m.group(1)) and not re.search(r"\d", m.group(1)):
                    label, vals = m.group(1), [m.group(2).strip()]
        else:
            m = split_rx.match(c)
            if m and _is_label(m.group(1)) and _is_label_like(m.group(1)):
                label, vals = m.group(1), [m.group(2).strip()]
            elif ":" in c:
                a, b = c.split(":", 1)
                if _is_label(a) and _num_re.search(b):
                    label, vals = a, [b.strip()]
        if label is None:
            i += 1
            continue
        j = i + 1
        while j < len(cells) and not _is_label(cells[j]):
            vals.append(cells[j])
            j += 1
        if vals and any(_num_re.search(v) for v in vals):
            out.append((label.strip(" :"), vals))
        i = j
    return out


def _is_label_like(s: str) -> bool:
    """Labels start with a letter and contain at most one number (unit indices like 'Pmax [W]' are fine)."""
    return bool(re.match(r"^[A-Za-zА-Яа-я*(]", s.strip())) and len(_num_re.findall(s)) <= 1


def _first(vals: list[float]) -> float | None:
    return vals[0] if vals else None


def _value_tokens(cells: list[str]) -> list[str]:
    """Normalise value cells – join units that pdftotext split into their own cell.

    OCR lines carry trailing garbage ("570 425 575 428 580 432 jbouiel oo LO \\ 500"); once a numeric run is
    interrupted by garbage the rest of the line is dropped.
    """
    out: list[str] = []
    for c in cells:
        if out and not _num_re.search(c) and len(c) <= 6:
            out[-1] = out[-1] + " " + c
        elif re.fullmatch(r"[\d.,\s±+\-]+", c) and len(_num_re.findall(c)) >= 2:
            out.extend(c.split())  # "640 645 650 655" written with single spaces (OCR / tight layout)
        elif re.match(r"^\d", c) and len(_num_re.findall(c)) >= 2:
            run: list[str] = []
            broken = False
            for tok in c.split():
                if re.fullmatch(r"[+\-±]?\d+(?:[.,]\d+)?(?:%|%/°?C|V|A|W|Wp|kg|Kg|mm)?", tok):
                    run.append(tok)
                else:
                    broken = True
                    break
            if len(run) >= 2:
                out.extend(run)
                if broken:
                    break
            else:
                out.append(c)
        else:
            out.append(c)
    return out


def _fit(x: float, lo: float, hi: float) -> float | None:
    """Return x scaled by a power of ten so it falls in [lo, hi] (repairs OCR'd '1586' -> 15.86)."""
    for f in (1, 10, 100, 1000, 0.001):
        v = x / f
        if lo <= v <= hi:
            return round(v, 3)
    return None


# ----------------------------------------------------------------------------- generic table scan
_SKIP_LABEL = re.compile(r"factor|efficien|thd|frequency|tolerance|uncertainty|consumption|harmonic|noise|warranty|degradation|gain|altitude|humidity|temperature range|operating temp|ambient", re.I)


_LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl", "\u2103": "°C", "\u00a0": " ", "\u2212": "-", "\u2013": "-"}


def normalise_text(text: str) -> str:
    """Replace typographic ligatures / symbols that break label matching (LONGi uses 'Coeﬃcient', '℃')."""
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    return text


class _Table:
    """Scans the text once and keeps, per label-regex, the first matching row."""

    def __init__(self, text: str, labels: dict[str, str], ranges: dict[str, tuple[float, float]] | None = None):
        self.rows: dict[str, list[str]] = {}
        self.raw: dict[str, str] = {}
        compiled = {k: re.compile(v, re.I) for k, v in labels.items()}
        ranges = ranges or {}
        text = normalise_text(text)
        for line in text.splitlines():
            if not line.strip():
                continue
            for label, vals in _pairs(line):
                for key, rx in compiled.items():
                    if key in self.rows:
                        continue
                    if rx.search(label):
                        toks = _value_tokens(vals)
                        rng = ranges.get(key)
                        if rng and not any(_fit(x, *rng) is not None for x in _nums(" ".join(toks))):
                            continue  # e.g. "Test uncertainty for Pmax: ±3%" is not the Pmax row
                        self.rows[key] = toks
                        self.raw[key] = line.strip()
                        break

    def ncols(self) -> int:
        counts = [len(v) for v in self.rows.values() if len(v) > 1]
        if not counts:
            return 1
        return max(set(counts), key=counts.count)

    def col(self, key: str, i: int, n: int) -> str | None:
        vals = self.rows.get(key)
        if not vals:
            return None
        if len(vals) == 1:
            return vals[0]
        if len(vals) == n:
            return vals[i] if i < len(vals) else None
        if len(vals) == 2 * n:  # STC / NOCT interleaved (LONGi style)
            return vals[2 * i] if 2 * i < len(vals) else None
        if len(vals) > n and i < len(vals):
            return vals[i]
        return vals[min(i, len(vals) - 1)]


# ----------------------------------------------------------------------------- PV modules
PANEL_LABELS = {
    "model": r"^(module )?(type|model)( name| no\.?| number)?$|^module type|^type designation|^model number",
    "wp": r"(max(imum)?\.? power|rated power|nominal power|pmax|p ?max)",
    "voc": r"open[- ]circuit voltage|\bvoc\b",
    "isc": r"short[- ]circuit current|\bisc\b",
    "vmp": r"(voltage at max|optimum operating voltage|max(imum)?\.? power voltage|\bvmp+\b|rated voltage)",
    "imp": r"(current at max|optimum operating current|max(imum)?\.? power current|\bimp+\b|rated current)",
    "efficiency": r"module efficiency|efficiency",
    "temp_coeff_pmax": r"temp(erature)?\.? coeff[^\n]*(pmax|power)|(pmax|power)[^\n]*temp",
    "temp_coeff_voc": r"temp(erature)?\.? coeff[^\n]*voc|\bvoc\b[^\n]*temp|open circuit voltage[^\n]*coeff",
    "temp_coeff_isc": r"temp(erature)?\.? coeff[^\n]*isc|\bisc\b[^\n]*temp|short circuit current[^\n]*coeff",
    "max_system_v": r"max(imum)?\.? system voltage",
    "max_series_fuse_a": r"(max(imum)?\.? )?(series )?fuse",
    "dimensions": r"dimension|module size|^size",
    "weight_kg": r"^weight|module weight|weight",
    "cells": r"(number of )?cells|cell (number|quantity|orientation|configuration)",
    "bifaciality": r"bifacial(ity)? (factor|coefficient)",
    "noct": r"\bnoct\b|nominal (module )?operating cell temp",
    "max_load": r"(mechanical|static|snow) load|load",
}

PANEL_RANGES = {
    "wp": (100, 800), "voc": (20, 100), "isc": (5, 25), "vmp": (15, 90), "imp": (4, 25), "efficiency": (15, 27),
    "max_system_v": (600, 1500), "max_series_fuse_a": (10, 40), "weight_kg": (8, 60), "cells": (30, 200),
}

_MODEL_TOKEN = re.compile(r"[A-Z]{2,}[A-Z0-9\-]*\d[A-Z0-9\-/\.+]*", re.I)


def _models_from_text(text: str, labels_rx: str) -> list[str]:
    rx = re.compile(labels_rx, re.I)
    for line in text.splitlines():
        for label, vals in _pairs(line):
            if rx.search(label) and len(vals) >= 2 and all(_MODEL_TOKEN.search(v) for v in vals):
                return _value_tokens(vals)
    return []


def parse_panel(text: str) -> list[dict[str, Any]]:
    """Return a spec dict per power class found in a PV module datasheet."""
    # restrict to the STC block when a bifacial-gain / BNPI table follows
    t = _Table(text, PANEL_LABELS, PANEL_RANGES)
    models = _models_from_text(text, PANEL_LABELS["model"])
    wp_vals = _nums(" ".join(t.rows.get("wp", [])))
    n = t.ncols()
    # LONGi/AIKO-style interleaving: STC, NOCT(, BNPI) values per model (595 452.9 600 456.7 …)
    period = 1
    for k in (2, 3):
        if len(wp_vals) >= 2 * k and len(wp_vals) % k == 0:
            firsts = wp_vals[0::k]
            if all(wp_vals[j + 1] < 0.9 * wp_vals[j] for j in range(0, len(wp_vals), k)) and all(b > a for a, b in zip(firsts, firsts[1:])):
                period = k
                break
    if period == 1 and models and len(models) > 1 and len(wp_vals) in (2 * len(models), 3 * len(models)):
        period = len(wp_vals) // len(models)
    if period > 1:
        n = len(wp_vals) // period
        for key, vals in list(t.rows.items()):
            if len(vals) == period * n:
                t.rows[key] = vals[0::period]
    if models and len(models) > 1 and (period == 1 or len(models) == n):
        n = len(models)
    out: list[dict[str, Any]] = []
    for i in range(n):
        sp: dict[str, Any] = {"specs_verified": False, "spec_source": "datasheet-auto"}
        fields: list[str] = []

        def put(key: str, conv: Callable[[str], Any]) -> None:
            v = t.col(key, i, n)
            if v is None:
                return
            try:
                r = conv(v)
            except Exception:
                return
            if r is not None:
                sp[key] = r
                fields.append(key)

        def fitted(key: str) -> Callable[[str], Any]:
            lo, hi = PANEL_RANGES[key]
            return lambda v: next((_fit(x, lo, hi) for x in _nums(v) if _fit(x, lo, hi) is not None), None)

        put("wp", lambda v: (lambda x: round(x) if x else None)(fitted("wp")(v)))
        for key in ("voc", "isc", "vmp", "imp", "efficiency", "max_system_v", "max_series_fuse_a", "weight_kg"):
            put(key, fitted(key))
        put("bifaciality", lambda v: _first([x for x in _nums(v) if 50 <= x <= 100]))
        for k in ("temp_coeff_pmax", "temp_coeff_voc", "temp_coeff_isc"):
            put(k, lambda v: _first([x for x in _nums(v) if abs(x) < 1.5 and x != 0]))
        # physics: Pmax/Voc coefficients are negative, Isc positive (datasheets use odd minus glyphs)
        for k in ("temp_coeff_pmax", "temp_coeff_voc"):
            if k in sp:
                sp[k] = -abs(sp[k])
        if "temp_coeff_isc" in sp:
            sp["temp_coeff_isc"] = abs(sp["temp_coeff_isc"])
        if "bifaciality" in sp and sp["bifaciality"] < 1:
            sp.pop("bifaciality")
        if models and i < len(models):
            sp["model"] = models[i]
            fields.append("model")
        dims = t.rows.get("dimensions")
        if dims:
            d = [x for x in _nums(" ".join(dims)) if 15 <= x <= 3000]
            if len(d) >= 2 and 1000 <= max(d[:2]) <= 2700 and 800 <= min(d[:2]) <= 1500:
                sp["height_mm"], sp["width_mm"] = int(max(d[:2])), int(min(d[:2]))
                fields.append("dimensions")
                if len(d) >= 3 and 20 <= d[2] <= 60:
                    sp["thickness_mm"] = int(d[2])
        cells = t.rows.get("cells")
        if cells:
            c = [int(x) for x in _nums(" ".join(cells)) if 30 <= x <= 200]
            if c:
                sp["cells"] = c[0]
        sp["parsed_fields"] = fields
        if sp.get("wp") and sp.get("voc") and sp.get("isc"):
            out.append(sp)
    # sanity: a module with Voc < 20 V or > 100 V is not a PV module row
    out = [s for s in out if 20 <= float(s.get("voc", 0)) <= 100 and 100 <= float(s.get("wp", 0)) <= 800 and 0.6 <= float(s.get("wp")) / (float(s["voc"]) * float(s["isc"])) <= 0.9]
    # dedupe identical Wp
    seen: set[int] = set()
    res = []
    for s in out:
        if int(s["wp"]) in seen:
            continue
        seen.add(int(s["wp"]))
        res.append(s)
    return res


# ----------------------------------------------------------------------------- inverters
INV_LABELS = {
    "model": r"^(model|type designation|type|product model|model name|model no)",
    "max_dc_voltage": r"max\w*\.?\s+(\w+[./]?\s+){0,3}?(voltage|dc voltage)|max\.? pv voltage|max\.? input voltage",
    "mppt_range": r"mppt?\s+(\w+\s+){0,2}?range|mpp\s+(\w+\s+){0,2}?range|operating voltage range|input voltage range",
    "start_voltage": r"start[- ]?(up)?\s+voltage|startup voltage|start voltage|turn[- ]on voltage|initial (input|feed)",
    "max_input_current_a": r"max\w*\.?\s+(\w+\s+){0,3}?(input|pv|dc)\s+current|max\.?\s+(\w+\s+){0,2}?current per mppt|rated (pv|dc) input current",
    "max_isc_a": r"max\w*\.?\s+(\w+\s+){0,3}?short[- ]?circuit current|isc pv|max\.? isc",
    "mppt_count": r"(no\.?|number|num\.?|quantity) of (independent )?mpp(t)?( trackers?)?|mppt (number|quantity|count|no\.?)|number of mppt|^mppt$|^mppts$|^no\.? of mppt",
    "strings_per_mppt": r"(strings?|inputs?)\s+per\s+mppt|max\w*\.?\s+(number of\s+)?(input\s+)?strings|number of (dc |pv )?(inputs|strings)|string inputs|inputs per mppt|max\.? input strings",
    "max_pv_kw": r"max\w*\.?\s+(\w+\s+){0,2}?(input|pv|dc|array)\s+power|recommended\s+(max\.?\s+)?pv\s+(input\s+)?power|max\.? pv (array )?power|max\.? dc power",
    "ac_power_kw": r"(rated|nominal)\s+(\w+[/]?\w*\s+){0,3}?(active\s+|output\s+|ac\s+)*power(?!\s+factor)|rated power|continuous output power",
    "max_ac_power_kw": r"max\w*\.?\s+(\w+\s+){0,2}?(output|ac|apparent|active)\s+power|max\.? apparent",
    "max_ac_current_a": r"max\w*\.?\s+(\w+\s+){0,2}?(output|ac)\s+current|rated\s+(\w+[/]?\w*\s+){0,3}?(output|ac)\s+current|rated current",
    "phases_row": r"^(operation |output |ac |grid )?(phase|connection)|^(ac )?output type|^grid type|^feed.?in phase|^phase",
    "battery_v_range": r"battery\s+(\w+\s+){0,2}?voltage( range)?|batt\.?\s+voltage|bat\.? voltage range",
    "battery_type": r"battery type|compatible battery",
    "battery_max_charge_a": r"max\w*\.?\s+(\w+\s+){0,2}?(charg|discharg)\w*(\s*/\s*\w+)?\s+current|(charg|discharg)\w*\s+current",
    "battery_max_charge_kw": r"max\w*\.?\s+(\w+\s+){0,2}?(charg|discharg)\w*(\s*/\s*\w+)?\s+power",
    "backup_power_kw": r"(backup|off[- ]grid|ups|eps)\s+(\w+\s+){0,2}?power|rated (output )?power \(?(backup|off|eps)",
    "weight_kg": r"^weight|weight \(|net weight",
    "dimensions": r"dimension|size \(|\(w\s*[x×*]\s*h\s*[x×*]\s*d\)",
    "protection": r"(ingress )?protection (degree|rating|class)|ip ?rating|degree of protection|^ip\b",
    "integrated_dc_switch": r"dc (disconnect|switch|isolator)|input[- ]side disconnection",
    "integrated_spd": r"(dc |ac )?(surge|spd|overvoltage) (protection|arrester)",
    "efficiency": r"max\w*\.?\s+efficiency|euro\w*\s+(weighted\s+)?efficiency",
}
INV_RANGES = {
    "max_dc_voltage": (100, 1600), "start_voltage": (40, 1000), "max_input_current_a": (3, 600), "max_isc_a": (4, 900),
    "mppt_count": (1, 24), "max_ac_current_a": (3, 1200), "battery_v_range": (30, 1000), "battery_max_charge_a": (10, 1500),
    "weight_kg": (3, 800), "ac_power_kw": (0.5, 600000), "max_pv_kw": (0.5, 900000), "mppt_range": (40, 1600),
}

_KW_IN_MODEL = re.compile(r"(?<![A-Z0-9])(\d{1,3}(?:[.,]\d)?)\s*(K|KW)?(?![A-Z0-9])", re.I)


def model_kw(model: str) -> float | None:
    """Guess the kW rating encoded in an inverter model name (SUN-12K-…, SG10RT, SH5.0RT, SUN2000-8K-LC0, S6-EH3P(10KW)…)."""
    s = model.upper().replace(" ", "")
    m = re.search(r"(?<![A-Z0-9.])(\d{1,3}(?:[.,]\d)?)KW?(?![A-Z0-9])|-(\d{1,3}(?:[.,]\d)?)K(?=-|$|[A-Z])", s)
    if m:
        return float((m.group(1) or m.group(2)).replace(",", "."))
    m = re.search(r"(?:^|-)(?:SUN|SG|SH|GW|S[56]-[A-Z0-9]*?P)(\d{1,3}(?:\.\d)?)(?=[A-Z-])", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(?<![A-Z0-9.])(\d{1,3}(?:\.\d)?)K(?![A-Z0-9])|(\d{1,3}(?:\.\d)?)K(?=-|$)|(?<=P)(\d{1,3}(?:\.\d)?)K", s)
    if m:
        return float(next(g for g in m.groups() if g))
    return None


def _range(v: str) -> tuple[float | None, float | None]:
    n = [x for x in _nums(v) if x >= 0]
    if len(n) >= 2:
        return min(n[0], n[1]), max(n[0], n[1])
    return (n[0], None) if n else (None, None)


def _kw(v: str) -> float | None:
    n = _nums(v)
    if not n:
        return None
    x = n[0]
    vl = v.lower()
    if "kw" in vl or "kva" in vl or (x < 400 and "w" not in vl.replace("kw", "")):
        return round(x, 2) if x < 1000 else round(x / 1000, 2)
    return round(x / 1000, 2)


def _per_mppt_current(v: str) -> tuple[float | None, list[float]]:
    """'54+54' → 54 ; '20 A / 40 A' → 40 ; '16 A' → 16 ; '2*16' → 16."""
    v = v.replace("×", "*")
    m = re.search(r"\(([^)]*\d[^)]*)\)", v)
    if m and len(_nums(m.group(1))) >= 2:  # "32 A (16 A / 16 A)" → per-MPPT values in brackets
        lst = _nums(m.group(1))
        return max(lst), lst
    vals = _nums(re.sub(r"\([^)]*\)", "", v))
    if not vals:
        return None, []
    if re.search(r"\d\s*[*x]\s*\d", v, re.I):
        n_, per = int(vals[0]), vals[-1]
        return per, [per] * n_ if n_ <= 12 else [per]
    return max(vals), vals


def parse_inverter(text: str, model_hints: list[str] | None = None) -> list[dict[str, Any]]:
    """Return a spec dict per model column found in an inverter datasheet."""
    t = _Table(text, INV_LABELS, INV_RANGES)
    models = _models_from_text(text, INV_LABELS["model"])
    if models and len({m for m in models}) == 1:
        models = []  # broken model row ("LP3-EU-SM2" repeated)
    if not models and model_hints:
        models = model_hints
    n = max(t.ncols(), len(models) or 1)
    if models and len(models) > 1 and t.ncols() != len(models):
        n = len(models) if t.ncols() == 1 else t.ncols()
    low = text.lower()
    three_rx = r"three[- ]phase|3/n/pe|3l/n/pe|3l\+n\+pe|3-phase|3 phase|3w\+n|3p\+n|3~|3ph\b"
    one_rx = r"single[- ]phase|1/n/pe|l/n/pe|l\+n\+pe|1-phase|1 phase|1p\+n|1~|1ph\b"
    phases_default = None
    prow = " ".join(t.rows.get("phases_row") or []).lower()
    if re.search(three_rx, prow):
        phases_default = 3
    elif re.search(one_rx, prow):
        phases_default = 1
    else:
        n3, n1 = len(re.findall(three_rx, low)), len(re.findall(one_rx, low))
        phases_default = 3 if n3 > n1 else (1 if n1 else None)
    hybrid = bool(re.search(r"\bbattery\b|hybrid|energy storage|\bess\b", low))
    out = []
    for i in range(n):
        sp: dict[str, Any] = {"specs_verified": False, "spec_source": "datasheet-auto", "hybrid": hybrid}
        fields: list[str] = []

        def val(key: str) -> str | None:
            return t.col(key, i, n)

        v = val("max_dc_voltage")
        if v and _nums(v):
            sp["max_dc_voltage"] = _nums(v)[0]
            fields.append("max_dc_voltage")
        v = val("mppt_range")
        if v:
            lo, hi = _range(v)
            if lo is not None and hi is not None and hi > lo >= 50:
                sp["mppt_v_min"], sp["mppt_v_max"] = lo, hi
                fields.append("mppt_range")
        v = val("start_voltage")
        if v and _nums(v):
            sp["start_voltage"] = _nums(v)[0]
            fields.append("start_voltage")
        v = val("max_input_current_a")
        if v:
            cur, lst = _per_mppt_current(v)
            if cur:
                sp["max_input_current_a"] = cur
                if len(lst) > 1:
                    sp["mppt_input_current_a"] = lst
                fields.append("max_input_current_a")
        v = val("max_isc_a")
        if v:
            cur, lst = _per_mppt_current(v)
            if cur:
                sp["max_isc_a"] = cur
                if len(lst) > 1:
                    sp["mppt_isc_a"] = lst
                fields.append("max_isc_a")
        v = val("mppt_count")
        if v:
            nn = [int(x) for x in _nums(v) if 1 <= x <= 24]
            if nn:
                sp["mppt_count"] = nn[0]
                fields.append("mppt_count")
                if len(nn) >= 2 and "/" in v and nn[1] >= nn[0]:  # "2/3" = MPPT / strings
                    sp["strings_total"] = nn[1]
                    sp["strings_per_mppt"] = max(1, -(-nn[1] // nn[0]))
                    fields.append("strings_per_mppt")
        v = val("strings_per_mppt")
        if v and "strings_per_mppt" not in sp:
            nn = [int(x) for x in _nums(v) if 1 <= x <= 40]
            if nn:
                if sp.get("mppt_count") and nn[0] > 4 and nn[0] % sp["mppt_count"] == 0:
                    sp["strings_total"] = nn[0]
                    sp["strings_per_mppt"] = nn[0] // sp["mppt_count"]
                elif "/" in v and len(nn) >= 2:
                    sp["strings_per_mppt"] = max(1, -(-nn[1] // nn[0])) if nn[0] <= 4 else nn[0]
                else:
                    sp["strings_per_mppt"] = nn[0]
                fields.append("strings_per_mppt")
        elif sp.get("mppt_input_current_a") and "mppt_count" not in sp:
            sp["mppt_count"] = len(sp["mppt_input_current_a"])
        v = val("max_pv_kw")
        if v and _kw(v):
            sp["max_pv_kw"] = _kw(v)
            fields.append("max_pv_kw")
        v = val("ac_power_kw")
        if v and _kw(v):
            sp["ac_power_kw"] = _kw(v)
            fields.append("ac_power_kw")
        v = val("max_ac_power_kw")
        if v and _kw(v) and _nums(v)[0] > 0:
            sp["max_ac_power_kw"] = _kw(v)
        v = val("max_ac_current_a")
        if v and _nums(v):
            sp["max_ac_current_a"] = max(_nums(v))
            fields.append("max_ac_current_a")
        v = val("battery_v_range")
        if v:
            lo, hi = _range(v)
            if lo is not None:
                sp["battery_v_min"], sp["battery_v_max"] = lo, hi or lo
                sp["battery_voltage_class"] = "LV" if (hi or lo) <= 120 else "HV"
                sp["hybrid"] = True
                fields.append("battery_v_range")
        v = val("battery_max_charge_a")
        if v and _nums(v):
            sp["battery_max_charge_a"] = max(_nums(v))
            fields.append("battery_max_charge_a")
        v = val("battery_max_charge_kw")
        if v and _kw(v):
            sp["battery_max_charge_kw"] = _kw(v)
        v = val("weight_kg")
        if v:
            w = [x for x in _nums(v) if 3 <= x <= 400]
            if w:
                sp["weight_kg"] = w[0]
        v = t.rows.get("dimensions")
        if v:
            d = [x for x in _nums(" ".join(v)) if 50 <= x <= 2500]
            if len(d) >= 3:
                sp["dimensions_mm"] = [int(x) for x in d[:3]]
        v = t.rows.get("protection")
        if v:
            m = re.search(r"IP ?(\d{2})", " ".join(v), re.I)
            if m:
                sp["ip_rating"] = "IP" + m.group(1)
        sp["phases"] = phases_default or 3
        if phases_default:
            fields.append("phases")
        if models and i < len(models):
            sp["model"] = models[i]
            kw = model_kw(models[i])
            if kw and "ac_power_kw" not in sp:
                sp["ac_power_kw"] = kw
        if not sp.get("hybrid"):
            sp["battery_voltage_class"] = None
        sp["parsed_fields"] = fields
        if sp.get("max_dc_voltage") or sp.get("mppt_v_min") or sp.get("ac_power_kw"):
            out.append(sp)
    return out


# ----------------------------------------------------------------------------- batteries
BAT_LABELS = {
    "model": r"^(model|type|product model|model name|type designation)",
    "kwh": r"(nominal |rated |total |usable |battery )?(energy|capacity)( \(?kwh\)?)?|energy capacity|nominal energy|rated energy",
    "usable_kwh": r"usable (energy|capacity)|available energy",
    "nominal_v": r"nominal voltage|rated voltage|battery voltage",
    "v_range": r"(operating |working |charge |discharge )?voltage range|voltage \(v\)",
    "ah": r"(nominal |rated )?capacity \(?ah|\bah\b",
    "max_charge_a": r"max(imum)?\.? (continuous )?charg(e|ing)(\s*/\s*discharg(e|ing))? current|(recommended|rated|standard) charg(e|ing)(\s*/\s*discharg(e|ing))? current",
    "max_discharge_a": r"max(imum)?\.? (continuous )?discharg(e|ing) current|peak discharg",
    "max_parallel": r"(max(imum)?\.? )?(number of )?(parallel|modules in parallel|units in parallel|expansion|scalab)",
    "cycles": r"cycle life|cycles",
    "weight_kg": r"^weight|weight \(",
    "dimensions": r"dimension|size \(",
    "protection": r"(ingress )?protection|ip ?rating|^ip\b",
    "chemistry": r"(cell )?(type|chemistry|technology)",
    "dod": r"\bdod\b|depth of discharge",
    "warranty": r"warranty",
}


def parse_battery(text: str) -> list[dict[str, Any]]:
    t = _Table(text, BAT_LABELS)
    models = _models_from_text(text, BAT_LABELS["model"])
    n = max(t.ncols(), len(models) or 1)
    out = []
    low = text.lower()
    for i in range(n):
        sp: dict[str, Any] = {"specs_verified": False, "spec_source": "datasheet-auto"}
        fields: list[str] = []
        v = t.col("kwh", i, n)
        if v:
            x = _nums(v)
            if x:
                kwh = x[0]
                if "wh" in v.lower() and "kwh" not in v.lower() and kwh > 100:
                    kwh = kwh / 1000
                elif kwh > 1500:
                    kwh = kwh / 1000
                if 0.5 <= kwh <= 5000:
                    sp["kwh"] = round(kwh, 2)
                    fields.append("kwh")
        v = t.col("usable_kwh", i, n)
        if v and _nums(v):
            u = _nums(v)[0]
            sp["usable_kwh"] = round(u / 1000 if u > 1500 else u, 2)
        v = t.col("nominal_v", i, n)
        if v and _nums(v):
            sp["nominal_v"] = _nums(v)[0]
            fields.append("nominal_v")
        v = t.col("v_range", i, n)
        if v:
            lo, hi = _range(v)
            if lo is not None and hi is not None:
                sp["v_min"], sp["v_max"] = lo, hi
        v = t.col("ah", i, n)
        if v and _nums(v):
            sp["ah"] = _nums(v)[0]
        v = t.col("max_charge_a", i, n)
        if v and _nums(v):
            sp["max_charge_a"] = max(_nums(v))
            fields.append("max_charge_a")
        v = t.col("max_discharge_a", i, n)
        if v and _nums(v):
            sp["max_discharge_a"] = max(_nums(v))
        v = t.col("max_parallel", i, n)
        if v:
            nn = [int(x) for x in _nums(v) if 2 <= x <= 64]
            if nn:
                sp["max_parallel"] = nn[0]
        v = t.col("cycles", i, n)
        if v:
            c = [int(x) for x in _nums(v) if x >= 1000]
            if c:
                sp["cycles"] = c[0]
        v = t.col("weight_kg", i, n)
        if v:
            w = [x for x in _nums(v) if 3 <= x <= 5000]
            if w:
                sp["weight_kg"] = w[0]
        v = t.rows.get("dimensions")
        if v:
            d = [x for x in _nums(" ".join(v)) if 50 <= x <= 2500]
            if len(d) >= 3:
                sp["dimensions_mm"] = [int(x) for x in d[:3]]
        v = t.rows.get("protection")
        if v:
            m = re.search(r"IP ?(\d{2})", " ".join(v), re.I)
            if m:
                sp["ip_rating"] = "IP" + m.group(1)
        v = t.col("dod", i, n)
        if v and _nums(v):
            sp["dod_pct"] = _nums(v)[0]
        if re.search(r"lifepo4|lfp|lithium iron", low):
            sp["chemistry"] = "LiFePO4"
        nv = sp.get("nominal_v") or sp.get("v_max") or 0
        if nv:
            sp["voltage_class"] = "LV" if nv <= 120 else "HV"
        if models and i < len(models):
            sp["model"] = models[i]
        if "kwh" not in sp and sp.get("ah") and nv:
            sp["kwh"] = round(sp["ah"] * nv / 1000, 2)
            fields.append("kwh")
        sp["parsed_fields"] = fields
        if sp.get("kwh"):
            out.append(sp)
    return out


def parse_by_category(category: str, text: str, model_hints: list[str] | None = None) -> list[dict[str, Any]]:
    if category == "panel":
        return parse_panel(text)
    if category == "inverter":
        return parse_inverter(text, model_hints)
    if category == "battery":
        return parse_battery(text)
    return []


# ----------------------------------------------------------------------------- Bulgarian product-page bullets
# green-energy.bg product descriptions carry a short "Основни характеристики" list that is specific to the
# exact product (one column), so these values override the multi-column datasheet guess.
BG_INV_LABELS = {
    "max_pv_kw": r"препоръчителн\w* макс\w*\.? (pv|фв|фотоволтаичн\w*)( входна)? мощност|макс\w*\.? (pv|фв) (входна )?мощност",
    "max_dc_voltage": r"макс\w*\.? (dc |pv )?входно (dc )?напрежение|максимално напрежение на вход",
    "start_voltage": r"(стартово|начално|пусково) напрежение",
    "mppt_range": r"диапазон на (работно |входно )?напрежение( на)? mppt|mppt диапазон|пълен диапазон на напрежение(?!\s*(за|на) батери)|диапазон mppt",
    "max_input_current_a": r"макс\w*\.? входен ток( за (всяко|всеки|един) mppt)?|входен ток на mppt",
    "max_isc_a": r"макс\w*\.? ток на късо|ток на късо съединение",
    "ac_power_kw": r"(номинална |максимална )?изходна (активна )?мощност|номинална мощност|изходна мощност",
    "max_ac_current_a": r"макс\w*\.? изходен ток|номинален изходен ток",
    "mppt_count": r"брой (mpp|mppt) тракер|независими mpp",
    "battery_v_range": r"напрежение (за|на) батери\w+|диапазон на батери\w+|работно напрежение на батери",
    "battery_max_charge_a": r"ток на (зареждане|разреждане)",
    "battery_max_charge_kw": r"мощност на (зареждане|разреждане)",
    "protection": r"степен на защита",
    "weight_kg": r"^тегло",
    "dimensions": r"^размери",
    "warranty": r"^гаранция",
    "phases_row": r"^фаз|брой фази|изходна честота и напрежение",
}
BG_PANEL_LABELS = {
    "wp": r"(номинална |максимална )?мощност( на модула)?( \(?pmax\)?)?$|pmax",
    "voc": r"напрежение на празен ход|\bvoc\b",
    "isc": r"ток на късо съединение|\bisc\b",
    "vmp": r"напрежение при максимална мощност|\bvmp+\b",
    "imp": r"ток при максимална мощност|\bimp+\b",
    "efficiency": r"ефективност",
    "max_system_v": r"макс\w*\.? (системно )?напрежение( на системата)?",
    "max_series_fuse_a": r"предпазител",
    "temp_coeff_pmax": r"температурен коефициент.*(pmax|мощност)",
    "temp_coeff_voc": r"температурен коефициент.*voc",
    "dimensions": r"^размери|габарит",
    "weight_kg": r"^тегло",
    "cells": r"брой клетки|клетки",
    "warranty": r"^гаранция",
}
BG_BAT_LABELS = {
    "kwh": r"(номинален |общ |полезен )?капацитет( на батерията)?( \(?kwh\)?)?|енергия|номинална енергия",
    "usable_kwh": r"(полезен|използваем\w*) (капацитет|енергия)",
    "nominal_v": r"номинално напрежение|напрежение на батерията",
    "ah": r"капацитет.*ah|ампер[- ]?час",
    "max_charge_a": r"макс\w*\.? ток на (зареждане|разреждане)|ток на зареждане",
    "max_parallel": r"паралел",
    "cycles": r"цик[лъ]",
    "weight_kg": r"^тегло",
    "dimensions": r"^размери|габарит",
    "protection": r"степен на защита",
    "dod": r"\bdod\b|дълбочина на разряд",
    "warranty": r"^гаранция",
}


def _bg_lines(text: str) -> str:
    """Normalise a product description: 'Label : value' → 'Label  value' so the table scanner splits it;
    '2 независими MPP тракера' → 'Брой MPP тракери  2'."""
    out = []
    for raw in text.splitlines():
        line = raw.strip(" •·-–\t")
        if not line:
            continue
        # thousands written as "15 000Wp" / "1.100 V" (Bulgarian decimals use a comma, so a dot-group is a thousands separator)
        line = re.sub(r"(?<=\d)[ \u00a0.](?=\d{3}(?!\d))", "", line)
        m = re.match(r"^(\d+)\s+(независими\s+mpp\s+тракер\w*)", line, re.I)
        if m:
            line = f"Брой MPP тракери  {m.group(1)}"
        line = re.sub(r"\s*[:：]\s*", "  ", line, count=1)
        out.append(line)
    return "\n".join(out)


def parse_bg_description(category: str, text: str) -> dict[str, Any]:
    """Extract specs from the Bulgarian bullet list of a product page (single product → single spec dict)."""
    norm = _bg_lines(text)
    sp: dict[str, Any] = {}
    if category == "inverter":
        t = _Table(norm, BG_INV_LABELS, INV_RANGES)
        v = " ".join(t.rows.get("max_pv_kw", []))
        if v and _kw(v):
            sp["max_pv_kw"] = _kw(v)
        v = " ".join(t.rows.get("max_dc_voltage", []))
        if v and _nums(v):
            sp["max_dc_voltage"] = _nums(v)[0]
        v = " ".join(t.rows.get("start_voltage", []))
        if v and _nums(v):
            sp["start_voltage"] = _nums(v)[0]
        v = " ".join(t.rows.get("mppt_range", []))
        if v:
            lo, hi = _range(v)
            if lo is not None and hi is not None and hi > lo >= 40:
                sp["mppt_v_min"], sp["mppt_v_max"] = lo, hi
        v = " ".join(t.rows.get("max_input_current_a", []))
        if v:
            cur, lst = _per_mppt_current(v)
            if cur:
                sp["max_input_current_a"] = cur
        v = " ".join(t.rows.get("max_isc_a", []))
        if v and _nums(v):
            sp["max_isc_a"] = max(_nums(v))
        v = " ".join(t.rows.get("ac_power_kw", []))
        if v and _nums(v):
            x = _nums(v)[0]
            # "11,000VA", "16000VA", "6600 kW" (typo for W), "10 kW"
            kw = x / 1000 if x >= 100 else x
            if 0.5 <= kw <= 1000:
                sp["ac_power_kw"] = round(kw, 2)
        v = " ".join(t.rows.get("max_ac_current_a", []))
        if v and _nums(v):
            sp["max_ac_current_a"] = _nums(v)[0]
        v = " ".join(t.rows.get("mppt_count", []))
        if v:
            nn = [int(x) for x in _nums(v) if 1 <= x <= 24]
            if nn:
                sp["mppt_count"] = nn[0]
        v = " ".join(t.rows.get("battery_v_range", []))
        if v:
            lo, hi = _range(v)
            if lo is not None:
                sp["battery_v_min"], sp["battery_v_max"] = lo, hi or lo
                sp["battery_voltage_class"] = "LV" if (hi or lo) <= 120 else "HV"
                sp["hybrid"] = True
        v = " ".join(t.rows.get("battery_max_charge_a", []))
        if v and _nums(v):
            sp["battery_max_charge_a"] = max(_nums(v))
        v = " ".join(t.rows.get("battery_max_charge_kw", []))
        if v and _kw(v):
            sp["battery_max_charge_kw"] = _kw(v)
        v = " ".join(t.rows.get("protection", []))
        m = re.search(r"IP ?(\d{2})", v, re.I) if v else None
        if m:
            sp["ip_rating"] = "IP" + m.group(1)
        v = " ".join(t.rows.get("weight_kg", []))
        if v:
            w = [x for x in _nums(v) if 3 <= x <= 800]
            if w:
                sp["weight_kg"] = w[0]
        v = " ".join(t.rows.get("dimensions", []))
        if v:
            d = [int(x) for x in _nums(v) if 50 <= x <= 2500]
            if len(d) >= 3:
                sp["dimensions_mm"] = d[:3]
        v = " ".join(t.rows.get("phases_row", []))
        if v and re.search(r"400|380|3[- ]?фаз|трифаз", v, re.I):
            sp["phases"] = 3
        elif v and re.search(r"230|1[- ]?фаз|монофаз|еднофаз", v, re.I):
            sp["phases"] = 1
    elif category == "panel":
        t = _Table(norm, BG_PANEL_LABELS, PANEL_RANGES)
        for key in ("wp", "voc", "isc", "vmp", "imp", "efficiency", "max_system_v", "max_series_fuse_a", "weight_kg"):
            v = " ".join(t.rows.get(key, []))
            if v:
                lo, hi = PANEL_RANGES[key]
                x = next((_fit(n, lo, hi) for n in _nums(v) if _fit(n, lo, hi) is not None), None)
                if x is not None:
                    sp[key] = round(x) if key == "wp" else x
        for key in ("temp_coeff_pmax", "temp_coeff_voc"):
            v = " ".join(t.rows.get(key, []))
            x = [n for n in _nums(v) if 0 < abs(n) < 1.5] if v else []
            if x:
                sp[key] = -abs(x[0])
        v = " ".join(t.rows.get("dimensions", []))
        if v:
            d = [x for x in _nums(v) if 15 <= x <= 3000]
            if len(d) >= 2 and 1000 <= max(d[:2]) <= 2700 and 800 <= min(d[:2]) <= 1500:
                sp["height_mm"], sp["width_mm"] = int(max(d[:2])), int(min(d[:2]))
                if len(d) >= 3 and 20 <= d[2] <= 60:
                    sp["thickness_mm"] = int(d[2])
        v = " ".join(t.rows.get("cells", []))
        if v:
            c = [int(x) for x in _nums(v) if 30 <= x <= 200]
            if c:
                sp["cells"] = c[0]
    elif category == "battery":
        t = _Table(norm, BG_BAT_LABELS)
        v = " ".join(t.rows.get("kwh", []))
        if v and _nums(v):
            x = _nums(v)[0]
            kwh = x / 1000 if ("wh" in v.lower() and "kwh" not in v.lower() and x > 100) or x > 1500 else x
            if 0.5 <= kwh <= 5000:
                sp["kwh"] = round(kwh, 2)
        v = " ".join(t.rows.get("nominal_v", []))
        if v and _nums(v):
            sp["nominal_v"] = _nums(v)[0]
            sp["voltage_class"] = "LV" if sp["nominal_v"] <= 120 else "HV"
        v = " ".join(t.rows.get("ah", []))
        if v and _nums(v):
            sp["ah"] = _nums(v)[0]
        v = " ".join(t.rows.get("max_charge_a", []))
        if v and _nums(v):
            sp["max_charge_a"] = max(_nums(v))
        v = " ".join(t.rows.get("max_parallel", []))
        if v:
            nn = [int(x) for x in _nums(v) if 2 <= x <= 64]
            if nn:
                sp["max_parallel"] = nn[0]
        v = " ".join(t.rows.get("cycles", []))
        if v:
            c = [int(x) for x in _nums(v) if x >= 1000]
            if c:
                sp["cycles"] = c[0]
        v = " ".join(t.rows.get("weight_kg", []))
        if v:
            w = [x for x in _nums(v) if 3 <= x <= 5000]
            if w:
                sp["weight_kg"] = w[0]
        v = " ".join(t.rows.get("dimensions", []))
        if v:
            d = [int(x) for x in _nums(v) if 50 <= x <= 2500]
            if len(d) >= 3:
                sp["dimensions_mm"] = d[:3]
        v = " ".join(t.rows.get("dod", []))
        if v and _nums(v):
            sp["dod_pct"] = _nums(v)[0]
        v = " ".join(t.rows.get("protection", []))
        m = re.search(r"IP ?(\d{2})", v, re.I) if v else None
        if m:
            sp["ip_rating"] = "IP" + m.group(1)
    w = re.search(r"гаранция\s*[:\-]?\s*(\d+\s*(години|год\.?|г\.?))", text, re.I)
    if w:
        sp["warranty_text"] = w.group(1)
    return sp
