"""Imports the self-hosted exercise clips into a database (2026-10-03).

Reads scripts/data/exercise_videos.json, which holds

  * ``new_exercises`` -- 32 exercises added from a trainer's clip library
    (full definition: description with technique/common mistake, muscles,
    target stats, patterns, equipment and the skill tags with their
    transfer notes), and
  * ``bindings`` -- clips attached to exercises the catalog already had
    (video_source_type='file', video_source_id=<clip file name without
    .mp4>).

Deliberately NOT a full catalog import: it only touches the exercises named
in the JSON, so it is safe next to the prod catalog (which differs from dev:
never run import_master_catalog.py there).

Dry run by default -- prints what it would do and writes nothing. Pass
--apply to write. Safe to re-run: an exercise that already exists is not
recreated (it only gets its clip bound if it has none), and a binding that is
already in place is skipped. An exercise that already has a DIFFERENT clip
is reported as a conflict and left alone unless --overwrite is given.

The clip files themselves are uploaded separately to /srv/hlu-media/
exercise-videos (docs/deploy.md, section 11.1); this script never touches
them.

Usage (on the server, from the project root):

    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/import_exercise_videos.py            # dry run
    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/import_exercise_videos.py --apply
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import EquipmentItem, Exercise, MovementPattern, TargetStat  # noqa: E402
from app.schemas.exercise import ExerciseCreate, ExerciseUpdate, MuscleGroupWeight  # noqa: E402
from app.schemas.skill import SkillTagCreate  # noqa: E402
from app.services.exercise_service import ExerciseService  # noqa: E402
from app.services.skill_service import SkillService  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parent / "data" / "exercise_videos.json"


async def main(args: argparse.Namespace) -> int:
    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    new_exercises = data["new_exercises"]
    bindings = data["bindings"]
    mode = "APPLY" if args.apply else "DRY RUN (nothing is written, pass --apply to write)"
    print(f"Mode: {mode}")
    print(f"Data: {len(new_exercises)} new exercises, {len(bindings)} bindings\n")

    async with AsyncSessionLocal() as session:
        exercise_service = ExerciseService(session)
        skill_service = SkillService(session)

        rows = await session.execute(
            select(Exercise.id, Exercise.name, Exercise.video_source_type, Exercise.video_source_id)
        )
        existing = {row.name: row for row in rows.all()}

        # Every skill the new exercises are tagged with must already exist
        # (seed_skills.py) -- check up front so a missing one aborts before
        # anything is written, not halfway through.
        skill_ids = {}
        missing_skills = set()
        for entry in new_exercises:
            for tag in entry["skill_tags"]:
                name = tag["skill"]
                if name in skill_ids or name in missing_skills:
                    continue
                skill = await skill_service.find_skill_by_name(name)
                if skill is None:
                    missing_skills.add(name)
                else:
                    skill_ids[name] = skill.id
        if missing_skills:
            print(f"ABORT: skills missing in this database: {sorted(missing_skills)}")
            print("Run scripts/seed_skills.py first.")
            return 1

        created = bound = already = conflicts = missing = 0

        async def bind(name: str, clip: str, label: str) -> str:
            """Attach the clip to an existing exercise. Returns the outcome."""
            row = existing[name]
            if row.video_source_type == "file" and row.video_source_id == clip:
                return "already"
            if row.video_source_id is not None and not args.overwrite:
                print(f"  CONFLICT ({label}): {name!r} already has "
                      f"{row.video_source_type}:{row.video_source_id}, wanted file:{clip} -- left alone")
                return "conflict"
            if args.apply:
                await exercise_service.update_exercise(
                    row.id, ExerciseUpdate(video_source_type="file", video_source_id=clip)
                )
            print(f"  bind ({label}): {name} -> {clip}")
            return "bound"

        print("== New exercises")
        for entry in new_exercises:
            name = entry["name"]
            clip = entry["video_source_id"]
            if name in existing:
                outcome = await bind(name, clip, "exists")
                already += outcome == "already"
                bound += outcome == "bound"
                conflicts += outcome == "conflict"
                if outcome == "already":
                    print(f"  skip (exists, clip already bound): {name}")
                continue

            print(f"  create: {name}  [{clip}]  skills: "
                  f"{', '.join(t['skill'] for t in entry['skill_tags'])}")
            created += 1
            if not args.apply:
                continue
            read = await exercise_service.create_exercise(
                ExerciseCreate(
                    name=name,
                    description=entry["description"],
                    category=entry["category"],
                    phase=entry["phase"],
                    difficulty_level=entry["difficulty_level"],
                    video_source_type="file",
                    video_source_id=clip,
                    target_sets=entry["target_sets"],
                    rep_range_min=entry["rep_range_min"],
                    rep_range_max=entry["rep_range_max"],
                    target_duration_seconds=entry["target_duration_seconds"],
                    tracks_weight=entry["tracks_weight"],
                    suitable_for_game_day=entry["suitable_for_game_day"],
                    is_unilateral=entry["is_unilateral"],
                    stimulus_type=entry["stimulus_type"],
                    exercise_type=entry["exercise_type"],
                )
            )
            await exercise_service.replace_target_stats(
                read.id, [TargetStat(s) for s in entry["target_stats"]]
            )
            await exercise_service.replace_movement_patterns(
                read.id, [MovementPattern(p) for p in entry["movement_patterns"]]
            )
            await exercise_service.replace_muscle_groups(
                read.id,
                [
                    MuscleGroupWeight(muscle_group=group, weight=weight)
                    for group, weight in entry["muscle_groups"].items()
                ],
            )
            if entry["equipment_items"]:
                await exercise_service.replace_equipment_items(
                    read.id, [EquipmentItem(i) for i in entry["equipment_items"]]
                )
            for tag in entry["skill_tags"]:
                await skill_service.create_tag(
                    skill_ids[tag["skill"]],
                    SkillTagCreate(exercise_id=read.id, transfer_note=tag["transfer_note"]),
                )
            # Content was reviewed and approved by the product owner.
            await exercise_service.update_exercise(read.id, ExerciseUpdate(admin_reviewed=True))

        print("\n== Bindings for existing exercises")
        for item in bindings:
            name, clip = item["name"], item["video_source_id"]
            if name not in existing:
                print(f"  MISSING in this database: {name}")
                missing += 1
                continue
            outcome = await bind(name, clip, "existing")
            already += outcome == "already"
            bound += outcome == "bound"
            conflicts += outcome == "conflict"

        verb = "" if args.apply else "would be "
        print(f"\nSummary: new exercises {verb}created {created}, clips {verb}bound {bound}, "
              f"already in place {already}, conflicts {conflicts}, names missing here {missing}.")
        if not args.apply:
            print("Dry run -- re-run with --apply to write.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace a different clip an exercise already has")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="path to the JSON data file")
    sys.exit(asyncio.run(main(parser.parse_args())))
