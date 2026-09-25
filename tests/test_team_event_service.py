"""TeamEventService: TeamEvent creation and the board (TeamEventDrill) --
draft/publish visibility, captain-only writes, reorder, and the
game-has-no-board guard. Same `_make_user` shape as test_team_service.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.team_event import TeamEventType
from app.models.user import User
from app.services.team_event_service import TeamEventService
from app.services.team_service import TeamService


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"team_event_{unique}",
        email=f"team_event_{unique}@example.com",
        password_hash="irrelevant",
    )
    defaults.update(overrides)
    return User(**defaults)


def _future(hours: int = 48) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


async def _make_team_with_player(db_session):
    captain = _make_user()
    player = _make_user()
    db_session.add_all([captain, player])
    await db_session.flush()

    teams = TeamService(db_session)
    team = await teams.create_team(captain, "Sharks")
    request = await teams.join_by_code(player, team.invite_code)
    await teams.approve_request(captain, request.id)
    return captain, player, team


@pytest.mark.asyncio
async def test_create_training_event_requires_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(player, team.id, TeamEventType.TRAINING, _future(), None)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_game_requires_opponent_name_training_rejects_it(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(captain, team.id, TeamEventType.GAME, _future(), None)
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        await events.create_event(
            captain, team.id, TeamEventType.TRAINING, _future(), "Rival HC"
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_board_draft_hides_sections_from_non_captain(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    assert event.sections == []
    section = await events.add_section(captain, team.id, event.id, "Разминка")
    await events.add_drill(
        captain, team.id, event.id, section.id, "Edge work", "Inside/outside edges", 10
    )

    as_player = await events.get_event(player, team.id, event.id)
    assert as_player.board_status == "draft"
    assert as_player.sections is None

    as_captain = await events.get_event(captain, team.id, event.id)
    assert as_captain.sections is not None
    assert len(as_captain.sections) == 1
    assert len(as_captain.sections[0].drills) == 1

    published = await events.publish_board(captain, team.id, event.id)
    assert published.board_status == "published"

    as_player_after = await events.get_event(player, team.id, event.id)
    assert as_player_after.sections is not None
    assert as_player_after.sections[0].name == "Разминка"
    drill = as_player_after.sections[0].drills[0]
    assert drill.title == "Edge work"
    assert drill.duration_minutes == 10


@pytest.mark.asyncio
async def test_game_event_has_no_board(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(
        captain, team.id, TeamEventType.GAME, _future(), "Rival HC"
    )
    assert event.board_status is None
    assert event.sections is None

    with pytest.raises(HTTPException) as exc_info:
        await events.add_section(captain, team.id, event.id, "Разминка")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_reorder_and_delete_drill_keep_order_dense_within_section(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    section = await events.add_section(captain, team.id, event.id, "Броски")
    other = await events.add_section(captain, team.id, event.id, "Игра")
    first = await events.add_drill(captain, team.id, event.id, section.id, "Drill 1", None, None)
    second = await events.add_drill(captain, team.id, event.id, section.id, "Drill 2", None, None)
    third = await events.add_drill(captain, team.id, event.id, section.id, "Drill 3", None, None)
    elsewhere = await events.add_drill(captain, team.id, event.id, other.id, "Other 1", None, None)
    assert [d.order for d in (first, second, third)] == [0, 1, 2]
    assert elsewhere.order == 0

    reordered = await events.reorder_drills(
        captain, team.id, event.id, section.id, [third.id, first.id, second.id]
    )
    assert [d.id for d in reordered] == [third.id, first.id, second.id]
    assert [d.order for d in reordered] == [0, 1, 2]

    await events.delete_drill(captain, team.id, event.id, first.id)
    sections = (await events.get_event(captain, team.id, event.id)).sections
    remaining = sections[0].drills
    assert [d.id for d in remaining] == [third.id, second.id]
    assert [d.order for d in remaining] == [0, 1]
    assert [d.id for d in sections[1].drills] == [elsewhere.id]


@pytest.mark.asyncio
async def test_reorder_rejects_mismatched_drill_ids(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    section = await events.add_section(captain, team.id, event.id, "Броски")
    await events.add_drill(captain, team.id, event.id, section.id, "Drill 1", None, None)

    with pytest.raises(HTTPException) as exc_info:
        await events.reorder_drills(captain, team.id, event.id, section.id, [uuid.uuid4()])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_moving_a_drill_to_another_section_appends_it_and_closes_the_gap(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    source = await events.add_section(captain, team.id, event.id, "Разминка")
    target = await events.add_section(captain, team.id, event.id, "Броски")
    moving = await events.add_drill(captain, team.id, event.id, source.id, "A", None, None)
    staying = await events.add_drill(captain, team.id, event.id, source.id, "B", None, None)
    await events.add_drill(captain, team.id, event.id, target.id, "C", None, None)

    moved = await events.update_drill(
        captain, team.id, event.id, moving.id, target.id, "A", "now in Броски", 15
    )
    assert moved.section_id == target.id
    assert moved.order == 1
    assert moved.duration_minutes == 15

    sections = (await events.get_event(captain, team.id, event.id)).sections
    assert [(d.id, d.order) for d in sections[0].drills] == [(staying.id, 0)]
    assert [d.title for d in sections[1].drills] == ["C", "A"]


@pytest.mark.asyncio
async def test_section_rename_reorder_and_delete_with_its_drills(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    warmup = await events.add_section(captain, team.id, event.id, "Разминка")
    shots = await events.add_section(captain, team.id, event.id, "Броски")
    game = await events.add_section(captain, team.id, event.id, "Игра")
    await events.add_drill(captain, team.id, event.id, shots.id, "Shot 1", None, None)

    renamed = await events.rename_section(captain, team.id, event.id, game.id, "  Игра 3 на 3 ")
    assert renamed.name == "Игра 3 на 3"

    await events.reorder_sections(captain, team.id, event.id, [game.id, warmup.id, shots.id])
    await events.delete_section(captain, team.id, event.id, shots.id)

    sections = (await events.get_event(captain, team.id, event.id)).sections
    assert [(s.name, s.order) for s in sections] == [("Игра 3 на 3", 0), ("Разминка", 1)]
    assert all(s.drills == [] for s in sections)

    with pytest.raises(HTTPException) as exc_info:
        await events.reorder_sections(captain, team.id, event.id, [game.id])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_non_captain_cannot_edit_sections_and_foreign_section_is_404(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)

    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    other_event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    foreign = await events.add_section(captain, team.id, other_event.id, "Чужой")

    with pytest.raises(HTTPException) as exc_info:
        await events.add_section(player, team.id, event.id, "Разминка")
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info:
        await events.add_drill(captain, team.id, event.id, foreign.id, "X", None, None)
    assert exc_info.value.status_code == 404


def _diagram(**overrides):
    from app.schemas.team_event import DrillDiagram

    data = {
        "tokens": [
            {"id": "t1", "kind": "own", "position": "F", "number": 17, "x": 0.3, "y": 0.66},
            {"id": "t2", "kind": "opponent", "x": 0.5, "y": 0.2},
            {"id": "p", "kind": "puck", "x": 0.31, "y": 0.64},
        ],
        "arrows": [
            {
                "id": "a1",
                "kind": "skate_puck",
                "from_token": "t1",
                "start": {"x": 0.3, "y": 0.66},
                "end": {"x": 0.4, "y": 0.35},
            },
            {"id": "a2", "kind": "pass", "start": {"x": 0.4, "y": 0.35}, "end": {"x": 0.6, "y": 0.25}},
        ],
    }
    data.update(overrides)
    return DrillDiagram.model_validate(data)


@pytest.mark.asyncio
async def test_drill_diagram_round_trips_and_clears(db_session) -> None:
    captain, player, team = await _make_team_with_player(db_session)
    events = TeamEventService(db_session)
    event = await events.create_event(captain, team.id, TeamEventType.TRAINING, _future(), None)
    section = await events.add_section(captain, team.id, event.id, "Броски")
    drill = await events.add_drill(captain, team.id, event.id, section.id, "2 в 1", None, None)
    assert drill.diagram is None

    saved = await events.set_drill_diagram(captain, team.id, event.id, drill.id, _diagram())
    assert saved.diagram is not None
    assert [t.id for t in saved.diagram.tokens] == ["t1", "t2", "p"]
    assert saved.diagram.arrows[0].from_token == "t1"

    await events.publish_board(captain, team.id, event.id)
    as_player = await events.get_event(player, team.id, event.id)
    assert as_player.sections[0].drills[0].diagram == saved.diagram

    cleared = await events.set_drill_diagram(captain, team.id, event.id, drill.id, None)
    assert cleared.diagram is None

    with pytest.raises(HTTPException) as exc_info:
        await events.set_drill_diagram(player, team.id, event.id, drill.id, _diagram())
    assert exc_info.value.status_code == 403


def test_drill_diagram_rejects_bad_shapes() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _diagram(tokens=[{"id": "t1", "kind": "own", "x": 1.5, "y": 0.5}], arrows=[])
    with pytest.raises(ValidationError):
        _diagram(
            tokens=[],
            arrows=[
                {
                    "id": "a1",
                    "kind": "pass",
                    "from_token": "ghost",
                    "start": {"x": 0.1, "y": 0.1},
                    "end": {"x": 0.2, "y": 0.2},
                }
            ],
        )
    with pytest.raises(ValidationError):
        _diagram(
            tokens=[
                {"id": "t1", "kind": "own", "x": 0.1, "y": 0.1},
                {"id": "t1", "kind": "own", "x": 0.2, "y": 0.2},
            ],
            arrows=[],
        )
    with pytest.raises(ValidationError):
        _diagram(tokens=[{"id": "t1", "kind": "opponent", "position": "D", "x": 0.1, "y": 0.1}], arrows=[])


def test_drill_diagram_curved_arrow_via_points() -> None:
    from pydantic import ValidationError

    curved = _diagram(
        arrows=[
            {
                "id": "c1",
                "kind": "skate",
                "from_token": "t1",
                "start": {"x": 0.3, "y": 0.66},
                "via": [{"x": 0.2, "y": 0.5}, {"x": 0.35, "y": 0.4}],
                "end": {"x": 0.5, "y": 0.3},
            }
        ]
    )
    assert [(p.x, p.y) for p in curved.arrows[0].via] == [(0.2, 0.5), (0.35, 0.4)]
    # Old straight arrows (no "via" at all) still validate.
    assert _diagram().arrows[1].via == []

    with pytest.raises(ValidationError):
        _diagram(
            arrows=[
                {
                    "id": "c1",
                    "kind": "skate",
                    "start": {"x": 0.3, "y": 0.66},
                    "via": [{"x": 0.5, "y": 0.5}] * 25,
                    "end": {"x": 0.5, "y": 0.3},
                }
            ]
        )
    with pytest.raises(ValidationError):
        _diagram(
            arrows=[
                {
                    "id": "c1",
                    "kind": "skate",
                    "start": {"x": 0.3, "y": 0.66},
                    "via": [{"x": 1.2, "y": 0.5}],
                    "end": {"x": 0.5, "y": 0.3},
                }
            ]
        )


def test_drill_diagram_accepts_repass_arrows() -> None:
    from pydantic import ValidationError

    diagram = _diagram(
        arrows=[{"id": "r1", "kind": "repass", "start": {"x": 0.2, "y": 0.5}, "end": {"x": 0.7, "y": 0.5}}]
    )
    assert diagram.arrows[0].kind == "repass"
    shot = _diagram(arrows=[{"id": "s1", "kind": "shot", "start": {"x": 0.4, "y": 0.3}, "end": {"x": 0.5, "y": 0.06}}])
    assert shot.arrows[0].kind == "shot"
    with pytest.raises(ValidationError):
        _diagram(arrows=[{"id": "r1", "kind": "slapshot", "start": {"x": 0.2, "y": 0.5}, "end": {"x": 0.7, "y": 0.5}}])


def test_drill_diagram_arrow_steps() -> None:
    from pydantic import ValidationError

    def arrow(step):
        return {"id": "s1", "kind": "pass", "start": {"x": 0.2, "y": 0.5}, "end": {"x": 0.7, "y": 0.5}, "step": step}

    assert _diagram(arrows=[arrow(2)]).arrows[0].step == 2
    # Older schemes without a step still validate (derived on display).
    assert _diagram().arrows[0].step is None
    for bad in (0, 21):
        with pytest.raises(ValidationError):
            _diagram(arrows=[arrow(bad)])
