"""One-off: delete every off_ice exercise while leaving on_ice exercises
completely untouched -- run this immediately before
import_master_catalog.py when switching an environment's off-ice catalog
over to the new master list (2026-08-31), without touching the separate
on-ice content.

session_blocks.exercise_id and set_completions.exercise_id deliberately
have no ON DELETE CASCADE (see their own model comments: "exercises are
curated, deleting one should never silently wipe a user's real training
history"), so deleting an off_ice exercise still referenced by either
would otherwise fail with a foreign-key violation. This script deletes
those referencing rows first, on purpose -- that means real logged
training history for off_ice exercises goes with them. Confirm that's
really wanted (e.g. on a server with no real users yet) before running
this against a database that matters.

Everything else that references an exercise (exercise_target_stats,
exercise_movement_patterns, exercise_muscle_groups, exercise_equipment_items,
skill_tags, user_movement_pattern_variants) already has ON DELETE CASCADE,
so it's cleaned up automatically the moment the exercise row itself is
deleted -- nothing to do for those here.

Run `alembic upgrade head` first if this is a fresh environment -- the
exercises table needs the admin_reviewed column
(migration ae98d105130e) before import_master_catalog.py can insert into
it.

Usage (run against whichever database DATABASE_URL points at):

    poetry run python scripts/wipe_off_ice_exercises.py

Prints exactly what it's about to delete and asks for a typed
confirmation before touching anything. Pass --yes to skip the prompt for
a scripted/CI run.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402


async def main(skip_confirm: bool) -> None:
    async with AsyncSessionLocal() as session:
        on_ice_count = (
            await session.execute(text("SELECT COUNT(*) FROM exercises WHERE category = 'on_ice'"))
        ).scalar_one()
        off_ice_count = (
            await session.execute(text("SELECT COUNT(*) FROM exercises WHERE category = 'off_ice'"))
        ).scalar_one()
        block_count = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM session_blocks sb "
                    "JOIN exercises e ON e.id = sb.exercise_id "
                    "WHERE e.category = 'off_ice'"
                )
            )
        ).scalar_one()
        set_count = (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM set_completions sc "
                    "JOIN exercises e ON e.id = sc.exercise_id "
                    "WHERE e.category = 'off_ice'"
                )
            )
        ).scalar_one()

        print(f"on_ice exercises -- KEPT, untouched: {on_ice_count}")
        print(f"off_ice exercises -- WILL BE DELETED: {off_ice_count}")
        print(f"  session_blocks referencing them -- WILL BE DELETED: {block_count}")
        print(f"  set_completions referencing them -- WILL BE DELETED: {set_count}")

        if off_ice_count == 0:
            print("Nothing to do.")
            return

        if not skip_confirm:
            answer = input('Type "YES" (all caps) to proceed, anything else to abort: ')
            if answer != "YES":
                print("Aborted -- nothing was changed.")
                return

        await session.execute(
            text(
                "DELETE FROM set_completions WHERE exercise_id IN "
                "(SELECT id FROM exercises WHERE category = 'off_ice')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM session_blocks WHERE exercise_id IN "
                "(SELECT id FROM exercises WHERE category = 'off_ice')"
            )
        )
        result = await session.execute(text("DELETE FROM exercises WHERE category = 'off_ice'"))
        await session.commit()
        print(f"Deleted {result.rowcount} off_ice exercises and their dependent rows.")
        print("Now run: poetry run python scripts/import_master_catalog.py")


if __name__ == "__main__":
    asyncio.run(main(skip_confirm="--yes" in sys.argv))
