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
  supplier?: string | null
  supplier_sku?: string | null
  lead_time_days?: number | null
  tier?: Tier | null
  effective_lead_time_days?: number | null
  effective_tier?: Tier | null
  updated_at?: string | null
}

export type Tier = 'economy' | 'standard' | 'premium'
export type Strategy = 'economy' | 'balanced' | 'premium' | 'fastest'

export interface ProposalKeyItem {
  role: string
  label: string
  item_id?: number | null
  name: string
  manufacturer?: string | null
  qty: number
  tier?: Tier | null
  lead_time_days?: number | null
  supplier?: string | null
  unit_price?: number
  warranty?: string | null
}

export interface ProposalVariant {
  strategy: Strategy
  label_bg: string
  label_en: string
  selections: Selections
  kwp: number
  panel_qty: number
  inverter_qty: number
  ac_kw?: number | null
  roof_panel_qty?: number | null
  battery_kwh: number
  subtotal: number
  vat: number
  total: number
  cost: number
  margin: number
  lead_time_days: number
  lead_bottleneck: string | null
  suppliers: Record<string, number>
  by_section: Record<string, number>
  execution_days?: number | null
  yield_kwh: number
  key_items: ProposalKeyItem[]
  warnings: string[]
  missing_price: string[]
  evaluated: number
  quality: number
  delta_total: number
  delta_days: number
  same_as?: Strategy | null
}

export type ProposalScope = 'auto' | 'target' | 'roof'

export interface ModuleCandidateLayout {
  layout_id: number
  name: string
  azimuth: number
  tilt: number
  area_m2: number
  factor: number
  orientation: 'portrait' | 'landscape'
  count_max: number
  count_used: number
  utilization: number
}
export interface ModuleCandidate {
  item_id: number
  name: string
  manufacturer: string | null
  sku: string | null
  wp: number
  width_mm: number
  height_mm: number
  weight_kg: number | null
  kg_m2: number | null
  efficiency: number
  cells: number | null
  thickness_mm: number | null
  bifacial: boolean
  tier: 'economy' | 'standard' | 'premium'
  quality: number
  lead_time_days: number
  supplier: string | null
  unit_price: number | null
  eur_per_wp: number | null
  eur_per_wp_effective: number | null
  modules_cost: number | null
  verified: boolean
  layouts: ModuleCandidateLayout[]
  count_max: number
  kwp_max: number
  count_used: number
  kwp: number
  mode: 'roof' | 'target'
  utilization: number | null
  kwp_per_m2: number | null
  warranty: string | null
  datasheet: boolean
  warnings: string[]
  reasons: string[]
  badges: string[]
  score: number
  rank: number
}
export interface ModuleRecommendation {
  candidates: ModuleCandidate[]
  evaluated: number
  target_kwp: number
  demand_basis: string
  scope: 'roof' | 'target'
  scope_requested: ProposalScope
  strategy: Strategy
  total_area_m2: number
  layouts: { layout_id: number; name: string; area_m2: number; azimuth: number; tilt: number; factor: number; panel_item_id: number | null; count: number }[]
  current_panel_id: number | null
}

export interface ScenePanel {
  x: number
  y: number
  w: number
  h: number
  enabled?: boolean
  row?: number
}
export interface ScenePlane {
  layout_id: number
  name: string
  width_m: number
  height_m: number
  tilt: number
  azimuth: number
  u_offset: number
  eave_offset: number
  eave_height: number
  roof_polygon: Pt[]
  obstacles: Pt[][]
  panels: ScenePanel[]
  panel: { name: string | null; wp: number; width_m: number; height_m: number; thickness_m: number; cells: number; bifacial: boolean }
  texture: string | null
  colour: [number, number, number]
  ballast: boolean
  elevated: boolean
}
export interface Scene {
  project_id: number
  name: string
  roof_type: string
  flat: boolean
  ground: boolean
  building: { width_m: number; depth_m: number; eave_height_m: number; ridge_height_m: number; colour: [number, number, number] }
  planes: ScenePlane[]
  modules: number
  kwp: number
  site: { lat: number; lon: number }
  render3d_path: string | null
}

