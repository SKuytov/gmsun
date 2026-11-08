# gmsun — оферти за фотоволтаични централи / PV quoting suite

**gmsun** е уеб + Android приложение за фирми, които проектират и монтират фотоволтаични централи.
От снимка на покрива (или терена) до готова оферта в PDF и количествено-стойностна сметка (КСС) в Excel — за минути.

**gmsun** is a web + Android app for solar‑installation companies: from a roof photo to panel layout, bill of
materials, inverter/battery sizing and a client‑ready PDF quote + Excel BOM.

[🇧🇬 Български](#български) · [🇬🇧 English](#english) · [Deploy](docs/DEPLOY.md) · [Android](docs/ANDROID.md) · [Ръководство](docs/USER_GUIDE_BG.md)

---

## Български

### Какво прави

| Стъпка | Какво се случва |
| --- | --- |
| **1. Клиент и обект** | Данни за клиента, адрес на обекта, бележки. Всичко се записва автоматично. |
| **2. Параметри** | Присъединена мощност (kW), фази, тип покрив/основа (керемиди, бетон, LT ламарина, сандвич панел, наземна), желана батерия. |
| **3. Покрив и панели** | Качвате снимка на покрива. Системата разпознава покривната равнина (с ръчна корекция), отбелязвате препятствия (комини, прозорци), задавате реалните размери и **„Запълни автоматично“** подрежда панелите. Всеки панел може да се включи/изключи, премести или добави ръчно. Поддържат се няколко покривни равнини. |
| **4. Оборудване** | Избор на модул (с datasheet и линк към доставчика); автоматично **оразмеряване** на инвертор и батерия от цялото портфолио на доставчика (Deye, Solis, Sungrow, GoodWe, Huawei …) според мощността и kWp, с предупреждения за DC/AC съотношение, фази и присъединена мощност. Всичко може да се промени ръчно. |
| **5. Материали** | **Автоматично проектиране** по IEC 62548 / IEC 60364‑7‑712: стрингове (Voc при −20 °C, Vmp при 70 °C, MPPT входове), соларен кабел със сечение и дължина по пад на напрежение, стрингови предпазители (само когато правилото (Ns−1)·Isc·1,25 > макс. предпазител на модула ги изисква), DC табло със SPD T2 при трасе над 10 m (IEC 61643‑32), AC прекъсвач и ДТЗ по ръководството на Deye, AC кабел по ток и пад, батериен прекъсвач и кабел, PE и изравняване на потенциалите с клеми, укрепване (UV връзки, тръби, скоби), измерване (CT или смарт електромер). Конструкцията (шини X50, съединители, куки, скоби, винтове, капачки, клипси) по правила за всеки тип покрив. **Индустриални резерви**: 15 % за кабели, 10 % за дребни крепежи, настройваеми. Всичко е предварителен изглед и всичко се коригира ръчно. |
| **6. Труд и условия** | СМР по матрица „дни × работници“ или „по мощност“ (€/W), срок на изпълнение, гаранции, условия на плащане. |
| **7. Оферта** | **Проверка на офертата** — автоматичен одит „какво още трябва да се купи/направи/уточни“ (комуникационен модул, ограничител на износа, проектна документация, скеле/вишка по височина, 4G рутер без интернет, главен прекъсвач, извозване, застраховка СМР, резервни модули, ориентировъчни цени, непотвърдени параметри …) с бутон **„Добави“** за всяка препоръка и **„Пакет за клиента (ZIP)“** — едно обединено PDF „Пълно предложение“ + оферта, техническо досие, чертежи и каталожни листове. Редове с количества и цени (всеки ред е редактируем и „заключен“ срещу преизчисление), надценка, отстъпка, ДДС, аванс, валидност. Версии на офертата, статус, **PDF за клиента**, **PDF вътрешен** (с доставни цени и марж), **Excel КСС** (+ лист „Поръчка“ по доставчици с кодове и доставни цени) и **Техническо досие (PDF)** — показатели, стрингова таблица с проверки, еднолинейна схема, AC/батерия/заземяване, чертеж на разположението по равнини със стрингове и шини, монтажен план, пълна спецификация с извод на количествата, списък за поръчка и приложими стандарти. |

Още: каталог с внос на ценови листи на доставчика (Excel), правила за конструкция по тип покрив, матрица за СМР,
потребители и роли, фирмени данни и лого за PDF, двуезичен интерфейс (BG по подразбиране, EN превключвател),
PWA (работи и като „инсталирано“ приложение в браузъра) и Android приложение.

| **8. Поръчки и доставки** | От приетата оферта — **по една поръчка на доставчик** (PO‑2026‑0001 …) с всички материали, очаквани дати по срока на доставка, Excel за изпращане. **Получаване** на всяка позиция (частично или изцяло), статус на поръчката, **готовност на материалите %**, най‑ранен старт на монтажа. Проектът минава автоматично в „Поръчан“. |
| **9. Документи** | Архив на проекта **на вашия сървър**: всички генерирани оферти, досиета, КСС, запитвания и поръчки се записват автоматично; качвате снимки от огледа, договори, протоколи. |

Общи страници: **Табло** (проекти по статус, оферти с изтичаща валидност, закъсняващи доставки, здраве на каталога,
документи на сървъра), **Доставки** (всички отворени поръчки по всички проекти, филтри по статус/доставчик/закъснение),
**Каталог → Документи на сървъра** (сваля всички datasheets и ръководства на Aerocompact локално — нищо не зависи от
външни сайтове). В стъпка 2 има **Оглед на обекта** (височина, достъп, състояние на покрива, ЕРП, електромер, главен
прекъсвач, трасе, интернет, мълниезащита) — източникът на проверката на офертата.

### Бърз старт на сървъра (Ubuntu Server 24.04 / 26.04)

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
```

Една команда на чисто инсталиран сървър. Скриптът инсталира Docker, сваля проекта в `/opt/gmsun`, генерира
тайни ключове в `.env`, стартира PostgreSQL + API + уеб сървър + **pgAdmin** (редактор на базата данни като
phpMyAdmin на `http://<IP>/pgadmin/`), инсталира **Tailscale** (достъп от телефони и лаптопи отвсякъде без
отваряне на портове; с `TS_AUTHKEY=tskey-auth-…` влиза автоматично), настройва защитна стена, нощни резервни копия
и ротация на логове. След 2–3 минути отворете `http://<IP-на-сървъра>/`. Същата команда по‑късно **обновява** инсталацията.

