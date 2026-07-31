"""Seed script for the Phase 7 skill catalog (real DB insert).

Creates the 11 skills used by the onboarding skill picker, each with its
SkillStatWeight rows. Idempotent: skips any skill whose `name` already
exists (does not touch its weights).

    poetry run python scripts/seed_skills.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.skill import Skill, SkillStatWeight  # noqa: E402

SKILLS: list[dict] = [
    {
        "name": "Взрывной старт",
        "stat_weights": {"strength": 0.6, "agility": 0.4},
    },
    {
        "name": "Силовая борьба",
        "stat_weights": {"strength": 0.7, "endurance": 0.3},
    },
    {
        "name": "Сила броска",
        "stat_weights": {"strength": 0.8, "agility": 0.2},
    },
    {
        "name": "Выносливость",
        "stat_weights": {"endurance": 1.0},
    },
    {
        "name": "Скоростная выносливость",
        "stat_weights": {"strength": 0.2, "agility": 0.3, "endurance": 0.5},
    },
    {
        "name": "Координация и реакция",
        "stat_weights": {"agility": 0.8, "intellect": 0.2},
    },
    {
        "name": "Баланс и устойчивость",
        "stat_weights": {"strength": 0.4, "agility": 0.6},
    },
    {
        "name": "Мобильность",
        "stat_weights": {"agility": 0.7, "endurance": 0.3},
    },
    {
        "name": "Катание",
        "stat_weights": {"strength": 0.3, "agility": 0.5, "endurance": 0.2},
    },
    {
        "name": "Обводка",
        "stat_weights": {"agility": 0.6, "intellect": 0.4},
    },
    {
        "name": "Игровое чтение",
        "stat_weights": {"agility": 0.3, "intellect": 0.7},
    },
]


async def seed() -> None:
    for skill in SKILLS:
        total = sum(skill["stat_weights"].values())
        assert abs(total - 1.0) < 1e-9, f"{skill['name']}: weights sum to {total}, not 1.0"

    async with AsyncSessionLocal() as session:
        existing_names = set((await session.execute(select(Skill.name))).scalars().all())

        created = 0
        for data in SKILLS:
            if data["name"] in existing_names:
                continue
            skill = Skill(name=data["name"])
            session.add(skill)
            await session.flush()
            for stat_type, weight in data["stat_weights"].items():
                session.add(SkillStatWeight(skill_id=skill.id, stat_type=stat_type, weight=weight))
            created += 1

        await session.commit()
        print(f"Seeded {created} new skill(s), skipped {len(SKILLS) - created} existing.")


if __name__ == "__main__":
    asyncio.run(seed())