export interface ProposalsResult {
  target_kwp: number
  target_basis: 'layout' | 'selection' | 'consumption' | 'connected_power' | 'target' | 'default' | 'none'
  layout_fixed: boolean
  target_kwh: number
  variants: ProposalVariant[]
  /** effective sizing scope: the client's demand or the whole layout */
  scope: 'target' | 'roof'
  scope_requested: ProposalScope
  demand_kwp: number
  demand_basis: 'target' | 'consumption' | 'connected_power' | 'none'
  roof_kwp: number
  roof_panel_qty: number
  notes: string[]
}

export interface RfqSupplier {
  supplier: string
  lines: number
  value: number
  lead_time_days: number
  email?: string | null
  contact?: string | null
  unpriced: number
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
  visual_path?: string | null
  rect_path?: string | null
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
  updated_at?: string | null
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
  /** removed from the quote (deleted engine row; restorable) */
  excluded?: boolean
  /** € taken over from hidden rows (already included in total) */
  alloc?: number
  /** unit price incl. the hidden-row share, as printed for the client */
  client_unit_price?: number | null
  meta: Record<string, unknown>
}

export type LaborMode = 'per_inverter_kw' | 'matrix' | 'per_w' | 'manual'

export type CompatStatus = 'ok' | 'warn' | 'blocked'
export interface CompatEntry {
  status: CompatStatus
  reasons: string[]
  /** inverters: number of parallel units the status was computed for */
  qty?: number
  window?: { ns_min: number; ns_max: number; inputs: number; mppt_strings: number[]; voc_cold: number; vmp_hot: number } | null
  range?: { min: number; max: number; max_per_cluster?: number; clusters_max?: number; clusters?: number[] } | null
}
export interface CompatMatrix {
  inverters: Record<string, CompatEntry>
  panels: Record<string, CompatEntry>
  batteries: Record<string, CompatEntry>
  selected?: { blocked: string[]; warnings: string[]; ok: boolean }
}

export interface Selections {
  panel_item_id?: number | null
  panel_qty?: number
  use_layout?: boolean
  inverter_item_id?: number | null
  inverter_qty?: number
  /** quote only this many modules of the layout (target-power proposals on a bigger roof) */
  panel_limit?: number | null
  battery_item_id?: number | null
  battery_qty?: number
  /** other battery accessories (covers, extra cables …) — BMS and rack have their own selections */
  battery_accessories?: { item_id: number; qty: number }[]
  /** BMS / control box: automatic (engineering), manual (listed items) or none */
  battery_bms?: BatteryPartSel
  /** rack / cabinet: automatic, manual or none */
  battery_rack?: BatteryPartSel
  switchboard_item_id?: number | null
  solar_cable_item_id?: number | null
  solar_cable_red_m?: number | null
  solar_cable_black_m?: number | null
  mc4_item_id?: number | null
  mc4_qty?: number | null
  power_cable_item_id?: number | null
  power_cable_m?: number | null
  dc_box?: 'auto' | 'yes' | 'no'
  dc_box_fuses?: boolean
  backup_output?: boolean
  metering?: 'ct' | 'smart_meter'
  earth_rod?: boolean
  auto_electrical?: boolean
  module_spare_pct?: number
  electrical_items?: { item_id: number; qty: number }[]
  mounting_mode?: 'auto' | 'detailed' | 'lump' | 'none'
  lump_price_per_module?: number
  labor_mode?: LaborMode
  /** per-quote override of the labor rate (EUR per kW of installed inverter AC power) */
  labor_eur_per_kw?: number | null
  /** pick the AC/DC board by inverter phases automatically (default true) */
  auto_switchboard?: boolean
  /** false = this quote no longer follows project / catalog changes */
  auto_sync?: boolean
  strategy?: Strategy | null
  labor_option_id?: number | null
  labor_auto?: boolean
  panel_auto?: boolean
  panel_fit?: { panel_item_id: number; count: number; roof_count: number; mode: 'roof' | 'target'; layouts: Record<string, { count_used: number; count_max: number; orientation: string }> }
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
  /** number of identical units needed for the PV power (1 = single inverter, N = parallel operation) */
  qty: number
  ac_total_kw: number
  ratio: number
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
  /** company default: add delivery-fee lines to quotes (GM SUN: off) */
  include_delivery_fees?: boolean
  delivery_fee_equipment: number
  delivery_fee_inverter: number
  delivery_fee_construction: number
  install_price_per_w: number
  /** labor = installed inverter AC kW × this rate (default mode) */
  labor_eur_per_inverter_kw?: number
  labor_mode_default?: LaborMode
  specific_yield_kwh_per_kwp: number
  dc_ac_ratio_max: number
  quote_number_prefix: string
  cable_margin_pct: number
  fastener_margin_pct: number
  module_spare_pct: number
  design_tmin_c: number
  design_tcell_max_c: number
  voc_margin?: number
  dc_vdrop_max_pct: number
  ac_vdrop_max_pct: number
  dc_run_default_m: number
  ac_run_default_m: number
  dc_box_distance_m: number
}