Първоначален вход: `admin@gmsun.local` и паролата, която скриптът отпечата (в `/opt/gmsun/.env`).
**Сменете я веднага** от Настройки → Потребители.

Ръчна инсталация, HTTPS, резервни копия и обновяване: [docs/DEPLOY.md](docs/DEPLOY.md).

### Android

APK се генерира автоматично от GitHub Actions (Actions → *Android APK* → артефакт `gmsun-debug-apk`).
Инсталирайте го на телефона, при първо стартиране въведете адреса на сървъра (напр. `http://192.168.1.50`) и влезте.
Подробности и подписване за Google Play: [docs/ANDROID.md](docs/ANDROID.md).

### Каталог на доставчика (green-energy.bg) и datasheets

Каталогът се зарежда с **цялото продуктово портфолио на green-energy.bg** (388 артикула: панели, хибридни и мрежови
инвертори, батерии, аксесоари, табла, кабели, конектори, защити) заедно с линк към продуктовата страница и
**datasheet-а (PDF)** на всеки продукт. Техническите параметри (Wp, Voc, Isc, Vmp, размери, MPPT диапазон, входни
токове, батерийни напрежения, kWh, Ah …) са извлечени автоматично от datasheet-ите и се използват от инженерния
модул (стрингове, кабели, защити, съвместимост инвертор–батерия). Автоматично извлечените параметри са отбелязани
като **„непроверени характеристики“** — проверете ги срещу PDF-а (бутон „Datasheet“ в Каталога и в стъпка
„Оборудване“) и потвърдете със `specs_verified: true` в полето „Спецификации“.

