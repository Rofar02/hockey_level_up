"""Seed script for the "Катание" SkillMilestone thresholds (real DB insert).

Only "Катание" is seeded for real here -- its wording was already reviewed
and approved. The other 10 Phase 7 skills only have draft milestones
(printed by a human for review, never written to the DB) until they're
signed off; see the assistant's Phase 7 handoff notes for that draft text.

Idempotent: skips seeding entirely if "Катание" already has any milestones.

    poetry run python scripts/seed_skill_milestones_skating.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.skill import Skill, SkillMilestone  # noqa: E402

SKILL_NAME = "Катание"

MILESTONES: list[dict] = [
    {
        "threshold": 20,
        "title": "Базовая устойчивость",
        "description": "держишь равновесие в развороте на среднем темпе",
    },
    {
        "threshold": 45,
        "title": "Уверенный разворот",
        "description": "входишь в поворот на скорости без потери равновесия",
    },
    {
        "threshold": 70,
        "title": "Взрывной старт",
        "description": "первые 3 шага разгона заметно быстрее среднего любителя",
    },
    {
        "threshold": 90,
        "title": "Игровой темп",
        "description": "держишь высокий темп катания весь период без потери техники",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        skill_id = (
            await session.execute(select(Skill.id).where(Skill.name == SKILL_NAME))
        ).scalar_one_or_none()
        if skill_id is None:
            print(f"Skill {SKILL_NAME!r} not found -- run scripts/seed_skills.py first.")
            return

        existing_count = (
            await session.execute(
                select(SkillMilestone.id).where(SkillMilestone.skill_id == skill_id)
            )
        ).scalars().all()
        if existing_count:
            print(f"{SKILL_NAME!r} already has {len(existing_count)} milestone(s), skipping.")
            return

        for data in MILESTONES:
            session.add(SkillMilestone(skill_id=skill_id, **data))

        await session.commit()
        print(f"Seeded {len(MILESTONES)} milestone(s) for {SKILL_NAME!r}.")


if __name__ == "__main__":
    asyncio.run(seed())
