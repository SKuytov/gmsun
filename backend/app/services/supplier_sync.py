"""green-energy.bg portfolio importer.

The supplier runs WooCommerce; its public Store API lists the whole portfolio
(``/wp-json/wc/store/v1/products``).  For every product we

* map the WooCommerce category to a gmsun catalog category,
* read the Bulgarian "Основни характеристики" bullets of the product page,
* download the linked PDF datasheet, extract its text and parse the spec table
  (one column per power class / model) with :mod:`datasheet_parse`,
* build one gmsun catalog item per concrete model (a datasheet "640~665 W"
  becomes six panel items when the product title does not pin the class),
* convert the list price from BGN to EUR (fixed rate 1.95583).

Datasheet PDFs are *not* stored in the repository (copyright) – only their
URLs.  The API caches them under ``DATA_DIR/datasheets`` on first request so
the technical file can embed them even without internet.

The same code powers the offline seed snapshot
(``app/seed_data/green_energy_catalog.json``, generated with
``python -m app.services.supplier_sync --write-seed``) and the admin "sync"
endpoint that refreshes the catalog from the live site.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

import httpx

from . import datasheet_parse as dp

STORE_API = "https://green-energy.bg/wp-json/wc/store/v1"
USER_AGENT = "Mozilla/5.0 (compatible; gmsun-catalog-sync/1.0; +https://github.com/SKuytov/gmsun)"
BGN_PER_EUR = 1.95583
SUPPLIER = "green-energy.bg"
SEED_FILE = Path(__file__).resolve().parent.parent / "seed_data" / "green_energy_catalog.json"

# WooCommerce category → gmsun category
CATEGORY_MAP: dict[str, str] = {
    "Фотоволтаични панели": "panel",
    "Соларни инвертори": "inverter",
    "Соларни батерии": "battery",
    "Battery": "battery",
    "Битови Батерии": "battery",
    "Индустриални батерии": "battery",
    "BMS": "battery_accessory",
    "Конструкции": "mounting",
    "Соларни кабели": "solar_cable",
    "Смарт метри": "monitoring",
    "Смарт Логери": "monitoring",
    "wi fi dongle": "monitoring",
    "Контролери": "accessory",
    "back up box": "accessory",
    "Зарядни устройства": "accessory",
    "Преобразувател": "accessory",
    "Фотоволтаични системи": "other",
    "Битови фотоволтаични системи": "other",
    "Индустриални фотоволтаични системи": "other",
}
# order matters: the most specific category wins
CATEGORY_PRIORITY = ["panel", "inverter", "battery_accessory", "battery", "mounting", "solar_cable", "monitoring", "accessory", "other"]

BRANDS = [
    "LONGi", "Longi", "Tongwei", "AIKO", "Aiko", "Ulica", "Jinko", "Risen", "DAH", "Dah", "Suntech", "Trina", "JA Solar", "Canadian",
    "Huawei", "HUAWEI", "Solis", "Deye", "DEYE", "GoodWe", "Goodwe", "GOODWE", "Sungrow", "SUNGROW", "Luxpower", "LuxPower", "EASUN", "Growatt",
    "Dyness", "DYNESS", "Pylontech", "BYD", "Felicity", "KSTAR", "Eastron", "Chint", "Aerocompact", "Schletter", "K2", "Staubli", "Stäubli",
]

_PDF_RE = re.compile(r"https?://[^\"'\s<>]+\.pdf", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


# ----------------------------------------------------------------------------- helpers
def strip_html(s: str) -> str:
    s = _TAG_RE.sub("\n", s or "")
    s = _html.unescape(s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def clean_name(name: str) -> str:
    name = _html.unescape(name or "")
    name = re.sub(r"\s+", " ", name).strip(" -–")
    return name


def brand_of(name: str, categories: list[dict[str, Any]]) -> str | None:
    for c in categories:
        n = c.get("name", "")
        for b in BRANDS:
            if b.lower() in n.lower():
                return _canonical_brand(b)
    for b in BRANDS:
        if re.search(r"(?<![A-Za-z])" + re.escape(b) + r"(?![a-z])", name, re.I):
            return _canonical_brand(b)
    return None


def _canonical_brand(b: str) -> str:
    return {"longi": "LONGi Solar", "tongwei": "Tongwei Solar", "aiko": "AIKO", "ulica": "Ulica Solar", "jinko": "Jinko Solar", "risen": "Risen Energy",
            "dah": "DAH Solar", "suntech": "Suntech", "huawei": "Huawei", "solis": "Solis", "deye": "Deye", "goodwe": "GoodWe", "sungrow": "Sungrow",
            "luxpower": "Luxpower", "easun": "EASUN", "dyness": "Dyness", "kstar": "KSTAR", "eastron": "Eastron", "stäubli": "Stäubli", "staubli": "Stäubli"}.get(b.lower(), b)


def gmsun_category(p: dict[str, Any]) -> str:
    cats = {CATEGORY_MAP.get(c.get("name", "")) for c in p.get("categories", [])}
    cats.discard(None)
    for c in CATEGORY_PRIORITY:
        if c in cats:
            return c
    n = clean_name(p.get("name", "")).lower()
    if "панел" in n or re.search(r"\d{3}\s*wp?\b", n):
        return "panel"
    if "инвертор" in n:
        return "inverter"
    if "батери" in n or "kwh" in n:
        return "battery"
    return "other"


def price_eur(p: dict[str, Any]) -> tuple[float, float]:
    """Return (price_bgn, price_eur) from the Store API minor-unit price string."""
    pr = p.get("prices") or {}
    try:
        minor = int(pr.get("currency_minor_unit") or 2)
        raw = float(pr.get("price") or 0) / (10 ** minor)
    except (TypeError, ValueError):
        return 0.0, 0.0
    if (pr.get("currency_code") or "BGN") == "EUR":
        return round(raw * BGN_PER_EUR, 2), round(raw, 2)
    return round(raw, 2), round(raw / BGN_PER_EUR, 2)


def datasheet_urls(p: dict[str, Any]) -> list[str]:
    text = _html.unescape((p.get("description") or "") + " " + (p.get("short_description") or ""))
    seen: list[str] = []
    for u in _PDF_RE.findall(text):
        if u not in seen:
            seen.append(u)
    return seen


# ----------------------------------------------------------------------------- model names in titles
def _normalise_models_text(title: str) -> str:
    t = clean_name(title)
    t = re.sub(r"\((\d+(?:[.,]\d+)?)\s*KW?\)", r"\1K", t, flags=re.I)  # S6-EH3P(10KW)K02 -> S6-EH3P10KK02
    t = re.sub(r"\s*\((\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)+)\)\s*K(\w*)", lambda m: m.group(1).replace(" ", "") + "K" + m.group(2), t)  # S6-EH1P (12/14/16) K03 -> S6-EH1P12/14/16K03
    t = t.replace("//", "/")
    t = re.sub(r"(?<=[A-Za-z0-9])\s*-\s+(?=[A-Za-z0-9])", "-", t)  # "SUN2000-25K- MB0", "SUN2000 -25KTL-M5"
    t = re.sub(r"(?<=[A-Za-z0-9])\s+-(?=[A-Za-z0-9])", "-", t)
    t = re.sub(r"\b(SUN2000-\d+K?)\s+(KTL-[A-Z0-9]+)", r"\1\2", t, flags=re.I)  # "SUN2000-50 KTL-MC0"
    t = re.sub(r"\b(SG|SH)\s+(\d)", r"\1\2", t)  # Sungrow "SG 15 RT"
    t = re.sub(r"(\d)\s+(RS-S|RS|RT|CX|HX|T)(?=\b|-)", r"\1\2", t)
    t = re.sub(r"\b(\d+(?:[.,]\d+)?)\s?K\s?W\b", r"\1KW", t, flags=re.I)
    return t


_MODEL_TOKEN_RX = re.compile(
    r"[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9/+,]+)+"  # SUN-14/15K-SG05LP3-EU-SM2, S6-EH1P12/14/16K03
    r"|[A-Za-z]{1,6}\d+(?:\.\d+)?[A-Za-z]{1,4}(?:/\d+(?:\.\d+)?[A-Za-z]{0,4})+"  # SH3.0RS/3.6RS/4.0RS
    r"|[A-Za-z]{2,}\d+(?:\.\d+)?[A-Za-z]+[A-Za-z0-9]*"  # SG350HX, GW25K, SH10RT
    r"|(?<![A-Za-z0-9-])\d+(?:\.\d+)?[A-Za-z]+(?:-[A-Za-z0-9]+)+"  # "3KTL-L1" (prefix inherited from the previous model)
)
_NOT_MODEL = re.compile(r"^(\d+(\.\d+)?\s*(K?W|KWP|WP|VA|KVA|A|V|MPPT?)|EU|USA?|PRO|PLUS|\d+(\.\d+)?KW)$", re.I)


def expand_models(title: str) -> list[str]:
    """'Deye SUN-14/15/16/18/20K-SG05LP3-EU-SM2' → ['SUN-14K-SG05LP3-EU-SM2', …];
    'Solis S5-GR3P6K / S5-GR3P10K' → both; 'SUNGROW SG 15 RT / SG 17 RT' → ['SG15RT', 'SG17RT']."""
    t = _normalise_models_text(title)
    models: list[str] = []
    for tok in _MODEL_TOKEN_RX.findall(t):
        tok = tok.strip(" ,;.")
        if "/" in tok:
            parts = tok.split("/")
            head = parts[0]
            m = re.match(r"^(.*)(?<![\d.])(\d+(?:\.\d+)?)([A-Za-z\-][A-Za-z0-9\-]*)?$", head)
            if m and len(parts) > 1:
                prefix, suffix = m.group(1), m.group(3) or ""
                lm = re.match(r"^(\d+(?:\.\d+)?)(.*)$", parts[-1].strip())
                tail = lm.group(2) if lm else ""
                for part in parts:
                    if part is not head and re.match(r"^[A-Za-z]", part.strip()):
                        models.append(part.strip())  # "SG33CX-P2/SG50CX-P2" – full model after the slash
                        continue
                    pm = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(.*)$", part if part is not head else head[len(prefix):])
                    if not pm:
                        continue
                    num, own_tail = pm.group(1), pm.group(2).strip()
                    models.append((prefix + num + (own_tail or tail or suffix)).strip())
                continue
        if re.match(r"^\d", tok):
            prev = next((m for m in reversed(models) if re.match(r"^[A-Za-z]+\d*-\d", m)), None)
            if prev:
                tok = re.match(r"^([A-Za-z]+\d*-)", prev).group(1) + tok
            else:
                continue
        if re.search(r"\d", tok) and len(tok) >= 4 and not _NOT_MODEL.match(tok):
            models.append(tok)
    out: list[str] = []
    for m in models:
        m = m.strip(" ,;")
        if m and m not in out and not re.fullmatch(r"\d+(\.\d+)?\s*(K?W|KWP|WP)", m, re.I) and len(m) >= 4:
            out.append(m)
    return out


# model-code heuristics (phases / hybrid / battery class) for brands sold by the supplier
_MODEL_HINTS: list[tuple[str, dict[str, Any]]] = [
    (r"SG0\dLP1|SG0\dLP1-EU", {"phases": 1, "hybrid": True, "battery_voltage_class": "LV"}),  # Deye LP1
    (r"SG0\dLP3", {"phases": 3, "hybrid": True, "battery_voltage_class": "LV"}),  # Deye LP3
    (r"SG0\dHP3", {"phases": 3, "hybrid": True, "battery_voltage_class": "HV"}),  # Deye HP3
    (r"SG0\dHP1|SG0\dHB1", {"phases": 1, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"\bS\d-EH1P", {"phases": 1, "hybrid": True}),  # Solis EH1P
    (r"\bS\d-EH3P.*-H\b|\bS\d-EH3P\d+K-H", {"phases": 3, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"\bS\d-EH3P", {"phases": 3, "hybrid": True}),
    (r"\bS\d-GR1P|\bS\d-GR1P", {"phases": 1, "hybrid": False}),
    (r"\bS\d-GR3P|\bS\d-GC\d+K|K-5G-PRO|EHV-5G", {"phases": 3, "hybrid": False}),
    (r"SUN2000-\d+(\.\d+)?KTL-L1", {"phases": 1, "hybrid": True, "battery_voltage_class": "HV"}),  # Huawei L1 (LUNA)
    (r"SUN2000-\d+K-LC0", {"phases": 1, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"SUN2000-\d+K-MAP0|SUN2000-\d+K-MB0|SUN2000-\d+KTL-M1\b", {"phases": 3, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"SUN2000-\d+KTL-M[0-9]|SUN2000-\d+KTL-M[C-Z]\d|SUN2000-\d+KTL-H\d", {"phases": 3, "hybrid": False}),
    (r"\bSH\d+(\.\d+)?RS", {"phases": 1, "hybrid": True, "battery_voltage_class": "HV"}),  # Sungrow SH RS
    (r"\bSH\d+(\.\d+)?RT|\bSH\d+T\b", {"phases": 3, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"\bSG\d+(\.\d+)?RS", {"phases": 1, "hybrid": False}),
    (r"\bSG\d+(\.\d+)?RT|\bSG\d+(CX|HX)", {"phases": 3, "hybrid": False}),
    (r"\bGW\d+K?-(MT|HT|DT|SDT|SMT)|\bGW\d+KN?-MT", {"phases": 3, "hybrid": False}),
    (r"\bGW\d+K-ET|\bET\b", {"phases": 3, "hybrid": True, "battery_voltage_class": "HV"}),
    (r"\bGW\d+K-ES|\bES\b", {"phases": 1, "hybrid": True, "battery_voltage_class": "LV"}),
    (r"\bDNS\b", {"phases": 1, "hybrid": False}),
    (r"SNA\b|SNA2\b", {"phases": 1, "hybrid": True, "battery_voltage_class": "LV"}),  # Luxpower SNA
    (r"TriP2|TRIP", {"phases": 3, "hybrid": True, "battery_voltage_class": "LV"}),
]


def model_hints(name: str, models: list[str]) -> dict[str, Any]:
    hay = " ".join([_normalise_models_text(name)] + models)
    for rx, hints in _MODEL_HINTS:
        if re.search(rx, hay, re.I):
            return dict(hints)
    return {}


def title_kw(title: str) -> list[float]:
    """kW values mentioned in a product title ('10K', '10 KW', '(12/14/16) K03')."""
    t = clean_name(title)
    vals: list[float] = []
    for m in re.finditer(r"\((\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)*)\)\s*K", t, re.I):
        vals += [float(x.replace(",", ".")) for x in re.split(r"\s*/\s*", m.group(1))]
    for m in re.finditer(r"(?<![A-Za-z0-9.])(\d{1,3}(?:[.,]\d)?)\s*K(?:W|VA)?(?![A-Za-z0-9])", t, re.I):
        vals.append(float(m.group(1).replace(",", ".")))
    for m in re.finditer(r"SUN-(\d{1,3}(?:/\d{1,3})*)K", t, re.I):
        vals += [float(x) for x in m.group(1).split("/")]
    for m in re.finditer(r"\b(?:SG|SH)\s?(\d{1,3}(?:\.\d)?)\s?R?[ST]", t, re.I):
        vals.append(float(m.group(1)))
    out: list[float] = []
    for v in vals:
        if 0.5 <= v <= 400 and v not in out:
            out.append(v)
    return out


def title_wp(title: str) -> list[int]:
    t = clean_name(title)
    rng = re.search(r"(\d{3})\s*[~–\-]\s*(\d{3})\s*W", t, re.I)
    if rng:
        return []  # range → import every class of the datasheet
    return [int(m.group(1)) for m in re.finditer(r"(?<!\d)(\d{3})\s*W(?:p|att)?(?![A-Za-z0-9])", t, re.I) if 100 <= int(m.group(1)) <= 800]


def title_kwh(title: str) -> float | None:
    m = re.search(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*k?Wh", clean_name(title), re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v / 1000 if "kwh" not in m.group(0).lower() and v > 100 else v


# ----------------------------------------------------------------------------- building catalog items
def _pick_column(cols: list[dict[str, Any]], key: str, target: float | None, tol: float = 0.16) -> dict[str, Any] | None:
    if not cols:
        return None
    if target is None:
        return cols[0]
    best, best_err = None, 1e9
    for c in cols:
        v = c.get(key)
        if v is None:
            continue
        err = abs(float(v) - target) / max(target, 1e-6)
        if err < best_err:
            best, best_err = c, err
    return best if best is not None and best_err <= tol else None


def _merge(base: dict[str, Any], *overrides: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for o in overrides:
        for k, v in (o or {}).items():
            if v is None or v == "" or v == []:
                continue
            out[k] = v
    return out


def build_items(
    products: list[dict[str, Any]],
    datasheet_text: Callable[[str], str] | None = None,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Turn Store API products into gmsun catalog item dicts (same shape as ``seed.CATALOG``)."""
    log = log or (lambda s: None)
    items: list[dict[str, Any]] = []
    text_cache: dict[str, str] = {}

    def ds_text(url: str) -> str:
        if url not in text_cache:
            text_cache[url] = (datasheet_text(url) if datasheet_text else "") or ""
        return text_cache[url]

    for p in products:
        name = clean_name(p.get("name", ""))
        if not name:
            continue
        category = gmsun_category(p)
        brand = brand_of(name, p.get("categories", []))
        price_bgn, eur = price_eur(p)
        urls = datasheet_urls(p)
        desc = strip_html((p.get("description") or "") + "\n" + (p.get("short_description") or ""))
        image = (p.get("images") or [{}])[0].get("src")
        base_specs: dict[str, Any] = {
            "supplier": SUPPLIER,
            "supplier_product_id": p.get("id"),
            "product_url": p.get("permalink"),
            "datasheet_url": urls[0] if urls else None,
            "datasheet_urls": urls if len(urls) > 1 else None,
            "image_url": image,
            "price_bgn": price_bgn or None,
            "price_source": f"{SUPPLIER} (листова цена)" if eur else None,
            "tags": [t.get("name") for t in p.get("tags") or []] or None,
            "specs_verified": False,
        }
        base_specs = {k: v for k, v in base_specs.items() if v is not None}
        common = {
            "category": category, "manufacturer": brand, "purchase_price": eur, "currency": "EUR",
            "description": desc[:800] if desc else None, "warranty": None, "active": True,
        }
        bg = dp.parse_bg_description(category, desc) if category in ("panel", "inverter", "battery") else {}
        if bg.get("warranty_text"):
            common["warranty"] = bg.pop("warranty_text")
        ds = ds_text(urls[0]) if urls else ""
        cols = dp.parse_by_category(category, ds, expand_models(name)) if ds else []
        ocr_like = ds.lstrip().upper().startswith("[OCR]")
        spec_source = "datasheet-ocr" if ocr_like else ("datasheet-auto" if cols else ("product-page" if bg else "supplier-listing"))

        if category == "panel":
            wanted = title_wp(name)
            classes = cols or ([{"wp": wanted[0]}] if wanted else [])
            if wanted:
                classes = [c for c in cols if int(c.get("wp", 0)) in wanted] or [_merge(cols[0], {"wp": wanted[0]}) if cols else {"wp": wanted[0]}]
            if not classes:
                classes = [{}]
            for c in classes:
                sp = _merge(base_specs, c, bg, {"spec_source": spec_source})
                sp.pop("parsed_fields", None)
                wp = int(sp.get("wp") or 0)
                model = sp.get("model") or _model_from_title(name)
                label = f"{brand or ''} {model or name} {wp} Wp".strip() if wp else name
                if model and model.lower() in label.lower() and len(classes) == 1 and not wp:
                    label = name
                items.append(_merge(common, {"name": _dedupe_words(label), "sku": model, "specs": sp, "unit": "бр."}))
        elif category == "inverter":
            models = expand_models(name)
            kws = title_kw(name)
            hints = model_hints(name, models)
            variants: list[tuple[str | None, float | None]] = []
            if models:
                for i, m in enumerate(models):
                    kw = dp.model_kw(m)
                    if kw is None or (len(kws) == 1 and abs(kw - kws[0]) / kws[0] > 0.3 and len(models) == 1):
                        kw = kws[i] if len(kws) == len(models) else (kws[0] if len(kws) == 1 else kw)
                    variants.append((m, kw))
            elif kws:
                variants = [(None, k) for k in kws]
            else:
                variants = [(None, None)]
            for i, (model, kw) in enumerate(variants):
                col = _pick_column(cols, "ac_power_kw", kw) or (cols[i] if len(cols) == len(variants) else None) or (cols[0] if len(cols) == 1 else {})
                sp = _merge(base_specs, col or {}, bg, {"spec_source": spec_source})
                sp.pop("parsed_fields", None)
                if kw:
                    sp["ac_power_kw"] = kw
                ac = sp.get("ac_power_kw") or 0
                # title words beat datasheet guesses; model-code hints beat both
                if re.search(r"[TТ]рифаз|three[- ]phase|\b3P\b", name, re.I):
                    sp["phases"] = 3
                elif re.search(r"[MМ]онофаз|еднофаз|single[- ]phase|\b1P\b", name, re.I):
                    sp["phases"] = 1
                if re.search(r"хибрид|hybrid", name, re.I):
                    sp["hybrid"] = True
                elif re.search(r"мрежов|on-grid|grid[- ]tie", name, re.I):
                    sp["hybrid"] = False
                for k, v in hints.items():
                    if k == "battery_voltage_class" and not v:
                        continue
                    sp[k] = v
                if ac >= 15 and not sp.get("phases"):
                    sp["phases"] = 3
                sp.setdefault("phases", 3)
                sp["hybrid"] = bool(sp.get("hybrid"))
                if not sp["hybrid"]:
                    sp.pop("battery_voltage_class", None)
                elif not sp.get("battery_voltage_class"):
                    bv = sp.get("battery_v_max")
                    sp["battery_voltage_class"] = "LV" if bv and bv <= 120 else ("HV" if bv else None)
                # plausibility of auto-parsed numbers (OCR / wrong row)
                if ac:
                    pv = sp.get("max_pv_kw")
                    if pv is not None and not (0.8 * ac <= pv <= 3 * ac):
                        sp.pop("max_pv_kw", None)
                if (sp.get("max_dc_voltage") or 0) < 100:
                    sp.pop("max_dc_voltage", None)
                if sp.get("mppt_v_max") and sp.get("max_dc_voltage") and sp["mppt_v_max"] > sp["max_dc_voltage"]:
                    sp.pop("mppt_v_max", None)
                sp.setdefault("mppt_count", 2)
                sp.setdefault("strings_per_mppt", 1)
                if len(variants) == 1:
                    label = name
                elif model:
                    label = f"{_title_prefix(name)} {model}".strip()
                else:
                    label = f"{_title_prefix(name)} {kw:g} kW"
                items.append(_merge(common, {"name": _dedupe_words(label), "sku": model, "specs": sp, "unit": "бр."}))
        elif category == "battery":
            kwh = title_kwh(name)
            col = _pick_column(cols, "kwh", kwh, tol=0.12) or (cols[0] if len(cols) == 1 else {})
            sp = _merge(base_specs, col or {}, bg, {"spec_source": spec_source})
            sp.pop("parsed_fields", None)
            if kwh and (not sp.get("kwh") or abs(sp["kwh"] - kwh) / kwh > 0.12):
                sp["kwh"] = kwh  # the title is the most reliable statement of the capacity class sold
            _sanitize_battery(sp, name)
            items.append(_merge(common, {"name": name, "sku": sp.get("model") or _model_from_title(name), "specs": sp, "unit": "бр."}))
        else:
            sp = _merge(base_specs, {"spec_source": "supplier-listing"})
            unit = "м" if category == "solar_cable" and re.search(r"\bм\b|метър|ролка", desc, re.I) else "бр."
            if category == "solar_cable":
                m = re.search(r"(\d+(?:[.,]\d)?)\s*(mm2|мм2|mm²|мм²|кв\.? ?мм)", name + " " + desc, re.I)
                if m:
                    sp["cross_section_mm2"] = float(m.group(1).replace(",", "."))
                sp["role"] = "solar_cable"
            if category == "monitoring":
                sp["role"] = "smart_meter" if re.search(r"метър|meter|SDM|DTSU|DDSU", name, re.I) else "dongle"
            items.append(_merge(common, {"name": name, "sku": _model_from_title(name), "specs": sp, "unit": unit}))
        log(f"{category:9s} {name[:60]:60s} cols={len(cols)} bg={len(bg)} price={eur}")
    return items


