"""Team league, division and city (2026-10-09): validation on create and in
the captain's settings, the admin "Другая лига" list, and the place among
teams of the same league in the same city (shown from 3 teams).
"""
import uuid

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.schemas.team import TeamLeagueFields
from app.services.team_rating_service import TeamRatingService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"league_{unique}",
        email=f"league_{unique}@example.com",
        password_hash="irrelevant",
    )
    defaults.update(overrides)
    return User(**defaults)


async def _create(db_session, name: str, xp: int = 0, **league) -> uuid.UUID:
    captain = _make_user(xp=xp)
    db_session.add(captain)
    await db_session.flush()
    team = await TeamService(db_session).create_team(captain, name, TeamLeagueFields(**league))
    return team.id


@pytest.mark.asyncio
async def test_create_team_defaults_to_no_league(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    team = await TeamService(db_session).create_team(captain, "Sharks")

    assert team.league_code == "none"
    assert team.league_name is None
    assert team.city is None


@pytest.mark.asyncio
async def test_create_team_with_league_division_and_city(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    team = await TeamService(db_session).create_team(
        captain,
        "Медведи",
        TeamLeagueFields(city="  Москва ", league_code="nhl", division_code="dream"),
    )

    assert team.city == "Москва"
    assert team.league_name == "Ночная хоккейная лига"
    assert team.division_name == "Лига Мечты"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        dict(league_code="khl"),
        dict(league_code="shl", division_code="dream"),
        dict(league_code="nhl", division_code="pro"),
        dict(league_code="other"),
        dict(league_code="other", league_other_name="   "),
    ],
)
async def test_invalid_league_fields_are_rejected(db_session, fields) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc:
        await TeamService(db_session).create_team(captain, "Bad", TeamLeagueFields(**fields))
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_switching_league_clears_division_and_other_name(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()
    service = TeamService(db_session)
    team = await service.create_team(
        captain, "Медведи", TeamLeagueFields(league_code="other", league_other_name="Лига Белого Медведя")
    )

    updated = await service.update_team(
        captain, team.id, "Медведи", TeamLeagueFields(city="Казань", league_code="shl")
    )

    assert updated.league_code == "shl"
    assert updated.league_other_name is None
    assert updated.division_code is None
    assert updated.city == "Казань"


@pytest.mark.asyncio
async def test_only_captain_can_update_team(db_session) -> None:
    captain = _make_user()
    stranger = _make_user()
    db_session.add_all([captain, stranger])
    await db_session.flush()
    service = TeamService(db_session)
    team = await service.create_team(captain, "Sharks")

    with pytest.raises(HTTPException) as exc:
        await service.update_team(stranger, team.id, "Hijacked", TeamLeagueFields())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_other_league_names_grouped_case_insensitively(db_session) -> None:
    unique = uuid.uuid4().hex[:6]
    popular = f"Лига {unique}"
    await _create(db_session, "A", league_code="other", league_other_name=popular)
    await _create(db_session, "B", league_code="other", league_other_name=popular.upper())
    await _create(db_session, "C", league_code="other", league_other_name=f"Редкая {unique}")

    rows = await TeamService(db_session).list_other_league_names()
    mine = [row for row in rows if unique in row.name.casefold() or unique.upper() in row.name]

    assert [(row.team_count) for row in mine] == [2, 1]
    assert mine[0].name.casefold() == popular.casefold()


@pytest.mark.asyncio
async def test_league_place_needs_three_teams_in_same_league_and_city(db_session) -> None:
    city = f"Город-{uuid.uuid4().hex[:6]}"
    service = TeamService(db_session)
    first_id = await _create(db_session, "First", xp=300, city=city, league_code="nhl")
    await _create(db_session, "Second", xp=200, city=city.lower(), league_code="nhl")
    # Same city, different league -- doesn't count.
    await _create(db_session, "Students", xp=999, city=city, league_code="shl")

    first = await service._get_team_or_404(first_id)
    score = await TeamRatingService(db_session).compute_team_score(first)
    assert score.league_place is None

    third_id = await _create(db_session, "Third", xp=100, city=city, league_code="nhl", division_code="hope")
    score = await TeamRatingService(db_session).compute_team_score(first)
    assert (score.league_place, score.league_team_count) == (1, 3)

    third = await service._get_team_or_404(third_id)
    score = await TeamRatingService(db_session).compute_team_score(third)
    assert (score.league_place, score.league_team_count) == (3, 3)


@pytest.mark.asyncio
async def test_no_city_means_no_league_place(db_session) -> None:
    team_ids = [await _create(db_session, f"T{i}", league_code="nhl") for i in range(3)]
    team = await TeamService(db_session)._get_team_or_404(team_ids[0])

    score = await TeamRatingService(db_session).compute_team_score(team)

    assert score.league_place is None
