#!/usr/bin/env bash
# Daily Postgres dump + upload-volume archive, with N-day retention, then a
# copy off the server (step 8, security, 5). Wire this into root's crontab
# on the server (see docs/deploy.md, "Бэкапы"):
#
#   0 3 * * * /opt/icelevel/deploy/backup.sh >> /var/log/icelevel-backup.log 2>&1
#
# Off-server copy: set in .env
#   BACKUP_PASSPHRASE   -- the archives are encrypted (gpg, AES256) before
#                          they leave the server: the dump holds emails and
#                          password hashes. Keep the passphrase outside the
#                          server too (password manager) -- without it a
#                          backup can't be opened.
#   BACKUP_REMOTE       -- rclone destination, e.g. offsite:icelevel-backups
#   RCLONE_CONFIG_OFFSITE_*  -- that remote's settings (type, provider, keys,
#                          endpoint), read by rclone straight from the env.
# Without BACKUP_REMOTE the backups stay on the server only, as before.

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/var/backups/icelevel}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
REMOTE_RETENTION_DAYS="${REMOTE_RETENTION_DAYS:-30}"
DATE="$(date +%F)"

# set -a: every variable from .env is exported, so rclone sees its
# RCLONE_CONFIG_* settings.
set -a
# shellcheck disable=SC1091
source .env
set +a

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

echo "==> Dumping Postgres ($POSTGRES_DB)"
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "$BACKUP_DIR/db-$DATE.sql.gz"

echo "==> Archiving upload volumes"
docker run --rm \
  -v icelevel_avatars_data:/avatars:ro \
  -v icelevel_reference_articles_data:/reference-articles:ro \
  -v icelevel_team_logos_data:/team-logos:ro \
  -v icelevel_feedback_data:/feedback:ro \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/uploads-$DATE.tar.gz" /avatars /reference-articles /team-logos /feedback

echo "==> Pruning local backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -name '*.gz' -mtime "+$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name '*.gpg' -mtime "+$RETENTION_DAYS" -delete

echo "==> Done locally: $BACKUP_DIR/db-$DATE.sql.gz, $BACKUP_DIR/uploads-$DATE.tar.gz"

if [ -z "${BACKUP_REMOTE:-}" ]; then
  echo "==> BACKUP_REMOTE not set -- no off-server copy"
  exit 0
fi
if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  echo "!! BACKUP_REMOTE is set but BACKUP_PASSPHRASE is not -- refusing to upload unencrypted dumps" >&2
  exit 1
fi

echo "==> Encrypting for the off-server copy"
for name in "db-$DATE.sql.gz" "uploads-$DATE.tar.gz"; do
  gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
    --passphrase-fd 3 --output "$BACKUP_DIR/$name.gpg" "$BACKUP_DIR/$name" \
    3<<<"$BACKUP_PASSPHRASE"
done

echo "==> Uploading to $BACKUP_REMOTE"
rclone copy "$BACKUP_DIR" "$BACKUP_REMOTE/daily" --include "*-$DATE.*.gpg"
# Exercise clips: public content, only new/changed files go up.
if [ -d /srv/hlu-media/exercise-videos ]; then
  rclone sync /srv/hlu-media/exercise-videos "$BACKUP_REMOTE/exercise-videos"
fi
# The .gpg copies exist only to be uploaded.
rm -f "$BACKUP_DIR"/*-"$DATE".*.gpg

echo "==> Pruning off-server backups older than $REMOTE_RETENTION_DAYS days"
rclone delete "$BACKUP_REMOTE/daily" --min-age "${REMOTE_RETENTION_DAYS}d"

echo "==> Done off-server: $BACKUP_REMOTE/daily"
