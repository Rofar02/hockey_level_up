"""Drill keywords for the players' plan reel (2026-10-13, В): up to three
short cues per drill, set on create or edit, shown to the team."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.team_event import TeamEventType
from app.models.user import User
from app.schemas.team_event import TeamEventDrillCreate, TeamEventDrillUpdate
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"kw_{unique}",
        email=f"kw_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )


@pytest.mark.asyncio
async def test_keywords_are_saved_edited_and_cleared(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()
    team = await TeamService(db_session).create_team(captain, "Bears")
    events = TeamEventService(db_session)
    event = await events.create_event(
        captain, team.id, TeamEventType.TRAINING, datetime.now(timezone.utc) + timedelta(days=2), None
    )
    section = await events.add_section(captain, team.id, event.id, "Разминка")

    drill = await events.add_drill(
        captain, team.id, event.id, section.id, "Передачи в парах", None, 8, None, ["Пас в крюк", "Скорость"]
    )
    assert drill.keywords == ["Пас в крюк", "Скорость"]

    edited = await events.update_drill(
        captain, team.id, event.id, drill.id, section.id, "Передачи в парах", None, 8, ["Голова поднята"]
    )
    assert edited.keywords == ["Голова поднята"]

    cleared = await events.update_drill(captain, team.id, event.id, drill.id, section.id, "Передачи в парах", None, 8, None)
    assert cleared.keywords == []

    board = await events.get_event(captain, team.id, event.id)
    assert board.sections[0].drills[0].keywords == []


def test_at_most_three_short_keywords() -> None:
    section_id = uuid.uuid4()
    ok = TeamEventDrillCreate(section_id=section_id, title="x", keywords=["  Рёбра ", "Старт", "Стоп"])
    assert ok.keywords == ["Рёбра", "Старт", "Стоп"]
    with pytest.raises(ValidationError):
        TeamEventDrillCreate(section_id=section_id, title="x", keywords=["a", "b", "c", "d"])
    with pytest.raises(ValidationError):
        TeamEventDrillUpdate(section_id=section_id, title="x", keywords=["слишком длинная подсказка"])
    with pytest.raises(ValidationError):
        TeamEventDrillUpdate(section_id=section_id, title="x", keywords=["   "])
