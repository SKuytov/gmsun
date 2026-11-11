"""Catalog packs added in November 2026 (GM SUN request).

* ``filkab``    – Filkab (Филкаб) cables with the catalogue prices from b2b.filkab.com (EUR without VAT, list price –
  GM SUN's own discount is entered as a lower purchase price in the catalog): solar cable H1Z2Z2-K 4 / 6 mm², СВТ
  0,6/1 kV (3/4/5 cores), ПВ-А2 (H07V-K) earthing conductors and the twisted aluminium service line AL/R ("усукан").
* ``pvc_pipes`` – corrugated PVC conduits Ø20 / Ø25 / Ø32 (Courbi Combo 320N, Tekra price list). Quoted in the
  materials but *hidden* in the client PDF – their price is spread evenly over the visible electrical rows.
* ``pv_fence``  – solar fence / PV wall (vertical modules between steel posts or on a wall / existing fence) with
  the quantity rules for roof type ``pv_fence``. Prices are indicative – confirm with the supplier.
"""
from __future__ import annotations

FILKAB_SOLAR_URL = "https://b2b.filkab.com/bg/Category/CategoryList/5637146345"
FILKAB_SVT_URL = "https://b2b.filkab.com/bg/Category/CategoryList/5637146111"
FILKAB_H07VK_URL = "https://b2b.filkab.com/bg/Product/ProductListViewWithCategory?CategID=5637146095&page=1"
FILKAB_ALR_URL = "https://b2b.filkab.com/bg/Category/CategoryList/5637146372"
TEKRA_PIPES_URL = "https://tekra.bg/bg/shop/browse/kabelovodeshti-sistemi/trubi/gofrirani-pvc-trubi/"
PRICE_DATE = "2026-11-11"


def _fk(category: str, name: str, sku: str, price: float, url: str, **specs) -> dict:
    return {
        "category": category, "name": name, "unit": "м", "purchase_price": price, "manufacturer": "Филкаб",
        "supplier": "Филкаб", "supplier_sku": sku,
        "specs": {**specs, "price_source": "filkab_catalog", "price_date": PRICE_DATE, "source_url": url},
    }


_SVT = [  # (cores, mm², Filkab No., EUR/m)
    (3, 2.5, "100503149100", 0.91), (3, 4, "100503150100", 2.85), (3, 6, "100503151100", 4.00), (3, 10, "100503152100", 6.56),
    (3, 16, "100503153100", 10.22),
    (4, 4, "100503270100", 3.68), (4, 6, "100503271100", 5.19), (4, 10, "100503272110", 8.74), (4, 16, "100503273100", 13.56),
    (5, 2.5, "100503331100", 2.89), (5, 4, "100503332100", 4.64), (5, 6, "100503333100", 6.63), (5, 10, "100503334100", 10.69),
    (5, 16, "100503335100", 17.26), (5, 25, "100503336300", 26.72), (5, 35, "100503337300", 37.39), (5, 50, "100503338300", 50.61),
]


def _mm(v: float) -> str:
    return str(v).replace(".", ",").removesuffix(",0")


