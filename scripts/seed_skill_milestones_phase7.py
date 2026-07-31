"""Seed script for the 10 remaining Phase 7 SkillMilestone sets (real DB insert).

These are the drafts reviewed and approved by the product owner (the
"Катание" set was already seeded separately by
scripts/seed_skill_milestones_skating.py). Same idempotency rule: a skill
is skipped entirely if it already has any milestone rows.

    poetry run python scripts/seed_skill_milestones_phase7.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.skill import Skill, SkillMilestone  # noqa: E402

MILESTONES_BY_SKILL: dict[str, list[dict]] = {
    "Взрывной старт": [
        {
            "threshold": 20,
            "title": "Есть чувство толчка",
            "description": "первые метры разгона перестали быть провисанием, стартуешь с места без задержки",
        },
        {
            "threshold": 45,
            "title": "Заметное ускорение",
            "description": "на первых 3 шагах разгона отрываешься от игрока с равным стартовым положением",
        },
        {
            "threshold": 70,
            "title": "Взрывной рывок",
            "description": "стартовое ускорение — реальное преимущество в борьбе за шайбу и позицию в начале эпизода",
        },
        {
            "threshold": 90,
            "title": "Лучший на старте",
            "description": "по взрывной скорости на короткой дистанции опережаешь абсолютное большинство любителей своего уровня",
        },
    ],
    "Силовая борьба": [
        {
            "threshold": 20,
            "title": "Не теряется в контакте",
            "description": "держишь позицию при первом силовом столкновении, не проигрываешь его сразу",
        },
        {
            "threshold": 45,
            "title": "Выигрывает единоборства",
            "description": "стабильно забираешь борьбу один в один в типичных игровых ситуациях у борта",
        },
        {
            "threshold": 70,
            "title": "Доминирует у борта",
            "description": "соперник реже идёт в прямой силовой контакт, предпочитая обыграть по-другому",
        },
        {
            "threshold": 90,
            "title": "Неудобный соперник",
            "description": "исход силового единоборства почти всегда решается в вашу пользу",
        },
    ],
    "Сила броска": [
        {
            "threshold": 20,
            "title": "Долетает до ворот",
            "description": "броску хватает мощности долететь до цели на уверенной скорости даже без разгона",
        },
        {
            "threshold": 45,
            "title": "Бросок в движении",
            "description": "сила броска сохраняется на ходу, не нужно останавливаться, чтобы бросить сильно",
        },
        {
            "threshold": 70,
            "title": "Быстрый и неожиданный",
            "description": "короткий замах и высокая скорость шайбы оставляют вратарю меньше времени на реакцию",
        },
        {
            "threshold": 90,
            "title": "Оружие уровня команды",
            "description": "бросок, которого ждут и опасаются соперники в каждом эпизоде у ворот",
        },
    ],
    "Выносливость": [
        {
            "threshold": 20,
            "title": "Хватает на смену",
            "description": "доигрываешь стандартную смену без резкого падения скорости к её концу",
        },
        {
            "threshold": 45,
            "title": "Ровный по игре",
            "description": "держишь темп на протяжении периода без длинных провалов по скорости и силе действий",
        },
        {
            "threshold": 70,
            "title": "Свежий в третьем периоде",
            "description": "последние минуты матча по интенсивности действий не отличаются от первых",
        },
        {
            "threshold": 90,
            "title": "Мотор без остановки",
            "description": "способность работать на высокой интенсивности всю игру перестаёт быть ограничением",
        },
    ],
    "Скоростная выносливость": [
        {
            "threshold": 20,
            "title": "Держит вторую попытку",
            "description": "повторное ускорение после первого рывка получается без резкой потери скорости",
        },
        {
            "threshold": 45,
            "title": "Стабильные повторы",
            "description": (
                "серия коротких ускорений подряд (борьба за шайбу, смена атака/оборона) "
                "не проседает по мощности"
            ),
        },
        {
            "threshold": 70,
            "title": "Быстрый весь эпизод",
            "description": "в затяжном игровом моменте с несколькими рывками скорость держится до конца эпизода",
        },
        {
            "threshold": 90,
            "title": "Не устаёт на скорости",
            "description": (
                "многократные ускорения в высоком темпе почти не сказываются на их мощности "
                "даже к концу смены"
            ),
        },
    ],
    "Координация и реакция": [
        {
            "threshold": 20,
            "title": "Быстрее реагирует",
            "description": (
                "успеваешь среагировать на резкую смену ситуации (передача, отскок), "
                "не теряясь на долю секунды"
            ),
        },
        {
            "threshold": 45,
            "title": "Уверенные руки",
            "description": "обработка шайбы и мелкая моторика клюшкой стабильны даже в дефиците времени",
        },
        {
            "threshold": 70,
            "title": "Читает раньше",
            "description": "реакция на неожиданное развитие эпизода становится быстрее среднего темпа игры",
        },
        {
            "threshold": 90,
            "title": "На грани рефлекса",
            "description": "скорость реакции и координация перестают быть узким местом даже в самых быстрых эпизодах",
        },
    ],
    "Баланс и устойчивость": [
        {
            "threshold": 20,
            "title": "Не падает при контакте",
            "description": "лёгкий толчок или неровность льда не сбивают с ног и не портят выполнение движения",
        },
        {
            "threshold": 45,
            "title": "Устойчив в развороте",
            "description": "смена направления на скорости не сопровождается потерей равновесия",
        },
        {
            "threshold": 70,
            "title": "Стабилен под давлением",
            "description": "сохраняет баланс и контроль тела даже при силовом контакте в движении",
        },
        {
            "threshold": 90,
            "title": "Непоколебимая опора",
            "description": "равновесие держится в любой нестандартной игровой ситуации, включая контакт на скорости",
        },
    ],
    "Мобильность": [
        {
            "threshold": 20,
            "title": "Двигается без скованности",
            "description": (
                "базовые игровые движения (присед в стойке, выпад, поворот корпуса) "
                "выполняются свободно"
            ),
        },
        {
            "threshold": 45,
            "title": "Широкая амплитуда",
            "description": "глубина стойки и ширина шага увеличились без ощущения ограничения в суставах",
        },
        {
            "threshold": 70,
            "title": "Гибкий под нагрузкой",
            "description": "сохраняет полную амплитуду движений даже в игровом темпе и на фоне усталости",
        },
        {
            "threshold": 90,
            "title": "Без ограничений подвижности",
            "description": "диапазон движения в суставах перестаёт быть фактором, ограничивающим технику",
        },
    ],
    "Обводка": [
        {
            "threshold": 20,
            "title": "Уверенно ведёт шайбу",
            "description": "контролирует шайбу на средней скорости без частых потерь при простом манёвре",
        },
        {
            "threshold": 45,
            "title": "Обыгрывает одного",
            "description": "способен обыграть соперника один в один в стандартной игровой ситуации",
        },
        {
            "threshold": 70,
            "title": "Сложно отобрать",
            "description": "контроль шайбы сохраняется даже под плотной опекой и на высокой скорости",
        },
        {
            "threshold": 90,
            "title": "Индивидуальное мастерство",
            "description": "обводка становится реальным оружием в эпизодах один в один против сильных соперников",
        },
    ],
    "Игровое чтение": [
        {
            "threshold": 20,
            "title": "Видит простые варианты",
            "description": "замечает очевидные свободные зоны и партнёров под передачу без задержки",
        },
        {
            "threshold": 45,
            "title": "Предугадывает развитие",
            "description": "чаще открывается или перекрывает верно ещё до того, как эпизод очевиден",
        },
        {
            "threshold": 70,
            "title": "На шаг впереди",
            "description": "принимает верные решения по позиционированию быстрее среднего темпа игры",
        },
        {
            "threshold": 90,
            "title": "Читает игру как ветеран",
            "description": (
                "понимание развития эпизода на уровне, где решения принимаются почти "
                "интуитивно и почти всегда верно"
            ),
        },
    ],
}


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        seeded_skills = 0
        seeded_milestones = 0
        for skill_name, milestones in MILESTONES_BY_SKILL.items():
            skill_id = (
                await session.execute(select(Skill.id).where(Skill.name == skill_name))
            ).scalar_one_or_none()
            if skill_id is None:
                print(f"Skill {skill_name!r} not found -- run scripts/seed_skills.py first, skipping.")
                continue

            existing = (
                await session.execute(
                    select(SkillMilestone.id).where(SkillMilestone.skill_id == skill_id)
                )
            ).scalars().all()
            if existing:
                print(f"{skill_name!r} already has {len(existing)} milestone(s), skipping.")
                continue

            for data in milestones:
                session.add(SkillMilestone(skill_id=skill_id, **data))
            seeded_skills += 1
            seeded_milestones += len(milestones)

        await session.commit()
        print(f"Seeded {seeded_milestones} milestone(s) across {seeded_skills} skill(s).")


if __name__ == "__main__":
    asyncio.run(seed())
