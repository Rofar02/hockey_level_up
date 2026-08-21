"""One-off script: fully reset training progress for every registered user.

Wipes everything the assessment/leveling system has accumulated so each
user starts over as if freshly registered:

  - deletes all UserStat rows (strength/agility/intellect/endurance/
    on_ice_skating/puck_handling current values)
  - deletes all StatHistory rows (the audit trail those values were built
    from)
  - users.xp -> 0, users.level -> 1
  - users.fitness_tier -> NULL (it's a byproduct of the off-ice test result
    that no longer exists)
  - users.has_assessment / has_onice_assessment -> False and
    users.suggested_reassessment / suggested_onice_reassessment -> False,
    so AssessmentService._check_gate treats every user as never having
    taken either test (mirrors a brand-new account, not a "retake unlocked"
    state) and they see the onboarding test again rather than a locked
    reassessment screen.

Destructive and irreversible -- there is no dry-run, this commits the
delete. Take a DB backup first (see deploy/backup.sh / docs/deploy.md)
before running this against prod. Requires --yes to actually commit;
without it, prints what it would do and exits.

    poetry run python scripts/reset_all_user_stats.py --yes

Against the prod compose stack:

    docker compose -f docker-compose.prod.yml exec backend \\
        python scripts/reset_all_user_stats.py --yes
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.progress import StatHistory, UserStat  # noqa: E402
from app.models.user import User  # noqa: E402


async def reset_all_user_stats(session: AsyncSession, *, commit: bool) -> None:
    user_count = (await session.execute(select(func.count(User.id)))).scalar_one()
    stat_count = (await session.execute(select(func.count(UserStat.id)))).scalar_one()
    history_count = (await session.execute(select(func.count(StatHistory.id)))).scalar_one()

    print(f"Users affected: {user_count}")
    print(f"UserStat rows to delete: {stat_count}")
    print(f"StatHistory rows to delete: {history_count}")
    print(
        "Also resetting per-user: xp=0, level=1, fitness_tier=NULL, "
        "has_assessment=False, suggested_reassessment=False, "
        "has_onice_assessment=False, suggested_onice_reassessment=False"
    )

    if not commit:
        print("\nDry run (no --yes passed) -- nothing was changed.")
        return

    await session.execute(delete(StatHistory))
    await session.execute(delete(UserStat))

    result = await session.execute(select(User))
    for user in result.scalars().all():
        user.xp = 0
        user.level = 1
        user.fitness_tier = None
        user.has_assessment = False
        user.suggested_reassessment = False
        user.has_onice_assessment = False
        user.suggested_onice_reassessment = False

    await session.commit()
    print("\nDone -- all users reset.")


async def main() -> None:
    commit = "--yes" in sys.argv[1:]
    async with AsyncSessionLocal() as session:
        await reset_all_user_stats(session, commit=commit)


if __name__ == "__main__":
    asyncio.run(main())
