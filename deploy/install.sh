#!/usr/bin/env bash
# gmsun — one-command installer for a FRESH Ubuntu Server (24.04 / 26.04).
#
#   curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
#
# What it does (idempotent — safe to re-run for updates):
#   1. System update, basic tools, unattended security updates
#   2. Docker Engine + Compose plugin
#   3. Clones/updates the repo into /opt/gmsun and creates .env with random secrets
#   4. Builds and starts the stack: PostgreSQL + API + web (nginx) + pgAdmin (DB viewer/editor at /pgadmin/)
#   5. Tailscale (private VPN access from phones/laptops anywhere) — joins the tailnet if TS_AUTHKEY is set
#   6. UFW firewall (SSH + HTTP + Tailscale), daily DB/file backups via cron, log rotation
#
# Optional environment variables:
#   GMSUN_PORT=80            published HTTP port
#   GMSUN_DIR=/opt/gmsun     install directory
#   GMSUN_REPO=<git url>     alternative repository
#   TS_AUTHKEY=tskey-auth-…  Tailscale pre-authenticated key (otherwise a login link is printed)
#   GMSUN_NO_TAILSCALE=1     skip Tailscale
#   GMSUN_NO_UFW=1           skip firewall configuration
set -euo pipefail

REPO="${GMSUN_REPO:-https://github.com/SKuytov/gmsun.git}"
DIR="${GMSUN_DIR:-/opt/gmsun}"
PORT="${GMSUN_PORT:-80}"
export DEBIAN_FRONTEND=noninteractive

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)."; exit 1; fi

step() { echo; echo "==> $*"; }

# ---------------------------------------------------------------- 1. base system
step "System packages"
apt-get update -y
apt-get install -y ca-certificates curl git gnupg openssl ufw unattended-upgrades apt-transport-https lsb-release cron logrotate
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 2. docker
step "Docker Engine + Compose"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  # Docker may not publish a repo for a brand-new Ubuntu release yet — fall back to the latest LTS.
  if ! curl -fsSI "https://download.docker.com/linux/ubuntu/dists/${CODENAME}/Release" >/dev/null 2>&1; then
    echo "   No Docker repo for '${CODENAME}' yet — using 'noble' packages."
    CODENAME=noble
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo "   Docker already installed: $(docker --version)"
fi
if ! docker compose version >/dev/null 2>&1; then
  apt-get install -y docker-compose-plugin
fi

# ---------------------------------------------------------------- 3. code + .env
step "Fetching gmsun into ${DIR}"
if [[ -d "${DIR}/.git" ]]; then
  git -C "${DIR}" pull --ff-only
else
  git clone "${REPO}" "${DIR}"
fi
cd "${DIR}"

rand_pw() { openssl rand -base64 18 | tr -d '/+=' | cut -c1-16; }

if [[ ! -f .env ]]; then
  step "Creating .env with random secrets"
  cp .env.example .env
  ADMIN_PW="$(rand_pw)"
  PGADMIN_PW="$(rand_pw)"
  sed -i "s|^HTTP_PORT=.*|HTTP_PORT=${PORT}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PW}|" .env
  sed -i "s|^PGADMIN_PASSWORD=.*|PGADMIN_PASSWORD=${PGADMIN_PW}|" .env
  chmod 600 .env
else
  # keep older .env files working when new keys are introduced
  grep -q '^PGADMIN_EMAIL=' .env || echo "PGADMIN_EMAIL=admin@gmsun.local" >> .env
  grep -q '^PGADMIN_PASSWORD=' .env || echo "PGADMIN_PASSWORD=$(rand_pw)" >> .env
fi
if [[ -n "${TS_AUTHKEY:-}" ]]; then
  grep -q '^TS_AUTHKEY=' .env && sed -i "s|^TS_AUTHKEY=.*|TS_AUTHKEY=${TS_AUTHKEY}|" .env || echo "TS_AUTHKEY=${TS_AUTHKEY}" >> .env
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

# pgAdmin pre-registered server must match the DB user/name from .env
sed -i "s|\"MaintenanceDB\": \".*\"|\"MaintenanceDB\": \"${POSTGRES_DB:-gmsun}\"|; s|\"Username\": \".*\"|\"Username\": \"${POSTGRES_USER:-gmsun}\"|" deploy/pgadmin/servers.json

# ---------------------------------------------------------------- 4. containers
step "Building and starting containers (first build takes a few minutes)"
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 5. tailscale
TS_IP=""
if [[ -z "${GMSUN_NO_TAILSCALE:-}" ]]; then
  step "Tailscale"
  if ! command -v tailscale >/dev/null 2>&1; then
    curl -fsSL https://tailscale.com/install.sh | sh
  fi
  systemctl enable --now tailscaled
  if [[ -n "${TS_AUTHKEY:-}" ]]; then
    tailscale up --authkey="${TS_AUTHKEY}" --hostname=gmsun --ssh || echo "   tailscale up failed — run it manually: sudo tailscale up --ssh"
  elif ! tailscale status >/dev/null 2>&1; then
    echo "   Tailscale is installed but not logged in. Run once and open the printed link:"
    echo "       sudo tailscale up --hostname=gmsun --ssh"
  fi
  TS_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
fi

# ---------------------------------------------------------------- 6. firewall, backups, logs
if [[ -z "${GMSUN_NO_UFW:-}" ]]; then
  step "Firewall (ufw): allow SSH, HTTP ${PORT}, Tailscale"
  ufw allow OpenSSH >/dev/null
  ufw allow "${PORT}/tcp" >/dev/null
  ufw allow in on tailscale0 >/dev/null 2>&1 || true
  ufw allow 41641/udp >/dev/null 2>&1 || true
  ufw --force enable >/dev/null
fi

step "Daily backups (02:30, last 14 kept) → ${DIR}/backups"
chmod +x deploy/*.sh
sed "s|/opt/gmsun|${DIR}|g" deploy/gmsun-backup.cron > /etc/cron.d/gmsun-backup
chmod 644 /etc/cron.d/gmsun-backup

cat > /etc/docker/daemon.json.gmsun <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" } }
JSON
if [[ ! -f /etc/docker/daemon.json ]]; then
  mv /etc/docker/daemon.json.gmsun /etc/docker/daemon.json
  systemctl restart docker && docker compose up -d
else
  rm -f /etc/docker/daemon.json.gmsun
fi

# ---------------------------------------------------------------- summary
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
URL_PORT=""; [[ "${PORT}" != "80" ]] && URL_PORT=":${PORT}"
echo
echo "============================================================"
echo " gmsun is up."
echo
echo "  Web app / Android server URL:  http://${IP}${URL_PORT}/"
[[ -n "${TS_IP}" ]] && echo "  via Tailscale:                 http://${TS_IP}${URL_PORT}/"
echo "  Login:                         ${ADMIN_EMAIL:-admin@gmsun.local} / ${ADMIN_PASSWORD}"
echo
echo "  Database editor (pgAdmin):     http://${IP}${URL_PORT}/pgadmin/"
echo "  pgAdmin login:                 ${PGADMIN_EMAIL:-admin@gmsun.local} / ${PGADMIN_PASSWORD}"
echo "  DB password (asked once):      ${POSTGRES_PASSWORD}"
echo
echo "  All secrets are in ${DIR}/.env (chmod 600)."
echo "  Logs:    cd ${DIR} && docker compose logs -f"
echo "  Update:  curl -fsSL ${REPO%.git}/raw/main/deploy/install.sh | sudo bash"
echo "  Backup:  ${DIR}/deploy/backup.sh      Restore: ${DIR}/deploy/restore.sh <file>"
echo "============================================================"
