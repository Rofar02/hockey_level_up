"""Archives the duplicate exercises agreed with the product owner (2026-10-03).

Each pair is (keep, archive): the exercise to keep is the one with the better
description / transfer note (the product owner's own reviewed edits win); the
other is archived -- the same `is_archived` flag the admin panel's Archive
button sets. Archived exercises drop out of future session assembly; past
sessions and history are untouched, nothing is deleted, and it can be undone
from the admin panel (Unarchive).

Safety rules:
  * dry run by default -- pass --apply to write;
  * a pair is archived ONLY if the exercise to keep exists here and is not
    archived itself (never lose an exercise without its replacement);
  * a name that does not exist in this database is simply skipped (the prod
    catalog is not the dev catalog);
  * only `is_archived` is written -- no other field of any exercise changes.

Usage (on the server, from the project root):

    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/archive_duplicate_exercises.py            # dry run
    docker compose -f docker-compose.prod.yml exec backend \
        python scripts/archive_duplicate_exercises.py --apply
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseUpdate
from app.services.exercise_service import ExerciseService

# (keep, archive)
PAIRS = [
    ("Присед со штангой на спине", "Приседания со штангой"),
    ("Планка", "Прямая планка"),
    ("Кроссовер", "Скрестный шаг"),
    ("Прыжок на тумбу", "Прыжки на тумбу"),
    ("Приводящие в длинной позиции (ПНФ)", "Привод ПНФ"),
    ("Боковая ходьба с мини-бэндом", "Lateral band walk"),
    ("Слайд лопаток у стены", "Wall slides"),
    ("Горизонтальная тяга сидя на 1 колене", "Тяга сидя на одном колене (горизонтальная)"),
    ("Координационная лестница", "Лестница для ног (agility ladder)"),
    ("Мобилизация грудного отдела на валике", "Мобилизация грудного отдела с роликом под лопатками"),
    ("Голубь (ПНФ)", "Голубь ПНФ"),
    ("Квадрицепс с задней ногой на возвышении", "Растяжка кушетка"),
    ("Ягодица крест-накрест лёжа", "Растяжка грушевидной мышцы"),
]


async def history(session, exercise_id) -> tuple[int, int]:
    blocks = await session.scalar(
        text("select count(*) from session_blocks where exercise_id = :i"), {"i": exercise_id}
    )
    sets = await session.scalar(
        text("select count(*) from set_completions where exercise_id = :i"), {"i": exercise_id}
    )
    return blocks, sets


async def main(apply: bool, pairs: list[tuple[str, str]]) -> int:
    print("Mode:", "APPLY" if apply else "DRY RUN (nothing is written, pass --apply to write)", "\n")
    archived = skipped = refused = 0
    async with AsyncSessionLocal() as session:
        service = ExerciseService(session)
        rows = await session.execute(
            select(Exercise.id, Exercise.name, Exercise.is_archived, Exercise.admin_reviewed)
        )
        by_name = {row.name: row for row in rows.all()}

        for keep_name, drop_name in pairs:
            keep, drop = by_name.get(keep_name), by_name.get(drop_name)
            if drop is None:
                print(f"SKIP   not in this database: {drop_name!r}")
                skipped += 1
                continue
            if drop.is_archived:
                print(f"SKIP   already archived: {drop_name!r}")
                skipped += 1
                continue
            if keep is None or keep.is_archived:
                why = "missing" if keep is None else "archived"
                print(f"REFUSE {drop_name!r}: the exercise to keep, {keep_name!r}, is {why} here")
                refused += 1
                continue
            blocks, sets = await history(session, drop.id)
            print(f"ARCHIVE {drop_name!r}  (history: {blocks} plan blocks, {sets} sets)  "
                  f"-> keeps {keep_name!r}{' [admin-reviewed]' if keep.admin_reviewed else ''}")
            if apply:
                await service.update_exercise(drop.id, ExerciseUpdate(is_archived=True))
            archived += 1

    verb = "" if apply else "would be "
    print(f"\nSummary: {verb}archived {archived}, skipped {skipped}, refused {refused}.")
    if not apply:
        print("Dry run -- re-run with --apply to write.")
    return 1 if refused else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default is a dry run)")
    parser.add_argument("--pairs", help="JSON file with [[keep, archive], ...] instead of the built-in list "
                                        "(e.g. scripts/data/archive_pairs_2.json)")
    args = parser.parse_args()
    chosen = PAIRS
    if args.pairs:
        chosen = [tuple(pair) for pair in json.loads(Path(args.pairs).read_text(encoding="utf-8"))]
    sys.exit(asyncio.run(main(args.apply, chosen)))