def _sanitize_battery(sp: dict[str, Any], name: str) -> None:
    """Drop auto-parsed numbers that contradict each other (OCR / wrong table row)."""
    kwh = sp.get("kwh")
    nv = sp.get("nominal_v")
    if nv is not None and not (36 <= nv <= 1500):
        sp.pop("nominal_v", None)
        sp.pop("voltage_class", None)  # class was derived from a bogus voltage (cell voltage, OCR)
        nv = None
    if re.search(r"LUNA2000|\bHV\b|high[- ]volt|високоволт", name, re.I):
        sp["voltage_class"] = "HV"
    if not sp.get("voltage_class"):
        if nv:
            sp["voltage_class"] = "LV" if nv <= 120 else "HV"
        elif re.search(r"\bLV\b|51[.,]2\s*V|48\s*V|low[- ]volt|низко", name, re.I):
            sp["voltage_class"] = "LV"
        elif re.search(r"\bHV\b|high[- ]volt|високо|tower|stack|BESS|kWh\)|контейнер", name, re.I):
            sp["voltage_class"] = "HV"
        else:
            sp["voltage_class"] = "LV"
    if sp["voltage_class"] == "LV" and not nv:
        sp["nominal_v"] = 51.2
        nv = 51.2
    if kwh:
        u = sp.get("usable_kwh")
        if u is not None and not (0.5 * kwh <= u <= kwh * 1.001):
            sp.pop("usable_kwh", None)
        ah = sp.get("ah")
        if nv and ah is not None and abs(ah * nv / 1000 - kwh) / kwh > 0.2:
            sp.pop("ah", None)
        if nv and not sp.get("ah") and sp["voltage_class"] == "LV":
            sp["ah"] = round(kwh * 1000 / nv)
        ca = sp.get("max_charge_a")
        if ca is not None and sp.get("ah") and ca > 2 * sp["ah"]:
            sp.pop("max_charge_a", None)
    if sp.get("cycles") and not (1000 <= sp["cycles"] <= 15000):
        sp.pop("cycles", None)
    if sp.get("max_parallel") and sp["max_parallel"] > 32:
        sp.pop("max_parallel", None)


