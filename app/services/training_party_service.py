import uuid
from datetime import date, datetime, timezone
from typing import NamedTuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import TrainingPhase
from app.models.schedule import DayPlan, DaySessionType
from app.models.training_party import TrainingParty, TrainingPartyMemberStatus, TrainingPartyStatus
from app.models.user import User
from app.repositories.exercise_repository import ExerciseRepository
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.training_party_repository import TrainingPartyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.exercise import ExerciseRead, exercises_to_read
from app.schemas.training_party import (
    MemberTrainingStatus,
    PartyStatus,
    TrainingPartyCreate,
    TrainingPartyDetailRead,
    TrainingPartyInviteRead,
    TrainingPartyMemberRead,
    TrainingPartySummaryRead,
)
from app.services.friend_service import FriendService
from app.services.schedule_service import ScheduleService

# Co-op session content is capped at this many exercises when nothing else
# constrains it (see suggest_exercises' default) -- a shared main block,
# same order of magnitude as ScheduleService.MAIN_EXERCISE_COUNT_RANGE's
# personal-plan main counts.
DEFAULT_SUGGESTION_COUNT = 6

# Read directly from outbox_events for the friend activity feed
# (FriendActivityService) -- no consumer registered, same as level_up and
# training_completed: nothing needs to react to this, only display it.
PARTY_COMPLETED_EVENT = "party_completed"

# A member counts as "actually training" (must finish for the party to
# auto-complete) only in these statuses -- resting/game_day/no_plan_for_date
# members are spectators, not blockers.
_TRAINING_MEMBER_STATUSES = ("not_started", "in_progress", "completed")


class _MemberStatus(NamedTuple):
    training_status: MemberTrainingStatus
    completed_blocks: int | None
    total_blocks: int | None
    day_plan_id: uuid.UUID | None


