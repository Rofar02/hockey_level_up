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
    # Blank ones are dropped, not refused (review 14.10, 24).
    assert TeamEventDrillUpdate(section_id=section_id, title="x", keywords=["   "]).keywords == []


def test_keywords_are_cleaned_before_the_limits() -> None:
    """Review 14.10 (24): line breaks, invisible characters, repeats."""
    section_id = uuid.uuid4()
    body = TeamEventDrillCreate(
        section_id=section_id,
        title="x",
        keywords=["Пас\nв крюк", "\u200bСкорость\ufeff", "скорость", "Пас в  крюк", "Стоп"],
    )
    assert body.keywords == ["Пас в крюк", "Скорость", "Стоп"]


@pytest.mark.asyncio
async def test_an_update_without_keywords_keeps_them(db_session) -> None:
    captain = _make_user()
    db_session.add(captain)
    await db_session.flush()
    team = await TeamService(db_session).create_team(captain, "Bears")
    events = TeamEventService(db_session)
    event = await events.create_event(
        captain, team.id, TeamEventType.TRAINING, datetime.now(timezone.utc) + timedelta(days=2), None
    )
    section = await events.add_section(captain, team.id, event.id, "Разминка")
    drill = await events.add_drill(captain, team.id, event.id, section.id, "Бросок", None, 8, None, ["Кисть"])

    # An older app's body: no keywords field at all.
    body = TeamEventDrillUpdate.model_validate({"section_id": str(section.id), "title": "Бросок с хода"})
    assert "keywords" not in body.model_fields_set
    kept = await events.update_drill(
        captain, team.id, event.id, drill.id, body.section_id, body.title, None, 8, body.keywords,
        update_keywords="keywords" in body.model_fields_set,
    )
    assert kept.title == "Бросок с хода"
    assert kept.keywords == ["Кисть"]


@pytest.mark.asyncio
async def test_a_template_keeps_its_keywords(db_session) -> None:
    from app.schemas.team_event import DrillTemplateCreate
    from app.services.drill_template_service import DrillTemplateService

    coach = _make_user()
    db_session.add(coach)
    await db_session.flush()
    saved = await DrillTemplateService(db_session).create_template(
        coach, DrillTemplateCreate(title="Восьмёрка", keywords=["Скорость", "Бросок"])
    )
    assert saved.keywords == ["Скорость", "Бросок"]
    listed = await DrillTemplateService(db_session).list_templates(coach)
    assert listed[0].keywords == ["Скорость", "Бросок"]
