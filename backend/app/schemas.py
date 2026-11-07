from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- auth ----------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORMModel):
    id: int
    email: str
    name: str
    role: str
    active: bool


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = ""
    password: str = Field(min_length=6)
    role: str = "user"


class UserUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=6)


# ---------------- settings ----------------
class SettingOut(BaseModel):
    key: str
    value: dict[str, Any]


class SettingIn(BaseModel):
    value: dict[str, Any]


# ---------------- catalog ----------------
class CatalogItemBase(BaseModel):
    category: str
    sku: str | None = None
    name: str
    manufacturer: str | None = None
    description: str | None = None
    unit: str = "бр."
    purchase_price: float = 0.0
    markup_pct: float | None = None
    sell_price: float | None = None
    currency: str = "EUR"
    warranty: str | None = None
    active: bool = True
    specs: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    supplier: str | None = None
    supplier_sku: str | None = None
    lead_time_days: int | None = None
    tier: str | None = None


class CatalogItemCreate(CatalogItemBase):
    pass


class CatalogItemUpdate(BaseModel):
    category: str | None = None
    sku: str | None = None
    name: str | None = None
    manufacturer: str | None = None
    description: str | None = None
    unit: str | None = None
    purchase_price: float | None = None
    markup_pct: float | None = None
    sell_price: float | None = None
    currency: str | None = None
    warranty: str | None = None
    active: bool | None = None
    specs: dict[str, Any] | None = None
    sort_order: int | None = None
    supplier: str | None = None
    supplier_sku: str | None = None
    lead_time_days: int | None = None
    tier: str | None = None


class CatalogItemOut(CatalogItemBase, ORMModel):
    id: int
    effective_price: float = 0.0
    effective_lead_time_days: int | None = None  # item override or supplier default
    effective_tier: str | None = None  # manual tier or automatic classification
    updated_at: datetime | None = None


class LaborOptionIn(BaseModel):
    days: int
    workers: int
    price: float
    description: str | None = None
    active: bool = True


class LaborOptionOut(LaborOptionIn, ORMModel):
    id: int


class RoofTypeIn(BaseModel):
    code: str
    label_bg: str
    label_en: str
    pricing_mode: str = "detailed"
    lump_price_per_module: float = 0.0
    rails_per_module: int = 2
    rail_stock_length_m: float = 3.55
    fixation_spacing_m: float = 1.2
    waste_pct: float = 8.0
    default_tilt_deg: float = 20.0
    notes: str | None = None
    sort_order: int = 0
    active: bool = True


class RoofTypeOut(RoofTypeIn, ORMModel):
    pass


class MountingRuleIn(BaseModel):
    roof_type: str
    catalog_item_id: int | None = None
    name: str
    basis: str
    factor: float = 1.0
    round_up: bool = True
    active: bool = True
    notes: str | None = None
    sort_order: int = 0


class MountingRuleOut(MountingRuleIn, ORMModel):
    id: int


# ---------------- projects ----------------
class ProjectBase(BaseModel):
    name: str
    status: str = "draft"
    client_name: str = ""
    client_company: str | None = None
    client_eik: str | None = None
    client_vat: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    client_address: str | None = None
    site_address: str | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    purpose: str = "self"
    phase: int = 3
    connected_power_kw: float = 0.0
    roof_type: str = "tile"
    voltage_class: str = "LV"
    desired_storage_kwh: float = 0.0
    annual_consumption_kwh: float | None = None
    notes: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    status: str | None = None
    client_name: str | None = None
    client_company: str | None = None
    client_eik: str | None = None
    client_vat: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    client_address: str | None = None
    site_address: str | None = None
    site_lat: float | None = None
    site_lon: float | None = None
    purpose: str | None = None
    phase: int | None = None
    connected_power_kw: float | None = None
    roof_type: str | None = None
    voltage_class: str | None = None
    desired_storage_kwh: float | None = None
    annual_consumption_kwh: float | None = None
    notes: str | None = None
    params: dict[str, Any] | None = None


class LayoutSummary(BaseModel):
    count: int = 0
    kwp: float = 0.0
    lines: list[dict[str, Any]] = Field(default_factory=list)
    area_m2: float = 0.0