def _model_from_title(name: str) -> str | None:
    ms = expand_models(name)
    return ms[0] if len(ms) == 1 else None


def _title_prefix(name: str) -> str:
    """'Хибриден трифазен инвертор Deye SUN-14/15/16/18/20K-SG05LP3-EU-SM2' → 'Хибриден трифазен инвертор Deye'."""
    words = clean_name(name).split()
    out = []
    for w in words:
        if re.search(r"\d", w) and (re.search(r"[A-Za-z]", w) or "/" in w) and len(out) >= 1:
            break
        out.append(w)
    return " ".join(out)


def _dedupe_words(s: str) -> str:
    seen: set[str] = set()
    out = []
    for w in s.split():
        k = w.lower()
        if k in seen and re.search(r"[A-Za-z]", w) and len(w) > 3:
            continue
        seen.add(k)
        out.append(w)
    return " ".join(out)


# ----------------------------------------------------------------------------- network
def fetch_products(client: httpx.Client | None = None, per_page: int = 100) -> list[dict[str, Any]]:
    own = client is None
    client = client or httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        out: list[dict[str, Any]] = []
        page = 1
        while True:
            r = client.get(f"{STORE_API}/products", params={"per_page": per_page, "page": page})
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            out.extend(batch)
            total_pages = int(r.headers.get("X-WP-TotalPages") or 0)
            if total_pages and page >= total_pages:
                break
            page += 1
            if page > 50:
                break
        return out
    finally:
        if own:
            client.close()


