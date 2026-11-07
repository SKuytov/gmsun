"""AEROCOMPACT® mounting-system catalogue (CompactPITCH / CompactMETAL / CompactFLAT / CompactGROUND).

Data compiled from the manufacturer's assembly instructions, leaflets, checklists and
intake forms (document library mirrored by the distributor Master Solar, Feb-2025 set) and
from aerocompact.com product pages. Component designations are the official Aerocompact
article designations; 6-digit article numbers are given where they are stated in the
documents or in the customer's real quote (Quote 64845).

Prices: items that appear in the real quote carry those purchase prices. All other prices
are *indicative* market levels (specs.price_source = "indicative") or 0 (unknown) and must
be confirmed against the current Aerocompact / distributor price list before quoting.

Each roof/terrain type gets a complete component rule set (MountingRule rows) so the BOM
engine produces an orderable list; the final static design (hook/bridge spacing, ballast,
roof-zone factors) is always confirmed with AEROTOOL (Aerocompact's planning software).
"""
from __future__ import annotations

MS = "https://www.mastersolar.rs/wp-content/uploads/2025/02/"
AC = "https://www.aerocompact.com/en/"

# --------------------------------------------------------------------------------------
# Documents (leaflets LF, assembly instructions AI, checklists CL, compatibility, planning)
# --------------------------------------------------------------------------------------
DOCS: dict[str, dict[str, str]] = {
    # CompactPITCH (pitched roofs)
    "XM-F": {
        "leaflet": MS + "AC_LF_CP_XM-F_en_web.pdf",
        "assembly": MS + "AI_CompactPITCH_XM_F_en_v3.3.pdf",
        "checklist": MS + "CL_EN_XM-F_2023.1.pdf",
        "tile_compatibility": MS + "AC_XM_F_Kompatibilitat_Dachziegel_202412_EN.pdf",
        "product": AC + "products/pitched-roofs/compactpitch-xm-f",
    },
    "XT": {
        "leaflet": MS + "AC_LF_CP_XT_en_web.pdf",
        "assembly": MS + "AI_CompactPITCH_XT_en_v3.3.pdf",
        "assembly_xt40_slim": MS + "AC_AI_CP_XT40_Slim_en-gbr_AI_XT40_Slim_08.pdf",
        "checklist": MS + "CL_EN_XT_2024.2-1-1.pdf",
        "product": AC + "products/pitched-roofs/compactpitch-xt",
    },
    "XT-R": {
        "leaflet": MS + "AC_LF_CP_XT-R_XM-B_en_web-1.pdf",
        "assembly": MS + "AI_CompactPITCH_XT_R_en_v3.1.pdf",
        "checklist": MS + "CL_EN_XT_2024.2-1-2.pdf",
        "product": AC + "products/pitched-roofs/compactpitch-xt-r",
    },
    "XM-B": {
        "leaflet": MS + "AC_CP_XM-B_EN-2.pdf",
        "assembly": MS + "AI_CompactPITCH_XM_B_en_v3.0.pdf",
    },
    "XT35-VLOW": {
        "leaflet": MS + "AEROCOMPACT_Leaflet_XT-VLOW_EN_V1_WEB.pdf",
        "assembly": MS + "AI_CompactPITCH_XT_VLOW_en_v3.2.pdf",
        "checklist": MS + "CL_EN_XT_2024.2-1-3.pdf",
    },
    "XM-PL": {
        "assembly": MS + "AI_CompactPITCH_XM_PL_en_v3.0.pdf",
        "checklist": MS + "CL_EN_XT_2024.2-1.pdf",
    },
    "XW": {
        "leaflet": MS + "AEROCOMPACT_Leaflet_XW_EN_V2.pdf",
        "assembly": MS + "AI_CompactPITCH_XW_en_v3.3.pdf",
        "assembly_uk": MS + "AC_AI_XW_en-gbr_AI_XW_07.pdf",
        "assembly_xws": MS + "AI_CompactPITCH_XWS_en_v3.3.pdf",
        "checklist": MS + "AC_CL_CP_XW_en_v01.pdf",
        "product": AC + "products/pitched-roofs/compactpitch-xw",
    },
    # CompactMETAL (metal roofs)
    "TS": {
        "leaflet": MS + "AC_LF_CM_TS_en.pdf",
        "assembly": MS + "AI_CompactMETAL_TS_TSE_en_v3.3.pdf",
        "assembly_uk": MS + "AC_AI_CM_TS15_en-gbr_AI_TS15_09.pdf",
        "checklist": MS + "CL_EN_TS_TL_2023.1.pdf",
        "product": AC + "products/pitched-roofs/compactmetal-ts",
    },
    "TL": {
        "leaflet": MS + "AC_LF_CM_TL_V2_en_web-1.pdf",
        "assembly": MS + "AI_CompactMETAL_TL_TLE_en_v3.4.pdf",
        "assembly_uk": MS + "AC_AI_TL25_en-gbr_AI_TL25_09.pdf",
        "checklist": MS + "CL_EN_TS_TL_2023.1.pdf",
        "product": AC + "products/pitched-roofs/compactmetal-tl",
    },
    "TM": {
        "leaflet": MS + "AC_LF_CM_TM_V1_en.pdf",
        "assembly": MS + "AI_CompactMETAL_TM_en_v3.4.pdf",
        "checklist": MS + "CL_EN_TM_2023.1.pdf",
        "product": AC + "products/pitched-roofs/compactmetal-tm",
    },
    "TR": {
        "leaflet": MS + "AC_LF_CM_TR_Schooling_en.pdf",
        "assembly": MS + "AI_CompactMETAL_TR_en_v3.5.pdf",
        "checklist": MS + "CL_EN_TR_2023.1.pdf",
    },
    # CompactFLAT (flat roofs) / CompactGROUND
    "S": {
        "leaflet_s05": MS + "AC_LF_CF_S05_en_web.pdf",
        "leaflet_s10": MS + "AC_LF_CF_S10_en_web.pdf",
        "leaflet_s15": MS + "AC_LF_CF_S15_en_web.pdf",
        "assembly": MS + "AI_CompactFLAT_S05_S10_S15_en_v3.4.pdf",
        "checklist": MS + "CL_EN_S_2023.1.pdf",
        "friction_test": MS + "AC_Flyer_Reibbeiwertklotz_en_print.pdf",
        "product": AC + "products/flat-roof/compactflat-s",
    },
    "S10PLUS": {
        "leaflet": MS + "AC_LF_CF_S10plus_en_web.pdf",
        "assembly": MS + "AI_CompactFLAT_S10_PLUS_en_v3.4.pdf",
        "checklist": MS + "CL_EN_S_2023.1.pdf",
        "product": AC + "products/flat-roof/compactflat-s",
    },
    "GS": {
        "leaflet": MS + "AC_LF_CF_GS_en_web.pdf",
        "assembly_gs15": MS + "AI_CompactFLAT_GS15_en_v3.2.pdf",
        "assembly_gs10plus": MS + "AI_CompactFLAT_GS10_PLUS_en_v3.2.pdf",
        "checklist": MS + "CL_EN_GS_2023.1.pdf",
        "product": AC + "products/ground-mount",
    },
    "SN2": {
        "leaflet": MS + "AC_LF_CF_SN2_V7_en_web.pdf",
        "design_load": MS + "AC_SN2_Design-Load-1.pdf",
        "assembly_lsk": MS + "AI_CompactFLAT_SN2_LSK_en_v3.3.pdf",
        "assembly_ksk": MS + "AI_CompactFLAT_SN2_KSK_en_v3.3.pdf",
        "assembly_plus_lsk": MS + "AI_CompactFLAT_SN2_PLUS_LSK_en_v3.3.pdf",
        "assembly_plus_ksk": MS + "AI_CompactFLAT_SN2_PLUS_KSK_en_v3.3.pdf",
        "assembly_q_plus": MS + "AI_CompactFLAT_SN2Q_PLUS_Port_en_v3.0.pdf",
        "mounting_gauge": MS + "AI_CompactFLAT_SN2-mounting-gauge_en_v3.1.pdf",
        "checklist": MS + "CL_EN_SN2_2024.142.pdf",
    },
    "WALL": {
        "leaflet": MS + "AC_LF_CW_en_web-1.pdf",
        "assembly_landscape": MS + "AI_CompactWALL_TSE_landscape_en_v3.1.pdf",
        "planning_guide": MS + "CG_CompactWALL_Planning_guide_en_v3.0.pdf",
        "checklist": MS + "CL_EN_TLTS_2024.1.pdf",
    },
}