class LayoutOut(ORMModel):
    id: int
    project_id: int
    name: str
    image_path: str | None
    image_w: int | None
    image_h: int | None
    render_path: str | None
    corners: list[Any]
    plane_w_m: float
    plane_h_m: float
    roof_polygon: list[Any]
    obstacles: list[Any]
    panel_item_id: int | None
    orientation: str
    gap_x_m: float
    gap_y_m: float
    setback_m: float
    row_spacing_m: float
    azimuth_deg: float
    tilt_deg: float
    panels: list[Any]
    summary: dict[str, Any]
    updated_at: datetime | None = None


class LayoutIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    corners: list[Any] | None = None
    plane_w_m: float | None = None
    plane_h_m: float | None = None
    roof_polygon: list[Any] | None = None
    obstacles: list[Any] | None = None
    panel_item_id: int | None = None
    orientation: str | None = None
    gap_x_m: float | None = None
    gap_y_m: float | None = None
    setback_m: float | None = None
    row_spacing_m: float | None = None
    azimuth_deg: float | None = None
    tilt_deg: float | None = None
    panels: list[Any] | None = None
    summary: dict[str, Any] | None = None


class ProjectOut(ProjectBase, ORMModel):
    id: int
    number: str
    created_at: datetime
    updated_at: datetime
    layouts: list[LayoutOut] = Field(default_factory=list)
    quote_count: int = 0
    latest_total: float | None = None


class ProjectListItem(ORMModel):
    id: int
    number: str
    name: str
    status: str
    client_name: str
    site_address: str | None
    roof_type: str
    phase: int
    connected_power_kw: float
    updated_at: datetime
    quote_count: int = 0
    latest_total: float | None = None
    kwp: float | None = None


# ---------------- quotes ----------------
class QuoteLineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str | None = None
    section: str = "other"
    position: int | None = None
    name: str
    unit: str = "бр."
    qty: float = 1.0
    unit_price: float = 0.0
    purchase_price: float | None = None
    catalog_item_id: int | None = None
    locked: bool = True
    hidden: bool = False
    meta: dict[str, Any] = Field(default_factory=dict)


class QuoteLineUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    section: str | None = None
    position: int | None = None
    name: str | None = None
    unit: str | None = None
    qty: float | None = None
    unit_price: float | None = None
    purchase_price: float | None = None
    locked: bool | None = None
    hidden: bool | None = None
    meta: dict[str, Any] | None = None


class QuoteLineOut(ORMModel):
    id: int
    key: str
    section: str
    position: int
    name: str
    unit: str
    qty: float
    unit_price: float
    purchase_price: float
    total: float
    catalog_item_id: int | None
    source: str
    locked: bool
    hidden: bool
    meta: dict[str, Any]


class QuoteCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    selections: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    vat_pct: float | None = None
    markup_pct: float | None = None
    discount_pct: float | None = None
    advance_pct: float | None = None
    valid_days: int | None = None
    notes: str | None = None
    copy_from_quote_id: int | None = None


class QuoteUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    selections: dict[str, Any] | None = None
    title: str | None = None
    status: str | None = None
    vat_pct: float | None = None
    markup_pct: float | None = None
    discount_pct: float | None = None
    advance_pct: float | None = None
    valid_days: int | None = None
    notes: str | None = None
    recalc: bool = True


class QuoteOut(ORMModel):
    id: int
    project_id: int
    number: str
    version: int
    status: str
    title: str | None
    selections: dict[str, Any]
    currency: str
    vat_pct: float
    markup_pct: float
    discount_pct: float
    advance_pct: float
    execution_days: int | None
    workers: int | None
    valid_days: int
    subtotal: float
    discount_amount: float
    net_total: float
    vat_amount: float
    total: float
    advance_amount: float
    balance_amount: float
    notes: str | None
    pdf_path: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[QuoteLineOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)
    cost_total: float = 0.0
    margin: float = 0.0


# ---------------- sizing ----------------
class InverterSuggestion(BaseModel):
    item: CatalogItemOut
    score: float
    reasons: list[str]
    warnings: list[str]


class BatterySuggestion(BaseModel):
    item: CatalogItemOut
    qty: int
    total_kwh: float
    reasons: list[str]
    warnings: list[str]
    accessories: list[dict[str, Any]] = Field(default_factory=list)


class RoofDetectOut(BaseModel):
    corners: list[list[float]]  # normalized 0..1 [[x,y],...] 4 points TL,TR,BR,BL
    confidence: float
    method: str
    polygon: list[list[float]] | None = None


Token.model_rebuild()
