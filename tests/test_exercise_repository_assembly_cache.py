"""ExerciseRepository.assembly_cache: lookups are memoized only inside a plan
assembly, results match the uncached calls (including key order, which
seeded picks depend on), and nothing leaks out of the scope."""
import uuid

import pytest
from sqlalchemy import event, select

from app.models.exercise import (
    EquipmentItem,
    Exercise,
    ExerciseCategory,
    ExerciseMovementPattern,
    MovementPattern,
    TrainingPhase,
    UserEquipmentItem,
)
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(id=uuid.uuid4(), username=f"memo_{unique}", email=f"memo_{unique}@example.com", password_hash="x")


class _StatementCounter:
    def __init__(self, db_session) -> None:
        self.count = 0
        self._session = db_session.sync_session

    def _on_execute(self, _state) -> None:
        self.count += 1

    def __enter__(self):
        event.listen(self._session, "do_orm_execute", self._on_execute)
        return self

    def __exit__(self, *exc) -> None:
        event.remove(self._session, "do_orm_execute", self._on_execute)


async def _user_with_band(db_session) -> User:
    user = _make_user()
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.RESISTANCE_BAND))
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_no_caching_outside_a_scope(db_session) -> None:
    user = await _user_with_band(db_session)
    repo = ExerciseRepository(db_session)

    assert await repo.list_owned_equipment(user.id) == {EquipmentItem.RESISTANCE_BAND}
    db_session.add(UserEquipmentItem(user_id=user.id, equipment_item=EquipmentItem.DUMBBELLS))
    await db_session.flush()

    assert await repo.list_owned_equipment(user.id) == {EquipmentItem.RESISTANCE_BAND, EquipmentItem.DUMBBELLS}


@pytest.mark.asyncio
async def test_repeated_lookup_inside_a_scope_hits_the_db_once(db_session) -> None:
    user = await _user_with_band(db_session)
    repo = ExerciseRepository(db_session)

    with repo.assembly_cache(), _StatementCounter(db_session) as counter:
        first = await repo.list_owned_equipment(user.id)
        first.add(EquipmentItem.BARBELL)  # a caller mutating its copy...
        second = await repo.list_owned_equipment(user.id)
        with repo.assembly_cache():  # nested scope shares the cache
            third = await repo.list_owned_equipment(user.id)

    assert counter.count == 1
    assert second == third == {EquipmentItem.RESISTANCE_BAND}  # ...doesn't touch the cache
    assert repo._memo is None


@pytest.mark.asyncio
async def test_a_write_through_the_repository_drops_the_cache(db_session) -> None:
    user = await _user_with_band(db_session)
    repo = ExerciseRepository(db_session)

    with repo.assembly_cache():
        assert await repo.list_owned_equipment(user.id) == {EquipmentItem.RESISTANCE_BAND}
        await repo.replace_owned_equipment(user.id, [EquipmentItem.DUMBBELLS])
        assert await repo.list_owned_equipment(user.id) == {EquipmentItem.DUMBBELLS}


@pytest.mark.asyncio
async def test_by_exercise_lookups_match_uncached_results_and_order(db_session) -> None:
    # Ids chosen so that asking for [ids[2], ids[0]] (4, 3) differs from both
    # insertion order and index order (3, 4) -- an implementation returning
    # keys in *request* order would fail the order checks below.
    base = uuid.uuid4().int & ~0xFF
    exercises = [
        Exercise(id=uuid.UUID(int=base + suffix), name=f"Memo {suffix} {uuid.uuid4().hex[:6]}",
                 category=ExerciseCategory.OFF_ICE, phase=TrainingPhase.MAIN, difficulty_level=1)
        for suffix in (3, 1, 4, 2)
    ]
    db_session.add_all(exercises)
    await db_session.flush()
    patterns = [MovementPattern.SQUAT, MovementPattern.PULL, MovementPattern.PUSH]
    for exercise, pattern in zip(exercises, patterns):  # the 4th has no patterns
        db_session.add(ExerciseMovementPattern(exercise_id=exercise.id, movement_pattern=pattern))
    await db_session.flush()
    ids = [exercise.id for exercise in exercises]
    repo = ExerciseRepository(db_session)

    uncached_all = await repo.list_movement_patterns_by_exercise(ids)
    uncached_subset = await repo.list_movement_patterns_by_exercise([ids[2], ids[0]])

    with repo.assembly_cache(), _StatementCounter(db_session) as counter:
        cached_subset_first = await repo.list_movement_patterns_by_exercise([ids[2], ids[0]])
        cached_all = await repo.list_movement_patterns_by_exercise(ids)
        cached_subset_again = await repo.list_movement_patterns_by_exercise([ids[2], ids[0]])

    assert cached_all == uncached_all
    assert list(cached_subset_first) == list(uncached_subset)
    assert list(cached_subset_again) == list(uncached_subset)
    assert ids[3] not in cached_all  # no rows -> absent, same as uncached
    assert counter.count == 2  # the subset, then only the two ids not seen yet

    rows = (await db_session.execute(select(ExerciseMovementPattern).where(ExerciseMovementPattern.exercise_id.in_(ids)))).scalars().all()
    assert len(rows) == 3
