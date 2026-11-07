#!/usr/bin/env bash
# Dump PostgreSQL + copy uploaded photos/PDFs into ./backups/gmsun-YYYYmmdd-HHMM.tar.gz
# Restore: see docs/DEPLOY.md
set -euo pipefail
cd "$(dirname "$0")/.."
STAMP="$(date +%Y%m%d-%H%M)"
OUT="backups/gmsun-${STAMP}"
mkdir -p "${OUT}"
set -a; . ./.env; set +a
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-gmsun}" -d "${POSTGRES_DB:-gmsun}" --no-owner > "${OUT}/db.sql"
docker compose cp api:/data "${OUT}/data"
tar -czf "${OUT}.tar.gz" -C backups "gmsun-${STAMP}"
rm -rf "${OUT}"
# keep the last 14 backups
ls -1t backups/gmsun-*.tar.gz | tail -n +15 | xargs -r rm -f
echo "Backup written: ${OUT}.tar.gz"
