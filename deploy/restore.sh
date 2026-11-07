#!/usr/bin/env bash
# Restore a backup created by backup.sh:  deploy/restore.sh backups/gmsun-20261107-1200.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f "${1:-}" ]] || { echo "usage: $0 <backup.tar.gz>"; exit 1; }
TMP="$(mktemp -d)"; tar -xzf "$1" -C "${TMP}"; SRC="$(find "${TMP}" -maxdepth 1 -mindepth 1 -type d | head -1)"
set -a; . ./.env; set +a
docker compose up -d db
docker compose exec -T db psql -U "${POSTGRES_USER:-gmsun}" -d postgres -c "DROP DATABASE IF EXISTS ${POSTGRES_DB:-gmsun};" -c "CREATE DATABASE ${POSTGRES_DB:-gmsun};"
docker compose exec -T db psql -U "${POSTGRES_USER:-gmsun}" -d "${POSTGRES_DB:-gmsun}" < "${SRC}/db.sql"
docker compose up -d api
docker compose cp "${SRC}/data/." api:/data
docker compose restart api
rm -rf "${TMP}"
echo "Restored from $1"
