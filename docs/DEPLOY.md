# Deploying gmsun on Ubuntu Server (24.04 / 26.04)

The whole stack runs in Docker Compose on one machine (a VM or mini‑PC in the office is enough):

```
browser / Android ──► web (nginx :80) ──► /api ──► api (FastAPI :8000) ──► db (PostgreSQL 16)
                                   └── static React app          └── /data volume (photos, PDFs, logo)
```

## 1. One‑shot install

```bash
curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
```

What it does: installs Docker Engine + Compose plugin (falls back to the `noble` Docker repo if Docker has not
published packages for your Ubuntu release yet), clones the repo to `/opt/gmsun`, writes `.env` with random
`SECRET_KEY`, `POSTGRES_PASSWORD` and admin password, runs `docker compose up -d --build`.

Environment overrides: `GMSUN_DIR=/srv/gmsun GMSUN_PORT=8080 sudo -E bash install.sh`.

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

```bash
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw enable
```
