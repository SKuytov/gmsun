# Deploying gmsun on Ubuntu Server (24.04 / 26.04)

The whole stack runs in Docker Compose on one machine (a VM or mini‑PC in the office is enough):

```
browser / Android ──► web (nginx :80) ──► /api ──► api (FastAPI :8000) ──► db (PostgreSQL 16)
                                   ├── /pgadmin ──► pgadmin (DB viewer/editor)
                                   └── static React app          └── /data volume (photos, PDFs, logo)
Tailscale (host) ──► same ports over the private tailnet (100.x.y.z) from phones/laptops anywhere
```

## 1. One‑command install (fresh Ubuntu Server)

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
```

With a Tailscale pre‑auth key (joins the tailnet without a browser login):

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo TS_AUTHKEY=tskey-auth-xxxxx bash
```

What it does, in order:

1. `apt` update, base tools, unattended security updates.
2. Docker Engine + Compose plugin (falls back to the `noble` Docker repo if Docker has not published packages for your Ubuntu release yet).
3. Clones the repo to `/opt/gmsun`, writes `.env` (chmod 600) with random `SECRET_KEY`, `POSTGRES_PASSWORD`, admin and pgAdmin passwords.
4. `docker compose up -d --build` — PostgreSQL 16, API, web (nginx) and **pgAdmin 4** at `http://<server>/pgadmin/` with the gmsun database pre‑registered.
5. **Tailscale**: installs `tailscaled`; with `TS_AUTHKEY` it runs `tailscale up --hostname=gmsun --ssh`, otherwise it prints the command to run once and open the login link.
6. `ufw` (OpenSSH + HTTP port + Tailscale), nightly backup cron (02:30, last 14 kept), Docker log rotation.

At the end it prints all URLs and passwords. Re‑running the same command later **updates** the installation (git pull + rebuild) and keeps `.env`.

Environment overrides: `GMSUN_DIR=/srv/gmsun GMSUN_PORT=8080 GMSUN_NO_TAILSCALE=1 GMSUN_NO_UFW=1`.

### Database viewer/editor (pgAdmin)

Open `http://<server>/pgadmin/`, log in with `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` from `.env`, expand
**Servers → gmsun** and enter `POSTGRES_PASSWORD` once (it is saved). Tables live in schema `public`
(`catalog_items`, `projects`, `layouts`, `quotes`, `quote_lines`, `settings`, `users`, …). Right‑click a table →
*View/Edit Data* to edit rows like in phpMyAdmin. Always back up before bulk edits (`deploy/backup.sh`).

### Tailscale access

After `tailscale up` the server gets a stable private IP (`tailscale ip -4`) and a MagicDNS name (`gmsun`).
Install Tailscale on the phones/laptops of the team, and use `http://gmsun/` or `http://100.x.y.z/` as the
server address in the Android app — no port‑forwarding, works from any network. `--ssh` also enables
Tailscale SSH to the server.

## 2. Manual install

```bash
sudo apt-get install -y git docker.io docker-compose-v2      # or Docker's official repo
git clone https://github.com/SKuytov/gmsun.git /opt/gmsun && cd /opt/gmsun
cp .env.example .env
nano .env        # set SECRET_KEY (openssl rand -hex 32), POSTGRES_PASSWORD, ADMIN_PASSWORD, HTTP_PORT
docker compose up -d --build
docker compose logs -f api   # wait for "Application startup complete"
```

Open `http://<server-ip>:<HTTP_PORT>/` and sign in.

## 3. `.env` reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `HTTP_PORT` | `80` | Port published by the `web` container |
| `POSTGRES_DB/USER/PASSWORD` | `gmsun` / `gmsun` / — | Database credentials (used by `api` via `DATABASE_URL`) |
| `SECRET_KEY` | — | JWT signing key, ≥ 32 random chars |
| `ACCESS_TOKEN_MINUTES` | `720` | Session length (12 h) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@gmsun.local` / `admin1234` | First admin, created only when the users table is empty |
| `CORS_ORIGINS` | `*` | Allowed origins; the Android app needs the server origin allowed (keep `*` on a LAN) |
| `SEED_DEMO` | `true` | Seed catalog, roof types, mounting rules, labor matrix and company defaults on first start |
| `PGADMIN_EMAIL` / `PGADMIN_PASSWORD` | `admin@gmsun.local` / — | pgAdmin login at `/pgadmin/` |
| `TS_AUTHKEY` | — | Optional Tailscale pre‑auth key used by the installer |

## 4. Updating

```bash
cd /opt/gmsun && git pull && docker compose up -d --build
```

Database schema changes are applied automatically at startup (SQLAlchemy `create_all` for new tables/columns are
additive; back up first anyway).

## 5. Backups

```bash
/opt/gmsun/deploy/backup.sh                    # -> backups/gmsun-YYYYmmdd-HHMM.tar.gz (pg_dump + /data)
sudo cp /opt/gmsun/deploy/gmsun-backup.cron /etc/cron.d/gmsun-backup   # nightly at 02:30, keeps 14
/opt/gmsun/deploy/restore.sh backups/gmsun-20261107-0230.tar.gz        # full restore
```

Copy the `backups/` folder off the machine (rsync, Dropbox, external disk).

## 6. HTTPS (optional, needed for the camera in a browser from another device)

Put Caddy or nginx with Let's Encrypt in front of the `web` container, or use a Tailscale/VPN address.
Simplest: install Caddy on the host, set `HTTP_PORT=8080` in `.env`, and `/etc/caddy/Caddyfile`:

```
gmsun.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

The Android app works fine over plain HTTP on the LAN (cleartext traffic is allowed in the manifest).

## 7. Operations cheat‑sheet

```bash
docker compose ps                       # status
docker compose logs -f api web db       # logs
docker compose restart api              # restart backend
docker compose exec db psql -U gmsun    # SQL shell
docker compose down                     # stop (data volumes are kept)
docker compose down -v                  # stop AND delete all data (!)
```

Health: `curl http://<server>/api/health` → `{"status":"ok", ...}`.

## 8. Firewall

The installer configures this; manually:

```bash
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow in on tailscale0 && sudo ufw enable
```

## 9. Documents produced per quote

| Document | Endpoint | Content |
| --- | --- | --- |
| Client PDF | `/api/quotes/{id}/pdf?mode=client` | Offer with sections, totals, terms |
| Internal PDF | `/api/quotes/{id}/pdf?mode=internal` | Purchase prices, margins |
| Excel (КСС) | `/api/quotes/{id}/xlsx` | Sheet 1: quote; sheet 2 **Поръчка** — order list by manufacturer (SKU, qty, purchase price, rule) |
| Technical file | `/api/quotes/{id}/techfile.pdf` | KPIs, string design + IEC 62548 checks, single‑line diagram, AC/battery/earthing, per‑plane layout drawing with strings & rails, mounting plan, full BOM with derivation, order list, standards |
