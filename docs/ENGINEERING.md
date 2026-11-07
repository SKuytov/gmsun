# Engineering rules used by gmsun (automatic BOM)

Everything below is implemented in `backend/app/services/engineering.py` (`string_design`, `full_design`) and
`bom.py` (mounting rules). All quantities appear in the quote as regular lines and can be overridden; the derivation
is kept in each line's `meta` (`role`, `auto_qty`, `spec`, `basis × factor`, `margin_pct`) and printed in the technical
file (`/api/quotes/{id}/techfile.pdf`).

## Strings (IEC 62548, IEC 60364‑7‑712)

| Rule | Formula / default | Setting |
| --- | --- | --- |
| Voc at design minimum temperature | `Voc(T) = Voc·(1 + |βVoc|·(25 − Tmin))`, must be ≤ inverter max DC voltage | `design_tmin_c` (−20 °C) |
| Vmp at hot cell | `Vmp(T) = Vmp·(1 − |βPmax|·(Tcell − 25))`, must be ≥ MPPT minimum | `design_tcell_max_c` (70 °C) |
| Modules per string | `ns_min = ceil(MPPT_min / Vmp_hot)`, `ns_max = floor(min(Vdc_max / Voc_cold, MPPT_max / Vmp_cold))` | — |
| Strings per roof plane | equal strings per plane; distributed over MPPTs (`mppt_count`, `strings_per_mppt`); current per MPPT ≤ `max_input_current_a`, Isc ≤ `max_isc_a` | — |
| String fuses | required only if `(Ns − 1)·Isc·1.25 > module max series fuse`; fuse `1.5·Isc ≤ In ≤ 2.4·Isc`, ≤ module max fuse (gPV, 10×38, 1000 V DC) | `dc_box_fuses` forces them |
| PV cable design current | `1.25·Isc`; H1Z2Z2‑K 6 mm² default (Iz ≈ 43 A), increased when the DC voltage drop exceeds the limit | `dc_vdrop_max_pct` (1 %) |
| DC SPD at the array | when array‑to‑inverter run > 10 m (IEC 61643‑32), a DC combiner box with SPD T2 (and DC isolator) is added | `dc_box_distance_m`, `dc_box` auto/yes/no |
| MC4 pairs | 2 per string (+2 per string when a DC box is present) + 1 spare | override `mc4_qty` |

## AC side (Deye SUN‑xK‑SG0xLP3‑EU‑SM2 manuals, IEC 60364)

| Item | Rule |
| --- | --- |
| Input breaker | from the inverter spec `ac_breaker_a` (63 A for 3–12 kW, 100 A for 14–20 kW three‑phase), 4P (3‑ph) / 2P (1‑ph), curve C |
| RCD | `rcd_a` ≥ breaker, 300 mA type A (manual requirement) |
| AC cable | CBT/NYY 5× (3‑ph) or 3× (1‑ph), cross‑section ≥ `ac_cable_mm2` from the manual (6 mm² ≤ 12 kW, 10 mm² 14–20 kW) and increased until voltage drop ≤ `ac_vdrop_max_pct` |
| PE conductor | `pe_cable_mm2` from the manual (10 / 16 mm²), length = AC run + 2 m |
| Backup output | optional second MCB + cable to the backup loads board |
| Metering | 3 CTs (bundled, 4 m leads; CT extension cable when the run is longer) or a Modbus smart meter + RS485 cable |
| Enclosures | AC board for MCB + RCD (+ SPD T2 3P+N when the inverter has no integrated AC SPD) |

## Battery (Deye LV: RW‑F16, RW‑M6.1‑B, SE‑G5.1 Pro‑B)

Breaker and cable from the inverter spec (`battery_breaker_a`, `battery_cable_mm2`: 42–70 mm² depending on power),
one breaker per battery input used, tube lugs 2 per cable end, busbar when batteries are paralleled beyond the inverter
inputs, CAN cable per battery, length = `battery_run_m` × 2 (+1 m) per battery.

## Earthing and bonding

Module frames and rails bonded with 6 mm² H07V‑K Y/G and bonding clamps (Aerocompact WCL8‑10; 1 per rail line + 1 per
row), earth bar in the AC board, PE to the inverter 10/16 mm²; new earth electrode (rod + strip) by default on ground
mounts (`earth_rod`).

