"""Technical file ("техническо досие") PDF for a quote.

Contents: project & system summary, string table with the temperature-corrected
voltage checks, single-line diagram (SVG generated here), per-plane layout
drawings with string colouring and the mounting plan (rails / fixation points),
full bill of materials grouped by section with the derivation rules, cable
schedule, equipment datasheet summary and the yield estimate.
"""
from __future__ import annotations

import html
import math
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CatalogItem, Quote, RoofTypeConfig
from ..seed_data.aerocompact import system_for_roof
from .pdf import _data_uri, _money, _num, _thousands
from .pricing import SECTIONS, estimate_yield
from .settings import get_setting

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
STRING_COLORS = ["#f0a500", "#2f80ed", "#27ae60", "#eb5757", "#9b51e0", "#f2994a", "#56ccf2", "#219653", "#bb6bd9", "#828282"]


def _short(name: str, n: int = 30) -> str:
    """Drop the parenthetical part of a catalog name and trim."""
    base = name.split(" (")[0].strip()
    return base if len(base) <= n else base[: n - 1] + "…"


def _esc(s: Any) -> str:
    return html.escape(str(s if s is not None else ""))


# ------------------------------------------------------------------ layout drawing
def layout_svg(lay: Any, strings: list[dict[str, Any]], roof: RoofTypeConfig | None, panel_w_m: float, width_px: int = 720) -> str:
    """Plan view of one plane in metres: roof polygon, obstacles, modules coloured by
    string, rails and fixation points (mounting plan)."""
    panels = [p for p in (lay.panels or []) if p.get("enabled", True)]
    poly = lay.roof_polygon or []
    xs = [float(p["x"]) for p in panels] + [float(p["x"]) + float(p["w"]) for p in panels] + [float(c[0]) for c in poly]
    ys = [float(p["y"]) for p in panels] + [float(p["y"]) + float(p["h"]) for p in panels] + [float(c[1]) for c in poly]
    if not xs:
        return ""
    minx, maxx, miny, maxy = min(xs) - 0.3, max(xs) + 0.3, min(ys) - 0.3, max(ys) + 0.3
    w_m, h_m = maxx - minx, maxy - miny
    scale = width_px / w_m
    height_px = int(h_m * scale) + 24
    tx = lambda x: (x - minx) * scale  # noqa: E731
    ty = lambda y: (y - miny) * scale  # noqa: E731
    out: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" viewBox="0 0 {width_px} {height_px}" font-family="DejaVu Sans, sans-serif">']
    out.append(f'<rect x="0" y="0" width="{width_px}" height="{height_px}" fill="#fafafa"/>')
    if poly:
        pts = " ".join(f"{tx(float(c[0])):.1f},{ty(float(c[1])):.1f}" for c in poly)
        out.append(f'<polygon points="{pts}" fill="#fff" stroke="#999" stroke-width="1.5" stroke-dasharray="6 3"/>')
    for ob in lay.obstacles or []:
        pts = " ".join(f"{tx(float(c[0])):.1f},{ty(float(c[1])):.1f}" for c in ob)
        out.append(f'<polygon points="{pts}" fill="#ffe5e5" stroke="#eb5757" stroke-width="1"/>')
    # string assignment: panels sorted by row then x, filled sequentially with the plane's strings
    ordered = sorted(panels, key=lambda p: (round(float(p["y"]), 2), float(p["x"])))
    plane_strings = [s for s in strings if s.get("plane") == lay.name] or strings
    assign: dict[int, dict[str, Any]] = {}
    i = 0
    for s in plane_strings:
        for _ in range(int(s.get("modules") or 0)):
            if i < len(ordered):
                assign[id(ordered[i])] = s
                i += 1
    # rails (mounting plan)
    rails_pm = roof.rails_per_module if roof else 2
    spacing = roof.fixation_spacing_m if roof else 1.2
    for ln in (lay.summary or {}).get("lines") or []:
        if ln.get("direction", "h") == "h":
            y0 = float(ln.get("y", 0))
            row = [p for p in ordered if abs(float(p["y"]) - y0) < 1e-3]
            if not row:
                continue
            x0 = min(float(p["x"]) for p in row)
            x1 = max(float(p["x"]) + float(p["w"]) for p in row)
            h = float(row[0]["h"])
            for k in range(int(ln.get("rails") or rails_pm)):
                yy = y0 + h * (k + 1) / (int(ln.get("rails") or rails_pm) + 1)
                out.append(f'<line x1="{tx(x0):.1f}" y1="{ty(yy):.1f}" x2="{tx(x1):.1f}" y2="{ty(yy):.1f}" stroke="#555" stroke-width="2"/>')
                n_fix = math.ceil((x1 - x0) / max(spacing, 0.1)) + 1
                for f in range(n_fix):
                    xx = x0 + (x1 - x0) * f / max(n_fix - 1, 1)
                    out.append(f'<circle cx="{tx(xx):.1f}" cy="{ty(yy):.1f}" r="3" fill="#1b1f24"/>')
        else:
            x0 = float(ln.get("x", 0))
            col = [p for p in ordered if abs(float(p["x"]) - x0) < 1e-3]
            if not col:
                continue
            y0 = min(float(p["y"]) for p in col)
            y1 = max(float(p["y"]) + float(p["h"]) for p in col)
            w = float(col[0]["w"])
            for k in range(int(ln.get("rails") or rails_pm)):
                xx = x0 + w * (k + 1) / (int(ln.get("rails") or rails_pm) + 1)
                out.append(f'<line x1="{tx(xx):.1f}" y1="{ty(y0):.1f}" x2="{tx(xx):.1f}" y2="{ty(y1):.1f}" stroke="#555" stroke-width="2"/>')
                n_fix = math.ceil((y1 - y0) / max(spacing, 0.1)) + 1
                for f in range(n_fix):
                    yy = y0 + (y1 - y0) * f / max(n_fix - 1, 1)
                    out.append(f'<circle cx="{tx(xx):.1f}" cy="{ty(yy):.1f}" r="3" fill="#1b1f24"/>')
    for idx, p in enumerate(ordered):
        s = assign.get(id(p))
        color = STRING_COLORS[(int(s["id"][1:]) - 1) % len(STRING_COLORS)] if s else "#cfd8e3"
        x, y, w, h = tx(float(p["x"])), ty(float(p["y"])), float(p["w"]) * scale, float(p["h"]) * scale
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{color}" fill-opacity="0.55" stroke="#1b1f24" stroke-width="0.8"/>')
        fs = max(7, min(11, w / 3))
        out.append(f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + fs / 3:.1f}" font-size="{fs:.0f}" text-anchor="middle" fill="#1b1f24">{idx + 1}</text>')
    # scale bar 1 m
    out.append(f'<line x1="12" y1="{height_px - 10}" x2="{12 + scale:.1f}" y2="{height_px - 10}" stroke="#1b1f24" stroke-width="2"/>')
    out.append(f'<text x="{14 + scale:.1f}" y="{height_px - 7}" font-size="9" fill="#1b1f24">1 m</text>')
    out.append(f'<text x="{width_px - 6}" y="{height_px - 7}" font-size="9" text-anchor="end" fill="#555">{_esc(lay.name)} · азимут {lay.azimuth_deg:g}° · наклон {lay.tilt_deg:g}° · {len(panels)} модула</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------- single line diagram
def sld_svg(design: dict[str, Any], inverter: CatalogItem | None, battery: CatalogItem | None, phase: int) -> str:
    strings = (design.get("strings") or {}).get("strings") or []
    dc, ac, bat = design.get("dc") or {}, design.get("ac") or {}, design.get("battery") or {}
    n = max(len(strings), 1)
    row_h = 44
    top = 30
    h = max(top + n * row_h + 140, 330)
    W = 900
    o: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" font-family="DejaVu Sans, sans-serif" font-size="10">']
    o.append(f'<rect width="{W}" height="{h}" fill="#fff"/>')

    def box(x: float, y: float, w: float, hh: float, title: str, lines: list[str], stroke: str = "#1b1f24") -> None:
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{hh}" rx="4" fill="#f6f7f9" stroke="{stroke}" stroke-width="1.2"/>')
        o.append(f'<text x="{x + w / 2}" y="{y + 14}" text-anchor="middle" font-weight="bold" font-size="10">{_esc(title)}</text>')
        for i, t in enumerate(lines):
            o.append(f'<text x="{x + w / 2}" y="{y + 28 + i * 12}" text-anchor="middle" font-size="8.5" fill="#333">{_esc(t)}</text>')

    def wire(x1: float, y1: float, x2: float, y2: float, color: str = "#1b1f24", dash: str = "") -> None:
        o.append(f'<path d="M{x1},{y1} H{(x1 + x2) / 2} V{y2} H{x2}" fill="none" stroke="{color}" stroke-width="1.6" {f"stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')

    # strings
    x_str = 20
    for i, s in enumerate(strings):
        y = top + i * row_h
        for k in range(min(int(s.get("modules") or 1), 6)):
            o.append(f'<rect x="{x_str + k * 16}" y="{y + 6}" width="12" height="20" fill="{STRING_COLORS[i % len(STRING_COLORS)]}" fill-opacity="0.6" stroke="#1b1f24" stroke-width="0.7"/>')
        o.append(f'<text x="{x_str + 104}" y="{y + 20}" font-size="9">{_esc(s["id"])}: {s["modules"]} мод. · {s.get("vmp_stc_v", 0):g} V · {_esc(dc.get("design_current_a", ""))} A</text>')
    # DC box
    x_box = 330
    inv_y = top + (n * row_h) / 2 - 40
    if dc.get("box"):
        box(x_box, max(top, inv_y), 120, 80, "DC табло", ["SPD T2 1000 V"] + ([f"gPV {(design.get('strings') or {}).get('fuse_a', '')} A"] if dc.get("fuses") or design.get("strings", {}).get("fuses_required") else []) + ["Разединител DC 32 A"])
        for i in range(n):
            wire(x_str + 262, top + i * row_h + 16, x_box, max(top, inv_y) + 40 - (n - 1) * 6 + i * 12, "#c0392b")
        x_next, y_next = x_box + 120, max(top, inv_y) + 40
    else:
        x_next, y_next = None, None
    # inverter
    x_inv = 480
    inv_lines = [_short(inverter.name) if inverter else "—", f"MPPT {dc and (design.get('strings') or {}).get('mppts', '')} · {_esc((inverter.specs or {}).get('max_dc_voltage', '') if inverter else '')} V DC", "вгр. DC прекъсвач + SPD T2" if dc.get("dc_switch_integrated", True) else "", f"{_esc(ac.get('i_max_a', ''))} A AC · {phase} ф."]
    box(x_inv, max(top, inv_y), 165, 90, "Инвертор", [l for l in inv_lines if l])
    if x_next:
        wire(x_next, y_next, x_inv, max(top, inv_y) + 45, "#c0392b")
    else:
        for i in range(n):
            wire(x_str + 262, top + i * row_h + 16, x_inv, max(top, inv_y) + 30 + i * (60 / max(n, 1)), "#c0392b")
    # battery
    if bat:
        by = max(top, inv_y) + 130
        box(x_inv, by, 165, 60, "Батерия", [_short(battery.name) if battery else "", f"{bat.get('qty')} × {_esc((battery.specs or {}).get('kwh', '') if battery else '')} kWh = {bat.get('kwh')} kWh"])
        o.append(f'<rect x="{x_inv + 62}" y="{by - 34}" width="40" height="18" fill="#fff" stroke="#1b1f24"/>')
        o.append(f'<text x="{x_inv + 82}" y="{by - 21}" text-anchor="middle" font-size="7.5">DC {bat.get("breaker_a")} A</text>')
        o.append(f'<line x1="{x_inv + 82}" y1="{max(top, inv_y) + 90}" x2="{x_inv + 82}" y2="{by - 34}" stroke="#1b1f24" stroke-width="1.6"/>')
        o.append(f'<line x1="{x_inv + 82}" y1="{by - 16}" x2="{x_inv + 82}" y2="{by}" stroke="#1b1f24" stroke-width="1.6"/>')
        o.append(f'<text x="{x_inv + 88}" y="{by - 44}" font-size="7.5" fill="#555">{bat.get("cable_mm2")} mm²</text>')
    # AC board
    x_ac = 745
    board_lines = [f"Прекъсвач {ac.get('breaker_poles', '')} {ac.get('breaker_a', '')} A C", f"ДТЗ {ac.get('rcd_a', '')} A / {ac.get('rcd_ma', 300)} mA тип A", f"SPD T2 {'3P+N' if phase == 3 else '1P+N'}", f"PE {_esc((design.get('grounding') or {}).get('pe_mm2', ''))} mm²"]
    box(x_ac, max(top, inv_y), 150, 90, "ГРТ (главно табло)", board_lines, "#2f80ed")
    wire(x_inv + 165, max(top, inv_y) + 45, x_ac, max(top, inv_y) + 45, "#2f80ed")
    o.append(f'<text x="{(x_inv + 165 + x_ac) / 2}" y="{max(top, inv_y) + 36}" text-anchor="middle" font-size="8" fill="#2f80ed">{ac.get("cores", "")}×{_esc(ac.get("cable_mm2", ""))} mm² · {ac.get("cable_m", "")} m</text>')
    # grid + meter
    o.append(f'<circle cx="{x_ac + 80}" cy="{max(top, inv_y) + 125}" r="14" fill="#fff" stroke="#1b1f24" stroke-width="1.2"/>')
    o.append(f'<text x="{x_ac + 80}" y="{max(top, inv_y) + 129}" text-anchor="middle" font-size="9">kWh</text>')
    o.append(f'<line x1="{x_ac + 80}" y1="{max(top, inv_y) + 90}" x2="{x_ac + 80}" y2="{max(top, inv_y) + 111}" stroke="#1b1f24" stroke-width="1.6"/>')
    o.append(f'<line x1="{x_ac + 80}" y1="{max(top, inv_y) + 139}" x2="{x_ac + 80}" y2="{max(top, inv_y) + 160}" stroke="#1b1f24" stroke-width="1.6"/>')
    o.append(f'<text x="{x_ac + 80}" y="{max(top, inv_y) + 174}" text-anchor="middle" font-size="9" font-weight="bold">Мрежа {"3×400 V" if phase == 3 else "230 V"} · {ac.get("metering") == "ct" and "CT ×3" or "смарт електромер"}</text>')
    # earth
    gy = h - 28
    o.append(f'<line x1="{x_inv + 20}" y1="{gy}" x2="{x_ac + 130}" y2="{gy}" stroke="#27ae60" stroke-width="1.6" stroke-dasharray="5 3"/>')
    o.append(f'<text x="{x_inv + 20}" y="{gy - 5}" font-size="8.5" fill="#27ae60">PE / изравняване на потенциалите — конструкция 6 mm², инвертор {_esc((design.get("grounding") or {}).get("pe_mm2", ""))} mm²</text>')
    o.append("</svg>")
    return "".join(o)


# ------------------------------------------------------------------------- render
def render_techfile_html(db: Session, quote: Quote) -> str:
    settings = get_settings()
    company = get_setting(db, "company")
    pricing = get_setting(db, "pricing")
    project = quote.project
    sel = quote.selections or {}
    info = sel.get("_info", {})
    design = info.get("design") or {}
    roof = db.get(RoofTypeConfig, project.roof_type)

    def item(key: str) -> CatalogItem | None:
        v = sel.get(key)
        return db.get(CatalogItem, int(v)) if v else None

    inverter = item("inverter_item_id")
    battery = item("battery_item_id")
    panel = item("panel_item_id") or (db.get(CatalogItem, project.layouts[0].panel_item_id) if project.layouts and project.layouts[0].panel_item_id else None)
    strings = (design.get("strings") or {}).get("strings") or []
    pw = float((panel.specs or {}).get("width_mm", 1134)) / 1000 if panel else 1.134

    planes = []
    for lay in project.layouts:
        if not (lay.summary or {}).get("count"):
            continue
        planes.append(
            {
                "name": lay.name,
                "svg": layout_svg(lay, strings, roof, pw),
                "photo": _data_uri(settings.data_dir / lay.render_path) if lay.render_path else None,
                "summary": lay.summary,
                "azimuth": lay.azimuth_deg,
                "tilt": lay.tilt_deg,
                "strings": [s for s in strings if s.get("plane") == lay.name],
            }
        )
    sections = []
    for code, title_bg, _ in SECTIONS:
        lns = [l for l in quote.lines if l.section == code and not l.hidden]
        if lns:
            sections.append({"code": code, "title": title_bg, "lines": lns})
    # ordering list grouped by manufacturer
    order: dict[str, list[Any]] = {}
    for l in quote.lines:
        if l.hidden or l.section in ("labor", "other") or (l.meta or {}).get("spare") is None and l.catalog_item_id is None and not (l.meta or {}).get("role"):
            continue
        ci = db.get(CatalogItem, l.catalog_item_id) if l.catalog_item_id else None
        order.setdefault((ci.manufacturer if ci and ci.manufacturer else "Други / местна доставка"), []).append({"line": l, "item": ci})
    kwp = float(info.get("kwp") or 0)
    tilt, az = (project.layouts[0].tilt_deg, project.layouts[0].azimuth_deg) if project.layouts else (roof.default_tilt_deg if roof else 20, 180)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["money"] = _money
    env.filters["num"] = _num
    env.filters["thousands"] = _thousands
    tpl = env.get_template("techfile.html")
    return tpl.render(
        company=company,
        quote=quote,
        project=project,
        info=info,
        design=design,
        sd=design.get("strings") or {},
        dc=design.get("dc") or {},
        ac=design.get("ac") or {},
        bat=design.get("battery") or {},
        grd=design.get("grounding") or {},
        mgmt=design.get("management") or {},
        margins=design.get("margins") or {},
        stats=info.get("mounting_stats") or {},
        roof=roof,
        msys=system_for_roof(project.roof_type),
        panel=panel,
        inverter=inverter,
        battery=battery,
        planes=planes,
        sld=sld_svg(design, inverter, battery, project.phase),
        sections=sections,
        order=order,
        logo_uri=_data_uri(settings.data_dir / company["logo_path"]) if company.get("logo_path") else None,
        date_str=date.today().strftime("%d.%m.%Y г."),
        annual_yield=estimate_yield(kwp, float(pricing.get("specific_yield_kwh_per_kwp", 1250)), az, tilt),
        specific_yield=pricing.get("specific_yield_kwh_per_kwp", 1250),
        colors=STRING_COLORS,
    )


def render_techfile_pdf(db: Session, quote: Quote) -> Path:
    from weasyprint import HTML

    settings = get_settings()
    out = settings.pdf_dir / f"techfile_{quote.number}_v{quote.version}.pdf"
    HTML(string=render_techfile_html(db, quote), base_url=str(TEMPLATES)).write_pdf(str(out))
    return out
