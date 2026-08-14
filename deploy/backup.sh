#!/usr/bin/env bash
# Daily Postgres dump + upload-volume archive, with N-day retention. Wire
# this into root's crontab on the server (see docs/deploy.md):
#
#   0 3 * * * /opt/icelevel/deploy/backup.sh >> /var/log/icelevel-backup.log 2>&1

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/var/backups/icelevel}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DATE="$(date +%F)"

# shellcheck disable=SC1091
source .env

mkdir -p "$BACKUP_DIR"

echo "==> Dumping Postgres ($POSTGRES_DB)"
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$BACKUP_DIR/db-$DATE.sql.gz"

echo "==> Archiving upload volumes"
docker run --rm \
  -v icelevel_avatars_data:/avatars:ro \
  -v icelevel_reference_articles_data:/reference-articles:ro \
  -v icelevel_team_logos_data:/team-logos:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/uploads-$DATE.tar.gz" /avatars /reference-articles /team-logos

echo "==> Pruning backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -name '*.gz' -mtime "+$RETENTION_DAYS" -delete

echo "==> Done: $BACKUP_DIR/db-$DATE.sql.gz, $BACKUP_DIR/uploads-$DATE.tar.gz"
