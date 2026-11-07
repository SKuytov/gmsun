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

## Mounting (Aerocompact CompactPITCH XM / CompactMETAL / CompactFLAT)

Per roof type in `MOUNTING_RULES`: X50‑3550 rails by total rail length (+1 splice per joint, −1 per line), hooks /
hanger bolts / TL25 clamps per fixation (spacing from the mounting instructions), mid clamps per inner joint, end
clamps 2 per row, 2 SDS‑W 8×100 + 1 GSC per hook, support plates, flashing, caps, cable clips, bonding clamps.
Small parts flagged `small_part` get the fastener margin.

## Margins (industry practice, configurable in Settings → Pricing → Engineering defaults)

| Margin | Default | Applies to |
| --- | --- | --- |
| `cable_margin_pct` | 15 % | PV, AC, battery, PE, bonding, communication cables (rounded up to 5 m / 1 m) |
| `fastener_margin_pct` | 10 % | screws, clamps, caps, clips, ties, lugs, end sleeves (`small_part`) |
| `module_spare_pct` | 0 % | spare PV modules line |

## Data sources

- LONGi Hi‑MO X10 LR8‑66HVD‑650M datasheet — https://eu.longi.com/longi-solar-panels-datasheets/lr8-66hvd-640-670m
- Deye SUN‑3–12K‑SG05LP3‑EU‑SM2 datasheet — https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-3-12k-sg05lp3-eu-sm2_240927_en.pdf
- Deye SUN‑14–20K‑SG05LP3‑EU‑SM2 datasheet — https://www.deyeinverter.com/deyeinverter/2024/09/27/datasheet_sun-14-20k-sg05lp3-eu-sm2_240927_en.pdf
- Deye SUN‑14–20K user manual (breakers, cables, clearances) — https://www.deyeinverter.com/deyeinverter/2026/03/19/rand/8499/%E3%80%90b%E3%80%91manual_sun-14-20k-sg05lp3-eu-sm2_20260319_en.pdf
- Deye SUN‑3–12K user manual — https://www.deyeinverter.com/deyeinverter/2026/03/19/BManualSUN-3-12K-SG05LP3-EU-SM220260319en.pdf
- Deye RW‑F16 — https://deye.com/product/rw-f16/ · SE‑G5.1 Pro‑B — https://deye.com/product/se-g5-1-pro-b/ · RW‑M6.1‑B — https://deyeinverters.net/en/products/batteries/deye-6-14kwh-low-voltage-lithium-solar-battery-rw-m6-1-b
- Aerocompact CompactPITCH XM‑F mounting instructions — https://shop.sonepar.at/asset_external/downloads/pim/402002/MD21_120160400.pdf
- Aerocompact CompactMETAL — https://www.aerocompact.com/en/products/pitched-roofs/compactmetal-tm · TL25 — https://www.mastersolar.rs/wp-content/uploads/2025/02/AC_AI_TL25_en-gbr_AI_TL25_09.pdf
- IEC 62548 DC architecture summary — https://ieccalc.com/solar-design-guide/dc-architecture/
- Weidmüller PV fuse / string protection fact sheet — https://assets.dam.weidmueller.com/assets/api/ebb318db-7048-4ce2-8fb1-79ae69074cb2/Original/HB-03_PV-Fact-Sheet-CB-Fuses_EN.pdf

Prices for protection/earthing/management items in the seed are marked `price_source: indicative` — replace them with
your supplier's prices (Catalog → edit or import).