# --------------------------------------------------------------------------------------
# Systems: technical data (from leaflets) used for engineering checks and the tech file
# --------------------------------------------------------------------------------------
SYSTEMS: list[dict] = [
    {"code": "XM-F", "family": "CompactPITCH", "name_bg": "CompactPITCH XM-F — универсална кука за керемиди с гъвкава ламарина", "name_en": "CompactPITCH XM-F universal roof hook with flexible flashing",
     "covering_bg": "Керемиди (глинени/бетонни) до 450×440 mm, височина на вълната до 40 mm", "orientation": "portrait/landscape (rails)",
     "roof_pitch_deg": [10, 75], "distance_to_roof_mm": [80, 120], "wind_kn_m2": 2.4, "snow_kn_m2": 6.0, "frame_mm": [30, 50],
     "rails": True, "notes_bg": "Монтира се винаги върху ребрата (SDS-W 2× 8×100 или 3× 6×100). Опорна плоча XM-FSP според височината на летвата; XM-FS плъзгач с 3 височини. Поле ~12 m по непрекъсната шина.", "docs": DOCS["XM-F"]},
    {"code": "XT", "family": "CompactPITCH", "name_bg": "CompactPITCH XT — регулируема кука (XT25/35/40, SLIM, CL бързозаключваща)", "name_en": "CompactPITCH XT adjustable roof hook",
     "covering_bg": "Керемиди, плоски керемиди, шиндли, вълнообразни и сандвич покриви", "orientation": "portrait/landscape (rails)",
     "roof_pitch_deg": [0, 60], "distance_to_roof_mm": [100, None], "wind_kn_m2": 2.4, "snow_kn_m2": 5.4, "frame_mm": [30, 50],
     "rails": True, "notes_bg": "Класическа кука с чукова глава или click (CL). XTR-2200 мост за тесни ребра. 2× SDS-W на кука.", "docs": DOCS["XT"]},
    {"code": "XT-R", "family": "CompactPITCH", "name_bg": "CompactPITCH XT-R 2.0 — кука с метална заместваща керемида XM-B", "name_en": "CompactPITCH XT-R 2.0 with XM-B metal replacement tile",
     "covering_bg": "Керемиди — XM-BC бетонни, XM-B26/XM-B25.1 глинени (вж. таблица за съвместимост)", "orientation": "portrait/landscape (rails)",
     "roof_pitch_deg": [10, 60], "distance_to_roof_mm": [100, None], "wind_kn_m2": 2.4, "snow_kn_m2": 5.4, "frame_mm": [30, 50],
     "rails": True, "notes_bg": "Без рязане на керемиди; стиропорен клин в комплекта на XM-B.", "docs": DOCS["XT-R"]},
    {"code": "XM-PL", "family": "CompactPITCH", "name_bg": "CompactPITCH XM-PL — кука за плоски керемиди (бобровка) с метална керемида", "name_en": "CompactPITCH XM-PL for plain/crown tiles",
     "covering_bg": "Плоски керемиди (бобровка), коронно покриване", "orientation": "portrait/landscape (rails)",
     "roof_pitch_deg": [10, 60], "distance_to_roof_mm": [100, None], "wind_kn_m2": 2.4, "snow_kn_m2": 5.4, "frame_mm": [30, 50],
     "rails": True, "notes_bg": "XM-PL30X кука към контралетвата + XM-PLR/PLB метална керемида (червена/черна) с 2 пирона.", "docs": DOCS["XM-PL"]},
    {"code": "XT35-VLOW", "family": "CompactPITCH", "name_bg": "CompactPITCH XT35-VLOW — много ниска кука за бетонни/летвени покриви", "name_en": "CompactPITCH XT35-VLOW very low hook",
     "covering_bg": "Бетонни скатни покриви (GSC10x16) и дървени ребра (SDS-W)", "orientation": "portrait/landscape (rails)",
     "roof_pitch_deg": [0, 60], "distance_to_roof_mm": [35, None], "wind_kn_m2": 2.4, "snow_kn_m2": 5.4, "frame_mm": [30, 50],
     "rails": True, "notes_bg": "", "docs": DOCS["XT35-VLOW"]},
    {"code": "XW", "family": "CompactPITCH", "name_bg": "CompactPITCH XW — шпилки (hanger bolts) M10/M12", "name_en": "CompactPITCH XW hanger bolts",
     "covering_bg": "Вълнообразна и LT ламарина, сандвич панели, етернит (вълнообразен фиброцимент), шисти", "orientation": "portrait/landscape (rails X40)",
     "roof_pitch_deg": [0, 60], "distance_to_roof_mm": [100, None], "wind_kn_m2": 2.4, "snow_kn_m2": 3.6, "frame_mm": [30, 46],
     "rails": True, "notes_bg": "Шпилката се завива в столица/ребро през гребена на вълната (предпробиване M10: Ø7 дърво/Ø13 покритие; M12: Ø8.4/Ø15). XW..CL с click адаптер.", "docs": DOCS["XW"]},
    {"code": "TS", "family": "CompactMETAL", "name_bg": "CompactMETAL TS08/TS15 — къси шини за LT ламарина (модули легнали)", "name_en": "CompactMETAL TS short rails for trapezoidal sheet",
     "covering_bg": "Трапецовидна ламарина ≥0.5 mm Al / ≥0.4 mm стомана", "orientation": "landscape",
     "roof_pitch_deg": [0, 75], "distance_to_roof_mm": [18, 100], "wind_kn_m2": None, "snow_kn_m2": None, "frame_mm": [30, 46],
     "rails": False, "notes_bg": "Къса шина с предварително залепена EPDM лента върху гребена; ≥2 винта MSS 6×25 на шина (3-ти по план). 2 модула = мин. 6 къси шини, 4 крайни + 2 средни скоби. Поле вертикално ~5 модула.", "docs": DOCS["TS"]},
    {"code": "TL", "family": "CompactMETAL", "name_bg": "CompactMETAL TL25/TL38 — мостове за LT ламарина (модули изправени)", "name_en": "CompactMETAL TL trapezoidal bridges",
     "covering_bg": "Трапецовидна ламарина ≥0.5 mm Al / ≥0.4 mm стомана; TL25 за стъпка на гребените 100–210 mm, TL38 за 211–333 mm", "orientation": "portrait",
     "roof_pitch_deg": [5, 45], "distance_to_roof_mm": [18, 100], "wind_kn_m2": None, "snow_kn_m2": None, "frame_mm": [30, 46],
     "rails": False, "notes_bg": "Мостът стъпва на два гребена, 4× MSS 6×25 (по 2 на страна), EPDM лента. Скобата 250–330 mm от късия ръб. Хоризонтално поле ~5 модула (5.7 m).", "docs": DOCS["TL"]},
    {"code": "TM", "family": "CompactMETAL", "name_bg": "CompactMETAL TM — фалцови скоби с къса шина (стоящ фалц)", "name_en": "CompactMETAL TM standing-seam clamps",
     "covering_bg": "Фалцова ламарина: двоен фалц (TMDS08), ъглов/snap фалц (TMM08), кръгъл фалц Kalzip/BEMO (TMR08), скрит плъзгащ фалц (TMRD08/TMK1508/TMK2008); мед със стоманено седло DSA10", "orientation": "landscape (direct) / portrait (rails)",
     "roof_pitch_deg": [0, 70], "distance_to_roof_mm": [30, 90], "wind_kn_m2": 2.4, "snow_kn_m2": 5.4, "frame_mm": [30, 46],
     "rails": False, "notes_bg": "Без пробиване; директен монтаж на скобите върху фалцовата скоба. Вертикално до 3 модула (6 при алуминиево покритие).", "docs": DOCS["TM"]},
    {"code": "TR", "family": "CompactMETAL", "name_bg": "CompactMETAL TR — самоносеща шина за сандвич панели", "name_en": "CompactMETAL TR self-supporting rail for sandwich roofs",
     "covering_bg": "Сандвич панели 60–162 mm, горна обшивка ≥0.4 mm, столици стомана 1.5–12 mm или дърво; стъпка на столиците до >3 m", "orientation": "landscape",
     "roof_pitch_deg": [0, 70], "distance_to_roof_mm": [84, 99], "wind_kn_m2": None, "snow_kn_m2": None, "frame_mm": [30, 46],
     "rails": True, "notes_bg": "TR15 конзола към столицата с дълъг самопробивен винт SDS-12 (с дистанционна втулка SP20) + MSS 6×25; шини TR59/TR74 5800 mm. Снегът се предава в столиците, панелът не се претоварва.", "docs": DOCS["TR"]},
    {"code": "S10", "family": "CompactFLAT", "name_bg": "CompactFLAT S05/S10/S15 — баластна система юг (5°/10°/15°)", "name_en": "CompactFLAT S south-facing ballasted",
     "covering_bg": "Плоски покриви: фолио, битум, бетон; чакъл/зелен покрив по запитване", "orientation": "landscape",
     "roof_pitch_deg": [0, 5], "distance_to_roof_mm": [60, None], "wind_kn_m2": 2.4, "snow_kn_m2": 2.4, "frame_mm": [30, 46],
     "rails": False, "notes_bg": "Модули 950–1150 × 1500–2250 mm. Разстояние от ръба на покрива 1200 mm. S10: стъпка между редовете 380 mm (засенчване 25°) или 527 mm (<20°). Над 5° наклон — само с анкери APA. Alpine версия до 4.4 kN/m² сняг. Баластът — по статичния доклад AEROTOOL.", "docs": DOCS["S"]},
    {"code": "S10PLUS", "family": "CompactFLAT", "name_bg": "CompactFLAT S10 PLUS — баластна система изток/запад 10°", "name_en": "CompactFLAT S10 PLUS east-west ballasted",
     "covering_bg": "Плоски покриви: фолио, битум, бетон", "orientation": "landscape",
     "roof_pitch_deg": [0, 5], "distance_to_roof_mm": [60, None], "wind_kn_m2": 2.4, "snow_kn_m2": 2.4, "frame_mm": [30, 46],
     "rails": False, "notes_bg": "Двойни редове; S10plusMB-PP среден носач под билото, S10FB-PP предни носачи, S10plusCNS/CNL-PP съединители между двойните редове (464 mm / 297 mm стъпка). Поле до 12×8 двойни реда (192 модула).", "docs": DOCS["S10PLUS"]},
    {"code": "GS", "family": "CompactFLAT/GROUND", "name_bg": "CompactFLAT GS15 / GS10 PLUS — повдигната баластна система за зелени покриви, бифациални модули и терен", "name_en": "CompactFLAT GS elevated ballasted (green roof / bifacial / ground)",
     "covering_bg": "Фолио, битум, бетон, чакъл, зелени покриви; CompactGROUND GS за терен без набиване (сметища, малки обекти)", "orientation": "landscape",
     "roof_pitch_deg": [0, 5], "distance_to_roof_mm": [400, None], "wind_kn_m2": 2.4, "snow_kn_m2": 2.4, "frame_mm": [30, 50],
     "rails": False, "notes_bg": "GS15 юг 15° (до 12×20 реда), GS10 PLUS изток/запад 10°. Модули 950–1150 × 1500–2280 mm. Скоби CLEG10/CLMG10 за рамка 30–50 mm.", "docs": DOCS["GS"]},
    {"code": "SN2", "family": "CompactFLAT", "name_bg": "CompactFLAT SN2 — система с базови шини (5°/10°, дълга/къса страна)", "name_en": "CompactFLAT SN2 base-rail system",
     "covering_bg": "Плоски покриви", "orientation": "landscape/portrait",
     "roof_pitch_deg": [0, 5], "distance_to_roof_mm": [60, None], "wind_kn_m2": 2.4, "snow_kn_m2": 2.4, "frame_mm": [28, 42],
     "rails": True, "notes_bg": "Базови шини BR450/900/1980/5800 с носачи SNLS; скоби CLE20; дефлектори Sx10WD.", "docs": DOCS["SN2"]},
]