FILKAB_ITEMS: list[dict] = [
    _fk("solar_cable", "Соларен кабел H1Z2Z2-K 1×4 mm² 1,5 kV DC (Филкаб)", "106808036500", 1.25, FILKAB_SOLAR_URL,
        role="pv_cable", cross_section_mm2=4, cores=1),
    _fk("solar_cable", "Соларен кабел H1Z2Z2-K 1×6 mm² 1,5 kV DC (Филкаб)", "106808037510", 1.67, FILKAB_SOLAR_URL,
        role="pv_cable", cross_section_mm2=6, cores=1),
    *[_fk("power_cable", f"Кабел СВТ-с 0,6/1 kV {c}×{_mm(mm)} mm² (Филкаб)", sku, p, FILKAB_SVT_URL,
          role="ac_cable", cross_section_mm2=mm, cores=c, material="Cu") for c, mm, sku, p in _SVT],
    _fk("grounding", "Проводник ПВ-А2 (H07V-K) 1×6 mm² жълто-зелен (Филкаб)", "100225037500", 1.22, FILKAB_H07VK_URL,
        role="bonding_cable", cross_section_mm2=6, cores=1),
    _fk("grounding", "Проводник ПВ-А2 (H07V-K) 1×10 mm² жълто-зелен (Филкаб)", "100225038500", 2.33, FILKAB_H07VK_URL,
        role="pe_cable", cross_section_mm2=10, cores=1),
    _fk("grounding", "Проводник ПВ-А2 (H07V-K) 1×16 mm² жълто-зелен (Филкаб)", "100225039500", 3.38, FILKAB_H07VK_URL,
        role="pe_cable", cross_section_mm2=16, cores=1),
    _fk("grounding", "Проводник ПВ-А2 (H07V-K) 1×25 mm² жълто-зелен (Филкаб)", "100225040500", 5.22, FILKAB_H07VK_URL,
        role="pe_cable", cross_section_mm2=25, cores=1),
    # twisted Al service line – quoted only when chosen by hand (no automatic role)
    _fk("power_cable", "Усукан проводник AL/R 0,6/1 kV 2×16 mm² (Филкаб)", "107414216200", 1.35, FILKAB_ALR_URL,
        cable_kind="alr", cross_section_mm2=16, cores=2, material="Al"),
    _fk("power_cable", "Усукан проводник AL/R 0,6/1 kV 2×25 mm² (Филкаб)", "107414225200", 2.33, FILKAB_ALR_URL,
        cable_kind="alr", cross_section_mm2=25, cores=2, material="Al"),
    _fk("power_cable", "Усукан проводник AL/R 0,6/1 kV 4×16 mm² (Филкаб)", "107414416200", 2.71, FILKAB_ALR_URL,
        cable_kind="alr", cross_section_mm2=16, cores=4, material="Al"),
    _fk("power_cable", "Усукан проводник AL/R 0,6/1 kV 4×25 mm² (Филкаб)", "107414425200", 4.15, FILKAB_ALR_URL,
        cable_kind="alr", cross_section_mm2=25, cores=4, material="Al"),
    _fk("power_cable", "Усукан проводник AL/R 0,6/1 kV 4×35 mm² (Филкаб)", "107414435300", 5.21, FILKAB_ALR_URL,
        cable_kind="alr", cross_section_mm2=35, cores=4, material="Al"),
]


def _pipe(d: int, sku: str, price: float) -> dict:
    return {
        "category": "cable_management", "name": f"PVC тръба Ø{d} гофрирана, 320N (за кабели)", "unit": "м", "purchase_price": price,
        "manufacturer": "Courbi", "supplier": "Текра", "supplier_sku": sku,
        "specs": {"role": "pvc_pipe", "diameter_mm": d, "client_hidden": True, "price_source": "supplier_list", "price_date": PRICE_DATE,
                  "source_url": TEKRA_PIPES_URL},
    }


PIPE_ITEMS: list[dict] = [_pipe(20, "CR31-21026-020", 0.25), _pipe(25, "CR31-21027-025", 0.40), _pipe(32, "CR31-21028-032", 0.52)]


def _fp(name: str, price: float, part: str, unit: str = "бр.", **specs) -> dict:
    return {"category": "mounting", "name": name, "unit": unit, "purchase_price": price,
            "specs": {"system": "Соларна ограда", "fence_part": part, "price_source": "indicative", **specs}}


