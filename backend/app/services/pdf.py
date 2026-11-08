from __future__ import annotations

import base64
import mimetypes
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Quote, RoofTypeConfig
from .pricing import SECTIONS, estimate_yield
from .settings import get_setting

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
PURPOSE = {"self": "За собствени нужди", "self_sell": "За собствени нужди и продажба на излишъка", "sell": "Само за продажба на електроенергия"}


def _money(v: float | None) -> str:
    v = float(v or 0)
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return s


def _num(v: float | None) -> str:
    v = float(v or 0)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _thousands(v: int) -> str:
    return f"{int(v):,}".replace(",", " ")


def _data_uri(path: Path) -> str | None:
    if not path or not path.exists():
        return None
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def render_quote_html(db: Session, quote: Quote, mode: str = "client") -> str:
    settings = get_settings()
    company = get_setting(db, "company")
    pricing = get_setting(db, "pricing")
    texts = get_setting(db, "texts")
    project = quote.project
    info = (quote.selections or {}).get("_info", {})
    show_unit = mode == "internal" or bool(pricing.get("show_unit_prices_client", False))

    roof = db.get(RoofTypeConfig, project.roof_type)
    internal = mode == "internal"
    collapse = mode == "client" and bool(pricing.get("client_pdf_collapse_construction", True))
    sections = []
    idx = 0
    for code, title_bg, _ in SECTIONS:
        lns = [l for l in quote.lines if l.section == code and not l.hidden]
        if not lns:
            continue
        total = sum(l.total for l in lns)
        cost = sum(float(l.purchase_price or 0) * float(l.qty or 0) for l in lns)
        rows = [_line_view(l) for l in lns]
        if code == "construction" and collapse and len(lns) > 1:
            roof_name = roof_short(roof, project)
            rows = [SimpleNamespace(name=f"Монтажна система Aerocompact за {roof_name[0].lower() + roof_name[1:]} — алуминиеви профили, скоби и крепежни елементи, комплект", unit="компл.", qty=1, unit_price=total, total=total, cost=cost, lead=None, supplier=None, sku=None)]
            title_bg = "Монтажна конструкция"
        sections.append({"roman": ROMAN[idx], "title": title_bg, "total": total, "cost": cost, "lines": rows})
        idx += 1
    cost_total = sum(s["cost"] for s in sections)
    margin = float(quote.net_total or 0) - cost_total
    margin_pct = (margin / float(quote.net_total) * 100) if quote.net_total else 0.0
    sup_days: dict[str, int] = {}
    for l in quote.lines:
        if l.hidden:
            continue
        m = l.meta or {}
        if m.get("supplier"):
            sup_days[m["supplier"]] = max(sup_days.get(m["supplier"], 0), int(m.get("lead_time_days") or 0))
    suppliers = sorted(sup_days.items(), key=lambda kv: -kv[1])

    logo_uri = None
    if company.get("logo_path"):
        logo_uri = _data_uri(settings.data_dir / company["logo_path"])
    layout_images = []
    visual_images = []  # photorealistic overlays on the client's own photos
    tilt, az = 20.0, 180.0
    for lay in project.layouts:
        if lay.render_path:
            uri = _data_uri(settings.data_dir / lay.render_path)
            if uri:
                layout_images.append(uri)
        if getattr(lay, "visual_path", None):
            uri = _data_uri(settings.data_dir / lay.visual_path)
            if uri:
                visual_images.append({"uri": uri, "name": lay.name})
        tilt, az = lay.tilt_deg, lay.azimuth_deg
    r3 = ((project.params or {}).get("visual") or {}).get("render3d_path")
    render3d = _data_uri(settings.data_dir / r3) if r3 else None
    kwp = float(info.get("kwp") or 0)
    annual_yield = estimate_yield(kwp, float(pricing.get("specific_yield_kwh_per_kwp", 1250)), az, tilt)
    solution = _solution_rows(db, quote, info, roof, annual_yield, project)
    created = quote.created_at.date() if quote.created_at else date.today()

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["money"] = _money
    env.filters["num"] = _num
    env.filters["thousands"] = _thousands
    tpl = env.get_template("quote.html")
    title = quote.title or _default_title(info, project)
    return tpl.render(
        company=company,
        texts=texts,
        quote=quote,
        visual_images=visual_images,
        render3d=render3d,
        project=project,
        info=info,
        sections=sections,
        show_unit_prices=show_unit,
        logo_uri=logo_uri,
        layout_images=layout_images,
        date_str=created.strftime("%d.%m.%Y г."),
        valid_until=(created + timedelta(days=quote.valid_days or 10)).strftime("%d.%m.%Y"),
        purpose_label=PURPOSE.get(project.purpose, project.purpose),
        roof_label=roof_short(roof, project),
        title=title,
        annual_yield=annual_yield,
        specific_yield=pricing.get("specific_yield_kwh_per_kwp", 1250),
        advance_basis=(quote.selections or {}).get("advance_basis", "net"),
        internal=internal,
        doc_kind="вътрешна калкулация" if internal else "оферта",
        solution=solution,
        cost_total=cost_total,
        margin=margin,
        margin_pct=margin_pct,
        suppliers=suppliers,
    )