# --------------------------------------------------------------------------------------
# Catalogue items. (sku, name_bg, price, specs) — category mounting, manufacturer Aerocompact
# price_source: "quote" (real quote 64845) | "indicative" | missing when 0/unknown
# --------------------------------------------------------------------------------------
def _it(name: str, price: float = 0.0, sku: str | None = None, system: str | None = None, role: str | None = None,
        small: bool = False, doc: str | None = None, price_source: str | None = None, **specs) -> dict:
    s: dict = {"manufacturer_url": AC + "products"}
    if system:
        s["system"] = system
        d = DOCS.get({"S10": "S"}.get(system, system), {})
        s["datasheet_url"] = doc or d.get("leaflet") or d.get("leaflet_s10") or d.get("assembly") or next(iter(d.values()), None)
        s["assembly_url"] = d.get("assembly") or d.get("assembly_gs15") or d.get("assembly_lsk")
        if d.get("product"):
            s["product_url"] = d["product"]
    elif doc:
        s["datasheet_url"] = doc
    if role:
        s["role"] = role
    if small:
        s["small_part"] = True
    if price_source:
        s["price_source"] = price_source
    elif price == 0:
        s["price_source"] = "unknown"
    s.update(specs)
    return {"category": "mounting", "sku": sku, "name": name, "manufacturer": "Aerocompact", "purchase_price": price, "specs": s}


RAIL_LENGTHS = {"X40": [1980, 3300, 3550, 4400, 4750, 5500, 5850], "X50": [1980, 3300, 3550, 4400, 4750, 5500, 5850], "X60": [1980, 3550, 4750, 5850]}
_RAIL_EUR_PER_M = {"X40": 5.9, "X50": 7.0, "X60": 8.6}  # indicative, derived from X50-3550 = 24.92 € in quote 64845
_RAIL_SKU = {"X40": "705000", "X50": "705100", "X60": "705600"}


def _rails() -> list[dict]:
    out = []
    for prof, lens in RAIL_LENGTHS.items():
        for L in lens:
            price = round(_RAIL_EUR_PER_M[prof] * L / 1000, 2)
            src = "quote" if (prof, L) == ("X50", 3550) else "indicative"
            if (prof, L) == ("X50", 3550):
                price = 24.92
            out.append(_it(f"{prof}-{L} монтажна шина {L} mm", price, sku=f"{_RAIL_SKU[prof]}-{L}" if prof == "X50" else None, system="XM-F", role="rail",
                           doc=DOCS["XM-F"]["assembly"], price_source=src, length_m=L / 1000, profile=prof, material="EN AW-6063 T66", click_rail=True))
    return out


