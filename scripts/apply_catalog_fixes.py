"""Applies agreed metadata corrections to warm-up / cool-down exercises (2026-10-03).

Reads scripts/data/catalog_metadata_fixes.json: a list of
{"name", "changes": {field: {"old": ..., "new": ...}}} with these fields:

  equipment                list of EquipmentItem values (e.g. ["foam_roller"])
  is_unilateral            true
  target_duration_seconds  int
  sets_reps                [target_sets, rep_range_min, rep_range_max]
  muscles                  {muscle_group: weight}
  description, phase, warmup_stage, admin_reviewed, is_archived
                           plain scalar values (enums as their string value)

Written for a catalog the product owner has edited by hand, so it only ever
does the minimum:
  * dry run by default -- pass --apply to write;
  * every field is changed ONLY if its current value is exactly `old`
    (a value the owner changed after the export is reported and left alone);
  * an exercise that is missing or archived is skipped;
  * nothing else on the exercise is touched (descriptions, flags, video,
    phase, patterns, stats stay as they are).

Usage (on the server, from the project root):

    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/apply_catalog_fixes.py            # dry run
    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/apply_catalog_fixes.py --apply
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseEquipmentItem,
    ExerciseMuscleGroup,
)
from app.schemas.exercise import ExerciseUpdate, MuscleGroupWeight
from app.services.exercise_service import ExerciseService

SCALAR_FIELDS = {"description", "phase", "warmup_stage", "admin_reviewed", "is_archived"}
DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "catalog_metadata_fixes.json"


def val(x):
    return x.value if hasattr(x, "value") else x


async def main(args: argparse.Namespace) -> int:
    items = json.loads(Path(args.data).read_text(encoding="utf-8"))
    print("Mode:", "APPLY" if args.apply else "DRY RUN (nothing is written, pass --apply to write)")
    print(f"Data: {len(items)} exercises\n")
    applied: dict[str, int] = {}
    skipped = {"missing": [], "archived": [], "changed_since_export": []}

    async with AsyncSessionLocal() as session:
        service = ExerciseService(session)
        rows = await session.execute(select(Exercise))
        by_name = {e.name: e for e in rows.scalars().all()}
        equip_rows = await session.execute(select(ExerciseEquipmentItem))
        equip: dict = {}
        for r in equip_rows.scalars().all():
            equip.setdefault(r.exercise_id, []).append(val(r.equipment_item))
        muscle_rows = await session.execute(select(ExerciseMuscleGroup))
        muscles: dict = {}
        for r in muscle_rows.scalars().all():
            muscles.setdefault(r.exercise_id, {})[val(r.muscle_group)] = round(float(r.weight), 4)

        for item in items:
            name = item["name"]
            ex = by_name.get(name)
            if ex is None:
                skipped["missing"].append(name)
                continue
            if ex.is_archived:
                skipped["archived"].append(name)
                continue
            for field, change in item["changes"].items():
                old, new = change["old"], change["new"]
                if field == "equipment":
                    current = sorted(equip.get(ex.id, []))
                    ok = current == sorted(old)
                elif field == "is_unilateral":
                    current, ok = ex.is_unilateral, ex.is_unilateral == old
                elif field == "target_duration_seconds":
                    current, ok = ex.target_duration_seconds, ex.target_duration_seconds == old
                elif field == "sets_reps":
                    current = [ex.target_sets, ex.rep_range_min, ex.rep_range_max]
                    ok = current == old
                elif field == "muscles":
                    current = muscles.get(ex.id, {})
                    ok = {k: round(float(v), 4) for k, v in current.items()} == {
                        k: round(float(v), 4) for k, v in old.items()
                    }
                elif field in SCALAR_FIELDS:
                    current = val(getattr(ex, field))
                    ok = current == old
                else:
                    raise SystemExit(f"unknown field {field!r}")
                if not ok:
                    skipped["changed_since_export"].append(f"{name} [{field}]")
                    continue
                shown = (lambda t: t if not isinstance(t, str) or len(t) < 60 else t[:57] + "...")
                print(f"  {name}: {field} {shown(old)} -> {shown(new)}")
                if args.apply:
                    if field == "equipment":
                        await service.replace_equipment_items(ex.id, [EquipmentItem(i) for i in new])
                    elif field == "muscles":
                        await service.replace_muscle_groups(
                            ex.id, [MuscleGroupWeight(muscle_group=g, weight=w) for g, w in new.items()]
                        )
                    elif field == "sets_reps":
                        await service.update_exercise(
                            ex.id,
                            ExerciseUpdate(target_sets=new[0], rep_range_min=new[1], rep_range_max=new[2]),
                        )
                    else:
                        await service.update_exercise(ex.id, ExerciseUpdate(**{field: new}))
                applied[field] = applied.get(field, 0) + 1

    verb = "" if args.apply else "would be "
    print(f"\nSummary: changes {verb}applied by field: {applied or 'none'}")
    for key, names in skipped.items():
        if names:
            print(f"  skipped, {key}: {len(names)}  e.g. {names[:4]}")
    if not args.apply:
        print("Dry run -- re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="path to the JSON data file")
    sys.exit(asyncio.run(main(parser.parse_args())))