## Cable management

UV‑resistant ties 4.8×200: 4 per module + 2 per metre of rail; HFT conduit Ø32 for DC, Ø40 for AC runs with 1 clip per
0.5 m; end sleeves per conductor termination.

## Mounting (AEROCOMPACT® full catalogue, `backend/app/seed_data/aerocompact.py`)

Fourteen roof/terrain types, each mapped to one AEROCOMPACT system (`ROOF_SYSTEM`) with its technical limits
(`SYSTEMS`: roof pitch, distance to roof, wind/snow design loads from the leaflets, module frame range, documents) and a
complete rule set (`RULES`, 141 rules → 159 catalogue items with article numbers, `datasheet_url`, `assembly_url`,
`product_url`, `small_part`, `price_source`).

| Roof type | System | Basis of the main component | Key manufacturer rule |
| --- | --- | --- | --- |
| `tile` | CompactPITCH XM‑F | hook per fixation (1.2 m) | 2× SDS‑W 8×100 (or 3× 6×100) per hook, flashing XM‑FCMR, support plate XM‑FSP; pitch 10–75°, snow 6.0 / wind 2.4 kN/m² |
| `tile_xt` | CompactPITCH XT | hook per fixation | 2× SDS‑W per hook, snow 5.4 kN/m² |
| `tile_xtr` | CompactPITCH XT‑R 2.0 + XM‑B metal tile | hook per fixation | no tile cutting, XM‑B replaces one tile per hook |
| `plain_tile` | CompactPITCH XM‑PL | hook per fixation (1.1 m) | XM‑PL30X on the counter‑batten + XM‑PLR/PLB metal tile |
| `fibre_cement` | CompactPITCH XW hanger bolts | bolt per fixation | pre‑drill M10 Ø7/Ø13, M12 Ø8.4/Ø15 |
| `lt_sheet` | CompactMETAL TL25/TL38 bridges | **`per_clamp`** (= mid + end clamps) | one bridge under every clamp, 4× MSS 6×25 per bridge, clamp 250–330 mm from the short module edge, 2 modules = 6 bridges / 4 CLE10 / 2 CLM10; sheet ≥ 0.5 mm Al / 0.4 mm steel |
| `lt_sheet_ts` | CompactMETAL TS15 short rails | `per_clamp` | ≥ 2 MSS 6×25 per short rail |
| `standing_seam` | CompactMETAL TM seam clamps | `per_clamp` | no penetration, clamps on the seam clamp; ≤ 3 modules vertically (6 on aluminium) |
| `sandwich` | CompactMETAL TR | TR15 console per fixation + TR59/TR74 rails | SDS‑12 long screw into the purlin + MSS 6×25, rails 5800 mm |
| `flat_concrete` | CompactFLAT S10 (south 10°) | brackets `per_clamp`, ballast trays per row | row spacing 380 / 527 mm, 1200 mm edge zone, > 5° roof pitch → APA anchors; ballast per AEROTOOL |
| `flat_ew` | CompactFLAT S10 PLUS (east/west) | brackets `per_clamp` | middle bracket S10plusMB‑PP, connectors 464 / 297 mm |
| `flat_bifacial`, `ground_ballast` | CompactGROUND GS15 | posts `per_clamp`, ballast per row | ≈ 400 mm elevation, 15° south; CLEG10/CLMG10 clamps |
| `ground` | generic driven/concrete ground mount | posts per fixation, rails per metre | — |

Shared rules: clamps torque 15 Nm (WCL8‑10 10 Nm), end clamp ≥ 40 mm from the rail end, CLM10 carries the bonding
pins, one left/right cap per rail line, `small_part` items get the fastener margin. For rail systems the BOM uses
`bom.compute_stats` (lines = rows × rails/module, pieces = ⌈rail m × (1+waste) / stock⌉, splices = pieces − lines,
fixations = ⌈row length / spacing⌉ + 1 per rail); for direct‑mount systems the rails are "support lines" and the
`per_clamp` basis puts one bridge / short rail / seam clamp / bracket under every mid and end clamp.

