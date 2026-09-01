"""Throwaway TEST DATA generator -- not real content.

Tags every currently-untagged MAIN-phase exercise with a skill (picked
round-robin over Skill, deterministic by exercise name order) so the admin
"skill tabs" filter has something in every tab to look at locally. Every
transfer_note is a placeholder, clearly marked, meant to be overwritten by
real admin work later -- this script exists purely to preview the UI, not
to seed production-quality SkillTag rows.

Every 4th exercise is left untagged on purpose, so the "Без навыка" tab
also has something in it to demo.

Idempotent-ish: only touches exercises with zero existing SkillTag rows, so
re-running after real tagging has started won't stomp on real work.

    poetry run python scripts/seed_test_skill_tags.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.exercise import Exercise, TrainingPhase  # noqa: E402
from app.models.skill import Skill, SkillTag  # noqa: E402

PLACEHOLDER_NOTE = (
    "[ТЕСТОВЫЕ ДАННЫЕ] Связь сгенерирована скриптом для проверки вкладок по "
    "навыкам в админке, а не настоящим переносом — заменить реальным "
    "обоснованием при ручной разметке."
)


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        already_tagged = set(
            (await session.execute(select(SkillTag.exercise_id))).scalars().all()
        )
        exercises = (
            (
                await session.execute(
                    select(Exercise)
                    .where(Exercise.phase == TrainingPhase.MAIN)
                    .where(Exercise.id.notin_(already_tagged) if already_tagged else True)
                    .order_by(Exercise.name)
                )
            )
            .scalars()
            .all()
        )
        skills = (await session.execute(select(Skill).order_by(Skill.name))).scalars().all()

        if not skills:
            print("No skills in DB -- run scripts/seed_skills.py first.")
            return
        if not exercises:
            print("No untagged MAIN-phase exercises left -- nothing to do.")
            return

        created = 0
        skipped_for_demo = 0
        for index, exercise in enumerate(exercises):
            # Leave every 4th one untagged so "Без навыка" has content too.
            if index % 4 == 3:
                skipped_for_demo += 1
                continue
            # `created`, not `index`, drives the round-robin -- index%4==3
            # would otherwise permanently exclude every skill whose own
            # position happens to be a multiple of 4 apart (12 skills is a
            # multiple of 4, so index%12 and index%4 would stay locked in
            # step for those skills every cycle).
            skill = skills[created % len(skills)]
            session.add(
                SkillTag(exercise_id=exercise.id, skill_id=skill.id, transfer_note=PLACEHOLDER_NOTE)
            )
            created += 1

        await session.commit()
        print(
            f"Created {created} placeholder SkillTag(s) across {len(skills)} skill(s); "
            f"left {skipped_for_demo} exercise(s) untagged on purpose."
        )


if __name__ == "__main__":
    asyncio.run(seed())