def datasheet_cache_dir(data_dir: str | os.PathLike[str]) -> Path:
    d = Path(data_dir) / "datasheets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cached_datasheet(url: str, data_dir: str | os.PathLike[str], client: httpx.Client | None = None, download: bool = True) -> Path | None:
    """Return the local PDF path for a datasheet URL, downloading it into DATA_DIR/datasheets on first use."""
    d = datasheet_cache_dir(data_dir)
    fn = d / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf")
    if fn.exists() and fn.stat().st_size > 1000:
        return fn
    if not download:
        return None
    own = client is None
    client = client or httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        r = client.get(url)
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None
        fn.write_bytes(r.content)
        return fn
    except httpx.HTTPError:
        return None
    finally:
        if own:
            client.close()


def datasheet_text_provider(data_dir: str | os.PathLike[str], client: httpx.Client | None = None) -> Callable[[str], str]:
    """Build a `url -> text` function backed by the datasheet cache (pdftotext; cached .txt next to the PDF)."""

    def provider(url: str) -> str:
        pdf = cached_datasheet(url, data_dir, client)
        if not pdf:
            return ""
        txt = pdf.with_suffix(".txt")
        if txt.exists():
            return txt.read_text("utf-8", errors="ignore")
        text = dp.pdf_to_text(str(pdf))
        txt.write_text(text, "utf-8")
        return text

    return provider


