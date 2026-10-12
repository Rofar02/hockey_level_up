"""Review 2026-10-11, 3.1-3.3: the age comes from the birth date and the
experience from «С какого года играете?» -- both grow by themselves; the old
typed-in values are the fallback; the public card never shows the date."""
import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.user import ADULT_AGE, User, full_years
from app.schemas.user import UserPublicRead, UserUpdate
from app.services.user_service import UserService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(id=uuid.uuid4(), username=f"bd_{unique}", email=f"bd_{unique}@example.com", password_hash="x", timezone="UTC")
    defaults.update(overrides)
    return User(**defaults)


def test_full_years_counts_the_birthday_itself() -> None:
    assert full_years(date(2010, 10, 12), date(2026, 10, 11)) == 15
    assert full_years(date(2010, 10, 12), date(2026, 10, 12)) == 16
    assert full_years(date(2008, 2, 29), date(2026, 2, 28)) == 17


def test_age_and_experience_computed_with_fallback() -> None:
    user = _make_user(age=30, years_of_experience=4.0)
    assert user.age == 30
    assert user.hockey_since_year == user.local_today().year - 4
    assert user.years_of_experience == 4.0
    user.birth_date = date(2000, 1, 1)
    user.hockey_since_year = 2015
    assert user.age == full_years(date(2000, 1, 1), user.local_today())
    assert user.years_of_experience == float(user.local_today().year - 2015)


def test_the_age_follows_the_players_time_zone(monkeypatch) -> None:
    """The birthday comes on the player's own date: at 01:00 in Vladivostok
    the UTC date is still the day before."""
    from datetime import datetime as real_datetime, timezone
    from zoneinfo import ZoneInfo

    from app.models import user as user_module

    moment = real_datetime(2026, 10, 12, 15, 0, tzinfo=ZoneInfo("Asia/Vladivostok")).replace(hour=1)

    class FixedDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz or timezone.utc)

    monkeypatch.setattr(user_module, "datetime", FixedDatetime)
    east = _make_user(timezone="Asia/Vladivostok", birth_date=date(2010, 10, 12))
    west = _make_user(timezone="UTC", birth_date=date(2010, 10, 12))
    assert east.age == 16 and west.age == 15


@pytest.mark.asyncio
async def test_sql_age_uses_the_birth_date_first(db_session) -> None:
    adult = _make_user(age=12, birth_date=date(1990, 5, 5))
    child = _make_user(age=40, birth_date=date.today().replace(year=date.today().year - 10) - timedelta(days=1))
    legacy = _make_user(age=25)
    db_session.add_all([adult, child, legacy])
    await db_session.flush()
    ids = {adult.id, child.id, legacy.id}

    found = set((await db_session.scalars(select(User.id).where(User.id.in_(ids), User.age >= ADULT_AGE))).all())

    assert found == {adult.id, legacy.id}


def test_validation_of_the_dates() -> None:
    today = date.today()
    for bad in (
        {"birth_date": today + timedelta(days=1)},
        {"birth_date": today.replace(year=today.year - 3)},
        {"birth_date": date(today.year - 95, 1, 1)},
        {"hockey_since_year": today.year + 1},
        {"hockey_since_year": 1900},
    ):
        with pytest.raises(ValidationError):
            UserUpdate(**bad)
    UserUpdate(birth_date=date(today.year - 20, 1, 1), hockey_since_year=today.year)


@pytest.mark.asyncio
async def test_hockey_cannot_start_before_birth(db_session) -> None:
    user = _make_user(birth_date=date(2010, 3, 3))
    db_session.add(user)
    await db_session.flush()
    service = UserService(db_session)

    with pytest.raises(HTTPException) as exc:
        await service.update_profile(user, UserUpdate(hockey_since_year=2009))
    assert exc.value.status_code == 400
    updated = await service.update_profile(user, UserUpdate(hockey_since_year=2016))
    assert updated.hockey_since_year == 2016


def test_public_card_has_the_year_never_the_age_or_date() -> None:
    assert "birth_date" not in UserPublicRead.model_fields and "age" not in UserPublicRead.model_fields
    user = _make_user(first_name="A", last_name="B", birth_date=date(2001, 6, 1), level=1, xp=0, has_premium=False)
    user.hockey_since_year = 2012
    from datetime import datetime, timezone

    user.created_at = datetime.now(timezone.utc)
    card = UserPublicRead.model_validate(user)
    assert card.hockey_since_year == 2012


@pytest.mark.asyncio
async def test_a_birth_date_alone_drops_a_contradicting_old_start_year(db_session) -> None:
    """Review 12.10, 2: Home's birthday card sends the date only -- an old
    estimated start year before it is dropped, not a 400."""
    user = _make_user()
    user.hockey_since_year = 2005
    db_session.add(user)
    await db_session.flush()

    updated = await UserService(db_session).update_profile(user, UserUpdate(birth_date=date(2010, 3, 3)))

    assert updated.birth_date == date(2010, 3, 3) and updated.hockey_since_year is None


@pytest.mark.asyncio
async def test_a_birth_date_alone_keeps_a_fitting_start_year(db_session) -> None:
    user = _make_user()
    user.hockey_since_year = 2016
    db_session.add(user)
    await db_session.flush()

    updated = await UserService(db_session).update_profile(user, UserUpdate(birth_date=date(2010, 3, 3)))

    assert updated.hockey_since_year == 2016


def test_a_beginner_keeps_a_fractional_experience() -> None:
    """Review 12.10, 3: started this year -- the typed-in half a season is
    kept; a start year alone gives half of the year gone so far."""
    typed = _make_user(years_of_experience=0.5)
    assert typed.hockey_since_year == typed.local_today().year
    assert typed.years_of_experience == 0.5

    fresh = _make_user()
    fresh.hockey_since_year = fresh.local_today().year
    today = fresh.local_today()
    assert 0 <= fresh.years_of_experience <= 0.5
    if today.month > 1:
        assert fresh.years_of_experience > 0
