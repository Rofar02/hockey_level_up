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
gunzip -c "$DUMP" | docker exec -i "$CONTAINER" psql -q -U postgres -d restore >/dev/null 2>"$WORK/restore.log" || true

USERS="$(docker exec "$CONTAINER" psql -tA -U postgres -d restore -c 'SELECT count(*) FROM users' 2>/dev/null || echo 0)"
HEAD="$(docker exec "$CONTAINER" psql -tA -U postgres -d restore -c 'SELECT version_num FROM alembic_version' 2>/dev/null || echo '?')"
ERRORS="$(grep -c 'ERROR' "$WORK/restore.log" || true)"
ROLE_ERRORS="$(grep -c 'role .* does not exist' "$WORK/restore.log" || true)"

echo "    users: $USERS, alembic head: $HEAD, errors: $ERRORS (of them missing-role: $ROLE_ERRORS)"
if [ "${USERS:-0}" -gt 0 ] && [ "$ERRORS" -eq "$ROLE_ERRORS" ]; then
  echo "==> OK: the dump restores"
else
  echo "!! Restore check FAILED -- first errors:" >&2
  grep 'ERROR' "$WORK/restore.log" | grep -v 'role .* does not exist' | head -n 10 >&2 || true
  exit 1
fi