def load_seed_items() -> list[dict[str, Any]]:
    """Offline snapshot shipped with the app (generated by ``--write-seed``)."""
    if not SEED_FILE.exists():
        return []
    data = json.loads(SEED_FILE.read_text("utf-8"))
    return data.get("items", []) if isinstance(data, dict) else data


# ----------------------------------------------------------------------------- DB upsert
def upsert_items(db: Any, items: list[dict[str, Any]], *, overwrite_prices: bool = True, overwrite_specs: bool = False) -> dict[str, int]:
    """Insert new supplier items; refresh prices / links on existing ones (matched by supplier product id + name).

    Specs are only overwritten when ``overwrite_specs`` is set and the stored item has not been verified by the user
    (``specs_verified`` false), so engineer corrections are never lost.
    """
    from ..models import CatalogItem  # local import – keep this module importable without the DB

    existing = db.query(CatalogItem).all()
    by_name = {c.name: c for c in existing}
    by_sid: dict[tuple[Any, str], CatalogItem] = {}
    by_sku: dict[tuple[str, str], CatalogItem] = {}
    for c in existing:
        sid = (c.specs or {}).get("supplier_product_id")
        if sid is not None:
            by_sid[(sid, c.name)] = c
        if c.sku and c.category in ("panel", "inverter", "battery"):
            by_sku.setdefault((c.category, c.sku.upper()), c)
    stats = {"created": 0, "updated": 0, "skipped": 0}
    for it in items:
        sp = it.get("specs") or {}
        key = (sp.get("supplier_product_id"), it["name"])
        row = by_sid.get(key) or by_name.get(it["name"])
        if row is None and it.get("sku") and it["category"] in ("panel", "inverter", "battery"):
            row = by_sku.get((it["category"], str(it["sku"]).upper()))
        if row is None:
            row = CatalogItem(
                category=it["category"], name=it["name"], sku=it.get("sku"), manufacturer=it.get("manufacturer"),
                description=it.get("description"), unit=it.get("unit") or "бр.", purchase_price=float(it.get("purchase_price") or 0),
                currency=it.get("currency") or "EUR", warranty=it.get("warranty"), active=True, specs=sp,
            )
            db.add(row)
            by_name[it["name"]] = row
            if row.sku and row.category in ("panel", "inverter", "battery"):
                by_sku.setdefault((row.category, row.sku.upper()), row)
            stats["created"] += 1
            continue
        changed = False
        cur = dict(row.specs or {})
        for k in ("product_url", "datasheet_url", "datasheet_urls", "image_url", "supplier", "supplier_product_id", "tags", "price_bgn"):
            if sp.get(k) is not None and cur.get(k) != sp.get(k):
                cur[k] = sp[k]
                changed = True
        if overwrite_prices and it.get("purchase_price") and float(row.purchase_price or 0) != float(it["purchase_price"]):
            row.purchase_price = float(it["purchase_price"])
            cur["price_source"] = sp.get("price_source")
            changed = True
        if overwrite_specs and not cur.get("specs_verified"):
            merged = _merge(cur, {k: v for k, v in sp.items() if k != "specs_verified"})
            if merged != cur:
                cur = merged
                changed = True
        if changed:
            row.specs = cur
            stats["updated"] += 1
        else:
            stats["skipped"] += 1
    db.commit()
    return stats


