#!/usr/bin/env bash
# gmsun one-shot installer for a fresh Ubuntu Server (24.04 / 26.04).
# Installs Docker Engine + Compose plugin, clones the repo, creates .env with random secrets, starts the stack.
#   curl -fsSL https://raw.githubusercontent.com/SKuytov/gmsun/main/deploy/install.sh | sudo bash
set -euo pipefail

REPO="${GMSUN_REPO:-https://github.com/SKuytov/gmsun.git}"
DIR="${GMSUN_DIR:-/opt/gmsun}"
PORT="${GMSUN_PORT:-80}"

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)."; exit 1; fi

echo "==> Installing Docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl git gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
  # Docker may not have a repo for a brand-new Ubuntu release yet; fall back to the latest LTS codename.
  if ! curl -fsSI "https://download.docker.com/linux/ubuntu/dists/${CODENAME}/Release" >/dev/null 2>&1; then
    echo "   No Docker repo for '${CODENAME}' yet — using 'noble' packages."
    CODENAME=noble
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  apt-get install -y git >/dev/null 2>&1 || true
fi

echo "==> Fetching gmsun into ${DIR}"
if [[ -d "${DIR}/.git" ]]; then
  git -C "${DIR}" pull --ff-only
else
  git clone "${REPO}" "${DIR}"
fi
cd "${DIR}"

if [[ ! -f .env ]]; then
  echo "==> Creating .env with random secrets"
  cp .env.example .env
  sed -i "s|^HTTP_PORT=.*|HTTP_PORT=${PORT}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 16)|" .env
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" .env
  ADMIN_PW="$(openssl rand -base64 12 | tr -d '/+=' | cut -c1-12)"
  sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${ADMIN_PW}|" .env
  echo
  echo "   Admin login:  admin@gmsun.local / ${ADMIN_PW}   (also stored in ${DIR}/.env)"
  echo
fi

echo "==> Building and starting containers (first build takes a few minutes)"
docker compose up -d --build

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "gmsun is starting. Open:  http://${IP}:${PORT}/"
echo "Logs:    cd ${DIR} && docker compose logs -f"
echo "Update:  cd ${DIR} && git pull && docker compose up -d --build"
echo "Backup:  ${DIR}/deploy/backup.sh"
