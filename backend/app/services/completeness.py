"""Pre-flight check of a quote: is everything the installer will have to buy or do actually in the quote?

The engine (pricing + engineering) adds the technical BOM automatically. This module looks at the *result* together
with the site survey (``project.params.survey``) and flags what is still missing or risky before the quote is sent to
the client: services that are often forgotten (scaffolding, grid documentation, commissioning protocols, waste
disposal), monitoring/internet, export limitation, missing or indicative prices, thin margin, slow deliveries …

Every finding is ``{code, level, title, detail, fix}`` where ``level`` ∈ ok | info | warn | bad and ``fix`` is an action
the UI can execute with one click: ``{"type": "add_item", "catalog_item_id", "qty", "target": "extra"|"electrical"}``
(target = which selections list to append to), ``{"type": "step", "step": "params"}`` or ``None``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..models import CatalogItem, Project, Quote
from .settings import get_setting

# Service / helper items the check can offer to add (seeded by seed.py; matched by name regex so renamed items still work)
SERVICE_ITEMS: dict[str, dict[str, Any]] = {
    "scaffold": {"pattern": r"скеле|подемн|вишка|scaffold|lift", "name": "Скеле / подемна техника — наем", "target": "extra"},
    "grid_docs": {"pattern": r"проектиран|документац|присъедин|съгласув|ЕРП", "name": "Проектиране и документация за присъединяване", "target": "extra"},
    "commissioning": {"pattern": r"IEC\s*62446|пускови изпитв|протокол", "name": "Пускови изпитвания и протоколи по IEC 62446-1, обучение на клиента", "target": "extra"},
    "insurance": {"pattern": r"застрахов", "name": "Застраховка СМР (строително-монтажни рискове)", "target": "extra"},
    "waste": {"pattern": r"извозван|отпадъц|опаковк", "name": "Извозване на опаковки и строителни отпадъци", "target": "extra"},
    "trench": {"pattern": r"изкоп|траншея", "name": "Изкопни работи за кабелна траншея (вкл. пясък, сигнална лента, засипване)", "target": "extra"},
    "tray": {"pattern": r"кабелна скара|кабелен канал|PVC канал", "name": "Кабелен канал PVC 60×40 mm с капак (м)", "target": "electrical"},
    "router_4g": {"pattern": r"4G|LTE|SIM", "name": "4G/LTE рутер със SIM карта за мониторинг (без интернет на обекта)", "target": "electrical"},
    "logger": {"pattern": r"wi-?fi|lan|dongle|логер|logger|stick|комуникационен модул", "name": "Wi-Fi/LAN комуникационен модул (логер) за инвертор", "target": "electrical"},
    "monitoring_setup": {"pattern": r"настройка на мониторинг", "name": "Монтаж и настройка на мониторинг (Wi-Fi/4G)", "target": "extra"},
    "fire_sign": {"pattern": r"противопожар|пожарн|табел.*ПВ|PV табел", "name": "Комплект предупредителни табели за ПБ и ЕРП (фасада, ГРТ, инвертор)", "target": "electrical"},
    "lightning_check": {"pattern": r"мълниезащит|LPS", "name": "Оглед и становище за мълниезащита (LPS) и свързване към съществуваща заземителна уредба", "target": "extra"},
    "roof_repair": {"pattern": r"ремонт на покрив|хидроизолац", "name": "Ремонт / хидроизолация на покрива около проходите (резерв)", "target": "extra"},
}


def _find_item(items: list[CatalogItem], key: str) -> CatalogItem | None:
    spec = SERVICE_ITEMS[key]
    exact = next((i for i in items if i.name == spec["name"]), None)
    if exact:
        return exact
    rx = re.compile(spec["pattern"], re.I)
    cands = [i for i in items if i.category in ("service", "monitoring", "electrical", "other", "transport") and rx.search(i.name)]
    return cands[0] if cands else None


def _fix_add(items: list[CatalogItem], key: str, qty: float = 1) -> dict[str, Any] | None:
    it = _find_item(items, key)
    if not it:
        # no such article in the (curated) catalog → offer a manual line; the price is entered in the quote
        return {"type": "add_line", "name": SERVICE_ITEMS[key]["name"], "qty": qty, "target": SERVICE_ITEMS[key]["target"], "price": 0.0}
    return {"type": "add_item", "catalog_item_id": it.id, "qty": qty, "target": SERVICE_ITEMS[key]["target"], "name": it.name, "price": it.price_for(0)}


def _has(lines: list[Any], pattern: str) -> bool:
    rx = re.compile(pattern, re.I)
    return any(not l.excluded and rx.search(l.name or "") for l in lines)


def _roles(lines: list[Any]) -> set[str]:
    return {(l.meta or {}).get("role") for l in lines if not l.excluded and (l.meta or {}).get("role") and not (l.meta or {}).get("missing_item")}


def check(db: Session, q: Quote) -> dict[str, Any]:
    project: Project = q.project
    sel = q.selections or {}
    info = sel.get("_info") or {}
    design = info.get("design") or {}
    ac = design.get("ac") or {}
    params = project.params or {}
    survey = params.get("survey") or {}
    pricing_cfg = get_setting(db, "pricing")
    proc_cfg = get_setting(db, "procurement") or {}
    items = db.query(CatalogItem).filter(CatalogItem.active.is_(True)).all()
    lines = [l for l in q.lines if not l.excluded]
    roles = _roles(lines)
    sections = {l.section for l in lines}
    kwp = float(info.get("kwp") or 0)
    n_inv = int(info.get("inverter_qty") or design.get("inverters") or 1)
    ac_kw = float(info.get("ac_kw") or 0)
    conn = float(project.connected_power_kw or 0)
    roof = project.roof_type or "tile"
    from .site_kind import ROOF_KINDS, project_kind

    kind = project_kind(db, project)
    on_roof = kind in ROOF_KINDS  # scaffold, roof condition, LPS … only matter on a building
    needs_trench = kind in ("ground", "fence")
    is_flat = kind == "flat"
    from .pricing import cable_modes

    modes = cable_modes(sel)
    out: list[dict[str, Any]] = []

    def add(code: str, level: str, title: str, detail: str = "", fix: dict[str, Any] | None = None, group: str = "bom") -> None:
        out.append({"code": code, "level": level, "title": title, "detail": detail, "fix": fix, "group": group})

    # ------------------------------------------------------------------ core BOM
    if "modules" not in sections or not any(l.section == "modules" and l.qty > 0 for l in lines):
        add("modules", "bad", "Няма фотоволтаични модули в офертата", "Изберете панел и разположение (стъпки Разположение / Оборудване).", {"type": "step", "step": "layout"})
    else:
        add("modules", "ok", f"Модули: {info.get('panel_qty', 0)} бр. / {kwp:g} kWp")
    if not any(l.key == "inverter" or l.key.startswith("inverter:") for l in lines):
        add("inverter", "bad", "Няма инвертор", "Изберете инвертор в стъпка Оборудване.", {"type": "step", "step": "equipment"})
    else:
        add("inverter", "ok", f"Инвертор(и): {n_inv} бр., {ac_kw:g} kW AC")
    if "construction" not in sections:
        add("mounting", "bad", "Няма монтажна конструкция", "Проверете типа покрив и правилата за конструкция.", {"type": "step", "step": "materials"})
    else:
        add("mounting", "ok", "Конструкция: включена")
    compat_info = info.get("compat") or {}
    for b in compat_info.get("blocked") or []:
        add("compat", "bad", "Несъвместимо оборудване", b, {"type": "step", "step": "equipment"})
    covered_roles = set(info.get("covered_roles") or [])
    nq_roles = set(info.get("not_quoted_roles") or [])
    roles = roles | covered_roles
    missing_roles = [l for l in lines if (l.meta or {}).get("missing_item")]
    if missing_roles:
        add("missing_items", "bad", f"{len(missing_roles)} инженерни позиции без артикул в каталога", "; ".join((l.name or "")[:60] for l in missing_roles[:5]) + (" …" if len(missing_roles) > 5 else "") + ". Добавете артикул с тази роля в Каталог.", {"type": "nav", "to": "/catalog"})
    nq = info.get("not_quoted") or []
    if nq:
        add("not_quoted", "info", f"{len(nq)} инженерни позиции не се офертират (няма такъв артикул в каталога)", "; ".join(str(x)[:60] for x in nq[:6]) + (" …" if len(nq) > 6 else "") + ". Ако са нужни, добавете артикул с тази роля в Каталог.", {"type": "nav", "to": "/catalog"})
    if covered_roles:
        add("switchboard_cover", "ok", "AC/DC защитите са включени в окомплектованото табло")
    for kit in info.get("kit_included") or []:
        add("kit", "ok", f"Не се офертира: {kit}")
    if info.get("addons_total"):
        add("addons", "ok", f"Допълнителни скрити разходи: {float(info['addons_total']):,.2f} {q.currency} — разпределени в цената на всички видими редове".replace(",", " "), group="ops")
    for rk, title in (("pv_cable", "Соларен кабел"), ("mc4_pair", "MC4 конектори"), ("ac_cable", "AC кабел"), ("ac_mcb", "AC прекъсвач"), ("ac_rcd", "Дефектнотокова защита"), ("pe_cable", "Заземителен проводник"), ("labels", "Предупредителни табели")):
        if rk in nq_roles:
            continue  # reported once above as "not quoted"
        if rk == "mc4_pair" and modes["mc4"] == "kit":
            continue
        if rk not in roles and not any((l.meta or {}).get("role") == rk for l in lines):
            hint = ("Ръчен избор на кабели — добавете ред в Материали → Кабели." if modes["cables"] == "manual" and rk in ("pv_cable", "ac_cable", "pe_cable")
                    else "Автоматичното електро оборудване може да е изключено (Материали → Автоматично ел. оборудване).")
            add(f"role_{rk}", "warn", f"{title}: няма ред в офертата", hint, {"type": "step", "step": "materials"})
    if not any(r in roles for r in ("dc_spd", "ac_spd")):
        add("spd", "warn", "Няма катоден отводител (SPD) DC/AC", "Ако инверторът няма вграден SPD тип II, добавете го — изисква се от ЕРП и застрахователите.", {"type": "step", "step": "materials"})
    if not any(r in roles for r in ("earth_rod", "earth_clamp", "bonding_clamp", "earth_tape")) and not _has(lines, r"заземител|заземяв|WCL|earth"):
        add("earthing", "info" if nq_roles & {"earth_rod", "bonding_clamp", "earth_strip", "pe_cable"} else "warn", "Няма заземяване на конструкцията", "Добавете заземителен кол/клеми за изравняване на потенциалите.", {"type": "step", "step": "materials"})

    # ------------------------------------------------------------------ monitoring / grid
    has_logger = _has(lines, SERVICE_ITEMS["logger"]["pattern"]) or any("wifi" in (l.name or "").lower() or "dongle" in (l.name or "").lower() for l in lines)
    if not has_logger:
        add("logger", "warn", "Няма комуникационен модул (Wi-Fi/LAN логер)", "Повечето инвертори го продават отделно. Без него няма мониторинг и клиентът ще го поиска след монтажа.", _fix_add(items, "logger", n_inv))
    else:
        add("logger", "ok", "Мониторинг: комуникационен модул включен")
    if survey.get("internet") == "none" and not _has(lines, SERVICE_ITEMS["router_4g"]["pattern"]):
        add("internet", "warn", "На обекта няма интернет — нужен 4G рутер", "От огледа: без Wi-Fi/LAN. Добавете 4G/LTE рутер със SIM.", _fix_add(items, "router_4g"))
    if not _has(lines, SERVICE_ITEMS["monitoring_setup"]["pattern"]) and not _has(lines, r"пуск и настройка"):
        add("monitoring_setup", "info", "Настройка на мониторинг не е посочена като услуга", "", _fix_add(items, "monitoring_setup"))
    if project.purpose == "self" and conn > 0 and ac_kw > conn * 1.001 and "smart_meter" not in roles:
        add("export_limit", "warn", f"AC мощност {ac_kw:g} kW > присъединена {conn:g} kW без ограничител на износа", "За „само за собствени нужди“ ЕРП изисква ограничаване на отдаваната мощност: smart meter + CT към инвертора.", {"type": "step", "step": "materials"})
    elif project.purpose == "self" and "smart_meter" not in roles and not _has(lines, r"smart meter|смарт метър|измервател"):
        add("export_limit", "info", "Няма smart meter за нулев износ", "Ако договорът с ЕРП е без продажба, добавете измервател с CT за ограничение на износа.", {"type": "step", "step": "materials"})
    if conn > 0 and ac_kw > conn * 1.001 and project.purpose != "self":
        add("grid_capacity", "warn", f"Инверторната мощност {ac_kw:g} kW надвишава присъединената {conn:g} kW", "Нужно е искане за увеличение на мощността към ЕРП (срок 1–3 месеца) — включете го в срока и цената.", None, "grid")
    if not _has(lines, SERVICE_ITEMS["grid_docs"]["pattern"]):
        add("grid_docs", "warn", "Няма проектна документация и съгласуване с ЕРП", "Становище за присъединяване, проект по част Електро, договор за достъп/изкупуване — работа, която иначе остава неплатена.", _fix_add(items, "grid_docs"), "grid")
    else:
        add("grid_docs", "ok", "Документация и ЕРП: включени", group="grid")
    mb = survey.get("main_breaker_a")
    need_a = ac.get("main_breaker_a") or ac.get("breaker_a")
    if mb and need_a and float(mb) < float(need_a):
        add("main_breaker", "warn", f"Главният прекъсвач на обекта ({mb} A) е по-малък от необходимия ({need_a} A)", "Предвидете подмяна на главния прекъсвач/ГРТ или съгласувайте с ЕРП.", {"type": "step", "step": "materials"}, "grid")
    if not _has(lines, SERVICE_ITEMS["commissioning"]["pattern"]) and not _has(lines, r"пуск"):
        add("commissioning", "warn", "Няма пускови изпитвания/протоколи (IEC 62446-1)", "Протоколите от изпитванията се изискват при приемането и за гаранцията.", _fix_add(items, "commissioning"), "grid")
    if not _has(lines, SERVICE_ITEMS["fire_sign"]["pattern"]) and "labels" not in roles:
        add("fire_sign", "info", "Табели за пожарна безопасност и ЕРП", "", _fix_add(items, "fire_sign"), "grid")

    # ------------------------------------------------------------------ site / works (from survey)
    height = float(survey.get("building_height_m") or 0)
    access = survey.get("roof_access") or ""
    if not survey:
        add("survey", "warn", "Няма въведен оглед на обекта", "Попълнете секция „Оглед“ в стъпка Параметри — височина, достъп, състояние на покрива, ЕРП, интернет. Това е източникът на най-честите непредвидени разходи.", {"type": "step", "step": "params"}, "site")
    else:
        add("survey", "ok", "Оглед: попълнен" + (f" ({survey.get('surveyed_at')})" if survey.get("surveyed_at") else ""), group="site")
    lays = list(project.layouts)
    if lays and not any(getattr(l, "visual_path", None) for l in lays):
        if any(l.image_path for l in lays):
            add("visual", "info", "Няма визуализация върху снимката", "Запазете разположението отново (стъпка Разположение → раздел „Визуализация“), за да се генерира реалистична визуализация за клиента.", {"type": "step", "step": "layout"}, "site")
        else:
            add("visual", "info", "Няма снимка на покрива", "Качете снимка на покрива в стъпка Разположение — системата ще покаже на клиента как ще изглежда инсталацията и ще я включи в офертата.", {"type": "step", "step": "layout"}, "site")
    else:
        if lays:
            add("visual", "ok", "Визуализация върху снимка: налична", group="site")
    if on_roof and (height >= 6 or access in ("scaffold", "lift", "crane")) and not _has(lines, SERVICE_ITEMS["scaffold"]["pattern"]):
        days = max(1, int(q.execution_days or info.get("execution_days") or 2))
        add("scaffold", "warn", f"Нужно скеле/подемна техника (височина {height:g} m, достъп: {access or 'неясен'})", "Наемът на скеле/вишка не е в офертата.", _fix_add(items, "scaffold", days), "site")
    elif on_roof and not survey.get("building_height_m"):
        add("scaffold", "info", "Височина на сградата не е въведена", "Над ~6 m обикновено е нужно скеле или вишка.", {"type": "step", "step": "params"}, "site")
    if on_roof and survey.get("roof_condition") == "poor":
        add("roof_condition", "bad", "Покривът е в лошо състояние според огледа", "Монтажът върху компрометиран покрив е риск за гаранцията. Предвидете ремонт/хидроизолация или го изключете писмено от обхвата.", _fix_add(items, "roof_repair"), "site")
    elif on_roof and survey.get("roof_condition") == "fair":
        add("roof_condition", "info", "Покрив в задоволително състояние", "Опишете в офертата, че ремонт на покрива не е включен.", None, "site")
    if roof in ("tile", "tile_xt", "tile_xtr", "plain_tile") and float(survey.get("roof_age_years") or 0) > 25:
        add("roof_age", "info", f"Керемиден покрив на {survey.get('roof_age_years')} г.", "Предвидете резерв от счупени керемиди (5–10 бр.).", None, "site")
    if needs_trench and not _has(lines, SERVICE_ITEMS["trench"]["pattern"]):
        run = float(survey.get("trench_m") or 0) or (float(params.get("ac_run_m") or 0) + float(params.get("dc_run_m") or 0))
        what = "Соларна ограда" if kind == "fence" else "Наземна централа"
        src = "по огледа" if survey.get("trench_m") else "по параметрите"
        add("trench", "warn", f"{what} без изкопни работи за кабелите", f"Траншея за DC/AC кабели (~{run:g} m {src}).", _fix_add(items, "trench", max(5, round(run))), "site")
    if needs_trench:
        soil = survey.get("soil_type") or ""
        if soil == "rock":
            add("soil", "warn", "Скалист терен според огледа", "Набиването/фундаментите и траншеята са по-скъпи — предвидете къртач/сондиране или бетонни блокове.", None, "site")
        elif soil == "fill":
            add("soil", "info", "Насипен терен", "Фундаментите трябва да стъпят под насипа — проверете дълбочината.", None, "site")
        if survey.get("machine_access") == "no":
            add("machine_access", "info", "Няма достъп за техника", "Изкопът и фундаментите се правят ръчно — увеличете труда/срока.", {"type": "step", "step": "labor"}, "site")
        if float(survey.get("terrain_slope_pct") or 0) > 10:
            add("slope", "info", f"Наклонен терен ({float(survey['terrain_slope_pct']):g} %)", "Стълбовете/опорите са с различна височина — проверете конструкцията.", None, "site")
    if kind == "fence":
        fl, fh = float(survey.get("fence_length_m") or 0), float(survey.get("fence_height_m") or 0)
        pw = sum(float(l.plane_w_m or 0) for l in lays)
        ph = max([float(l.plane_h_m or 0) for l in lays] or [0])
        if not fl:
            add("fence_len", "info", "Дължината на оградата не е въведена", "Въведете дължина и височина на оградата в огледа.", {"type": "step", "step": "params"}, "site")
        elif pw > fl * 1.02:
            add("fence_len", "warn", f"Разположението ({pw:g} m) е по-дълго от оградата ({fl:g} m)", "Коригирайте размера на равнината в стъпка Разположение.", {"type": "step", "step": "layout"}, "site")
        if fh and ph > fh * 1.02:
            add("fence_h", "info", f"Панелите ({ph:g} m) са по-високи от оградата ({fh:g} m)", "Проверете височината на стълбовете и допустимото по ЗУТ за огради.", None, "site")
        if survey.get("wind_exposure") == "high":
            add("fence_wind", "warn", "Силно ветровита зона", "Вертикалните панели поемат пълния вятърен натиск — нужна е статическа проверка на стълбовете/фундаментите.", None, "site")
        if survey.get("fence_base") == "wall":
            add("fence_wall", "info", "Монтаж към стена/фасада", "Проверете носимоспособността на стената и вида анкери (тухла/бетон/топлоизолация).", None, "site")
        elif survey.get("fence_base") == "existing":
            add("fence_existing", "info", "Монтаж към съществуваща ограда", "Проверете състоянието и фундаментите на оградата — тя ще носи и вятърния товар на панелите.", None, "site")
        pnl = next((l.catalog_item for l in lines if l.section == "modules" and l.catalog_item), None)
        if pnl is not None and not float((pnl.specs or {}).get("bifaciality") or 0):
            add("fence_bifacial", "info", "Монофациален модул за вертикална ограда", "При ограда изток–запад бифациалните модули дават ~25–35 % повече добив.", {"type": "step", "step": "equipment"}, "site")
    if on_roof and survey.get("has_lightning_protection") and not _has(lines, SERVICE_ITEMS["lightning_check"]["pattern"]):
        add("lps", "warn", "Сградата има мълниезащита — нужно съгласуване", "При съществуваща LPS конструкцията трябва да се свърже по правилата (разделително разстояние/еквипотенциал).", _fix_add(items, "lightning_check"), "site")
    if on_roof and survey.get("structure") == "wood" and not is_flat and not _has(lines, r"статичес|конструктив"):
        add("statics", "info", "Дървена покривна конструкция", "При тежки/бифациални модули поискайте статическа оценка.", None, "site")
    if float(survey.get("cable_route_m") or 0) > 0:
        route = float(survey["cable_route_m"])
        known = float(params.get("ac_run_m") or 0)
        if known and route > known * 1.3:
            add("cable_route", "warn", f"Кабелното трасе от огледа ({route:g} m) е по-дълго от AC дължината в параметрите ({known:g} m)", "Коригирайте AC/DC дължините в стъпка Параметри — иначе кабелите няма да стигнат.", {"type": "step", "step": "params"}, "site")
    if not _has(lines, SERVICE_ITEMS["tray"]["pattern"]) and not ({"conduit_32", "conduit_40", "pvc_pipe"} & roles):
        add("conduit", "info", "Няма тръба/канал за кабелите", "", _fix_add(items, "tray", 10), "site")

    # ------------------------------------------------------------------ labor / logistics
    if "labor" not in sections:
        add("labor", "bad", "Няма труд (монтаж и пуск)", "Изберете вариант за труд в стъпка Труд.", {"type": "step", "step": "labor"}, "ops")
    else:
        add("labor", "ok", "Труд: включен", group="ops")
    if not any(l.key == "transport" or l.section == "other" and "транспорт" in (l.name or "").lower() for l in lines):
        add("transport", "warn", "Няма транспорт до обекта", "", {"type": "step", "step": "labor"}, "ops")
    if (q.selections or {}).get("delivery_fees") is True and not any(l.key.startswith("delivery:") for l in lines) and float(proc_cfg.get("min_free_delivery", 0) or 0) == 0:
        add("delivery_fees", "info", "Няма такси за доставка от доставчици", "Ако доставчикът не доставя безплатно, добавете транспорта му в Настройки → Доставчици.", None, "ops")
    if not _has(lines, SERVICE_ITEMS["waste"]["pattern"]):
        add("waste", "info", "Извозване на опаковки/отпадъци не е включено", "", _fix_add(items, "waste"), "ops")
    if kwp >= 30 and not _has(lines, SERVICE_ITEMS["insurance"]["pattern"]):
        add("insurance", "info", "Застраховка СМР за обект над 30 kWp", "", _fix_add(items, "insurance"), "ops")
    spare = int(info.get("panel_spare") or 0)
    if kwp >= 20 and spare == 0:
        add("spare_modules", "info", "Няма резервни модули", "При 40+ модула е добра практика 1–2 резервни (Настройки → Ценообразуване → резерв модули %).", None, "ops")
    battery = design.get("battery") or {}
    if any(l.key == "battery" for l in lines) and modes["battery_cables"] == "kit":
        add("battery_acc", "ok", "Батерийни кабели: в комплекта с батерията", group="ops")
    elif any(l.key == "battery" for l in lines) and not any(r.startswith("battery_") for r in roles):
        add("battery_acc", "warn", "Батерия без кабели/предпазител/стойка", "Проверете ролите battery_* в Материали.", {"type": "step", "step": "materials"}, "ops")

    # ------------------------------------------------------------------ prices / margin / lead times
    unpriced = [l for l in lines if l.catalog_item_id and float(l.unit_price or 0) <= 0]
    if unpriced:
        add("unpriced", "bad", f"{len(unpriced)} позиции без цена", "; ".join((l.name or "")[:50] for l in unpriced[:4]) + (" …" if len(unpriced) > 4 else ""), {"type": "nav", "to": "/catalog"}, "price")
    indicative = [l for l in lines if l.catalog_item and (l.catalog_item.specs or {}).get("price_source") == "indicative"]
    if indicative:
        val = sum(float(l.total or 0) for l in indicative)
        add("indicative", "warn", f"{len(indicative)} позиции с ориентировъчна цена ({val:,.0f} {q.currency})", "Изпратете запитване (RFQ) към доставчиците и обновете цените преди офертата да стане обвързваща.", {"type": "rfq"}, "price")
    else:
        add("indicative", "ok", "Всички цени са от доставчик/ценова листа", group="price")
    max_age = int(proc_cfg.get("price_max_age_days") or 120)
    now = datetime.now(timezone.utc)
    stale = []
    for l in lines:
        ci = l.catalog_item
        if ci and ci.updated_at and ci.purchase_price:
            upd = ci.updated_at if ci.updated_at.tzinfo else ci.updated_at.replace(tzinfo=timezone.utc)
            if (now - upd).days > max_age and l.total and float(l.total) > 0.02 * float(q.subtotal or 1):
                stale.append(l)
    if stale:
        add("stale_prices", "info", f"{len(stale)} значими позиции с цена, непроменяна над {max_age} дни", "; ".join((l.name or "")[:40] for l in stale[:3]), {"type": "rfq"}, "price")
    unverified = [l for l in lines if l.catalog_item and l.section in ("modules", "inverter") and (l.catalog_item.specs or {}).get("specs_verified") is False]
    if unverified:
        add("unverified", "warn", "Технически параметри на основно оборудване не са потвърдени", "; ".join((l.name or "")[:40] for l in unverified[:3]) + ". Отворете каталожния лист и потвърдете Voc/Isc/мощност.", {"type": "nav", "to": "/catalog"}, "price")
    min_margin = float(pricing_cfg.get("min_margin_pct") or 10)
    cost = sum(float(l.purchase_price or 0) * float(l.qty or 0) for l in lines if l.purchase_price)
    if q.net_total and cost:
        margin_pct = 100 * (float(q.net_total) - cost) / float(q.net_total)
        if margin_pct < min_margin:
            add("margin", "bad", f"Марж {margin_pct:.1f} % под минимума {min_margin:g} %", "Проверете отстъпката и надценката в стъпка Оферта.", {"type": "step", "step": "quote"}, "price")
        else:
            add("margin", "ok", f"Марж {margin_pct:.1f} %", group="price")
    lead = int(info.get("lead_time_days") or 0)
    if lead > 21:
        add("lead_time", "warn", f"Най-бавната доставка е {lead} дни ({info.get('lead_bottleneck') or ''})", "Съобразете срока за изпълнение в офертата или изберете стратегия „най-бърза доставка“.", {"type": "step", "step": "equipment"}, "price")
    elif lead:
        add("lead_time", "ok", f"Доставка на материалите: ~{lead} дни", group="price")
    if q.execution_days and lead and q.valid_days and lead > (q.valid_days + int(q.execution_days)):
        add("schedule", "info", "Срокът на доставка надвишава валидността на офертата + монтажа", "Опишете в офертата, че срокът тече от потвърждението на доставчика.", None, "price")
    for w in sel.get("_warnings") or []:
        if "Липсва цена" in w or "Няма артикул" in w:
            continue
        add("engine", "info", w[:140], "", None, "engine")

    levels = {"bad": 0, "warn": 0, "info": 0, "ok": 0}
    for f in out:
        levels[f["level"]] += 1
    score = max(0, 100 - 25 * levels["bad"] - 8 * levels["warn"] - 2 * levels["info"])
    return {"quote_id": q.id, "score": score, "counts": levels, "ready": levels["bad"] == 0 and levels["warn"] == 0, "items": out,
            "groups": [("bom", "Оборудване и материали"), ("grid", "Мрежа, документи, пуск"), ("site", "Обект и монтаж"), ("ops", "Труд и логистика"), ("price", "Цени, марж, срокове"), ("engine", "Бележки от изчислението")]}


def apply_fixes(db: Session, q: Quote, fixes: list[dict[str, Any]]) -> None:
    """Append the chosen items to the quote selections (extra_items / electrical_items). Caller recalculates."""
    sel = dict(q.selections or {})
    extra = list(sel.get("extra_items") or [])
    elec = list(sel.get("electrical_items") or [])
    import uuid

    from ..models import QuoteLine

    for f in fixes:
        if f.get("type") == "add_line" and f.get("name"):
            name = str(f["name"])[:250]
            if any((l.name or "") == name and not l.excluded for l in q.lines):
                continue
            q.lines.append(QuoteLine(key=f"manual:{uuid.uuid4().hex[:8]}", section="electrical" if f.get("target") == "electrical" else "other",
                                     position=max((l.position or 0 for l in q.lines), default=-1) + 1, name=name, unit="бр.",
                                     qty=float(f.get("qty") or 1), unit_price=float(f.get("price") or 0), purchase_price=0.0,
                                     total=round(float(f.get("qty") or 1) * float(f.get("price") or 0), 2), source="manual", locked=True,
                                     hidden=False, meta={"from_completeness": True}))
            continue
        if f.get("type") != "add_item" or not f.get("catalog_item_id"):
            continue
        cid, qty = int(f["catalog_item_id"]), float(f.get("qty") or 1)
        lst = elec if f.get("target") == "electrical" else extra
        cur = next((x for x in lst if int(x.get("catalog_item_id") or x.get("item_id") or 0) == cid), None)
        if cur:
            cur["qty"] = qty
        else:
            lst.append({"catalog_item_id": cid, "qty": qty})
    sel["extra_items"], sel["electrical_items"] = extra, elec
    q.selections = sel
    from . import autosync

    autosync.mirror_to_project(db, q, {"extra_items": extra, "electrical_items": elec})