- **Каталог → „Синхронизирай с green-energy.bg“** (администратор) обновява цени, линкове и нови продукти от магазина
  на доставчика; с опцията „datasheets“ изтегля и анализира и PDF-ите (няколко минути, кешират се в
  `DATA_DIR/datasheets`). От команден ред: `python -m app.services.supplier_sync --write-seed`.
- **Качване на собствен datasheet** за всеки артикул (Каталог → Редакция → „Качи datasheet“) с автоматично попълване
  на празните параметри.
- **Цени**: цените от сайта са преизчислени от BGN в EUR по 1,95583; не е ясно дали са с/без ДДС — проверете с
  доставчика и коригирайте надценката. Панелите на сайта са **без публична цена** (`0`) до попълване.
  Офертата ви предупреждава за всеки артикул без цена.

### Конструкция AEROCOMPACT® — пълен каталог

Вградени са **14 типа покрив/терен** с пълния набор компоненти на съответната система AEROCOMPACT (159 артикула с
артикулни номера, продуктови листове, инструкции за монтаж и чеклисти): керемиди (CompactPITCH XM‑F, XT, XT‑R + XM‑B,
XM‑PL за плоски керемиди), LT ламарина (CompactMETAL TL25/TL38 мостове и TS15 къси шини), фалц (CompactMETAL TM),
сандвич панел (CompactMETAL TR), етернит/битум (CompactPITCH XW шпилки), плосък покрив (CompactFLAT S10 юг, S10 PLUS
изток/запад), наземни (CompactGROUND GS15 баластна и бифациална) и универсална наземна. Количествата се изчисляват по
правилата от инструкциите на производителя (напр. TL25: 2 модула = 6 моста, 4 крайни + 2 средни скоби, 4× MSS 6×25 на
мост). Техническото досие включва раздел „Монтажна система AEROCOMPACT“ с техническите граници (наклон, отстояние,
сняг/вятър, рамка) и линкове към документите. Окончателното статично оразмеряване (стъпка на куките, баласт) се
потвърждава с AEROTOOL на производителя. Цените на елементите извън офертата на доставчика са **ориентировъчни**
(`price_source: indicative`) — заменете ги с актуални.

### Автоматични предложения, класове и срокове на доставка

- Всеки артикул има **доставчик**, **код при доставчика**, **срок на доставка (раб. дни)** и **клас** (икономичен /
  стандартен / премиум). Непопълненото се извежда автоматично: срокът — от настройките на доставчика
  (green‑energy.bg 3 дни, Aerocompact 15 дни, общ 7, при „backorder/изчерпан“ 21), класът — от цената за единица
  (€/Wp, €/kW, €/kWh) спрямо еквивалентите в каталога, марката и качеството (гаранция, ефективност, цикли).
- **Стъпка 4 → „Генерирай предложения“** оразмерява четири пълни конфигурации — **Най‑ниска цена**, **Балансиран**
  (цена + стойност на времето за доставка), **Премиум** и **Най‑бърза доставка** — всяка с модули, инвертор, батерия,
  конструкция, защити, кабели и труд, крайна цена, марж, срок (с най‑бавната позиция) и доставчици. Един клик прилага
  варианта; всичко остава ръчно редактируемо. При избрана стратегия и еквивалентните дребни материали (кабели,
  защити, скоби) се избират по нея.