export interface DesignRole {
  role: string
  name: string
  qty: number
  unit: string
  section: string
  spec: Record<string, unknown>
  item_id: number | null
  item_name: string | null
  unit_price: number | null
  /** quoted = has a catalog article; covered = included in the equipped AC/DC board; not_quoted = listed only */
  status?: 'quoted' | 'covered' | 'not_quoted'
  covered_by?: 'construction'
}

export interface DesignString {
  id: string
  /** 1-based inverter index when several inverters run in parallel */
  inverter?: number
  plane: string
  modules: number
  mppt: number
  input: number
  voc_cold_v: number
  vmp_stc_v: number
  vmp_hot_v: number
  kwp: number
  cable_one_way_m: number
  vdrop_pct: number
}

export interface Design {
  inverters?: number
  switchboard?: { item_id: number; name: string; qty: number; covers_roles: string[] } | null
  strings: { strings: DesignString[]; warnings: string[]; checks: { ok: boolean; text: string }[]; modules_per_string: number; fuses_required: boolean; fuse_a: number; inverters?: number }
  dc: Record<string, number | string | boolean>
  ac: Record<string, number | string | boolean>
  battery: Record<string, number | string | boolean>
  grounding: Record<string, number | string | boolean>
  management: Record<string, number | string | boolean>
  margins: Record<string, number>
  roles: DesignRole[]
  warnings: string[]
}

export interface TextsSettings {
  quote_title: string
  warranty: string
  notes: string
  payment: string
  intro: string
  closing: string
  rfq_note: string
}

export interface SupplierCfg {
  name: string
  contact?: string
  email?: string
  phone?: string
  url?: string
  lead_time_days?: number | null
  notes?: string
}

export interface SuppliersSettings {
  list: SupplierCfg[]
  default_lead_time_days: number
  backorder_lead_time_days: number
  delivery_address: string
}

export interface ProcurementSettings {
  brand_tiers: { premium: string[]; economy: string[] }
  tier_weights: { price: number; brand: number; quality: number }
  tier_economy_max: number
  tier_premium_min: number
  balanced_eur_per_day: number
  fastest_max_days: number
  candidate_panels: number
  candidate_inverters: number
  candidate_batteries: number
  bos_per_module_eur?: number
}

// ---------------------------------------------------------------- ERP: orders, deliveries, documents, completeness
export interface PoLine {
  id: number
  order_id: number
  catalog_item_id: number | null
  sku: string | null
  name: string
  unit: string
  qty_ordered: number
  qty_received: number
  qty_open: number
  unit_price: number
  expected_at: string | null
  received_at: string | null
  status: 'open' | 'partial' | 'received' | 'cancelled'
  overdue: boolean
  notes: string | null
  receipts: { date: string; qty: number; note: string; user: string }[]
  meta: Record<string, unknown>
  // present in cross-project lists
  order_number?: string
  supplier?: string
  project_id?: number
  project_number?: string
  project_name?: string
  order_status?: string
}

export type PoStatus = 'draft' | 'sent' | 'confirmed' | 'partial' | 'received' | 'cancelled'

export interface PurchaseOrder {
  id: number
  number: string
  project_id: number
  project_number: string | null
  project_name: string | null
  quote_id: number | null
  quote_number: string | null
  supplier: string
  status: PoStatus
  supplier_ref: string | null
  ordered_at: string | null
  expected_at: string | null
  notes: string | null
  currency: string
  total: number
  created_at: string | null
  lines: PoLine[]
  lines_total: number
  lines_received: number
  lines_overdue: number
  overdue: boolean
}

export interface Readiness {
  project_id: number
  quote_id: number | null
  quote_number: string | null
  quote_status: string | null
  items_total: number
  items_ordered: number
  items_received: number
  pct_ordered: number
  pct_received: number
  value_total: number
  value_received: number
  orders: PurchaseOrder[]
  waiting: PoLine[]
  overdue: PoLine[]
  not_ordered: { name: string; unit: string; qty: number; supplier: string; section: string; item_id: number | null }[]
  earliest_start: string | null
  ready: boolean
}

