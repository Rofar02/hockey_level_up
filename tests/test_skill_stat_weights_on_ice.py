"""SkillService.get_skill_value with the re-weighted "Катание"/"Обводка"
skills (see migration 8d42e514b77f): each now folds in an on-ice stat
(on_ice_skating / puck_handling) alongside its existing off-ice stats.

Builds its own Skill/SkillStatWeight/UserStat rows rather than relying on
the seeded production skills, so the expected value is computed from known
inputs instead of whatever happens to be in the dev DB.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.exercise import TargetStat
from app.models.progress import UserStat
from app.models.skill import Skill, SkillStatWeight
from app.models.user import User
from app.services.skill_service import SkillService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"skillw_{unique}",
        email=f"skillw_{unique}@example.com",
        password_hash="irrelevant",
    )


async def _set_stat(db_session, user_id: uuid.UUID, stat_type: TargetStat, value: float) -> None:
    db_session.add(
        UserStat(
            id=uuid.uuid4(),
            user_id=user_id,
            stat_type=stat_type,
            current_value=value,
            last_updated_at=datetime.now(timezone.utc),  # fresh -- no decay
        )
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_skating_skill_value_with_on_ice_skating_weight(db_session) -> None:
    user = _make_user()
    skill = Skill(id=uuid.uuid4(), name=f"Катание {uuid.uuid4().hex[:8]}")
    db_session.add_all(
        [
            user,
            skill,
            SkillStatWeight(
                id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.STRENGTH, weight=0.15
            ),
            SkillStatWeight(
                id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.AGILITY, weight=0.2
            ),
            SkillStatWeight(
                id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.ENDURANCE, weight=0.15
            ),
            SkillStatWeight(
                id=uuid.uuid4(),
                skill_id=skill.id,
                stat_type=TargetStat.ON_ICE_SKATING,
                weight=0.5,
            ),
        ]
    )
    await db_session.flush()

    await _set_stat(db_session, user.id, TargetStat.STRENGTH, 40.0)
    await _set_stat(db_session, user.id, TargetStat.AGILITY, 50.0)
    await _set_stat(db_session, user.id, TargetStat.ENDURANCE, 30.0)
    await _set_stat(db_session, user.id, TargetStat.ON_ICE_SKATING, 60.0)

    value = await SkillService(db_session).get_skill_value(skill.id, user.id)

    # 40*0.15 + 50*0.2 + 30*0.15 + 60*0.5 = 6 + 10 + 4.5 + 30
    assert value == pytest.approx(50.5)


@pytest.mark.asyncio
async def test_stickhandling_skill_value_with_puck_handling_weight(db_session) -> None:
    user = _make_user()
    skill = Skill(id=uuid.uuid4(), name=f"Обводка {uuid.uuid4().hex[:8]}")
    db_session.add_all(
        [
            user,
            skill,
            SkillStatWeight(
                id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.AGILITY, weight=0.25
            ),
            SkillStatWeight(
                id=uuid.uuid4(), skill_id=skill.id, stat_type=TargetStat.INTELLECT, weight=0.15
            ),
            SkillStatWeight(
                id=uuid.uuid4(),
                skill_id=skill.id,
                stat_type=TargetStat.PUCK_HANDLING,
                weight=0.6,
            ),
        ]
    )
    await db_session.flush()

    await _set_stat(db_session, user.id, TargetStat.AGILITY, 50.0)
    await _set_stat(db_session, user.id, TargetStat.INTELLECT, 20.0)
    await _set_stat(db_session, user.id, TargetStat.PUCK_HANDLING, 70.0)

    value = await SkillService(db_session).get_skill_value(skill.id, user.id)

    # 50*0.25 + 20*0.15 + 70*0.6 = 12.5 + 3 + 42
    assert value == pytest.approx(57.5)