- Офертата показва **срок на доставка на оборудването** (max по позициите) и позицията‑„тясно място“.
- **Запитвания към доставчици**: от стъпка 7 — един Excel с лист за всеки доставчик или ZIP с отделни файлове
  (`Zayavka_<доставчик>_<оферта>.xlsx`) с код, наименование, количество, последна цена, очакван срок и колона
  „Вашата оферта“ — готови за изпращане за оферта/поръчка. Артикулите без доставчик са в лист „Неразпределени“.
- **Настройки → Доставчици и срокове** — списък доставчици (срок, имейл, контакт), марки по клас и тежести на
  класификацията; **Текстове** — уводен и заключителен текст на офертата и бележка към запитването.
- Документите (оферта за клиента, вътрешна калкулация, техническо досие, Excel КСС/Поръчка/Запитване) са с единен
  фирмен стил: шрифт Inter, бланка, обобщение „Предложено решение“, ценови блок, спецификация по раздели, условия.

### Желана мощност, целият покрив и няколко инвертора в паралел

- В стъпка 2 има поле **„Желана мощност (kWp)“**. Предложенията се оразмеряват по нея; без него — по
  потреблението, а като последна възможност — по присъединената мощност × 1,2.
- Когато покривът побира повече (напр. 83 kWp при нужда от 20 kWp), превключвателят **Автоматично / По необходимост /
  Целият покрив** в стъпка 4 решава: „по необходимост“ офертира само нужния брой модули (останалите остават на
  разположението като резерв), „целият покрив“ оразмерява всички модули — с **N еднакви инвертора в паралел**
  (напр. 4 × 20 kW), ако един не стига. Броят се изчислява от макс. PV вход и DC/AC ≤ 1,35 и е ръчно редактируем
  („Брой инвертори“ в стъпка 4, бутон „предложи“).
- При N > 1 инженерният модул разделя масива по инвертори, проектира стринговете на всеки (всяка плоскост на
  собствен MPPT, еднакви дължини в паралел, Voc(−20 °C) ≤ 97 % от макс. DC), слага прекъсвач + ДТЗ и захранващ кабел
  за всеки инвертор, **табло AC за паралелни инвертори**, **главен прекъсвач (MCCB)** и главен кабел към ГРТ по
  общия ток и пада на напрежение, кабели за паралелна комуникация и съответните обувки/PE. Офертата, техническото
  досие (еднолинейна схема с N инвертора и табло AC) и КСС го показват.
- Надвишаването на присъединената мощност се показва изрично (увеличение на мощността или export limit);
  паралелна работа се предлага само с инвертори ≥ `min_parallel_unit_kw` (8 kW) и до `max_parallel_inverters` (6).

### Препоръка за модул, фотореалистична визуализация и 3D

- **Препоръка за модул** (стъпка 3 и 4): всеки активен модул от каталога се подрежда върху реалните плоскости
  (контур, препятствия, отстъп, портрет/пейзаж) и се класира по стратегия и обхват — ефективна €/Wp (цена + конструкция
  и труд за брой), срок на доставка, клас/ефективност, покритие на целта и добри практики (формат и тегло спрямо достъпа
  и височината, рамка 30–46 mm за скобите, двулицеви на плоски покриви, проверка на стринговете с инвертора, липсващи
  размери/цени). „Приложи“ записва модула, ориентацията и подредбата във всяка плоскост. Предложенията в стъпка 4 правят
  същото за всяка стратегия („Автоматичен избор на модул“).
- **Визуализация върху снимката**: модулите се проектират фотореалистично върху качената снимка на покрива (стъкло,
  отблясък, клетки, черна/сребриста рамка, сянка, съгласуване на осветеността) и влизат в офертата като приложение
  „Как ще изглежда Вашата централа“ и в техническото досие.
- **3D модел**: сграда и плоскости по наклон/азимут/размери/височина, модули с рамка и шини/баласт, сенки по час и месец,
  реалната снимка като текстура; „Запази изгледа за документите“ добавя изгледа към офертата.

### Пълен набор данни и редакция на всички таблици в Excel