Prices for the XM‑F set come from the supplier quote 64845 (X50‑3550 24.92 €, XM‑F 12.29 €, CLM10/CLE10 1.54 €, SDS‑W
0.26 € …); everything else is `price_source: indicative` (or `unknown`) and must be replaced by the distributor's
offer. The seed is additive: `POST /api/catalog/mounting/reseed` (Catalog → "Add missing Aerocompact items") adds new
items / roof types / rules without touching edited rows; rules in `RETIRED_RULES` are deactivated on upgrade.
Final structural sizing (hook spacing, ballast, wind zones to EN 1991‑1‑4) is confirmed with the manufacturer's
AEROTOOL report, as the technical file states.

## Supplier portfolio and datasheets (`backend/app/services/supplier_sync.py`, `datasheet_parse.py`)

- Source: the public WooCommerce Store API of green-energy.bg (`/wp-json/wc/store/v1/products`, 302 products →
  388 items after expanding multi‑model titles such as `SUN-14/15/16/18/20K-SG05LP3-EU-SM2`).
- Each product gives `product_url`, `image_url`, `datasheet_url` (PDF links found in the description), the Bulgarian
  spec bullet list (parsed with `parse_bg_description`) and the price (`prices.price` in BGN minor units → EUR at
  1.95583, VAT status unknown; panels have no public price).
- Datasheets are downloaded to `DATA_DIR/datasheets/<sha1>.pdf`, converted with `pdftotext -layout` and parsed by
  category (`parse_panel`, `parse_inverter`, `parse_battery`): multi‑column tables are split per model, STC columns
  are preferred over NOCT, numbers outside physical ranges (`*_RANGES`) are rejected, OCR garbage lines ignored; for
  multi‑model sheets the column closest to the Wp / kW in the title is chosen. `_sanitize_battery` drops cell
  voltages (3.2 V) and recomputes Ah from kWh / nominal V.
- Everything auto‑parsed is stored with `specs_verified: false` and `spec_source` (`datasheet-auto`, `datasheet-ocr`,
  `bg-description`); the engineering engine still uses it but the quote/techfile carry a warning until a user verifies
  the item. Verified rows are never overwritten by a sync unless `overwrite_specs` is requested.
- Snapshot: `backend/app/seed_data/green_energy_catalog.json` (regenerate with
  `python -m app.services.supplier_sync --write-seed`), live refresh: `POST /api/catalog/sync/green-energy`,
  status: `GET /api/catalog/supplier/status`, PDF: `GET /api/catalog/items/{id}/datasheet`, upload:
  `POST /api/catalog/items/{id}/datasheet?autofill=true`.

## Margins (industry practice, configurable in Settings → Pricing → Engineering defaults)

| Margin | Default | Applies to |
| --- | --- | --- |
| `cable_margin_pct` | 15 % | PV, AC, battery, PE, bonding, communication cables (rounded up to 5 m / 1 m) |
| `fastener_margin_pct` | 10 % | screws, clamps, caps, clips, ties, lugs, end sleeves (`small_part`) |
| `module_spare_pct` | 0 % | spare PV modules line |

## Procurement model and proposal engine (`services/procurement.py`, `services/proposals.py`)

- **Lead time** per line: item `lead_time_days` → supplier default (Settings → suppliers) → global default; items
  with `stock_status` `backorder`/`outofstock` use the backorder lead time. Quote `_info.lead_time_days` = max over
  visible lines, `_info.lead_bottleneck` = that line.
- **Tier classification**: within an equivalence group (category + rating: €/Wp for modules, €/kW for inverters,
  €/kWh for batteries, unit price otherwise) each item gets `score = 0.6·price_pct + 0.25·brand + 0.15·quality`;
  score ≤ 0.38 → economy, ≥ 0.62 → premium, else standard. Manual `tier` overrides. Brand lists and weights are
  configurable (`procurement` setting).
- **Strategies**: `economy` (min total), `balanced` (total + `balanced_eur_per_day` × lead days), `premium`
  (max quality/tier, then price), `fastest` (min lead time, then price). Candidates: top‑N priced panels,
  inverters that fit (AC ≥ kWp/dc_ac_max·0.98, kWp ≤ max PV·1.02, AC ≤ connected·1.1, not oversized) and compatible
  batteries (voltage class, parallel limit). Every variant is fully costed through `pricing.build_lines` (same engine
  as the quote), so proposal totals equal the quote after apply + recalc. Unpriced items carry a 1e6 penalty so
  priced equivalents win; `missing_price` lists what still needs a price.
