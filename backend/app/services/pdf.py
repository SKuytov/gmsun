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
    collapse = mode == "client" and bool(pricing.get("client_pdf_collapse_construction", True))
    sections = []
    idx = 0
    for code, title_bg, _ in SECTIONS:
        lns = [l for l in quote.lines if l.section == code and not l.hidden]
        if not lns:
            continue
        total = sum(l.total for l in lns)
        if code == "construction" and collapse and len(lns) > 1:
            roof_name = roof.label_bg.lower() if roof else project.roof_type
            lns = [SimpleNamespace(name=f"Модулна алуминиева конструкция за закрепване на фотоволтаични модули — {roof_name}", unit="компл.", qty=1, unit_price=total, total=total)]
            title_bg = "Част конструкция (алуминиева модулна)"
        sections.append({"roman": ROMAN[idx], "title": title_bg, "total": total, "lines": lns})
        idx += 1

    logo_uri = None
    if company.get("logo_path"):
        logo_uri = _data_uri(settings.data_dir / company["logo_path"])
    layout_images = []
    tilt, az = 20.0, 180.0
    for lay in project.layouts:
        if lay.render_path:
            uri = _data_uri(settings.data_dir / lay.render_path)
            if uri:
                layout_images.append(uri)
        tilt, az = lay.tilt_deg, lay.azimuth_deg
    kwp = float(info.get("kwp") or 0)
    annual_yield = estimate_yield(kwp, float(pricing.get("specific_yield_kwh_per_kwp", 1250)), az, tilt)
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
        project=project,
        info=info,
        sections=sections,
        show_unit_prices=show_unit,
        logo_uri=logo_uri,
        layout_images=layout_images,
        date_str=created.strftime("%d.%m.%Y г."),
        valid_until=(created + timedelta(days=quote.valid_days or 10)).strftime("%d.%m.%Y"),
        purpose_label=PURPOSE.get(project.purpose, project.purpose),
        roof_label=roof.label_bg if roof else project.roof_type,
        title=title,
        annual_yield=annual_yield,
        specific_yield=pricing.get("specific_yield_kwh_per_kwp", 1250),
        advance_basis=(quote.selections or {}).get("advance_basis", "net"),
    )


def _default_title(info: dict, project) -> str:
    kw = float(info.get("kwp") or 0) * 1000
    storage = float(info.get("storage_kwh") or 0)
    t = f"ДОСТАВКА И МОНТАЖ НА ОБОРУДВАНЕ ЗА 1 БРОЙ ФвЕЦ {kw:,.0f} W".replace(",", " ")
    t += ", НА ПОКРИВ НА СЪЩЕСТВУВАЩА СГРАДА" if not str(project.roof_type).startswith("ground") else ", НАЗЕМНА"
    if storage:
        t += f" И БАТЕРИЙНА СИСТЕМА ЗА СЪХРАНЕНИЕ С КАПАЦИТЕТ {storage:g} kWh"
    if project.site_address:
        t += f", {project.site_address}"
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