def roof_short(roof, project) -> str:
    """Short roof label: 'LT ламарина — CompactMETAL TL25/TL38 ...' -> 'LT ламарина'."""
    lab = roof.label_bg if roof else str(project.roof_type)
    return lab.split(" — ")[0].split(" (")[0].strip()


def _line_view(l) -> SimpleNamespace:
    m = l.meta or {}
    return SimpleNamespace(
        name=l.name, unit=l.unit, qty=l.qty, unit_price=l.unit_price, total=l.total,
        cost=float(l.purchase_price or 0) * float(l.qty or 0),
        lead=m.get("lead_time_days"), supplier=m.get("supplier"), sku=m.get("supplier_sku"),
    )


def _fmt_specs(it, keys: list[tuple[str, str, str]]) -> str:
    sp = it.specs or {}
    parts = []
    for key, label, unit in keys:
        v = sp.get(key)
        if v in (None, "", 0):
            continue
        parts.append(f"{label} {_num(v) if isinstance(v, (int, float)) else v}{unit}")
    return " · ".join(parts)


def _solution_rows(db: Session, quote: Quote, info: dict, roof, annual_yield: float, project) -> list[dict]:
    """Human-readable summary of the offered system for page one of the quote."""
    from ..models import CatalogItem

    sel = quote.selections or {}
    rows: list[dict] = []

    def item(iid):
        return db.get(CatalogItem, int(iid)) if iid else None

    def label(it) -> str:
        man = (it.manufacturer or "").strip()
        if man and not it.name.lower().startswith(man.lower()):
            return f"{man} {it.name}"
        return it.name

    panel = item(sel.get("panel_item_id"))
    qty = int(info.get("panel_qty") or 0)
    if panel:
        wp = (panel.specs or {}).get("wp")
        rows.append({"k": "Фотоволтаични модули", "v": f"{qty} × {label(panel)}",
                     "sub": _fmt_specs(panel, [("wp", "", " Wp"), ("efficiency", "КПД", " %"), ("bifaciality", "бифациалност", " %")]) + (f" · гаранция {panel.warranty}" if panel.warranty else "")})
    inv = item(sel.get("inverter_item_id"))
    if inv:
        iq = int(sel.get("inverter_qty") or 1)
        sp = inv.specs or {}
        kind = "Хибриден инвертор" if sp.get("hybrid") else "Мрежов инвертор"
        kind = kind + (f" — {iq} бр. в паралел" if iq > 1 else "")
        tot = f"общо {_num(float(sp.get('ac_power_kw') or 0) * iq)} kW AC · " if iq > 1 and sp.get("ac_power_kw") else ""
        rows.append({"k": kind, "v": (f"{iq} × " if iq > 1 else "") + label(inv),
                     "sub": tot + _fmt_specs(inv, [("ac_power_kw", "", " kW AC"), ("phases", "", " фази"), ("mppt_count", "", " MPPT"), ("max_pv_kw", "макс. PV", " kWp")]) + (f" · гаранция {inv.warranty}" if inv.warranty else "")})
    bat = item(sel.get("battery_item_id"))
    bq = int(sel.get("battery_qty") or 0)
    if bat and bq:
        sp = bat.specs or {}
        rows.append({"k": "Батерийно съхранение", "v": f"{bq} × {label(bat)}" + (f" — общо {_num(info.get('storage_kwh'))} kWh" if info.get("storage_kwh") else ""),
                     "sub": _fmt_specs(bat, [("kwh", "", " kWh/модул"), ("chemistry", "", ""), ("cycles", "", " цикъла")]) + (f" · гаранция {bat.warranty}" if bat.warranty else "")})
    else:
        rows.append({"k": "Батерийно съхранение", "v": "Не е включено", "sub": "Възможно е добавяне на по-късен етап при хибриден инвертор." if (inv and (inv.specs or {}).get("hybrid")) else ""})
    ms = info.get("mounting_stats") or {}
    systems = sorted({str((l.catalog_item.specs or {}).get("system")) for l in quote.lines if l.section == "construction" and l.catalog_item and (l.catalog_item.specs or {}).get("system")})
    mount_v = "Aerocompact " + ", ".join(systems) if systems else "Алуминиева модулна конструкция"
    rows.append({"k": "Монтажна система", "v": mount_v,
                 "sub": roof_short(roof, project) + (f" · {ms.get('rows')} реда" if ms.get("rows") else "") + (f" · наклон {_num(ms.get('tilt_deg'))}°" if ms.get("tilt_deg") else "")})
    st = info.get("strings") or {}
    if st.get("strings"):
        n_inv = int(st.get("inverters") or 1)
        if n_inv > 1:
            per = st.get("per_inverter") or []
            lens = sorted({int(x) for p in per for x in [p.get("modules_per_string") or 0] if x})
            mps = f"{lens[0]}–{lens[-1]}" if len(lens) > 1 else (str(lens[0]) if lens else str(st.get("modules_per_string")))
            v = f"{st['strings']} стринга (до {mps} модула) на {n_inv} инвертора × {st.get('mppts') or '—'} MPPT"
            sub = "Инверторите работят в паралел през общо AC табло с главен прекъсвач · DC/AC защити, кабели и заземяване — подробно в спецификацията"
        else:
            v = f"{st['strings']} стринга × {st.get('modules_per_string')} модула на {st.get('mppts') or '—'} MPPT"
            sub = "DC/AC защити, кабели и заземяване — подробно в спецификацията"
        rows.append({"k": "Електрическа част", "v": v, "sub": sub})
    return rows


def _default_title(info: dict, project) -> str:
    kwp = float(info.get("kwp") or 0)
    storage = float(info.get("storage_kwh") or 0)
    where = "наземна" if str(project.roof_type).startswith("ground") else "покривна"
    t = f"Фотоволтаична централа {_num(round(kwp, 2))} kWp, {where}"
    if storage:
        t += f", с батерийно съхранение {_num(storage)} kWh"
    t += " — доставка, монтаж и пускане в експлоатация"
    return t


def render_quote_pdf(db: Session, quote: Quote, mode: str = "client") -> Path:
    from weasyprint import HTML

    settings = get_settings()
    html = render_quote_html(db, quote, mode)
    out = settings.pdf_dir / f"quote_{quote.number}_v{quote.version}_{mode}.pdf"
    HTML(string=html, base_url=str(TEMPLATES)).write_pdf(str(out))
    quote.pdf_path = str(out.relative_to(settings.data_dir))
    db.commit()
    return out