export interface Awaiting {
  today: string
  orders: PurchaseOrder[]
  open_lines: PoLine[]
  overdue_lines: PoLine[]
  suppliers: { supplier: string; orders: number; open_lines: number; overdue_lines: number; value: number }[]
}

export interface CompletenessFix {
  type: 'add_item' | 'step' | 'nav' | 'rfq'
  catalog_item_id?: number
  qty?: number
  target?: 'extra' | 'electrical'
  name?: string
  price?: number
  step?: string
  to?: string
}

export interface CompletenessItem {
  code: string
  level: 'ok' | 'info' | 'warn' | 'bad'
  title: string
  detail: string
  fix: CompletenessFix | null
  group: string
}

export interface Completeness {
  quote_id: number
  score: number
  counts: Record<'ok' | 'info' | 'warn' | 'bad', number>
  ready: boolean
  items: CompletenessItem[]
  groups: [string, string][]
}

export interface ProjectDoc {
  id: number
  project_id: number
  quote_id: number | null
  kind: string
  kind_label: string
  title: string
  filename: string
  path: string
  url: string
  size: number
  mime: string | null
  notes: string | null
  created_at: string | null
  created_by: number | null
}

export interface Survey {
  surveyed_at?: string
  surveyed_by?: string
  building_height_m?: number | null
  floors?: number | null
  roof_access?: 'ladder' | 'scaffold' | 'lift' | 'crane' | 'internal' | ''
  roof_condition?: 'good' | 'fair' | 'poor' | ''
  structure?: 'concrete' | 'steel' | 'wood' | ''
  roof_age_years?: number | null
  shading?: 'none' | 'partial' | 'strong' | ''
  grid_operator?: string
  meter_no?: string
  main_breaker_a?: number | null
  meter_location?: string
  cable_route_m?: number | null
  cable_route_notes?: string
  internet?: 'wifi' | 'lan' | 'none' | ''
  has_lightning_protection?: boolean
  earth_existing?: boolean
  notes?: string
}

export interface Dashboard {
  today: string
  pipeline: Record<string, number>
  projects_total: number
  recent_projects: { id: number; number: string; name: string; client_name: string; status: string; updated_at: string | null; kwp: number | null }[]
  quotes: { sent: number; accepted: number; value_open: number; value_won: number; expiring: { id: number; number: string; version: number; project_id: number; project_name: string; client_name: string; total: number; valid_until: string; expired: boolean }[] }
  deliveries: { open_orders: number; open_lines: number; overdue_lines: number; overdue: PoLine[]; next: PoLine[]; suppliers: Awaiting['suppliers'] }
  catalog: { items: number; no_price: number; indicative: number; unverified: number; stale: number; max_age_days: number; no_price_items: { id: number; name: string }[]; unverified_items: { id: number; name: string }[] }
  datasheets: { items_with_url: number; items_local: number; library_total: number; library_local: number; files: number; size_mb: number; running: boolean }
}

export interface DatasheetStatus {
  items_with_url: number
  items_local: number
  items_uploaded_only: number
  library_total: number
  library_local: number
  files: number
  size_mb: number
  running: boolean
  progress: { running: boolean; total: number; done: number; ok: number; failed: number; started_at: string | null; finished_at: string | null; current: string | null; errors: string[] }
}

export type BatteryPartMode = 'auto' | 'manual' | 'none'
export interface BatteryPartSel {
  mode: BatteryPartMode
  items: { item_id: number; qty: number }[]
}
export interface BatteryPartOption {
  item_id: number
  name: string
  family?: string | null
  role?: string | null
  capacity?: number | null
  max_series?: number | null
  price: number
  compatible: boolean
}
export interface BatteryPartsInfo {
  hv: boolean
  family?: string | null
  clusters: number[]
  config: { bms: BatteryPartSel; rack: BatteryPartSel }
  auto: { bms: { item_id: number; name: string; qty: number; why: string }[]; rack: { item_id: number; name: string; qty: number; why: string }[] }
  resolved: { bms: { item_id: number; name: string; qty: number }[]; rack: { item_id: number; name: string; qty: number }[]; other: { item_id: number; name: string; qty: number }[] }
  warnings: string[]
  notes: string[]
  options: { bms: BatteryPartOption[]; rack: BatteryPartOption[]; other: BatteryPartOption[] }
}