ITEMS: list[dict] = [
    # ---------------- universal click clamps / accessories ----------------
    _it("CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", 1.54, sku="707011", system="XM-F", role="mid_clamp", small=True, price_source="quote", torque_nm=15, frame_mm=[30, 46], grounding_pins=True),
    _it("CLE10 крайна скоба Click 30-46", 1.54, sku="707003", system="XM-F", role="end_clamp", small=True, price_source="quote", torque_nm=15, edge_distance_mm=40, frame_mm=[30, 46]),
    _it("CLMB10 средна скоба Click 30-46 черна", 1.9, sku="707611", system="XM-F", role="mid_clamp", small=True, price_source="indicative", torque_nm=15, frame_mm=[30, 46], color="black"),
    _it("CLEB10 крайна скоба Click 30-46 черна", 1.9, sku="707603", system="XM-F", role="end_clamp", small=True, price_source="indicative", torque_nm=15, frame_mm=[30, 46], color="black"),
    _it("CLE10 PLUS крайна скоба Click 30-46, дължина 80 mm (CompactFLAT)", 2.35, sku="707080", system="S10", role="end_clamp", small=True, price_source="indicative", torque_nm=15, frame_mm=[30, 46]),
    _it("CLE20 крайна скоба Click 28-42 (CompactFLAT SN2)", 2.1, system="SN2", role="end_clamp", small=True, price_source="indicative", frame_mm=[28, 42]),
    _it("CLEG10 крайна скоба за рамка 30-50 mm (CompactFLAT GS)", 2.4, system="GS", role="end_clamp", small=True, price_source="indicative", frame_mm=[30, 50]),
    _it("CLMG10 средна скоба за рамка 30-50 mm (CompactFLAT GS)", 2.4, system="GS", role="mid_clamp", small=True, price_source="indicative", frame_mm=[30, 50]),
    _it("XPCN съединител за шина X40/X50", 1.85, sku="705202", system="XM-F", role="rail_connector", small=True, price_source="quote"),
    _it("XPCN60 съединител за шина X60", 2.6, system="XM-F", role="rail_connector", small=True, price_source="indicative"),
    _it("XDL кръстат съединител X40/X50/X60 (кръстосана връзка на шини)", 3.4, system="XM-F", role="cross_connector", small=True, price_source="indicative"),
    _it("XCL50 капачка лява за шина X50", 0.46, sku="705205", system="XM-F", role="rail_cap", small=True, price_source="quote"),
    _it("XCR50 капачка дясна за шина X50", 0.46, sku="705206", system="XM-F", role="rail_cap", small=True, price_source="quote"),
    _it("GSC 10×30 фиксиращ винт (кука↔шина)", 0.23, sku="701590", system="XM-F", role="grub_screw", small=True, price_source="quote"),
    _it("GSC 10×16 фиксиращ винт M10×16 (XT35-VLOW към бетон)", 0.22, system="XT35-VLOW", role="grub_screw", small=True, price_source="indicative"),
    _it("SCR-MA комплект болтове за аксесоари към шина X40/X50/X60 (MLPE/оптимизатор)", 1.2, system="XM-F", role="accessory_bolt", small=True, price_source="indicative"),
    _it("OC-GA универсална скоба за микроинвертор/оптимизатор към шина", 3.9, system="XM-F", role="mlpe_mount", small=True, price_source="indicative"),
    _it("MA-BR монтажна конзола за MLPE (CompactFLAT)", 3.9, system="S10", role="mlpe_mount", small=True, price_source="indicative"),
    _it("BR-MI монтажна конзола за MLPE (CompactMETAL TL/TS)", 3.9, system="TL", role="mlpe_mount", small=True, price_source="indicative", max_frame_mm=48),
    _it("CLP-M кабелна клипса за модул", 0.26, sku="701902", system="XM-F", role="cable_clip", small=True, price_source="quote", frame_mm=[1, 3]),
    _it("CLP-R кабелна клипса за шина", 0.16, sku="706457", system="XM-F", role="cable_clip", small=True, price_source="quote"),
    _it("CLP-U универсална кабелна клипса", 0.3, system="XM-F", role="cable_clip", small=True, price_source="indicative"),
    _it("CLP-WD клипса за ветрозащитен дефлектор (CompactFLAT S)", 0.35, system="S10", role="deflector_clip", small=True, price_source="indicative"),
    _it("WCL8-10 клема за заземителен проводник 6–10 mm² към шина", 1.9, system="XM-F", role="bonding_clamp", small=True, price_source="indicative", torque_nm=10),
    # ---------------- CompactPITCH XM-F ----------------
    _it("XM-F кука за керемиден покрив (регулируема)", 12.29, sku="705310", system="XM-F", role="roof_hook", price_source="quote", screws="2× SDS-W 8×100 или 3× SDS-W 6×100", material="Al EN AW-6005 T6 / A2"),
    _it("XM-FSP опорна плоча за кука", 1.76, sku="705309", system="XM-F", role="hook_support", small=True, price_source="quote"),
    _it("XM-FCMR покривна ламарина среден размер, червена", 8.02, sku="705308-8004", system="XM-F", role="flashing", price_source="quote", color="RAL 8004", max_tile_mm="450×440", max_bead_mm=40),
    _it("XM-FCM покривна ламарина среден размер (гъвкава, натурална)", 7.6, sku="705308", system="XM-F", role="flashing", price_source="indicative"),
    _it("XM-FS плъзгач за кука XM-F (3 височини)", 1.4, system="XM-F", role="hook_slider", small=True, price_source="indicative"),
    _it("XM-F100 базова плоча 100 mm за кука XM-F", 2.9, system="XM-F", role="base_plate", small=True, price_source="indicative"),
    _it("XM-FR-1980 дълга базова плоча 1980 mm (мост при тесни ребра)", 19.0, system="XM-F", role="base_plate", price_source="indicative", length_m=1.98),
    _it("XDP дистанционна плоча", 0.9, system="XM-F", role="spacer", small=True, price_source="indicative"),
    _it("XFW60 стиропорен клин за ламарина", 0.8, system="XM-F", role="foam_wedge", small=True, price_source="indicative"),
    _it("MSS 7.2×19 ремонтен винт за кука XM-F", 0.25, system="XM-F", role="screw", small=True, price_source="indicative"),
    _it("MSS 6×25-AH метален винт (XM-F ламарина)", 0.14, system="XM-F", role="screw", small=True, price_source="indicative"),
    _it("SDS-W 8×100 самонарезен винт за дърво (A2)", 0.26, sku="701544", system="XM-F", role="wood_screw", small=True, price_source="quote", d_mm=8, l_mm=100),
    _it("SDS-W 8×120 самонарезен винт за дърво (A2)", 0.3, system="XM-F", role="wood_screw", small=True, price_source="indicative", d_mm=8, l_mm=120),
    _it("SDS-W 8×140 самонарезен винт за дърво (A2)", 0.34, system="XM-F", role="wood_screw", small=True, price_source="indicative", d_mm=8, l_mm=140),
    _it("SDS-W 6×100 самонарезен винт за дърво (A2)", 0.2, system="XM-F", role="wood_screw", small=True, price_source="indicative", d_mm=6, l_mm=100),
    # ---------------- CompactPITCH XT / XT-R / XM-B / XM-PL / VLOW ----------------
    _it("XT40 алуминиева кука с чукова глава, регулируема", 9.5, system="XT", role="roof_hook", price_source="indicative", screws="2× SDS-W"),
    _it("XT40CL алуминиева кука с click бързо закрепване", 10.5, system="XT", role="roof_hook", price_source="indicative"),
    _it("XT25 алуминиева кука (ниска)", 8.5, system="XT", role="roof_hook", price_source="indicative"),
    _it("XT35 алуминиева кука (средна)", 9.0, system="XT", role="roof_hook", price_source="indicative"),
    _it("XT40-EL алуминиева кука (повдигната)", 10.0, system="XT", role="roof_hook", price_source="indicative"),
    _it("XT40-SLIM тясна алуминиева кука", 9.8, system="XT", role="roof_hook", price_source="indicative", doc=DOCS["XT"]["assembly_xt40_slim"]),
    _it("XT40-SLIM-LOW тясна ниска алуминиева кука", 9.8, system="XT", role="roof_hook", price_source="indicative"),
    _it("XTR-2200 мост за кука 2200 mm (тесни/несъвпадащи ребра)", 21.0, system="XT", role="base_plate", price_source="indicative", length_m=2.2),
    _it("XTS40XCL кука с ъгъл и click закрепване", 11.5, system="XT", role="roof_hook", price_source="indicative"),
    _it("XT-R 2.0 кука за керемиди с интегриран бърз съединител", 10.9, system="XT-R", role="roof_hook", price_source="indicative"),
    _it("XT-R базова плоча 100", 2.9, system="XT-R", role="base_plate", small=True, price_source="indicative"),
    _it("XT-R-1980 дълга базова плоча 1980 mm", 19.0, system="XT-R", role="base_plate", price_source="indicative"),
    _it("XM-BC метална заместваща керемида за бетонни керемиди (с клин)", 9.9, system="XM-B", role="flashing", price_source="indicative", tiles="Bramac Classic/Dolomit/Donau/Montero, Braas Doppel-S/Frankfurter/Harzer/Römer/Taunus, Nelskamp Finkenberger/S-Pfanne/Sigma/Kronen, Creaton Heidelberg/Maxima…"),
    _it("XM-B26 метална заместваща керемида за глинени керемиди (с клин)", 9.9, system="XM-B", role="flashing", price_source="indicative", tiles="Wienerberger Cosmo 12/Universo 14, Erlus E58/Reformpfanne, Nelskamp F13/F14/F15, Röben Flandern, Braas Rubin 13, Creaton Viva, Mühlacker Z17/Z18…"),
    _it("XM-B25.1 метална заместваща керемида за глинени керемиди тип 25.1 (с клин)", 9.9, system="XM-B", role="flashing", price_source="indicative", tiles="Braas R13 S, Jacobi Walther Z2, Creaton Domino, ZZ Wancor Fama/Jura/Campa, Rapperswil FS03/J72, Braas Granat 13, Erlus Großfalzziegel, Nelskamp D13…"),
    _it("XM-PL30X кука за плоски керемиди (бобровка)", 9.2, system="XM-PL", role="roof_hook", price_source="indicative"),
    _it("XM-PLR плоска метална керемида червена", 6.5, system="XM-PL", role="flashing", price_source="indicative", color="red"),
    _it("XM-PLB плоска метална керемида черна", 6.5, system="XM-PL", role="flashing", price_source="indicative", color="black"),
    _it("XT35-VLOW много ниска кука 35×8", 8.9, system="XT35-VLOW", role="roof_hook", price_source="indicative"),
    # ---------------- CompactPITCH XW hanger bolts ----------------
    _it("XW10250CL шпилка M10×250 с click адаптер за шина X40", 6.9, system="XW", role="hanger_bolt", price_source="indicative", thread="M10", l_mm=250, predrill="Ø7 дърво / Ø13 покритие"),
    _it("XW10300CL шпилка M10×300 с click адаптер за шина X40", 7.4, system="XW", role="hanger_bolt", price_source="indicative", thread="M10", l_mm=300),
    _it("XW12200CL шпилка M12×200 с click адаптер за шина X40", 7.6, system="XW", role="hanger_bolt", price_source="indicative", thread="M12", l_mm=200, predrill="Ø8.4 дърво / Ø15 покритие"),
    _it("XW12250CL шпилка M12×250 с click адаптер за шина X40", 8.1, system="XW", role="hanger_bolt", price_source="indicative", thread="M12", l_mm=250),
    _it("XW12300CL шпилка M12×300 с click адаптер за шина X40", 8.6, system="XW", role="hanger_bolt", price_source="indicative", thread="M12", l_mm=300),
    _it("XW10250 шпилка M10×250 с чукова глава (адаптер за шина)", 6.2, system="XW", role="hanger_bolt", price_source="indicative", thread="M10", l_mm=250),
    _it("XW12300 шпилка M12×300 с чукова глава (адаптер за шина)", 7.9, system="XW", role="hanger_bolt", price_source="indicative", thread="M12", l_mm=300),
    # ---------------- CompactMETAL TS / TL / TM / TR ----------------
    _it("CompactMETAL TS08 къса шина 80 mm с EPDM за LT ламарина", 3.2, system="TS", role="short_rail", price_source="indicative", screws="≥2× MSS 6×25"),
    _it("CompactMETAL TS15 къса шина 150 mm с EPDM за LT ламарина", 3.9, system="TS", role="short_rail", price_source="indicative", screws="≥2× MSS 6×25", doc=DOCS["TS"]["assembly_uk"]),
    _it("CompactMETAL TSE15 повдигната къса шина 150 mm", 5.4, system="TS", role="short_rail", price_source="indicative"),
    _it("CompactMETAL TL25 трапецовиден мост 250 mm с EPDM", 4.5, sku="705511-250", system="TL", role="bridge", price_source="indicative", screws="4× MSS 6×25", rib_spacing_mm=[100, 210], doc=DOCS["TL"]["assembly_uk"]),
    _it("CompactMETAL TL38 трапецовиден мост 380 mm с EPDM", 5.6, system="TL", role="bridge", price_source="indicative", screws="4× MSS 6×25", rib_spacing_mm=[211, 333]),
    _it("CompactMETAL TLE25 повдигнат трапецовиден мост 250 mm", 6.4, system="TL", role="bridge", price_source="indicative", rib_spacing_mm=[100, 210]),
    _it("CompactMETAL TLE38 повдигнат трапецовиден мост 380 mm", 7.5, system="TL", role="bridge", price_source="indicative", rib_spacing_mm=[211, 333]),
    _it("MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", 0.12, sku="701514", system="TL", role="sheet_screw", small=True, price_source="indicative", single_use=True, max_rpm=500),
    _it("EL05 адаптер за височина 33 mm (TS/TL/TM)", 1.6, system="TL", role="height_adapter", small=True, price_source="indicative"),
    _it("EL10 адаптер за височина 83 mm (TS/TL)", 2.4, system="TL", role="height_adapter", small=True, price_source="indicative"),
    _it("PS преден адаптер за наклон 20 mm (TS/TL)", 2.2, system="TL", role="tilt_adapter", small=True, price_source="indicative"),
    _it("PM заден адаптер за наклон 100 mm (TS/TL)", 3.4, system="TL", role="tilt_adapter", small=True, price_source="indicative"),
    _it("PL заден адаптер за наклон 180 mm (TS/TL)", 4.2, system="TL", role="tilt_adapter", small=True, price_source="indicative"),
    _it("LSP комплект обезопасителни болтове (TS/TL)", 2.0, system="TL", role="safety_bolt", small=True, price_source="indicative"),
    _it("BIT8SL бит SW8 × 150 mm (TS/TL монтаж)", 6.0, system="TL", role="tool", price_source="indicative"),
    _it("TMDS08 фалцова скоба за двоен фалц с къса шина 80 mm", 7.9, system="TM", role="seam_clamp", price_source="indicative", seam="double standing seam"),
    _it("TMM08 фалцова скоба за ъглов/snap фалц с къса шина 80 mm", 7.9, system="TM", role="seam_clamp", price_source="indicative", seam="angle / snap seam"),
    _it("TMR08 фалцова скоба за кръгъл фалц (Kalzip/BEMO) с къса шина 80 mm", 8.9, system="TM", role="seam_clamp", price_source="indicative", seam="round seam"),
    _it("TMRD08 фалцова скоба за скрит плъзгащ фалц – малка", 8.9, system="TM", role="seam_clamp", price_source="indicative", seam="concealed sliding seam small"),
    _it("TMK1508 фалцова скоба за скрит плъзгащ фалц – средна", 9.4, system="TM", role="seam_clamp", price_source="indicative", seam="concealed sliding seam medium"),
    _it("TMK2008 фалцова скоба за скрит плъзгащ фалц – голяма", 9.9, system="TM", role="seam_clamp", price_source="indicative", seam="concealed sliding seam large"),
    _it("DSA10 стоманено седло 55 mm за меден фалцов покрив", 4.5, system="TM", role="seam_saddle", small=True, price_source="indicative"),
    _it("CompactMETAL TR15 конзола 150 mm за сандвич панел", 6.9, system="TR", role="sandwich_bracket", price_source="indicative", mounting="1× SDS-12 към столица + SP20 + MSS 6×25"),
    _it("TR59-5800 самоносеща шина 5800 mm (сандвич, 84 mm до модула)", 44.0, system="TR", role="rail", price_source="indicative", length_m=5.8, profile="TR59"),
    _it("TR74-5800 самоносеща шина 5800 mm (сандвич, 99 mm до модула)", 52.0, system="TR", role="rail", price_source="indicative", length_m=5.8, profile="TR74"),
    _it("TRPCN59 съединител за шина TR59", 3.2, system="TR", role="rail_connector", small=True, price_source="indicative"),
    _it("TRPCN74 съединител за шина TR74", 3.6, system="TR", role="rail_connector", small=True, price_source="indicative"),
    _it("SDS-12/185 E16 дълъг самопробивен винт 5.5×185 за столица (сандвич) с уплътнение", 1.9, system="TR", role="purlin_screw", small=True, price_source="indicative", lengths_mm=[142, 185, 210, 235]),
    _it("SP20 дистанционна втулка 20 mm за винт TR", 0.5, system="TR", role="spacer", small=True, price_source="indicative"),
    # ---------------- CompactFLAT S05/S10/S15 (south) ----------------
    _it("S10FB-PP преден носач S10 с предпазна подложка", 9.8, sku="821011", system="S10", role="front_bracket", price_source="indicative"),
    _it("S10CNS-PP съединител S10/25 (стъпка 380 mm) с подложка", 11.5, system="S10", role="connector_bracket", price_source="indicative", row_spacing_mm=380),
    _it("S10CNL-PP съединител S10/18 (стъпка 527 mm) с подложка", 12.5, system="S10", role="connector_bracket", price_source="indicative", row_spacing_mm=527),
    _it("S10EB-PP заден (краен) носач S10 с подложка", 9.8, system="S10", role="end_bracket", price_source="indicative"),
    _it("S10WD-2050 ветрозащитен дефлектор 10°, 2050 mm", 11.0, system="S10", role="wind_deflector", price_source="indicative", lengths_mm=[1800, 2050, 2300, 2500]),
    _it("S10WD-2300 ветрозащитен дефлектор 10°, 2300 mm", 12.0, system="S10", role="wind_deflector", price_source="indicative"),
    _it("S05FB-PP преден носач S05 с подложка", 9.2, system="S10", role="front_bracket", price_source="indicative", doc=DOCS["S"]["leaflet_s05"]),
    _it("S05CN-PP съединител S05 с подложка", 10.5, system="S10", role="connector_bracket", price_source="indicative"),
    _it("S05EB-PP заден носач S05 с подложка", 9.2, system="S10", role="end_bracket", price_source="indicative"),
    _it("S05WD-2050 ветрозащитен дефлектор 5°, 2050 mm", 10.0, system="S10", role="wind_deflector", price_source="indicative"),
    _it("S15FB-PP преден носач S15 с подложка", 10.5, system="S10", role="front_bracket", price_source="indicative", doc=DOCS["S"]["leaflet_s15"]),
    _it("S15CNS-PP съединител S15/25 с подложка", 12.5, system="S10", role="connector_bracket", price_source="indicative"),
    _it("S15CNL-PP съединител S15/18 с подложка", 13.5, system="S10", role="connector_bracket", price_source="indicative"),
    _it("S15EB-PP заден носач S15 с подложка", 10.5, system="S10", role="end_bracket", price_source="indicative"),
    _it("S15WD-2050 ветрозащитен дефлектор 15°, 2050 mm", 12.0, system="S10", role="wind_deflector", price_source="indicative"),
    _it("S10BS / S10FS алпийски носач заден/преден (сняг > 2.4 kN/m²)", 7.5, system="S10", role="alpine_bracket", price_source="indicative"),
    _it("STS 8×16 самонарезен винт M8×16 (CompactFLAT)", 0.15, system="S10", role="screw", small=True, price_source="indicative"),
    _it("SCS 8×20 резбонарезен комбиниран винт M8×20 (CompactFLAT)", 0.18, system="S10", role="screw", small=True, price_source="indicative"),
    _it("PP200 строителна защитна подложка за баластни блокове/вани", 1.5, system="S10", role="protection_pad", small=True, price_source="indicative"),
    _it("BT-450 баластна вана къса 450 mm", 6.5, sku="820643", system="S10", role="ballast_tray", price_source="indicative"),
    _it("BT-880 баластна вана къса 880 mm", 9.5, system="S10", role="ballast_tray", price_source="indicative"),
    _it("BT-2050 баластна вана дълга 2050 mm", 17.0, system="S10", role="ballast_tray", price_source="indicative", lengths_mm=[1800, 2050, 2300]),
    _it("BSB скоба за обезопасяване на баласта във ваната", 1.2, system="S10", role="ballast_bracket", small=True, price_source="indicative"),
    _it("APA връзка към покривен анкер (CompactFLAT, при наклон > 5° или недостиг на баласт)", 14.0, system="S10", role="roof_anchor", price_source="indicative"),
    _it("BR-CP конзола за кабелна тръба (CompactFLAT)", 1.8, system="S10", role="cable_pipe_bracket", small=True, price_source="indicative"),
    _it("CP-620 кабелна тръба 620 mm (CompactFLAT)", 3.5, system="S10", role="cable_pipe", price_source="indicative", lengths_mm=[430, 620, 840]),
    # ---------------- CompactFLAT S10 PLUS (east-west) ----------------
    _it("S10plusMB-PP среден носач S10 PLUS с подложки (под билото изток/запад)", 13.5, sku="820921", system="S10PLUS", role="middle_bracket", price_source="indicative"),
    _it("S10plusCNS-PP съединител S10 PLUS къс (стъпка 297 mm) с подложка", 11.5, sku="820931", system="S10PLUS", role="connector_bracket", price_source="indicative", row_spacing_mm=297),
    _it("S10plusCNL-PP съединител S10 PLUS дълъг (стъпка 464 mm) с подложка", 12.5, system="S10PLUS", role="connector_bracket", price_source="indicative", row_spacing_mm=464),
    # ---------------- CompactFLAT GS (bifacial / green roof / CompactGROUND) ----------------
    _it("GS15FB преден носач GS15", 18.0, system="GS", role="front_bracket", price_source="indicative", doc=DOCS["GS"]["assembly_gs15"]),
    _it("GS15CNS съединител къс GS15", 21.0, system="GS", role="connector_bracket", price_source="indicative"),
    _it("GS15EB заден (краен) носач GS15", 18.0, system="GS", role="end_bracket", price_source="indicative"),
    _it("GS10plusFB преден/краен носач GS10 PLUS", 18.0, system="GS", role="front_bracket", price_source="indicative", doc=DOCS["GS"]["assembly_gs10plus"]),
    _it("GS10plusMB среден носач GS10 PLUS", 22.0, system="GS", role="middle_bracket", price_source="indicative"),
    _it("GS10plusCN съединител GS10 PLUS", 20.0, system="GS", role="connector_bracket", price_source="indicative"),
    # ---------------- CompactFLAT SN2 (base rails) ----------------
    _it("SNLSFB преден носач SN2 (дълга страна)", 7.5, system="SN2", role="front_bracket", price_source="indicative"),
    _it("SNLS10RB заден носач SN2 10° (дълга страна)", 9.5, system="SN2", role="end_bracket", price_source="indicative"),
    _it("SNLS05RB заден носач SN2 5° (дълга страна)", 9.0, system="SN2", role="end_bracket", price_source="indicative"),
    _it("BR1980 базова шина 1980 mm (SN2)", 15.5, system="SN2", role="base_rail", price_source="indicative", length_m=1.98),
    _it("BR5800 базова шина 5800 mm (SN2)", 42.0, system="SN2", role="base_rail", price_source="indicative", length_m=5.8),
    _it("BRCNSN съединител за базова шина SN2", 2.4, system="SN2", role="rail_connector", small=True, price_source="indicative"),
    _it("Sx10WD-2175 ветрозащитен дефлектор 10° SN2, 2175 mm", 11.5, system="SN2", role="wind_deflector", price_source="indicative", lengths_mm=[1850, 2175, 2450]),
    _it("AB8x18S болт с вътрешен шестостен M8×18 назъбен (SN2)", 0.2, system="SN2", role="screw", small=True, price_source="indicative"),
    _it("APA-SN единична връзка към покривен анкер SN2", 14.0, system="SN2", role="roof_anchor", price_source="indicative"),
    # ---------------- generic site-supplied items used by rules ----------------
    {"category": "mounting", "name": "Баластен блок бетон 40×20×10 cm (≈18 kg)", "purchase_price": 3.2, "specs": {"weight_kg": 18, "price_source": "indicative", "role": "ballast", "note": "Минимална якост на натиск C20/25; брой по статичния доклад AEROTOOL"}},
    {"category": "mounting", "name": "Защитна подложка (строителна защита) за хидроизолация", "purchase_price": 1.5, "specs": {"role": "protection_pad", "price_source": "indicative"}},
    {"category": "mounting", "name": "Метална покривна плоча/обшивка към шпилка (етернит/шисти, доставка клиент)", "purchase_price": 4.0, "specs": {"role": "flashing", "price_source": "indicative"}},
] + _rails()

