export type Role = 'admin' | 'user'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  active: boolean
}

export interface CatalogItem {
  id: number
  category: string
  sku: string | null
  name: string
  manufacturer: string | null
  description: string | null
  unit: string
  purchase_price: number
  markup_pct: number | null
  sell_price: number | null
  currency: string
  warranty: string | null
  active: boolean
  specs: Record<string, unknown>
  sort_order: number
  effective_price: number
  updated_at?: string | null
}

export interface LaborOption {
  id: number
  days: number
  workers: number
  price: number
  description: string | null
  active: boolean
}

export interface RoofType {
  code: string
  label_bg: string
  label_en: string
  pricing_mode: 'detailed' | 'lump' | string
  lump_price_per_module: number
  rails_per_module: number
  rail_stock_length_m: number
  fixation_spacing_m: number
  waste_pct: number
  default_tilt_deg: number
  notes: string | null
  sort_order: number
  active: boolean
}

export interface MountingRule {
  id: number
  roof_type: string
  catalog_item_id: number | null
  name: string
  basis: string
  factor: number
  round_up: boolean
  active: boolean
  notes: string | null
  sort_order: number
}

export type Pt = [number, number]

export interface PanelRect {
  x: number
  y: number
  w: number
  h: number
  enabled: boolean
  row?: number
}

export interface LayoutSummary {
  count: number
  kwp: number
  area_m2: number
  lines: { modules: number; length_m: number; rails: number; direction?: 'h' | 'v'; x?: number; y?: number }[]
}

export interface Layout {
  id: number
  project_id: number
  name: string
  image_path: string | null
  image_w: number | null
  image_h: number | null
  render_path: string | null
  corners: Pt[]
  plane_w_m: number
  plane_h_m: number
  roof_polygon: Pt[]
  obstacles: Pt[][]
  panel_item_id: number | null
  orientation: 'portrait' | 'landscape' | 'auto'
  gap_x_m: number
  gap_y_m: number
  setback_m: number
  row_spacing_m: number
  azimuth_deg: number
  tilt_deg: number
  panels: PanelRect[]
  summary: LayoutSummary
}

export interface Project {
  id: number
  number: string
  name: string
  status: string
  client_name: string
  client_company: string | null
  client_eik: string | null
  client_vat: string | null
  client_phone: string | null
  client_email: string | null
  client_address: string | null
  site_address: string | null
  site_lat: number | null
  site_lon: number | null
  purpose: 'self' | 'self_sell' | 'sell' | string
  phase: 1 | 3
  connected_power_kw: number
  roof_type: string
  voltage_class: 'LV' | 'HV' | string
  desired_storage_kwh: number
  annual_consumption_kwh: number | null
  notes: string | null
  params: Record<string, unknown>
  created_at: string
  updated_at: string
  layouts: Layout[]
  quote_count: number
  latest_total: number | null
}

export interface ProjectListItem {
  id: number
  number: string
  name: string
  status: string
  client_name: string
  site_address: string | null
  roof_type: string
  phase: number
  connected_power_kw: number
  updated_at: string
  quote_count: number
  latest_total: number | null
  kwp: number | null
}

export interface QuoteLine {
  id: number
  key: string
  section: string
  position: number
  name: string
  unit: string
  qty: number
  unit_price: number
  purchase_price: number
  total: number
  catalog_item_id: number | null
  source: string
  locked: boolean
  hidden: boolean
  meta: Record<string, unknown>
}

export interface Selections {
  panel_item_id?: number | null
  panel_qty?: number
  use_layout?: boolean
  inverter_item_id?: number | null
  inverter_qty?: number
  battery_item_id?: number | null
  battery_qty?: number
  battery_accessories?: { item_id: number; qty: number }[]
  switchboard_item_id?: number | null
  solar_cable_item_id?: number | null
  solar_cable_red_m?: number
  solar_cable_black_m?: number
  mc4_item_id?: number | null
  mc4_qty?: number
  power_cable_item_id?: number | null
  power_cable_m?: number
  electrical_items?: { item_id: number; qty: number }[]
  mounting_mode?: 'auto' | 'detailed' | 'lump' | 'none'
  lump_price_per_module?: number
  labor_mode?: 'matrix' | 'per_w' | 'manual'
  labor_option_id?: number | null
  install_price_per_w?: number
  labor_price?: number
  labor_name?: string
  transport_price?: number
  transport_name?: string
  extra_items?: { name: string; qty: number; unit?: string; unit_price: number; section?: string }[]
  delivery_fees?: boolean
  advance_basis?: 'net' | 'total'
  markup_pct?: number
  discount_pct?: number
  vat_pct?: number
  valid_days?: number
  advance_pct?: number
  _info?: Record<string, unknown>
  _warnings?: string[]
}

export interface Quote {
  id: number
  project_id: number
  number: string
  version: number
  status: string
  title: string | null
  selections: Selections
  currency: string
  vat_pct: number
  markup_pct: number
  discount_pct: number
  advance_pct: number
  execution_days: number | null
  workers: number | null
  valid_days: number
  subtotal: number
  discount_amount: number
  net_total: number
  vat_amount: number
  total: number
  advance_amount: number
  balance_amount: number
  notes: string | null
  pdf_path: string | null
  created_at: string
  updated_at: string
  lines: QuoteLine[]
  warnings: string[]
  sections: { code: string; title: string; total: number }[]
  cost_total: number
  margin: number
}

export interface InverterSuggestion {
  item: CatalogItem
  score: number
  reasons: string[]
  warnings: string[]
}

export interface BatterySuggestion {
  item: CatalogItem
  qty: number
  total_kwh: number
  reasons: string[]
  warnings: string[]
  accessories: { item_id: number; name: string; qty: number; price: number }[]
}

export interface CompanySettings {
  name: string
  address: string
  eik: string
  vat_no: string
  phone: string
  email: string
  website: string
  signatory: string
  logo_path: string | null
  bank: string
  iban: string
}

export interface PricingSettings {
  currency: string
  vat_pct: number
  default_markup_pct: number
  advance_options: number[]
  default_advance_pct: number
  quote_validity_days: number
  show_unit_prices_client: boolean
  client_pdf_collapse_construction: boolean
  advance_basis: 'net' | 'total'
  delivery_fee_equipment: number
  delivery_fee_inverter: number
  delivery_fee_construction: number
  install_price_per_w: number
  specific_yield_kwh_per_kwp: number
  dc_ac_ratio_max: number
  quote_number_prefix: string
}

export interface TextsSettings {
  quote_title: string
  warranty: string
  notes: string
  payment: string
}
