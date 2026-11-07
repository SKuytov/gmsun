from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users & settings
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")  # admin | user
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Key/value JSON settings (company, pricing defaults, quote texts)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
CATEGORIES = [
    "panel",
    "inverter",
    "battery",
    "battery_accessory",
    "switchboard",
    "solar_cable",
    "power_cable",
    "mounting",
    "electrical",
    "dc_protection",
    "ac_protection",
    "grounding",
    "cable_management",
    "monitoring",
    "accessory",
    "service",
    "transport",
    "other",
]


TIERS = ("economy", "standard", "premium")


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(16), default="бр.")
    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    markup_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # None -> use default
    sell_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # explicit override
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    warranty: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    specs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # procurement
    supplier: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)  # who we order it from
    supplier_sku: Mapped[str | None] = mapped_column(String(64), nullable=True)  # code in the supplier's system
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None -> supplier default
    tier: Mapped[str | None] = mapped_column(String(16), nullable=True)  # economy | standard | premium | None=auto
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def price_for(self, default_markup_pct: float) -> float:
        if self.sell_price is not None:
            return round(float(self.sell_price), 2)
        m = self.markup_pct if self.markup_pct is not None else default_markup_pct
        return round(float(self.purchase_price) * (1 + m / 100.0), 2)


class LaborOption(Base):
    __tablename__ = "labor_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    days: Mapped[int] = mapped_column(Integer)
    workers: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class RoofTypeConfig(Base):
    """Per-roof-type construction parameters and pricing mode."""

    __tablename__ = "roof_types"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    label_bg: Mapped[str] = mapped_column(String(128))
    label_en: Mapped[str] = mapped_column(String(128))
    pricing_mode: Mapped[str] = mapped_column(String(16), default="detailed")  # detailed | lump
    lump_price_per_module: Mapped[float] = mapped_column(Float, default=0.0)
    rails_per_module: Mapped[int] = mapped_column(Integer, default=2)
    rail_stock_length_m: Mapped[float] = mapped_column(Float, default=3.55)
    fixation_spacing_m: Mapped[float] = mapped_column(Float, default=1.2)
    waste_pct: Mapped[float] = mapped_column(Float, default=8.0)
    default_tilt_deg: Mapped[float] = mapped_column(Float, default=20.0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


MOUNTING_BASES = [
    "per_module",
    "per_line",  # per rail line (continuous rail run)
    "per_rail",  # per stock rail piece
    "per_rail_meter",
    "per_fixation",
    "per_string",
    "per_kwp",
    "per_project",
    "per_mid_clamp",
    "per_end_clamp",
    "per_connector",
    "per_clamp",  # mid + end clamp positions (support points along the module long sides)
]


class MountingRule(Base):
    """Rule: how many pieces of a catalog item per unit basis for a roof type."""

    __tablename__ = "mounting_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    roof_type: Mapped[str] = mapped_column(String(32), ForeignKey("roof_types.code"), index=True)
    catalog_item_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    basis: Mapped[str] = mapped_column(String(32))
    factor: Mapped[float] = mapped_column(Float, default=1.0)
    round_up: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    item: Mapped[CatalogItem | None] = relationship()


# ---------------------------------------------------------------------------
# Projects, layouts, quotes
# ---------------------------------------------------------------------------
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|quoted|won|lost|archived

    client_name: Mapped[str] = mapped_column(String(255), default="")
    client_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_eik: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_vat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    site_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    site_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    site_lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    purpose: Mapped[str] = mapped_column(String(32), default="self")  # self|self_sell|sell
    phase: Mapped[int] = mapped_column(Integer, default=3)  # 1 | 3
    connected_power_kw: Mapped[float] = mapped_column(Float, default=0.0)
    roof_type: Mapped[str] = mapped_column(String(32), default="tile")
    voltage_class: Mapped[str] = mapped_column(String(4), default="LV")  # LV | HV
    desired_storage_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    annual_consumption_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    layouts: Mapped[list[Layout]] = relationship(back_populates="project", cascade="all, delete-orphan")
    quotes: Mapped[list[Quote]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Layout(Base):
    """A roof/land surface with a photo, rectification data and panel placement."""

    __tablename__ = "layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="Покрив 1")
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    render_path: Mapped[str | None] = mapped_column(String(255), nullable=True)  # PNG of the final layout

    # Four image-space corners (px) of the reference rectangle and its real size in metres
    corners: Mapped[list[Any]] = mapped_column(JSON, default=list)
    plane_w_m: Mapped[float] = mapped_column(Float, default=10.0)
    plane_h_m: Mapped[float] = mapped_column(Float, default=6.0)

    roof_polygon: Mapped[list[Any]] = mapped_column(JSON, default=list)  # metres, in plane coords
    obstacles: Mapped[list[Any]] = mapped_column(JSON, default=list)  # list of polygons (metres)

    panel_item_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"), nullable=True)
    orientation: Mapped[str] = mapped_column(String(10), default="portrait")
    gap_x_m: Mapped[float] = mapped_column(Float, default=0.02)
    gap_y_m: Mapped[float] = mapped_column(Float, default=0.02)
    setback_m: Mapped[float] = mapped_column(Float, default=0.3)
    row_spacing_m: Mapped[float] = mapped_column(Float, default=0.0)  # ground mount rows
    azimuth_deg: Mapped[float] = mapped_column(Float, default=180.0)
    tilt_deg: Mapped[float] = mapped_column(Float, default=20.0)

    panels: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [{x,y,w,h,enabled}]
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {count, kwp, lines:[...]}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="layouts")


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_quote_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    number: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|sent|accepted|rejected
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Selections used by the pricing engine (see services/pricing.py)
    selections: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    vat_pct: Mapped[float] = mapped_column(Float, default=20.0)
    markup_pct: Mapped[float] = mapped_column(Float, default=0.0)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    advance_pct: Mapped[float] = mapped_column(Float, default=70.0)
    execution_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    valid_days: Mapped[int] = mapped_column(Integer, default=10)

    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0.0)
    net_total: Mapped[float] = mapped_column(Float, default=0.0)
    vat_amount: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    advance_amount: Mapped[float] = mapped_column(Float, default=0.0)
    balance_amount: Mapped[float] = mapped_column(Float, default=0.0)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    project: Mapped[Project] = relationship(back_populates="quotes")
    lines: Mapped[list[QuoteLine]] = relationship(
        back_populates="quote", cascade="all, delete-orphan", order_by="QuoteLine.position"
    )


class QuoteLine(Base):
    __tablename__ = "quote_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))  # stable key for auto-generated lines
    section: Mapped[str] = mapped_column(String(32))  # modules|inverter|construction|electrical|labor|other
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(16), default="бр.")
    qty: Mapped[float] = mapped_column(Float, default=1.0)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    purchase_price: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    catalog_item_id: Mapped[int | None] = mapped_column(ForeignKey("catalog_items.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="auto")  # auto | manual
    locked: Mapped[bool] = mapped_column(Boolean, default=False)  # user override, keep on recalc
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)  # excluded from quote
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    quote: Mapped[Quote] = relationship(back_populates="lines")
    catalog_item: Mapped[CatalogItem | None] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
