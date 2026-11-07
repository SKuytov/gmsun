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
| **4. Оборудване** | Избор на модул; автоматично **оразмеряване** на инвертор (Deye SUN‑xK‑SG0x) и батерия (RW‑F16, SE‑G/F серия) според мощността и kWp, с предупреждения за DC/AC съотношение, фази и присъединена мощност. Всичко може да се промени ръчно. |
| **5. Материали** | **Автоматично проектиране** по IEC 62548 / IEC 60364‑7‑712: стрингове (Voc при −20 °C, Vmp при 70 °C, MPPT входове), соларен кабел със сечение и дължина по пад на напрежение, стрингови предпазители (само когато правилото (Ns−1)·Isc·1,25 > макс. предпазител на модула ги изисква), DC табло със SPD T2 при трасе над 10 m (IEC 61643‑32), AC прекъсвач и ДТЗ по ръководството на Deye, AC кабел по ток и пад, батериен прекъсвач и кабел, PE и изравняване на потенциалите с клеми, укрепване (UV връзки, тръби, скоби), измерване (CT или смарт електромер). Конструкцията (шини X50, съединители, куки, скоби, винтове, капачки, клипси) по правила за всеки тип покрив. **Индустриални резерви**: 15 % за кабели, 10 % за дребни крепежи, настройваеми. Всичко е предварителен изглед и всичко се коригира ръчно. |
| **6. Труд и условия** | СМР по матрица „дни × работници“ или „по мощност“ (€/W), срок на изпълнение, гаранции, условия на плащане. |
| **7. Оферта** | Редове с количества и цени (всеки ред е редактируем и „заключен“ срещу преизчисление), надценка, отстъпка, ДДС, аванс, валидност. Версии на офертата, статус, **PDF за клиента**, **PDF вътрешен** (с доставни цени и марж), **Excel КСС** (+ лист „Поръчка“ по доставчици с кодове и доставни цени) и **Техническо досие (PDF)** — показатели, стрингова таблица с проверки, еднолинейна схема, AC/батерия/заземяване, чертеж на разположението по равнини със стрингове и шини, монтажен план, пълна спецификация с извод на количествата, списък за поръчка и приложими стандарти. |

Още: каталог с внос на ценови листи на доставчика (Excel), правила за конструкция по тип покрив, матрица за СМР,
потребители и роли, фирмени данни и лого за PDF, двуезичен интерфейс (BG по подразбиране, EN превключвател),
PWA (работи и като „инсталирано“ приложение в браузъра) и Android приложение.

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

### Важно за цените

Каталогът се зарежда с модули LONGi, инвертори и батерии Deye, монтажни елементи и материали от реалните КСС на фирмата.
Ценовата листа на доставчика, с която е зареден, **не съдържа цени** за повечето инвертори/батерии, затова те са `0`
докато не ги попълните (Каталог → Редакция) или не внесете актуална ценова листа (Каталог → Импорт).
Офертата ви предупреждава за всеки артикул без цена.

---

## English

### Features

- **Roof photo → panel layout.** Upload a roof (or ground) photo, let the detector propose the roof plane and obstacles, correct by hand, enter real dimensions, then auto‑fill panels (portrait/landscape, row gaps, edge margins). Toggle, drag or add panels manually. Multiple roof planes per project.
- **Sizing.** Inverter and battery recommendations (Deye hybrid range) from connected power, phases and kWp, with DC/AC ratio and phase warnings. Everything overridable.
- **Engineering engine (IEC 62548 / IEC 60364‑7‑712).** String design (Voc at design T‑min, Vmp at T‑cell max, MPPT inputs), PV cable size and length by voltage drop, string fuses only when `(Ns−1)·Isc·1.25 > module max fuse`, DC combiner with SPD T2 when the array‑to‑inverter run exceeds 10 m (IEC 61643‑32), AC MCB/RCD per the Deye manual, AC cable by current and drop, battery breaker/cable, PE and equipotential bonding with clamps, cable management (UV ties, conduit, clips), metering (CTs or smart meter). Configurable industry margins (15 % cables, 10 % small fasteners, spare modules). Every quantity is previewed in the Materials step and can be overridden.
- **BOM engine.** Mounting‑system rules per roof type (Aerocompact CompactPITCH/METAL/FLAT: rails, splices, hooks, mid/end clamps, screws, caps, clips, bonding clamps) with configurable multipliers and waste.
- **Labor.** Days × workers price matrix or €/W mode.
- **Quotes.** Editable line items with auto‑lock, markup, discount, VAT, advance, validity, versions and statuses. Client PDF, internal PDF (purchase prices + margin), Excel BOM (KSS + order list by manufacturer) and a **technical file PDF** (string table and checks, single‑line diagram, layout drawing with strings and rails, mounting plan, full BOM with derivation, standards).
- **Catalog.** Panels, inverters, batteries, mounting parts, materials; supplier price‑list import (xlsx) with fuzzy matching; export.
- **Admin.** Users/roles, company details and logo, default pricing and quote texts.
- **Bilingual UI** (Bulgarian default, English toggle), PWA, Capacitor Android app.

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
