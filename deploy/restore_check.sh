#!/usr/bin/env bash
# Proves the latest dump actually restores (step 8, security, 5): a
# throwaway Postgres container, the dump loaded into it, a sanity count,
# the container removed. Touches nothing of the live stack.
#
#   deploy/restore_check.sh                 # newest db-*.sql.gz in BACKUP_DIR
#   deploy/restore_check.sh path/to/db-2026-10-12.sql.gz[.gpg]
#
# A .gpg file (an off-server copy) is decrypted with BACKUP_PASSPHRASE from
# .env first. Worth running monthly, and after any change to backup.sh.

set -euo pipefail

cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-/var/backups/icelevel}"
# Same major as the live postgres service in docker-compose.prod.yml.
PG_IMAGE="${PG_IMAGE:-postgres:16-alpine}"
CONTAINER="icelevel-restore-check-$$"

DUMP="${1:-$(ls -1t "$BACKUP_DIR"/db-*.sql.gz 2>/dev/null | head -n 1 || true)}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "!! No dump found (looked in $BACKUP_DIR)" >&2
  exit 1
fi

WORK="$(mktemp -d)"
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

if [[ "$DUMP" == *.gpg ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  echo "==> Decrypting $DUMP"
  gpg --batch --quiet --decrypt --passphrase-fd 3 --output "$WORK/dump.sql.gz" "$DUMP" \
    3<<<"${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE is not set in .env}"
  DUMP="$WORK/dump.sql.gz"
fi

# 2026-10-13 (А6): the file itself first -- a truncated or corrupt gzip, or
# a dump pg_dump never finished, fails here, before anything is restored.
echo "==> Checking $(basename "$DUMP")"
if ! gzip -t "$DUMP" 2>"$WORK/gzip.log"; then
  echo "!! Restore check FAILED -- not a valid gzip file:" >&2
  head -n 3 "$WORK/gzip.log" >&2
  exit 1
fi
if ! gunzip -c "$DUMP" | tail -n 5 | grep -q 'PostgreSQL database dump complete'; then
  echo "!! Restore check FAILED -- the dump has no 'dump complete' trailer (pg_dump was cut off)" >&2
  exit 1
fi
EXPECTED_TABLES="$(gunzip -c "$DUMP" | grep -c '^CREATE TABLE public\.' || true)"

echo "==> Starting a throwaway $PG_IMAGE"
docker run -d --name "$CONTAINER" -e POSTGRES_PASSWORD=check -e POSTGRES_DB=restore "$PG_IMAGE" >/dev/null
for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -U postgres -d restore >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "==> Restoring $(basename "$DUMP")"
# The dump names the prod role as owner; it doesn't exist here -- the
# ownership errors are expected, ON_ERROR_STOP stays off for them.
# psql itself still exits 0 on those; a non-zero exit means it could not run
# the dump at all (connection lost, out of disk) -- that fails the check.
if ! gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql -q -U postgres -d restore >/dev/null 2>"$WORK/restore.log"; then
  echo "!! Restore check FAILED -- psql could not load the dump:" >&2
  tail -n 10 "$WORK/restore.log" >&2
  exit 1
fi

USERS="$(docker exec "$CONTAINER" psql -tA -U postgres -d restore -c 'SELECT count(*) FROM users' 2>/dev/null || echo 0)"
HEAD="$(docker exec "$CONTAINER" psql -tA -U postgres -d restore -c 'SELECT version_num FROM alembic_version' 2>/dev/null || echo '?')"
ERRORS="$(grep -c 'ERROR' "$WORK/restore.log" || true)"
ROLE_ERRORS="$(grep -c 'role .* does not exist' "$WORK/restore.log" || true)"
TABLES="$(docker exec "$CONTAINER" psql -tA -U postgres -d restore -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'" 2>/dev/null || echo 0)"

echo "    users: $USERS, alembic head: $HEAD, tables: $TABLES of $EXPECTED_TABLES, errors: $ERRORS (of them missing-role: $ROLE_ERRORS)"
if [ "${USERS:-0}" -gt 0 ] && [ "$ERRORS" -eq "$ROLE_ERRORS" ] && [ "$EXPECTED_TABLES" -gt 0 ] && [ "$TABLES" -eq "$EXPECTED_TABLES" ]; then
  echo "==> OK: the dump restores"
else
  echo "!! Restore check FAILED -- first errors:" >&2
  grep 'ERROR' "$WORK/restore.log" | grep -v 'role .* does not exist' | head -n 10 >&2 || true
  exit 1
fi