# --------------------------------------------------------------------------------------
# Roof / terrain types
# --------------------------------------------------------------------------------------
ROOF_TYPES: list[dict] = [
    {"code": "tile", "label_bg": "Покрив с керемиди — CompactPITCH XM-F", "label_en": "Tile roof — CompactPITCH XM-F", "pricing_mode": "detailed", "lump_price_per_module": 124.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 25.0, "sort_order": 1,
     "notes": "Куки XM-F върху ребрата (стъпка ≤1.2 m, по AEROTOOL), гъвкава ламарина XM-FCM, шини X50 Click, скоби CLM10/CLE10. Наклон 10–75°, сняг до 6.0 kN/m², вятър 2.4 kN/m²."},
    {"code": "tile_xt", "label_bg": "Покрив с керемиди — класическа кука XT (чукова/click)", "label_en": "Tile roof — CompactPITCH XT hook", "pricing_mode": "detailed", "lump_price_per_module": 118.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 25.0, "sort_order": 2,
     "notes": "Регулируема алуминиева кука XT40 (или XT25/35/SLIM), 2× SDS-W 8×100, шини X40/X50. Подходяща и за шиндли, вълнообразни и сандвич покриви."},
    {"code": "tile_xtr", "label_bg": "Покрив с керемиди — XT-R 2.0 + метална керемида XM-B (без рязане)", "label_en": "Tile roof — XT-R 2.0 with XM-B replacement tile", "pricing_mode": "detailed", "lump_price_per_module": 128.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 25.0, "sort_order": 3,
     "notes": "Кука XT-R 2.0 с базова плоча + метална заместваща керемида XM-BC (бетон) или XM-B26/B25.1 (глина). Изберете правилната керемида по таблицата за съвместимост."},
    {"code": "plain_tile", "label_bg": "Плоски керемиди (бобровка) — CompactPITCH XM-PL", "label_en": "Plain/beaver tile roof — CompactPITCH XM-PL", "pricing_mode": "detailed", "lump_price_per_module": 126.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.1, "waste_pct": 8.0, "default_tilt_deg": 35.0, "sort_order": 4,
     "notes": "Кука XM-PL30X към контралетвата + плоска метална керемида XM-PLR/PLB."},
    {"code": "lt_sheet", "label_bg": "LT ламарина — CompactMETAL TL25/TL38 мостове (модули изправени)", "label_en": "Trapezoidal sheet — CompactMETAL TL bridges (portrait)", "pricing_mode": "detailed", "lump_price_per_module": 62.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 10.0, "sort_order": 5,
     "notes": "Без дълги шини: мост TL25 (гребени 100–210 mm) или TL38 (211–333 mm) на всяка скоба, 4× MSS 6×25 на мост, скобите директно на моста. 2 модула = 6 моста, 4 CLE10, 2 CLM10. Ламарина ≥0.5 mm Al / 0.4 mm стомана, наклон 5–45°."},
    {"code": "lt_sheet_ts", "label_bg": "LT ламарина — CompactMETAL TS15 къси шини (модули легнали)", "label_en": "Trapezoidal sheet — CompactMETAL TS short rails (landscape)", "pricing_mode": "detailed", "lump_price_per_module": 58.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 10.0, "sort_order": 6,
     "notes": "Къса шина TS15 (или TS08) върху гребена с EPDM, ≥2× MSS 6×25 (3-ти винт по план); скоби CLE10/CLM10 директно. Най-икономичната система за халета."},
    {"code": "standing_seam", "label_bg": "Фалцова ламарина (стоящ фалц) — CompactMETAL TM", "label_en": "Standing-seam metal roof — CompactMETAL TM", "pricing_mode": "detailed", "lump_price_per_module": 72.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 15.0, "sort_order": 7,
     "notes": "Без пробиване: фалцова скоба с къса шина (TMDS08 двоен фалц по подразбиране; сменете с TMM08/TMR08/TMRD08/TMK по типа фалц), скоби CLE10/CLM10 директно. Наклон до 70°, сняг до 5.4 kN/m²."},
    {"code": "sandwich", "label_bg": "Сандвич панел — CompactMETAL TR (самоносеща шина към столиците)", "label_en": "Sandwich panel roof — CompactMETAL TR", "pricing_mode": "detailed", "lump_price_per_module": 84.0, "rails_per_module": 2, "rail_stock_length_m": 5.8, "fixation_spacing_m": 1.5, "waste_pct": 5.0, "default_tilt_deg": 10.0, "sort_order": 8,
     "notes": "TR15 конзоли само над столиците (стъпка на столиците — реалната, тук 1.5 m по подразбиране), шини TR59-5800, винт SDS-12 с втулка SP20 + MSS 6×25. Панел 60–162 mm, 'проходим' по EN 14509."},
    {"code": "fibre_cement", "label_bg": "Етернит / вълнообразна ламарина — CompactPITCH XW шпилки", "label_en": "Corrugated fibre-cement / sheet — CompactPITCH XW hanger bolts", "pricing_mode": "detailed", "lump_price_per_module": 80.0, "rails_per_module": 2, "rail_stock_length_m": 4.4, "fixation_spacing_m": 1.2, "waste_pct": 8.0, "default_tilt_deg": 15.0, "sort_order": 9,
     "notes": "Шпилки XW12250CL в столиците/ребрата през гребена на вълната, шини X40 (4400 mm), скоби CLE10/CLM10. Метална плоча към шпилката при етернит — доставка клиент."},
    {"code": "flat_concrete", "label_bg": "Плосък покрив — CompactFLAT S10 юг 10° (баласт)", "label_en": "Flat roof — CompactFLAT S10 south 10° (ballast)", "pricing_mode": "detailed", "lump_price_per_module": 95.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 10.0, "sort_order": 10,
     "notes": "Фолио/битум/бетон без пробиване. Носачи S10FB (преден), S10CNS (между редовете, 380 mm) и S10EB (краен), дефлектор S10WD на модул, CLE10 PLUS/CLM10. Баласт и анкери APA — по статичния доклад AEROTOOL; 1200 mm от ръба."},
    {"code": "flat_ew", "label_bg": "Плосък покрив — CompactFLAT S10 PLUS изток/запад 10° (баласт)", "label_en": "Flat roof — CompactFLAT S10 PLUS east-west 10°", "pricing_mode": "detailed", "lump_price_per_module": 88.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 10.0, "sort_order": 11,
     "notes": "Двойни редове без дефлектори: S10FB предни, S10plusMB среден под билото, S10plusCNS между двойните редове. Най-висока плътност (до 192 модула на поле)."},
    {"code": "flat_bifacial", "label_bg": "Плосък/зелен покрив, бифациални — CompactFLAT GS15 юг (повдигната)", "label_en": "Flat/green roof, bifacial — CompactFLAT GS15", "pricing_mode": "detailed", "lump_price_per_module": 120.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 15.0, "sort_order": 12,
     "notes": "≈400 mm над покрива за зелени покриви и бифациален добив. Носачи GS15FB/GS15CNS/GS15EB, скоби CLEG10/CLMG10, баластни вани BT-880/BT-2050."},
    {"code": "ground_ballast", "label_bg": "Терен — CompactGROUND GS15 (баластна, без набиване)", "label_en": "Ground — CompactGROUND GS15 ballasted (no piling)", "pricing_mode": "detailed", "lump_price_per_module": 125.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 1.15, "waste_pct": 0.0, "default_tilt_deg": 15.0, "sort_order": 13,
     "notes": "За терени, където набиването не е икономично (сметища, малки обекти). GS15 носачи върху изравнена основа/бетонни плочи, баласт по AEROTOOL; за по-големи паркове — класическа набита конструкция (тип 'Наземна конструкция')."},
    {"code": "ground", "label_bg": "Наземна конструкция — стоманена, набити/бетонирани опори", "label_en": "Ground mount — steel, rammed/concrete posts", "pricing_mode": "detailed", "lump_price_per_module": 83.0, "rails_per_module": 2, "rail_stock_length_m": 3.55, "fixation_spacing_m": 2.5, "waste_pct": 5.0, "default_tilt_deg": 30.0, "sort_order": 14,
     "notes": "Стоманени маси 2V/3V, фундаменти/забити профили. Разстояние между редовете за избягване на засенчване."},
]

