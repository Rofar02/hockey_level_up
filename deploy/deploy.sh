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

echo "==> pruning dangling images"
docker image prune -f

echo "==> backend logs (Ctrl+C to stop watching -- containers keep running)"
echo "    A failing migration crash-loops the backend container; check here first."
docker compose -f docker-compose.prod.yml logs --tail=50 -f backend