def sync_from_site(db: Any, data_dir: str | os.PathLike[str], *, parse_datasheets: bool = True, overwrite_specs: bool = False, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    client = httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    try:
        products = fetch_products(client)
        provider = datasheet_text_provider(data_dir, client) if parse_datasheets else None
        items = build_items(products, provider, log)
        stats = upsert_items(db, items, overwrite_specs=overwrite_specs)
        stats.update({"products": len(products), "items": len(items)})
        return stats
    finally:
        client.close()


# ----------------------------------------------------------------------------- CLI
def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="green-energy.bg portfolio importer")
    ap.add_argument("--products-json", help="use a saved Store API dump instead of fetching")
    ap.add_argument("--text-dir", help="directory with <sha1(url)[:16]>.txt datasheet texts (offline)")
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR", tempfile.gettempdir()))
    ap.add_argument("--write-seed", action="store_true", help=f"write {SEED_FILE}")
    ap.add_argument("--out", help="write items JSON to this path")
    a = ap.parse_args(argv)
    if a.products_json:
        products = json.loads(Path(a.products_json).read_text("utf-8"))
    else:
        products = fetch_products()
    if a.text_dir:
        tdir = Path(a.text_dir)

        def provider(url: str) -> str:
            f = tdir / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".txt")
            return f.read_text("utf-8", errors="ignore") if f.exists() else ""
    else:
        provider = datasheet_text_provider(a.data_dir)
    items = build_items(products, provider, lambda s: print(s, file=sys.stderr))
    payload = {"source": SUPPLIER, "store_api": STORE_API, "products": len(products), "items": items}
    if a.write_seed:
        SEED_FILE.parent.mkdir(parents=True, exist_ok=True)
        SEED_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
        print(f"wrote {SEED_FILE} ({len(items)} items)")
    if a.out:
        Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