- При първи старт **всички** артикули получават цена, доставчик, срок, клас, код и гаранция. Там, където няма реална
  цена/срок, системата попълва **ориентировъчни стойности** (модули €/Wp по марка, инвертори €/kW по марка и
  топология, батерии €/kWh по сегмент, типични цени за аксесоари и услуги, срокове по доставчик и наличност).
  Такива стойности са маркирани в спецификациите с `price_source = "indicative"` / `lead_source = "indicative"` и
  се заменят с реалните оферти — през интерфейса, при синхронизация с доставчика или чрез Excel. Нищо въведено
  ръчно не се презаписва; **Каталог → Всички таблици (Excel) → „Попълни липсващите стойности“** може да се пусне и
  по‑късно, след добавяне на нови артикули.
- **Каталог → Всички таблици (Excel)** експортира целия набор данни — *Артикули*, *Труд*, *Типове покриви*,
  *Правила конструкция*, *Доставчици*, *Настройки* — като един `.xlsx` с лист за всяка таблица или `.zip` с отделен
  файл за всяка. Ред 1 е технически ключ, ред 2 — българско име на колоната; сивите колони (ID/код) са ключове.
  Редактираният файл (или целият `.zip`) се качва обратно с един бутон: празна клетка = без промяна, `-` изтрива
  стойност, ред без ID създава нов запис; резултатът показва създадени/обновени редове и грешки по редове.

---

## English

### Features

- **Roof photo → panel layout.** Upload a roof (or ground) photo, let the detector propose the roof plane and obstacles, correct by hand, enter real dimensions, then auto‑fill panels (portrait/landscape, row gaps, edge margins). Toggle, drag or add panels manually. Multiple roof planes per project.
- **Sizing.** Inverter and battery recommendations (Deye hybrid range) from connected power, phases and kWp, with DC/AC ratio and phase warnings. Everything overridable.
- **Engineering engine (IEC 62548 / IEC 60364‑7‑712).** String design (Voc at design T‑min, Vmp at T‑cell max, MPPT inputs), PV cable size and length by voltage drop, string fuses only when `(Ns−1)·Isc·1.25 > module max fuse`, DC combiner with SPD T2 when the array‑to‑inverter run exceeds 10 m (IEC 61643‑32), AC MCB/RCD per the Deye manual, AC cable by current and drop, battery breaker/cable, PE and equipotential bonding with clamps, cable management (UV ties, conduit, clips), metering (CTs or smart meter). Configurable industry margins (15 % cables, 10 % small fasteners, spare modules). Every quantity is previewed in the Materials step and can be overridden.
- **BOM engine.** Mounting‑system rules per roof type (Aerocompact CompactPITCH/METAL/FLAT: rails, splices, hooks, mid/end clamps, screws, caps, clips, bonding clamps) with configurable multipliers and waste.
- **Labor.** Days × workers price matrix or €/W mode.
- **Quotes.** Editable line items with auto‑lock, markup, discount, VAT, advance, validity, versions and statuses. Client PDF, internal PDF (purchase prices + margin), Excel BOM (KSS + order list by manufacturer) and a **technical file PDF** (string table and checks, single‑line diagram, layout drawing with strings and rails, mounting plan, full BOM with derivation, standards).
- **Catalog.** The complete green-energy.bg portfolio (388 items) with product links and **PDF datasheets**; specs auto‑extracted from the datasheets (flagged until verified), one‑click re‑sync with the supplier shop, per‑item datasheet upload with auto‑fill; supplier price‑list import (xlsx) with fuzzy matching; export.
- **Aerocompact catalogue.** 14 roof/terrain types mapped to the matching AEROCOMPACT system (CompactPITCH XM‑F/XT/XT‑R/XM‑PL/XW, CompactMETAL TL/TS/TM/TR, CompactFLAT S10/S10 PLUS, CompactGROUND GS) with 159 components, article numbers, leaflets, assembly instructions and checklists; quantities follow the manufacturer's assembly rules, the technical file documents the system limits.
- **Quote check (completeness audit).** `GET /api/quotes/{id}/completeness` scores the quote and lists what still has to be bought, done or clarified — comms logger, export limiter vs connected power, grid paperwork, scaffold/lift by building height, 4G router when there is no internet, main breaker upgrade, waste removal, CAR insurance, spare modules, transport, indicative prices, unverified specs, margin below minimum — each with a one‑click fix (`…/completeness/apply`). Fed by the **site survey** card (`project.params.survey`).
- **ERP: purchase orders and receiving.** `POST /api/quotes/{id}/orders/generate` creates one PO per supplier from the accepted quote (`PO‑YYYY‑NNNN`, expected dates from lead times), `GET /api/orders` lists everything awaiting delivery across projects (overdue first), lines are received partially or fully with a receipt log, project readiness % and earliest install start are computed, each PO exports to Excel for the supplier.
- **Documents on your server.** Every generated quote, technical file, BOM, RFQ, PO and client package is archived under `DATA_DIR/projects/<id>/…`; survey photos, contracts and protocols are uploaded per project; `POST /api/catalog/datasheets/mirror` downloads every supplier datasheet and Aerocompact manual locally (progress in `…/status`), so nothing depends on external sites once mirrored. `GET /api/quotes/{id}/client-package.zip` bundles one merged proposal PDF + quote + technical file + drawings + datasheets.
- **Dashboard** (`GET /api/dashboard`): pipeline, expiring quotes, overdue/next deliveries, catalog health (no price, indicative, unverified, stale), local document coverage.
- **Admin.** Users/roles, company details and logo, default pricing and quote texts.
- **Bilingual UI** (Bulgarian default, English toggle), PWA, Capacitor Android app.