class TrainingPartyService:
    """Co-op layer over each member's own personal training -- see
    app/models/training_party.py for why this deliberately doesn't generate
    shared session content.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._parties = TrainingPartyRepository(session)
        self._schedule = ScheduleRepository(session)
        self._schedule_service = ScheduleService(session)
        self._exercises = ExerciseRepository(session)
        self._users = UserRepository(session)
        self._friends = FriendService(session)
        self._outbox = OutboxRepository(session)

    # -- party lifecycle --

    async def create_party(self, creator: User, payload: TrainingPartyCreate) -> TrainingPartyDetailRead:
        if payload.target_date < date.today():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нельзя позвать на тренировку в прошедшую дату",
            )
        if await self._has_completed_training(creator.id, payload.target_date):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="В этот день у вас уже есть завершённая тренировка -- совместную создать нельзя",
            )
        friend_ids = {friend_id for friend_id in payload.friend_ids if friend_id != creator.id}
        if not friend_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Нужен хотя бы один друг"
            )
        for friend_id in friend_ids:
            if not await self._friends.are_friends(creator.id, friend_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Позвать можно только друзей",
                )

        party = await self._parties.create_party(creator.id, payload.target_date)
        creator_member = await self._parties.create_member(
            party.id, creator.id, TrainingPartyMemberStatus.JOINED
        )
        creator_member.joined_at = datetime.now(timezone.utc)
        for friend_id in friend_ids:
            await self._parties.create_member(party.id, friend_id, TrainingPartyMemberStatus.INVITED)

        await self._session.commit()
        return await self._to_detail_read(party)

    async def list_my_parties(self, user: User) -> list[TrainingPartySummaryRead]:
        memberships = await self._parties.list_joined_party_ids_for_user(user.id)
        summaries = []
        for membership in memberships:
            party = await self._parties.get_party_by_id(membership.party_id)
            if party is None:
                continue
            member_count = await self._parties.count_members(party.id)
            summaries.append(
                TrainingPartySummaryRead(
                    id=party.id,
                    target_date=party.target_date,
                    status=self._effective_status(party),
                    member_count=member_count,
                    is_creator=party.created_by == user.id,
                )
            )
        return summaries

    async def list_incoming_invites(self, user: User) -> list[TrainingPartyInviteRead]:
        invites = await self._parties.list_incoming_invites(user.id, date.today())
        reads = []
        for invite in invites:
            party = await self._parties.get_party_by_id(invite.party_id)
            if party is None:
                continue
            creator = await self._users.get_by_id(party.created_by)
            if creator is None:
                continue
            member_count = await self._parties.count_members(party.id)
            reads.append(
                TrainingPartyInviteRead(
                    party_id=party.id,
                    target_date=party.target_date,
                    created_by_id=creator.id,
                    created_by_first_name=creator.first_name,
                    created_by_last_name=creator.last_name,
                    created_by_avatar_url=creator.avatar_url,
                    member_count=member_count,
                )
            )
        return reads

    async def get_party(self, user: User, party_id: uuid.UUID) -> TrainingPartyDetailRead:
        party = await self._get_party_or_404(party_id)
        member = await self._parties.get_member(party_id, user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Вы не участник этой тренировки"
            )
        return await self._to_detail_read(party)

    async def respond_to_invite(
        self, user: User, party_id: uuid.UUID, accept: bool
    ) -> TrainingPartyDetailRead:
        party = await self._get_party_or_404(party_id)
        member = await self._parties.get_member(party_id, user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено"
            )
        if member.status != TrainingPartyMemberStatus.INVITED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Уже отвечено на это приглашение"
            )

        if accept:
            if await self._has_completed_training(user.id, party.target_date):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="В этот день у вас уже есть завершённая тренировка -- присоединиться нельзя",
                )
            member.status = TrainingPartyMemberStatus.JOINED
            member.joined_at = datetime.now(timezone.utc)
            # Joining after the creator already confirmed a shared set --
            # give the newcomer that exact same set immediately rather than
            # leaving them on whatever they had before (rest/personal plan/
            # nothing), so "everyone trains the same exercises" holds
            # regardless of when they actually joined.
            if party.exercises_finalized_at is not None:
                exercise_ids = await self._canonical_exercise_ids(party)
                if exercise_ids:
                    await self._materialize_for_member(user, party.target_date, exercise_ids)
        else:
            member.status = TrainingPartyMemberStatus.DECLINED

        await self._session.commit()
        return await self._to_detail_read(party)

    async def cancel_party(self, user: User, party_id: uuid.UUID) -> None:
        party = await self._get_party_or_404(party_id)
        if party.created_by != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Отменить тренировку может только тот, кто её создал",
            )
        if party.status != TrainingPartyStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Эту тренировку уже нельзя отменить"
            )
        party.status = TrainingPartyStatus.CANCELLED
        await self._session.commit()

    async def leave_party(self, user: User, party_id: uuid.UUID) -> None:
        party = await self._get_party_or_404(party_id)
        member = await self._parties.get_member(party_id, user.id)
        if member is None or member.status != TrainingPartyMemberStatus.JOINED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Вы не участник этой тренировки"
            )
        if party.created_by == user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Создатель не может выйти -- отмените тренировку вместо этого",
            )
        await self._parties.delete_member(member)
        await self._session.commit()

    # -- shared exercise set --
    #
    # Two modes, one engine (ScheduleService.suggest_party_exercises) and one
    # confirm endpoint: "Сгенерировать" calls suggest_exercises and hands the
    # result straight to confirm_exercises (or calls suggest_exercises again
    # to "перемешать" first); "Собрать самому" also calls suggest_exercises
    # (to highlight recommendations in the picker) but the frontend lets the
    # creator submit any exercise_ids to confirm_exercises regardless of
    # whether they came from the suggestion list -- manual mode is
    # deliberately unconstrained, so confirm_exercises itself never
    # re-applies the equipment/difficulty rules, only "do these exist".
    #
    # Finalization happens on this single explicit creator action
    # (confirm_exercises), not at party-creation time and not once every
    # invitee has responded -- invites can sit unanswered indefinitely, and
    # "everyone answered" is a fragile trigger to build a training around.
    # A member who joins *after* confirm_exercises gets the exact same set
    # materialized immediately (see respond_to_invite above); a member who
    # joins *before* it just waits like today, with nothing materialized
    # until the creator confirms.

    async def suggest_exercises(
        self, user: User, party_id: uuid.UUID, count: int = DEFAULT_SUGGESTION_COUNT
    ) -> list[ExerciseRead]:
        party = await self._get_party_or_404(party_id)
        self._require_creator(party, user)
        self._require_pending(party)

        joined_users = await self._joined_users(party.id)
        exercises = await self._schedule_service.suggest_party_exercises(joined_users, count)
        stats_by_id = await self._exercises.list_target_stats_by_exercise(
            [exercise.id for exercise in exercises]
        )
        return exercises_to_read(exercises, stats_by_id)

    async def confirm_exercises(
        self, user: User, party_id: uuid.UUID, exercise_ids: list[uuid.UUID]
    ) -> TrainingPartyDetailRead:
        party = await self._get_party_or_404(party_id)
        self._require_creator(party, user)
        self._require_pending(party)

        for exercise_id in exercise_ids:
            if await self._exercises.get_by_id(exercise_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Упражнение {exercise_id} не найдено",
                )
        if await self._has_completed_training(user.id, party.target_date):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Вы уже завершили тренировку в этот день -- изменить набор нельзя",
            )

        joined_users = await self._joined_users(party.id)
        for member_user in joined_users:
            # Per-member skip, not an all-or-nothing failure: a friend may
            # have completed unrelated training that day between joining and
            # this confirm (or a re-confirm/"перемешать" after an earlier
            # confirm), or have a GAME day scheduled -- either way their
            # existing state is left untouched rather than clobbered. The
            # creator's own completed-training case is already handled above
            # as a hard 409, since there's no "someone else" to leave alone.
            await self._materialize_for_member(member_user, party.target_date, exercise_ids)

        party.exercises_finalized_at = datetime.now(timezone.utc)
        await self._session.commit()
        return await self._to_detail_read(party)

    # -- auto-completion (called from SessionBlockService, same transaction
    # as the training_completed event -- no commit here, the caller's own
    # commit covers this too) --

    async def try_complete_parties_for(self, user_id: uuid.UUID, target_date: date) -> None:
        parties = await self._parties.list_pending_parties_for_member_on_date(user_id, target_date)
        for party in parties:
            await self._maybe_finish(party)

    async def _maybe_finish(self, party: TrainingParty) -> None:
        members_with_users = await self._parties.list_members_with_users(party.id)
        joined = [
            (member, user)
            for member, user in members_with_users
            if member.status == TrainingPartyMemberStatus.JOINED
        ]

        trained_user_ids: list[uuid.UUID] = []
        saw_a_trainer = False
        for _member, user in joined:
            resolved = await self._resolve_member_training_status(user.id, party.target_date)
            if resolved.training_status not in _TRAINING_MEMBER_STATUSES:
                continue  # resting / game_day / no_plan_for_date -- spectator, not a blocker
            saw_a_trainer = True
            if resolved.training_status != "completed":
                # Someone who's actually training today isn't done yet.
                return
            trained_user_ids.append(user.id)

        # Nobody in the party is actually training today (everyone's resting
        # or has no plan) -- nothing to celebrate, leave it pending.
        if not saw_a_trainer:
            return

        party.status = TrainingPartyStatus.COMPLETED
        party.completed_at = datetime.now(timezone.utc)
        # One row per trainer, each keyed by their own user_id -- same shape
        # as level_up/training_completed, so FriendActivityService's existing
        # payload->>'user_id' filter picks these up with no query changes.
        # "Алиса тренировалась с друзьями" reads better per-friend anyway
        # than one merged multi-user row would.
        for user_id in trained_user_ids:
            self._outbox.add(
                PARTY_COMPLETED_EVENT,
                {
                    "user_id": str(user_id),
                    "party_id": str(party.id),
                    "target_date": party.target_date.isoformat(),
                    "party_size": len(trained_user_ids),
                },
            )

    # -- shared helpers --

    async def _get_party_or_404(self, party_id: uuid.UUID) -> TrainingParty:
        party = await self._parties.get_party_by_id(party_id)
        if party is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тренировка не найдена")
        return party

    @staticmethod
    def _require_creator(party: TrainingParty, user: User) -> None:
        if party.created_by != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Только организатор может управлять набором упражнений",
            )

    @staticmethod
    def _require_pending(party: TrainingParty) -> None:
        if party.status != TrainingPartyStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Эту тренировку уже нельзя изменить"
            )

    @staticmethod
    def _day_plan_has_completed_block(day_plan: DayPlan) -> bool:
        if day_plan.training_session is None:
            return False
        return any(
            block.completed_at is not None or block.skipped_at is not None
            for block in day_plan.training_session.blocks
        )

    async def _has_completed_training(self, user_id: uuid.UUID, target_date: date) -> bool:
        day_plan = await self._schedule.get_day_plan_for_date(user_id, target_date)
        return day_plan is not None and self._day_plan_has_completed_block(day_plan)

    async def _joined_users(self, party_id: uuid.UUID) -> list[User]:
        members_with_users = await self._parties.list_members_with_users(party_id)
        return [
            member_user
            for member, member_user in members_with_users
            if member.status == TrainingPartyMemberStatus.JOINED
        ]

    async def _materialize_for_member(
        self, member_user: User, target_date: date, exercise_ids: list[uuid.UUID]
    ) -> None:
        day_plan = await self._schedule.get_day_plan_for_date(member_user.id, target_date)
        if day_plan is not None:
            if day_plan.session_type == DaySessionType.GAME:
                return  # pre-game activation isn't replaced with a co-op workout
            if self._day_plan_has_completed_block(day_plan):
                return  # already trained something else that day -- don't clobber it
        else:
            day_plan = await self._schedule_service.ensure_day_plan_for_date(member_user, target_date)
        await self._schedule_service.replace_day_plan_content(day_plan, exercise_ids, member_user)

    async def _canonical_exercise_ids(self, party: TrainingParty) -> list[uuid.UUID]:
        """The finalized set, read back from whichever joined member's own
        materialized SessionBlocks still carry it -- there is no separate
        party-content table (see the model docstring), so this *is* the
        source of truth once exercises_finalized_at is set. Checks the
        creator first (present unless declined via a GAME day on their own
        target_date) and falls back to any other joined member's blocks.

        Filtered to MAIN-phase blocks only -- replace_day_plan_content now
        also attaches a warmup/cooldown picked per-member (so different
        members can end up with different ones), which must never leak into
        what confirm_exercises originally confirmed: this feeds both the
        finalized-exercises read and _materialize_for_member for late
        joiners, either of which would otherwise re-confirm a warmup/
        cooldown exercise as if it were part of the shared MAIN set.
        """
        joined_users = await self._joined_users(party.id)
        joined_users.sort(key=lambda member_user: member_user.id != party.created_by)
        for member_user in joined_users:
            day_plan = await self._schedule.get_day_plan_for_date(member_user.id, party.target_date)
            if day_plan is not None and day_plan.training_session is not None:
                blocks = [
                    block
                    for block in day_plan.training_session.blocks
                    if block.phase == TrainingPhase.MAIN
                ]
                if blocks:
                    return [block.exercise_id for block in blocks]
        return []

    async def _finalized_exercises_read(self, party: TrainingParty) -> list[ExerciseRead] | None:
        if party.exercises_finalized_at is None:
            return None
        exercises = []
        for exercise_id in await self._canonical_exercise_ids(party):
            exercise = await self._exercises.get_by_id(exercise_id)
            if exercise is not None:
                exercises.append(exercise)
        stats_by_id = await self._exercises.list_target_stats_by_exercise(
            [exercise.id for exercise in exercises]
        )
        return exercises_to_read(exercises, stats_by_id)

    @staticmethod
    def _effective_status(party: TrainingParty) -> PartyStatus:
        if party.status == TrainingPartyStatus.PENDING and party.target_date < date.today():
            return "expired"
        return party.status.value  # type: ignore[return-value]

    async def _resolve_member_training_status(
        self, user_id: uuid.UUID, target_date: date
    ) -> _MemberStatus:
        day_plan = await self._schedule.get_day_plan_for_date(user_id, target_date)
        if day_plan is None:
            return _MemberStatus("no_plan_for_date", None, None, None)
        if day_plan.session_type == DaySessionType.REST:
            return _MemberStatus("resting", None, None, day_plan.id)
        if day_plan.session_type == DaySessionType.GAME:
            return _MemberStatus("game_day", None, None, day_plan.id)

        blocks = day_plan.training_session.blocks if day_plan.training_session is not None else []
        total = len(blocks)
        completed = sum(
            1 for block in blocks if block.completed_at is not None or block.skipped_at is not None
        )
        if completed == 0:
            return _MemberStatus("not_started", completed, total, day_plan.id)
        if total > 0 and completed == total:
            return _MemberStatus("completed", completed, total, day_plan.id)
        return _MemberStatus("in_progress", completed, total, day_plan.id)

    async def _to_detail_read(self, party: TrainingParty) -> TrainingPartyDetailRead:
        members_with_users = await self._parties.list_members_with_users(party.id)
        member_reads = []
        for member, user in members_with_users:
            resolved = (
                await self._resolve_member_training_status(user.id, party.target_date)
                if member.status == TrainingPartyMemberStatus.JOINED
                else None
            )
            member_reads.append(
                TrainingPartyMemberRead(
                    user_id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    avatar_url=user.avatar_url,
                    membership_status=member.status.value,  # type: ignore[arg-type]
                    training_status=resolved.training_status if resolved is not None else None,
                    completed_blocks=resolved.completed_blocks if resolved is not None else None,
                    total_blocks=resolved.total_blocks if resolved is not None else None,
                    day_plan_id=resolved.day_plan_id if resolved is not None else None,
                )
            )
        return TrainingPartyDetailRead(
            id=party.id,
            created_by=party.created_by,
            target_date=party.target_date,
            status=self._effective_status(party),
            members=member_reads,
            created_at=party.created_at,
            completed_at=party.completed_at,
            exercises_finalized_at=party.exercises_finalized_at,
            exercises=await self._finalized_exercises_read(party),
        )
