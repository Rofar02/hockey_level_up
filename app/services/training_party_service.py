import uuid
from datetime import date, datetime, timezone
from typing import NamedTuple

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schedule import DaySessionType
from app.models.training_party import TrainingParty, TrainingPartyMemberStatus, TrainingPartyStatus
from app.models.user import User
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.schedule_repository import ScheduleRepository
from app.repositories.training_party_repository import TrainingPartyRepository
from app.repositories.user_repository import UserRepository
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
        member = await self._parties.get_member(party_id, user.id)
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Приглашение не найдено"
            )
        if member.status != TrainingPartyMemberStatus.INVITED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Уже отвечено на это приглашение"
            )
        member.status = (
            TrainingPartyMemberStatus.JOINED if accept else TrainingPartyMemberStatus.DECLINED
        )
        if accept:
            member.joined_at = datetime.now(timezone.utc)
        await self._session.commit()

        party = await self._get_party_or_404(party_id)
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
        completed = sum(1 for block in blocks if block.completed_at is not None)
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
        )