### Procurement automation (tiers, lead times, proposals, RFQs)

Catalog items carry `supplier`, `supplier_sku`, `lead_time_days` and `tier` (economy / standard / premium); missing
values are derived (supplier defaults, price‑per‑unit percentile + brand + quality). The **proposal engine**
(`POST /api/projects/{id}/proposals`) sizes four complete, costed configurations — cheapest, balanced
(price + €/day of lead time), premium and fastest delivery — and `…/proposals/apply` sets them as the project
selections. Quotes record the equipment lead time and bottleneck line. `GET /api/quotes/{id}/rfq`, `rfq.xlsx` and
`rfq.zip` produce supplier‑ready request‑for‑quotation workbooks grouped by supplier. New columns are added to
existing databases automatically on startup (`ensure_columns`).

### Target power, whole roof and parallel inverters

Projects carry `params.target_kwp` (step 2). Proposals size to that demand (fallbacks: consumption, connected
power × 1.2); when the layout holds much more, the scope switch **auto / target / roof** either quotes the needed
module count only (`panel_limit`) or the whole roof with **N identical inverters in parallel** (`inverter_qty`,
`sizing.inverter_count()`: per‑unit PV ≤ max PV input, DC/AC ≤ 1.35, preferred ≤ 1.25). `engineering.string_design`
splits the array per inverter (plane → own MPPT, equal parallel lengths, Voc(cold) ≤ 0.97·Vdc,max) and
`full_design` adds per‑inverter MCB/RCD/feeders, an AC combiner board, a main MCCB and main cable sized for the total
current and voltage drop, parallel‑communication cables and PE. Catalog roles `ac_combiner` and `parallel_cable` are
new; settings `procurement.max_parallel_inverters` (6) and `procurement.min_parallel_unit_kw` (8) bound the search.

### Module recommendation, photo visualisation and 3D

