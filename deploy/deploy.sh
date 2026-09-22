#!/usr/bin/env bash
# Run on the SERVER, from the repo root, to ship whatever's on the tracked
# branch/tag. This is the whole "update via git pull" workflow the plan
# asked for.
#
#   cd /opt/icelevel && ./deploy/deploy.sh
#
# Migrations run automatically (see Dockerfile.prod's CMD) as part of the
# backend container starting -- there's no separate migration step here.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> git pull"
git pull --ff-only

echo "==> docker compose up -d --build"
docker compose -f docker-compose.prod.yml up -d --build

# 2026-09-22: nginx resolves the "backend" upstream hostname once and keeps
# that IP -- the line above always recreates the backend container (no
# service filter), which gets a new IP on the compose network every time,
# so nginx keeps routing to the now-dead old IP until something makes it
# re-resolve. Found live: /api/* 502s ("Host is unreachable") right after a
# deploy that otherwise looked clean, nginx's own error log named the stale
# IP. A plain restart (not recreate -- nginx's own image/config didn't
# change) is enough to force the fresh lookup.
echo "==> restarting nginx (picks up the backend's new container IP)"
docker compose -f docker-compose.prod.yml restart nginx

echo "==> pruning dangling images"
docker image prune -f

echo "==> backend logs (Ctrl+C to stop watching -- containers keep running)"
echo "    A failing migration crash-loops the backend container; check here first."
docker compose -f docker-compose.prod.yml logs --tail=50 -f backend
