"""DrillTemplateService: a coach's own saved drills -- owner-only CRUD, the
per-coach cap, and a template landing on a board as a drill with its
scheme in one write (TeamEventService.add_drill's diagram).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEventType
from app.models.user import User
from app.schemas.team_event import DrillDiagram, DrillTemplateCreate
from app.services.drill_template_service import DrillTemplateService
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService

DIAGRAM = DrillDiagram.model_validate(
    {
        "tokens": [{"id": "p1", "kind": "own", "x": 0.3, "y": 0.75, "number": 17}],
        "arrows": [
            {
                "id": "a1",
                "kind": "skate_puck",
                "from_token": "p1",
                "start": {"x": 0.3, "y": 0.75},
                "via": [{"x": 0.4, "y": 0.5}],
                "end": {"x": 0.35, "y": 0.37},
                "step": 1,
            }
        ],
    }
)


def _make_user() -> User:
    unique = uuid.uuid4().hex[:8]
    return User(
        id=uuid.uuid4(),
        username=f"drilltpl_{unique}",
        email=f"drilltpl_{unique}@example.com",
        password_hash="irrelevant",
        timezone="UTC",
    )


@pytest.mark.asyncio
async def test_save_list_rename_delete_own_template(db_session) -> None:
    coach = _make_user()
    db_session.add(coach)
    await db_session.flush()
    templates = DrillTemplateService(db_session)

    saved = await templates.create_template(
        coach,
        DrillTemplateCreate(title="2 в 1 через центр", description="Пас в среднюю", duration_minutes=15, diagram=DIAGRAM),
    )
    assert saved.diagram == DIAGRAM
    assert saved.duration_minutes == 15

    renamed = await templates.rename_template(coach, saved.id, "2 в 1")
    assert renamed.title == "2 в 1"
    assert renamed.diagram == DIAGRAM

    listed = await templates.list_templates(coach)
    assert [template.title for template in listed] == ["2 в 1"]

    await templates.delete_template(coach, saved.id)
    assert await templates.list_templates(coach) == []


@pytest.mark.asyncio
async def test_someone_elses_template_is_not_found(db_session) -> None:
    coach, stranger = _make_user(), _make_user()
    db_session.add_all([coach, stranger])
    await db_session.flush()
    templates = DrillTemplateService(db_session)
    saved = await templates.create_template(coach, DrillTemplateCreate(title="Бросок"))

    assert await templates.list_templates(stranger) == []
    for attempt in (
        templates.rename_template(stranger, saved.id, "Моё"),
        templates.delete_template(stranger, saved.id),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await attempt
        assert exc_info.value.status_code == 404
    assert [template.title for template in await templates.list_templates(coach)] == ["Бросок"]


@pytest.mark.asyncio
async def test_cap_per_coach(db_session, monkeypatch) -> None:
    coach = _make_user()
    db_session.add(coach)
    await db_session.flush()
    monkeypatch.setattr(DrillTemplateService, "MAX_TEMPLATES_PER_USER", 2)
    templates = DrillTemplateService(db_session)
    await templates.create_template(coach, DrillTemplateCreate(title="Один"))
    await templates.create_template(coach, DrillTemplateCreate(title="Два"))

    with pytest.raises(HTTPException) as exc_info:
        await templates.create_template(coach, DrillTemplateCreate(title="Три"))
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_template_lands_on_the_board_with_its_scheme(db_session) -> None:
    captain, player = _make_user(), _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()
    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    events = TeamEventService(db_session)
    event = await events.create_event(
        captain, team.id, TeamEventType.TRAINING, datetime.now(timezone.utc) + timedelta(days=3), None
    )
    section = await events.add_section(captain, team.id, event.id, "Розыгрыш")
    template = await DrillTemplateService(db_session).create_template(
        captain, DrillTemplateCreate(title="2 в 1", duration_minutes=15, diagram=DIAGRAM)
    )

    drill = await events.add_drill(
        captain,
        team.id,
        event.id,
        section.id,
        template.title,
        template.description,
        template.duration_minutes,
        template.diagram,
    )
    assert drill.diagram == DIAGRAM

    board = await events.get_event(captain, team.id, event.id)
    assert board.sections is not None
    assert board.sections[0].drills[0].diagram == DIAGRAM
