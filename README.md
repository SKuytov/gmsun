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
| **5. Материали** | Автоматична **спецификация на конструкцията** (шини X50, съединители, куки, скоби, винтове, капачки, клипси) по правила за всеки тип покрив, плюс кабели, конектори MC4, табло, доставки. |
| **6. Труд и условия** | СМР по матрица „дни × работници“ или „по мощност“ (€/W), срок на изпълнение, гаранции, условия на плащане. |
| **7. Оферта** | Редове с количества и цени (всеки ред е редактируем и „заключен“ срещу преизчисление), надценка, отстъпка, ДДС, аванс, валидност. Версии на офертата, статус, **PDF за клиента**, **PDF вътрешен** (с доставни цени и марж) и **Excel КСС**. |

Още: каталог с внос на ценови листи на доставчика (Excel), правила за конструкция по тип покрив, матрица за СМР,
потребители и роли, фирмени данни и лого за PDF, двуезичен интерфейс (BG по подразбиране, EN превключвател),
PWA (работи и като „инсталирано“ приложение в браузъра) и Android приложение.

### Бърз старт на сървъра (Ubuntu Server 24.04 / 26.04)

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
```

Скриптът инсталира Docker, сваля проекта в `/opt/gmsun`, генерира тайни ключове в `.env` и стартира
PostgreSQL + API + уеб сървър. След 2–3 минути отворете `http://<IP-на-сървъра>/`.

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
- **BOM engine.** Mounting‑system rules per roof type (rails, splices, hooks, mid/end clamps, screws, caps, clips) with configurable multipliers and waste; cables, MC4, switchboard, delivery.
- **Labor.** Days × workers price matrix or €/W mode.
- **Quotes.** Editable line items with auto‑lock, markup, discount, VAT, advance, validity, versions and statuses. Client PDF, internal PDF (purchase prices + margin) and Excel BOM (KSS).
- **Catalog.** Panels, inverters, batteries, mounting parts, materials; supplier price‑list import (xlsx) with fuzzy matching; export.
- **Admin.** Users/roles, company details and logo, default pricing and quote texts.
- **Bilingual UI** (Bulgarian default, English toggle), PWA, Capacitor Android app.

### Stack

| Part | Tech |
| --- | --- |
| Backend | FastAPI · SQLAlchemy 2 · PostgreSQL (SQLite for dev) · WeasyPrint (PDF) · openpyxl (xlsx) · OpenCV/Pillow (roof detection) |
| Frontend | React 19 · TypeScript · Vite · Tailwind · TanStack Query · vite‑plugin‑pwa |
| Mobile | Capacitor 8 (Android) — same codebase, APK via GitHub Actions |
| Deploy | Docker Compose: `db` (postgres:16) · `api` · `web` (nginx serving the SPA and proxying `/api`) |

### Quick start (production)

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
# or manually:
git clone https://github.com/SKuytov/gmsun.git /opt/gmsun && cd /opt/gmsun
cp .env.example .env && nano .env     # SECRET_KEY, POSTGRES_PASSWORD, ADMIN_PASSWORD
docker compose up -d --build
```

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
backend/   FastAPI app: models, routers, services (layout_engine, bom, sizing, pricing, roof_detect, pdf, excel), seed data, tests
frontend/  React app + Capacitor Android project (frontend/android)
deploy/    install.sh, backup.sh, restore.sh, cron example
docs/      DEPLOY.md, ANDROID.md, USER_GUIDE_BG.md
```

### License

MIT — see [LICENSE](LICENSE).