FENCE_ITEMS: list[dict] = [
    _fp("Стълб за соларна ограда — поцинкована стомана 80×80×3 mm, h 2,6 m", 38.0, "post"),
    _fp("Бетонен фундамент за стълб (изкоп Ø300×800 mm, бетон C20/25)", 22.0, "foundation"),
    _fp("Капачка за стълб 80×80 mm", 0.8, "post_cap", small_part=True),
    _fp("Скоба стълб–шина, поцинкована, с болт M10 и гайка", 3.2, "post_bracket", small_part=True),
    _fp("Конзола за монтаж на шина към стена/фасада, поцинкована, с анкер M10", 4.5, "wall_bracket", small_part=True),
    _fp("U-болт M10 за закрепване на шина към съществуваща ограда/стълб", 2.8, "existing_clamp", small_part=True),
    _fp("Хоризонтална алуминиева шина 40×40 за соларна ограда, 3,55 m", 15.0, "rail"),
    _fp("Съединител за шина 40×40", 2.5, "rail_connector", small_part=True),
    _fp("Средна скоба за модул 30–40 mm (соларна ограда)", 1.1, "mid_clamp", small_part=True),
    _fp("Крайна скоба за модул 30–40 mm (соларна ограда)", 1.1, "end_clamp", small_part=True),
    _fp("Заземителна клема за шина (соларна ограда)", 1.5, "earth_clamp", small_part=True),
    _fp("Кабелна клипса за модул (соларна ограда)", 0.25, "cable_clip", small_part=True),
]

# which fence parts apply to which base (survey.fence_base); parts not listed apply always
FENCE_BASE_PARTS: dict[str, set[str]] = {
    "freestanding": {"post", "foundation", "post_cap", "post_bracket"},
    "existing": {"existing_clamp"},
    "wall": {"wall_bracket"},
}
FENCE_BASE_ONLY = set().union(*FENCE_BASE_PARTS.values())

FENCE_RULES: list[tuple[str, str, str, float, bool]] = [
    ("pv_fence", "Стълб за соларна ограда — поцинкована стомана 80×80×3 mm, h 2,6 m", "per_fixation", 0.5, True),
    ("pv_fence", "Бетонен фундамент за стълб (изкоп Ø300×800 mm, бетон C20/25)", "per_fixation", 0.5, True),
    ("pv_fence", "Капачка за стълб 80×80 mm", "per_fixation", 0.5, True),
    ("pv_fence", "Скоба стълб–шина, поцинкована, с болт M10 и гайка", "per_fixation", 1, True),
    ("pv_fence", "Конзола за монтаж на шина към стена/фасада, поцинкована, с анкер M10", "per_fixation", 1, True),
    ("pv_fence", "U-болт M10 за закрепване на шина към съществуваща ограда/стълб", "per_fixation", 1, True),
    ("pv_fence", "Хоризонтална алуминиева шина 40×40 за соларна ограда, 3,55 m", "per_rail", 1, True),
    ("pv_fence", "Съединител за шина 40×40", "per_connector", 1, True),
    ("pv_fence", "Средна скоба за модул 30–40 mm (соларна ограда)", "per_mid_clamp", 1, True),
    ("pv_fence", "Крайна скоба за модул 30–40 mm (соларна ограда)", "per_end_clamp", 1, True),
    ("pv_fence", "Заземителна клема за шина (соларна ограда)", "per_line", 1, True),
    ("pv_fence", "Кабелна клипса за модул (соларна ограда)", "per_module", 2, True),
]

FENCE_ROOF_TYPE: dict = {
    "code": "pv_fence", "kind": "fence",
    "label_bg": "Соларна ограда / стена — вертикален монтаж на панелите",
    "label_en": "Solar fence / PV wall — vertical module mounting",
    "pricing_mode": "lump", "lump_price_per_module": 95.0, "rails_per_module": 2, "rail_stock_length_m": 3.55,
    "fixation_spacing_m": 2.5, "waste_pct": 5.0, "default_tilt_deg": 90.0, "sort_order": 15,
    "notes": "Панелите се монтират вертикално (90°) на 2 хоризонтални шини между поцинковани стълбове през ~2,5 m с бетонни "
             "фундаменти, към съществуваща ограда (U-болтове) или към стена/фасада (конзоли с анкери) — по полето "
             "„Основа на оградата“ в огледа. Препоръчват се бифациални модули с ориентация изток–запад (двустранен добив). "
             "Долен ръб ≥ 0,3 m над терена; при силен вятър — статическа проверка.",
}