# Rules: (roof_type, item name, basis, factor, round_up)
# basis per_clamp = mid + end clamp positions (= number of support points along the module long sides)
_COMMON_RAIL = lambda rt, rail="X50-3550 монтажна шина 3550 mm", conn="XPCN съединител за шина X40/X50": [  # noqa: E731
    (rt, rail, "per_rail", 1, True),
    (rt, conn, "per_connector", 1, True),
    (rt, "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    (rt, "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    (rt, "XCL50 капачка лява за шина X50", "per_line", 1, True),
    (rt, "XCR50 капачка дясна за шина X50", "per_line", 1, True),
    (rt, "CLP-M кабелна клипса за модул", "per_module", 2, True),
    (rt, "CLP-R кабелна клипса за шина", "per_module", 1, True),
    (rt, "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_line", 1, True),
]

_DIRECT_CLAMPS = lambda rt: [  # noqa: E731
    (rt, "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
    (rt, "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
    (rt, "CLP-M кабелна клипса за модул", "per_module", 2, True),
    (rt, "CLP-U универсална кабелна клипса", "per_module", 1, True),
    (rt, "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_module", 0.25, True),
]

RULES: list[tuple[str, str, str, float, bool]] = (
    # tile — XM-F (same as the real quote 64845)
    _COMMON_RAIL("tile") + [
        ("tile", "XM-F кука за керемиден покрив (регулируема)", "per_fixation", 1, True),
        ("tile", "XM-FSP опорна плоча за кука", "per_fixation", 0.75, True),
        ("tile", "XM-FCMR покривна ламарина среден размер, червена", "per_fixation", 1, True),
        ("tile", "SDS-W 8×100 самонарезен винт за дърво (A2)", "per_fixation", 2, True),
        ("tile", "GSC 10×30 фиксиращ винт (кука↔шина)", "per_fixation", 1, True),
    ]
    # tile — XT classic hook
    + _COMMON_RAIL("tile_xt") + [
        ("tile_xt", "XT40 алуминиева кука с чукова глава, регулируема", "per_fixation", 1, True),
        ("tile_xt", "SDS-W 8×100 самонарезен винт за дърво (A2)", "per_fixation", 2, True),
    ]
    # tile — XT-R + XM-B
    + _COMMON_RAIL("tile_xtr") + [
        ("tile_xtr", "XT-R 2.0 кука за керемиди с интегриран бърз съединител", "per_fixation", 1, True),
        ("tile_xtr", "XT-R базова плоча 100", "per_fixation", 1, True),
        ("tile_xtr", "XM-BC метална заместваща керемида за бетонни керемиди (с клин)", "per_fixation", 1, True),
        ("tile_xtr", "SDS-W 8×100 самонарезен винт за дърво (A2)", "per_fixation", 2, True),
        ("tile_xtr", "GSC 10×30 фиксиращ винт (кука↔шина)", "per_fixation", 1, True),
    ]
    # plain tile — XM-PL
    + _COMMON_RAIL("plain_tile") + [
        ("plain_tile", "XM-PL30X кука за плоски керемиди (бобровка)", "per_fixation", 1, True),
        ("plain_tile", "XM-PLR плоска метална керемида червена", "per_fixation", 1, True),
        ("plain_tile", "SDS-W 8×100 самонарезен винт за дърво (A2)", "per_fixation", 2, True),
    ]
    # trapezoidal — TL25 bridges (direct)
    + _DIRECT_CLAMPS("lt_sheet") + [
        ("lt_sheet", "CompactMETAL TL25 трапецовиден мост 250 mm с EPDM", "per_clamp", 1, True),
        ("lt_sheet", "MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", "per_clamp", 4, True),
    ]
    # trapezoidal — TS15 short rails (direct)
    + _DIRECT_CLAMPS("lt_sheet_ts") + [
        ("lt_sheet_ts", "CompactMETAL TS15 къса шина 150 mm с EPDM за LT ламарина", "per_clamp", 1, True),
        ("lt_sheet_ts", "MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", "per_clamp", 3, True),
    ]
    # standing seam — TM (direct)
    + _DIRECT_CLAMPS("standing_seam") + [
        ("standing_seam", "TMDS08 фалцова скоба за двоен фалц с къса шина 80 mm", "per_clamp", 1, True),
    ]
    # sandwich — TR
    + [
        ("sandwich", "TR59-5800 самоносеща шина 5800 mm (сандвич, 84 mm до модула)", "per_rail", 1, True),
        ("sandwich", "TRPCN59 съединител за шина TR59", "per_connector", 1, True),
        ("sandwich", "CompactMETAL TR15 конзола 150 mm за сандвич панел", "per_fixation", 1, True),
        ("sandwich", "SDS-12/185 E16 дълъг самопробивен винт 5.5×185 за столица (сандвич) с уплътнение", "per_fixation", 1, True),
        ("sandwich", "SP20 дистанционна втулка 20 mm за винт TR", "per_fixation", 1, True),
        ("sandwich", "MSS 6×25 самопробивен винт с EPDM шайба (ламарина)", "per_fixation", 2, True),
        ("sandwich", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
        ("sandwich", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
        ("sandwich", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("sandwich", "CLP-R кабелна клипса за шина", "per_module", 1, True),
        ("sandwich", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_line", 1, True),
    ]
    # fibre cement / corrugated — XW hanger bolts on X40
    + [
        ("fibre_cement", "X40-4400 монтажна шина 4400 mm", "per_rail", 1, True),
        ("fibre_cement", "XPCN съединител за шина X40/X50", "per_connector", 1, True),
        ("fibre_cement", "XW12250CL шпилка M12×250 с click адаптер за шина X40", "per_fixation", 1, True),
        ("fibre_cement", "Метална покривна плоча/обшивка към шпилка (етернит/шисти, доставка клиент)", "per_fixation", 1, True),
        ("fibre_cement", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
        ("fibre_cement", "CLE10 крайна скоба Click 30-46", "per_end_clamp", 1, True),
        ("fibre_cement", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("fibre_cement", "CLP-R кабелна клипса за шина", "per_module", 1, True),
        ("fibre_cement", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_line", 1, True),
    ]
    # flat — S10 south (bracket positions = clamp positions: front half FB, rear half CN/EB)
    + [
        ("flat_concrete", "S10FB-PP преден носач S10 с предпазна подложка", "per_clamp", 0.5, True),
        ("flat_concrete", "S10CNS-PP съединител S10/25 (стъпка 380 mm) с подложка", "per_clamp", 0.3, True),
        ("flat_concrete", "S10EB-PP заден (краен) носач S10 с подложка", "per_clamp", 0.2, True),
        ("flat_concrete", "S10WD-2050 ветрозащитен дефлектор 10°, 2050 mm", "per_module", 1, True),
        ("flat_concrete", "CLP-WD клипса за ветрозащитен дефлектор (CompactFLAT S)", "per_module", 2, True),
        ("flat_concrete", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
        ("flat_concrete", "CLE10 PLUS крайна скоба Click 30-46, дължина 80 mm (CompactFLAT)", "per_end_clamp", 1, True),
        ("flat_concrete", "STS 8×16 самонарезен винт M8×16 (CompactFLAT)", "per_clamp", 1, True),
        ("flat_concrete", "SCS 8×20 резбонарезен комбиниран винт M8×20 (CompactFLAT)", "per_module", 2, True),
        ("flat_concrete", "Баластен блок бетон 40×20×10 cm (≈18 kg)", "per_module", 4, True),
        ("flat_concrete", "PP200 строителна защитна подложка за баластни блокове/вани", "per_module", 2, True),
        ("flat_concrete", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("flat_concrete", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_module", 0.25, True),
    ]
    # flat — S10 PLUS east-west
    + [
        ("flat_ew", "S10FB-PP преден носач S10 с предпазна подложка", "per_clamp", 0.3, True),
        ("flat_ew", "S10plusMB-PP среден носач S10 PLUS с подложки (под билото изток/запад)", "per_clamp", 0.25, True),
        ("flat_ew", "S10plusCNS-PP съединител S10 PLUS къс (стъпка 297 mm) с подложка", "per_clamp", 0.2, True),
        ("flat_ew", "CLM10 средна скоба Click 30-46 (със заземяващи щифтове)", "per_mid_clamp", 1, True),
        ("flat_ew", "CLE10 PLUS крайна скоба Click 30-46, дължина 80 mm (CompactFLAT)", "per_end_clamp", 1, True),
        ("flat_ew", "STS 8×16 самонарезен винт M8×16 (CompactFLAT)", "per_clamp", 1, True),
        ("flat_ew", "Баластен блок бетон 40×20×10 cm (≈18 kg)", "per_module", 3, True),
        ("flat_ew", "PP200 строителна защитна подложка за баластни блокове/вани", "per_module", 2, True),
        ("flat_ew", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("flat_ew", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_module", 0.25, True),
    ]
    # flat — GS15 bifacial / green roof
    + [
        ("flat_bifacial", "GS15FB преден носач GS15", "per_clamp", 0.5, True),
        ("flat_bifacial", "GS15CNS съединител къс GS15", "per_clamp", 0.3, True),
        ("flat_bifacial", "GS15EB заден (краен) носач GS15", "per_clamp", 0.2, True),
        ("flat_bifacial", "CLMG10 средна скоба за рамка 30-50 mm (CompactFLAT GS)", "per_mid_clamp", 1, True),
        ("flat_bifacial", "CLEG10 крайна скоба за рамка 30-50 mm (CompactFLAT GS)", "per_end_clamp", 1, True),
        ("flat_bifacial", "SCS 8×20 резбонарезен комбиниран винт M8×20 (CompactFLAT)", "per_clamp", 1, True),
        ("flat_bifacial", "BT-880 баластна вана къса 880 mm", "per_module", 1, True),
        ("flat_bifacial", "Баластен блок бетон 40×20×10 cm (≈18 kg)", "per_module", 5, True),
        ("flat_bifacial", "PP200 строителна защитна подложка за баластни блокове/вани", "per_module", 2, True),
        ("flat_bifacial", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("flat_bifacial", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_module", 0.25, True),
    ]
    # ground — GS15 ballasted
    + [
        ("ground_ballast", "GS15FB преден носач GS15", "per_clamp", 0.5, True),
        ("ground_ballast", "GS15CNS съединител къс GS15", "per_clamp", 0.3, True),
        ("ground_ballast", "GS15EB заден (краен) носач GS15", "per_clamp", 0.2, True),
        ("ground_ballast", "CLMG10 средна скоба за рамка 30-50 mm (CompactFLAT GS)", "per_mid_clamp", 1, True),
        ("ground_ballast", "CLEG10 крайна скоба за рамка 30-50 mm (CompactFLAT GS)", "per_end_clamp", 1, True),
        ("ground_ballast", "SCS 8×20 резбонарезен комбиниран винт M8×20 (CompactFLAT)", "per_clamp", 1, True),
        ("ground_ballast", "BT-2050 баластна вана дълга 2050 mm", "per_module", 1, True),
        ("ground_ballast", "Баластен блок бетон 40×20×10 cm (≈18 kg)", "per_module", 6, True),
        ("ground_ballast", "CLP-M кабелна клипса за модул", "per_module", 2, True),
        ("ground_ballast", "WCL8-10 клема за заземителен проводник 6–10 mm² към шина", "per_module", 0.25, True),
    ]
)


# roof type code -> Aerocompact system code
ROOF_SYSTEM: dict[str, str] = {
    "tile": "XM-F", "tile_xt": "XT", "tile_xtr": "XT-R", "plain_tile": "XM-PL", "lt_sheet": "TL", "lt_sheet_ts": "TS",
    "standing_seam": "TM", "sandwich": "TR", "fibre_cement": "XW", "flat_concrete": "S10", "flat_ew": "S10PLUS",
    "flat_bifacial": "GS", "ground_ballast": "GS",
}


def system_for_roof(roof_code: str | None) -> dict | None:
    """Return the Aerocompact system record for a roof/terrain type code (None for generic ground mount)."""
    code = ROOF_SYSTEM.get(roof_code or "")
    if not code:
        return None
    return next((s for s in SYSTEMS if s["code"] == code), None)


def all_documents() -> list[dict]:
    """Flat list of every Aerocompact document (system, kind, url) for the API / docs page."""
    out = []
    for sys_code, docs in DOCS.items():
        for kind, url in docs.items():
            out.append({"system": sys_code, "kind": kind, "url": url})
    return out