`services/module_fit.py` lays every active catalog module on the real planes (polygon, obstacles, setback, both
orientations, cached) and ranks candidates per strategy/scope: effective €/Wp (price + `procurement.bos_per_module_eur`
for mounting/labour per module), lead time, tier/efficiency, target coverage and best‑practice rules (format/weight vs
roof access and height, 30–46 mm frame for the clamps, bifacial on flat/ground, string quick‑check against the chosen
inverter, missing dimensions/prices, unverified specs). `apply()` writes module, orientation and a compact centred block
(`pick_compact`) into each plane; proposals use the same engine per strategy (`panel_auto`, default on).
`services/visual.py` renders the modules photorealistically onto the uploaded photo (homography from the plane corners,
glass gradient, specular band, cells, frame, shadow, luminance matching) → quote appendix and technical file.
`services/scene.py` + `components/Scene3D.tsx` (three.js, lazy‑loaded) build a schematic 3D model from the planes
(tilt/azimuth/size/survey height), with sun position by hour/month, the photo as texture and a “save view” that embeds
the render in the documents.

### Complete dataset and whole-database Excel round trip

`services/datafill.py` completes the catalogue once at first start: every item gets a purchase price, supplier,
lead time, tier, SKU, manufacturer and warranty. Values that are not real supplier quotes are **indicative**
(€/Wp, €/kW, €/kWh models calibrated on priced items and public distributor prices) and are tagged
`specs.price_source = "indicative"` / `lead_source = "indicative"`; existing data is never overwritten
(`POST /api/catalog/dataset/fill-missing` re-runs it for new items). `services/dataset_io.py` exports all editable
tables (`GET /api/catalog/dataset.xlsx` — one sheet per table, `GET /api/catalog/dataset.zip` — one workbook per
table) and imports them back (`POST /api/catalog/dataset/import`, `.xlsx` or `.zip`): rows are matched by
`id`/`code`/name, only filled cells are applied, `-` clears, rows without a key are created, and a per-table report
with row-level errors is returned.

### Stack

| Part | Tech |
| --- | --- |
| Backend | FastAPI · SQLAlchemy 2 · PostgreSQL (SQLite for dev) · WeasyPrint (PDF) · openpyxl (xlsx) · OpenCV/Pillow (roof detection) |
| Frontend | React 19 · TypeScript · Vite · Tailwind · TanStack Query · vite‑plugin‑pwa |
| Mobile | Capacitor 8 (Android) — same codebase, APK via GitHub Actions |
| Deploy | Docker Compose: `db` (postgres:16) · `api` · `web` (nginx serving the SPA, proxying `/api` and `/pgadmin`) · `pgadmin` (DB viewer/editor); Tailscale on the host |

### Quick start (production)

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
# or manually:
git clone https://github.com/SKuytov/gmsun.git /opt/gmsun && cd /opt/gmsun
cp .env.example .env && nano .env     # SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD
docker compose up -d --build
```

The one‑liner also installs pgAdmin (`http://<server-ip>/pgadmin/`), Tailscale (pass `TS_AUTHKEY=…` to join automatically),
ufw, nightly backups and log rotation, and prints every URL and password at the end. Re‑run it to update.

Open `http://<server-ip>/`, sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` and change the password.

### Development

```bash
# backend
cd backend && pip install -r requirements.txt
DATABASE_URL=sqlite:///./dev.db PYTHONPATH=. uvicorn app.main:app --reload --port 8000
PYTHONPATH=. pytest -q tests

# frontend (proxies /api to :8000)
cd frontend && npm ci && npm run dev
```

API docs: `http://localhost:8000/docs`.

### Repository layout

```
backend/   FastAPI app: models, routers, services (layout_engine, engineering, bom, sizing, pricing, techfile, roof_detect, pdf, excel), seed data, tests
frontend/  React app + Capacitor Android project (frontend/android)
deploy/    install.sh (one‑command installer), backup.sh, restore.sh, cron example, pgadmin/servers.json
docs/      DEPLOY.md, ANDROID.md, USER_GUIDE_BG.md
```

### License

MIT — see [LICENSE](LICENSE).
