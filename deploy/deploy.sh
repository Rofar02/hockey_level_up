#!/usr/bin/env bash
# Run on the SERVER, from the repo root, to ship whatever's on the tracked
# branch/tag. This is the whole "update via git pull" workflow the plan
# asked for.
#
#   cd /opt/icelevel && ./deploy/deploy.sh
#
# Migrations run automatically: the one-shot `migrate` service in
# docker-compose.prod.yml applies them before backend/worker start. If one
# fails, `up` below fails (set -e stops the script) and the old containers
# keep serving.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> git pull"
git pull --ff-only

echo "==> docker compose up -d --build --remove-orphans"
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

# 15.10: the edge nginx reads deploy/nginx/active.conf (gitignored, bind
# mounted), not app.conf -- a change to app.conf used to reach prod only if
# someone remembered to copy it by hand. Copied here, checked with
# `nginx -t`, and put back as it was if the check fails (the old config
# keeps serving). `cp` onto the existing file, never `mv`: the bind mount
# follows the file's inode. Skipped while active.conf is still the
# certbot bootstrap config (docs/deploy.md §5).
NGINX_DIR=deploy/nginx
if [ -f "$NGINX_DIR/active.conf" ] && ! cmp -s "$NGINX_DIR/bootstrap.conf" "$NGINX_DIR/active.conf"     && ! cmp -s "$NGINX_DIR/app.conf" "$NGINX_DIR/active.conf"; then
  echo "==> nginx config changed: app.conf -> active.conf"
  cp "$NGINX_DIR/active.conf" "$NGINX_DIR/active.conf.prev"
  cp "$NGINX_DIR/app.conf" "$NGINX_DIR/active.conf"
  if ! docker compose -f docker-compose.prod.yml exec -T nginx nginx -t; then
    echo "!!! nginx -t failed -- restoring the previous active.conf" >&2
    cp "$NGINX_DIR/active.conf.prev" "$NGINX_DIR/active.conf"
    NGINX_CONFIG_FAILED=1
  fi
fi

# 2026-09-22: nginx resolves the "backend" upstream hostname once and keeps
# that IP -- the line above always recreates the backend container (no
# service filter), which gets a new IP on the compose network every time,
# so nginx keeps routing to the now-dead old IP until something makes it
# re-resolve. Found live: /api/* 502s ("Host is unreachable") right after a
# deploy that otherwise looked clean, nginx's own error log named the stale
# IP. A plain restart (not recreate -- nginx's own image/config didn't
# change) is enough to force the fresh lookup. It also loads a new
# active.conf from the step above.
echo "==> restarting nginx (picks up the backend's new container IP and its config)"
docker compose -f docker-compose.prod.yml restart nginx

# Smoke test of what the phones depend on (docs/deploy.md §12): the service
# worker is always revalidated, hashed assets are cached for good,
# version.json is the build stamp (not the SPA's index.html fallback).
SMOKE_HOST=${SMOKE_HOST:-icelevel.ru}
smoke() {
  curl -sk --max-time 10 --resolve "$SMOKE_HOST:443:127.0.0.1" "$@"
}
SMOKE_FAILED=0
sleep 3
# Each answer captured first: with pipefail, `curl | grep -q` fails when
# grep stops reading early.
SW_HEADERS=$(smoke -I "https://$SMOKE_HOST/sw.js" || true)
if ! grep -qi '^cache-control:.*no-cache' <<<"$SW_HEADERS"; then
  echo "!!! smoke: /sw.js has no 'Cache-Control: no-cache'" >&2
  SMOKE_FAILED=1
fi
INDEX_HTML=$(smoke "https://$SMOKE_HOST/" || true)
ASSET=$(grep -o '/assets/[^"]*\.js' <<<"$INDEX_HTML" | head -n 1 || true)
ASSET_HEADERS=$( [ -n "$ASSET" ] && smoke -I "https://$SMOKE_HOST$ASSET" || true)
if ! grep -qi '^cache-control:.*immutable' <<<"$ASSET_HEADERS"; then
  echo "!!! smoke: /assets/* is not 'immutable' (${ASSET:-no asset found in index.html})" >&2
  SMOKE_FAILED=1
fi
VERSION_JSON=$(smoke "https://$SMOKE_HOST/version.json" || true)
if ! grep -q '^{"build"' <<<"$VERSION_JSON"; then
  echo "!!! smoke: /version.json is not the build stamp JSON" >&2
  SMOKE_FAILED=1
fi
if [ "${NGINX_CONFIG_FAILED:-0}" = 1 ] || [ "$SMOKE_FAILED" = 1 ]; then
  echo "!!! deploy finished WITH PROBLEMS (see above)" >&2
else
  echo "==> smoke: sw.js no-cache, assets immutable, version.json ok"
fi

echo "==> pruning dangling images"
docker image prune -f

echo "==> migration log"
docker compose -f docker-compose.prod.yml logs --tail=20 migrate

echo "==> backend + worker logs (Ctrl+C to stop watching -- containers keep running)"
docker compose -f docker-compose.prod.yml logs --tail=50 -f backend worker
