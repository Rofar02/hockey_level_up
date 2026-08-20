#!/usr/bin/env bash
# Runs the full catalog seeding/backfill sequence from docs/deploy.md
# ("## 8. Сидирование базы") in one shot, in the documented order, against
# the prod compose stack. Every script it calls is idempotent (skips
# already-existing/already-correct rows), so this is safe to re-run after
# a fresh deploy or any time the catalog changes upstream.
#
# Run from the project root (where docker-compose.prod.yml lives):
#     bash scripts/seed_all_prod.sh
#
# Stops on the first failing step (set -e) rather than plowing ahead --
# if something fails partway through, fix the reported error and re-run
# the whole script; every step is safe to repeat.

set -euo pipefail

COMPOSE_FILE="docker-compose.prod.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "ERROR: $COMPOSE_FILE not found in $(pwd) -- run this from the project root." >&2
  exit 1
fi

run() {
  echo "==> $1"
  docker compose -f "$COMPOSE_FILE" exec backend python "$1"
}

run scripts/seed_exercises.py
run scripts/fix_joint_gymnastics_phase.py
run scripts/seed_offseason_catalog_additions.py
run scripts/backfill_warmup_stages.py
run scripts/backfill_coordination_patterns.py
run scripts/backfill_forearms_muscle_group.py
run scripts/seed_skills.py
run scripts/seed_skill_tags.py
run scripts/seed_skill_milestones_skating.py
run scripts/seed_skill_milestones_phase7.py
run scripts/seed_skill_shot_accuracy.py
run scripts/seed_reference_articles.py

echo "==> Done -- prod catalog now matches dev."