- **Strategy‑aware part picking**: `procurement.chooser()` selects among equivalent protections/cables/clamps for
  the active strategy; without a strategy the previous deterministic choice is kept.
- **RFQ workbooks** (`services/workbooks.py`): one sheet per supplier (or ZIP of files) with SKU, name, unit, qty,
  last purchase price, expected lead time and an empty “your offer” column; a summary sheet lists suppliers, line
  counts, value and lead time.
- **Schema migration**: `db.ensure_columns()` adds new nullable columns to existing SQLite/PostgreSQL tables at
  startup, so upgrades need no manual migration.

## Data sources

- LONGi Hi‑MO X10 LR8‑66HVD‑650M datasheet — https://eu.longi.com/longi-solar-panels-datasheets/lr8-66hvd-640-670m
- Deye SUN‑3–12K‑SG05LP3‑EU‑SM2 datasheet — https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-3-12k-sg05lp3-eu-sm2_240927_en.pdf
- Deye SUN‑14–20K‑SG05LP3‑EU‑SM2 datasheet — https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-14-20k-sg05lp3-eu-sm2_240927_en.pdf
- Deye SUN‑14–20K user manual (breakers, cables, clearances) — https://www.deyeinverter.com/deyeinverter/2026/03/19/rand/8499/%E3%80%90b%E3%80%91manual_sun-14-20k-sg05lp3-eu-sm2_20260319_en.pdf
- Deye SUN‑3–12K user manual — https://www.deyeinverter.com/deyeinverter/2026/03/19/BManualSUN-3-12K-SG05LP3-EU-SM220260319en.pdf
- Deye RW‑F16 — https://deye.com/product/rw-f16/ · SE‑G5.1 Pro‑B — https://deye.com/product/se-g5-1-pro-b/ · RW‑M6.1‑B — https://deyeinverters.net/en/products/batteries/deye-6-14kwh-low-voltage-lithium-solar-battery-rw-m6-1-b
- green-energy.bg product portfolio (Store API) — https://green-energy.bg/wp-json/wc/store/v1/products · example product — https://green-energy.bg/produkt/fotovoltaichen-panel-ulica-solar-575-wp-n-type-topcon-bifacial/
- Aerocompact product pages — https://www.aerocompact.com/en/products/pitched-roofs/compactmetal-tm · https://www.aerocompact.com/en/products/pitched-roofs/compactmetal-tl · https://www.aerocompact.com/en-in/products/flat-roof/compactflat-s · https://www.aerocompact.com/en/products/ground-mount
- Aerocompact document library (leaflets, assembly instructions, checklists; mirrored by distributor Master Solar) — https://www.mastersolar.rs/aerocompact-en/?lang=en · XM‑F AI — https://www.mastersolar.rs/wp-content/uploads/2025/02/AI_CompactPITCH_XM_F_en_v3.3.pdf · TL25 AI — https://www.mastersolar.rs/wp-content/uploads/2025/02/AC_AI_TL25_en-gbr_AI_TL25_09.pdf · S10 PLUS manual — https://sunbeam369.sk/wp-content/uploads/2025/02/AC720921_Aerocompact-S10-Mittelstutze_Installation-manual_ENU.pdf
- Aerocompact article list (Sonepar, 01/2024, no prices) — https://shop.sonepar.at/asset_external/downloads/pim/402002/MD21_120160400.pdf
- IEC 62548 DC architecture summary — https://ieccalc.com/solar-design-guide/dc-architecture/
- Weidmüller PV fuse / string protection fact sheet — https://assets.dam.weidmueller.com/assets/api/ebb318db-7048-4ce2-8fb1-79ae69074cb2/Original/HB-03_PV-Fact-Sheet-CB-Fuses_EN.pdf

Prices for protection/earthing/management items in the seed are marked `price_source: indicative` — replace them with
your supplier's prices (Catalog → edit or import).
