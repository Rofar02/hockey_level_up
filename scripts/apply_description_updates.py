"""Applies reviewed description rewrites to warm-up / cool-down exercises (2026-10-03).

Reads scripts/data/warmup_cooldown_descriptions.json: a list of
{"name", "old", "new", "mark"} where `old` is the description the rewrite was
based on and `mark` says whether the exercise also gets the admin-reviewed flag.

Written for a catalog the product owner has been editing by hand, so it only
ever does the minimum:
  * dry run by default -- pass --apply to write;
  * writes ONLY `description` (and `admin_reviewed=True` where mark is true) --
    no other field of any exercise is touched;
  * an exercise is changed ONLY if its current description is exactly `old`
    (so a hand edit made after the export is never overwritten), it is
    not archived, it is a warm-up/cool-down exercise and it is not already
    admin-reviewed;
  * a name that does not exist in the database is skipped.

Usage (on the server, from the project root):

    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/apply_description_updates.py            # dry run
    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/apply_description_updates.py --apply
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseUpdate
from app.services.exercise_service import ExerciseService

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "warmup_cooldown_descriptions.json"
ALLOWED_PHASES = {"warmup", "cooldown"}


async def main(args: argparse.Namespace) -> int:
    items = json.loads(Path(args.data).read_text(encoding="utf-8"))
    print("Mode:", "APPLY" if args.apply else "DRY RUN (nothing is written, pass --apply to write)")
    print(f"Data: {len(items)} rewrites\n")
    updated = marked = 0
    skipped = {"missing": [], "archived": [], "wrong_phase": [], "already_reviewed": [], "changed_since_export": [], "already_new": []}

    async with AsyncSessionLocal() as session:
        service = ExerciseService(session)
        rows = await session.execute(
            select(Exercise.id, Exercise.name, Exercise.description, Exercise.phase,
                   Exercise.is_archived, Exercise.admin_reviewed)
        )
        by_name = {r.name: r for r in rows.all()}
        for item in items:
            name, old, new = item["name"], (item["old"] or "").strip(), item["new"].strip()
            row = by_name.get(name)
            if row is None:
                skipped["missing"].append(name)
                continue
            current = (row.description or "").strip()
            phase = row.phase.value if hasattr(row.phase, "value") else str(row.phase)
            if row.is_archived:
                skipped["archived"].append(name)
            elif phase not in ALLOWED_PHASES:
                skipped["wrong_phase"].append(name)
            elif row.admin_reviewed:
                skipped["already_reviewed"].append(name)
            elif current == new:
                skipped["already_new"].append(name)
            elif current != old:
                skipped["changed_since_export"].append(name)
            else:
                data = {"description": new}
                if item["mark"]:
                    data["admin_reviewed"] = True
                if args.apply:
                    await service.update_exercise(row.id, ExerciseUpdate(**data))
                updated += 1
                marked += bool(item["mark"])
                continue

    verb = "" if args.apply else "would be "
    print(f"Summary: descriptions {verb}updated {updated} (of them {verb}marked reviewed {marked}).")
    for key, names in skipped.items():
        if names:
            print(f"  skipped, {key}: {len(names)}" + (f"  e.g. {names[:4]}" if key != "already_new" else ""))
    if not args.apply:
        print("Dry run -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="path to the JSON data file")
    sys.exit(asyncio.run(main(parser.parse_args())))
