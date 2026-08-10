"""Seed script for the "Точность броска" skill (real DB insert).

Creates the skill itself, its SkillStatWeight rows, and its 4
SkillMilestone thresholds in one script -- unlike the Phase 7 catalog
(seed_skills.py + seed_skill_milestones_phase7.py as two passes), this is
a single new skill added after that catalog shipped, so skill + weights +
milestones are seeded together here.

Idempotent: skips the skill (and its weights) entirely if a skill named
"Точность броска" already exists; skips milestones separately if that
skill already has any.

    poetry run python scripts/seed_skill_shot_accuracy.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.skill import Skill, SkillMilestone, SkillStatWeight  # noqa: E402

SKILL_NAME = "Точность броска"
REQUIRED_LEVEL = 1  # available immediately, same as the rest of the Phase 7 catalog

STAT_WEIGHTS: dict[str, float] = {
    "intellect": 0.3,
    "agility": 0.2,
    "puck_handling": 0.5,
}

MILESTONES: list[dict] = [
    {
        "threshold": 20,
        "title": "Первые попадания",
        "description": "Начинаете чувствовать, куда летит шайба после броска — уже не совсем случайно.",
    },
    {
        "threshold": 45,
        "title": "Стабильная меткость",
        "description": "Большинство бросков идут туда, куда планировали, даже под небольшим давлением.",
    },
    {
        "threshold": 70,
        "title": "Прицельный бросок",
        "description": "Можете выбирать угол броска осознанно, а не просто бить сильнее в сторону ворот.",
    },
    {
        "threshold": 90,
        "title": "Снайперская точность",
        "description": (
            "Точность на уровне, где вратарь должен угадывать направление заранее, "
            "а не реагировать по факту."
        ),
    },
]


async def seed() -> None:
    total_weight = sum(STAT_WEIGHTS.values())
    assert abs(total_weight - 1.0) < 1e-9, f"weights sum to {total_weight}, not 1.0"

    async with AsyncSessionLocal() as session:
        skill_id = (
            await session.execute(select(Skill.id).where(Skill.name == SKILL_NAME))
        ).scalar_one_or_none()

        if skill_id is None:
            skill = Skill(name=SKILL_NAME, required_level=REQUIRED_LEVEL)
            session.add(skill)
            await session.flush()
            skill_id = skill.id
            for stat_type, weight in STAT_WEIGHTS.items():
                session.add(SkillStatWeight(skill_id=skill_id, stat_type=stat_type, weight=weight))
            print(f"Created skill {SKILL_NAME!r} with {len(STAT_WEIGHTS)} stat weight(s).")
        else:
            print(f"Skill {SKILL_NAME!r} already exists, skipping skill/weights.")

        existing_milestones = (
            await session.execute(
                select(SkillMilestone.id).where(SkillMilestone.skill_id == skill_id)
            )
        ).scalars().all()
        if existing_milestones:
            print(f"{SKILL_NAME!r} already has {len(existing_milestones)} milestone(s), skipping.")
        else:
            for data in MILESTONES:
                session.add(SkillMilestone(skill_id=skill_id, **data))
            print(f"Seeded {len(MILESTONES)} milestone(s) for {SKILL_NAME!r}.")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
