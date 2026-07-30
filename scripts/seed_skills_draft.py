"""Draft seed data for the Phase 6 skill layer -- REVIEW ONLY.

Unlike scripts/seed_exercises.py, this does not write to the database. It
only prints the proposed Skill / SkillStatWeight / SkillMilestone data so a
human can review the wording and weights before anyone turns it into a real
seed script:

    poetry run python scripts/seed_skills_draft.py

Weights per skill must sum to 1.0 (checked below) -- SkillStatWeight.weight
is a per-stat contribution, not independently bounded to 100%.
"""
import json
import sys

# Windows consoles/redirects often default stdout to a legacy codepage
# (e.g. cp1251), which mangles the Cyrillic skill/milestone text below.
sys.stdout.reconfigure(encoding="utf-8")

SKILLS: list[dict] = [
    {
        "name": "катание",
        "stat_weights": {
            "agility": 0.5,
            "strength": 0.3,
            "endurance": 0.2,
        },
        "milestones": [
            {
                "threshold": 20,
                "title": "Уверенно на коньках",
                "description": (
                    "Базовое катание перестало быть отдельной задачей — "
                    "можно сосредоточиться на игровой ситуации, а не на "
                    "балансе."
                ),
            },
            {
                "threshold": 45,
                "title": "Плавные повороты",
                "description": (
                    "Повороты и смена направления даются без потери "
                    "скорости — заметно меньше \"спотыканий\" на льду."
                ),
            },
            {
                "threshold": 70,
                "title": "Взрывной старт",
                "description": (
                    "Первые 3 шага разгона заметно быстрее среднего "
                    "любителя — отрыв от соперника на старте эпизода "
                    "становится реальным оружием."
                ),
            },
            {
                "threshold": 90,
                "title": "Катание высокого уровня",
                "description": (
                    "Скорость и манёвренность на уровне, где катание "
                    "перестаёт быть ограничением в игровых эпизодах любой "
                    "сложности."
                ),
            },
        ],
    },
    {
        "name": "бросок",
        "stat_weights": {
            "strength": 0.6,
            "agility": 0.2,
            "intellect": 0.2,
        },
        "milestones": [
            {
                "threshold": 20,
                "title": "Бросок с места",
                "description": (
                    "Хватает силы и техники, чтобы бросок долетал до "
                    "ворот с уверенной скоростью даже без разгона."
                ),
            },
            {
                "threshold": 45,
                "title": "Бросок в движении",
                "description": (
                    "Мощность броска сохраняется на ходу — не нужно "
                    "останавливаться, чтобы бросить сильно."
                ),
            },
            {
                "threshold": 70,
                "title": "Быстрый и неожиданный",
                "description": (
                    "Короткий замах и высокая скорость шайбы — вратарю "
                    "заметно меньше времени на реакцию."
                ),
            },
            {
                "threshold": 90,
                "title": "Оружие уровня команды",
                "description": (
                    "Бросок, которого ждут и боятся соперники — сила и "
                    "скорострельность на уровне, где решает исход "
                    "эпизода."
                ),
            },
        ],
    },
    {
        "name": "силовая борьба",
        "stat_weights": {
            "strength": 0.7,
            "endurance": 0.3,
        },
        "milestones": [
            {
                "threshold": 20,
                "title": "Не теряется у борта",
                "description": (
                    "Хватает силы удержать шайбу и позицию в первом "
                    "контакте у борта, не проигрывая единоборство сразу."
                ),
            },
            {
                "threshold": 45,
                "title": "Выигрывает единоборства",
                "description": (
                    "Устойчивая позиция и сила корпуса позволяют чаще "
                    "выигрывать борьбу один в один в стандартных игровых "
                    "ситуациях."
                ),
            },
            {
                "threshold": 70,
                "title": "Доминирует у борта",
                "description": (
                    "Соперник заметно реже решается идти в силовой "
                    "контакт напрямую — позиция и сила читаются как "
                    "преимущество."
                ),
            },
            {
                "threshold": 90,
                "title": "Неудобный соперник",
                "description": (
                    "Силовая борьба на уровне, где именно вы диктуете "
                    "исход контакта практически в любом единоборстве."
                ),
            },
        ],
    },
]


def main() -> None:
    for skill in SKILLS:
        total_weight = sum(skill["stat_weights"].values())
        status = "OK" if abs(total_weight - 1.0) < 1e-9 else "WARNING: does not sum to 1.0"
        print(f"=== {skill['name']} (weights sum={total_weight}) [{status}] ===")
        print(json.dumps(skill, ensure_ascii=False, indent=2))
        print()


if __name__ == "__main__":
    main()
