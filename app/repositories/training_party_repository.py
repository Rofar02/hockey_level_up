import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_party import (
    TrainingParty,
    TrainingPartyMember,
    TrainingPartyMemberStatus,
    TrainingPartyStatus,
)
from app.models.user import User


class TrainingPartyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- party --

    async def create_party(self, created_by: uuid.UUID, target_date: date) -> TrainingParty:
        party = TrainingParty(created_by=created_by, target_date=target_date)
        self._session.add(party)
        await self._session.flush()
        return party

    async def get_party_by_id(self, party_id: uuid.UUID) -> TrainingParty | None:
        return await self._session.get(TrainingParty, party_id)

    async def list_pending_parties_for_member_on_date(
        self, user_id: uuid.UUID, target_date: date
    ) -> list[TrainingParty]:
        """Backs TrainingPartyService.try_complete_parties_for -- every
        still-open party this user is a JOINED member of, targeting exactly
        this date."""
        result = await self._session.execute(
            select(TrainingParty)
            .join(TrainingPartyMember, TrainingPartyMember.party_id == TrainingParty.id)
            .where(
                TrainingParty.status == TrainingPartyStatus.PENDING,
                TrainingParty.target_date == target_date,
                TrainingPartyMember.user_id == user_id,
                TrainingPartyMember.status == TrainingPartyMemberStatus.JOINED,
            )
        )
        return list(result.scalars().all())

    # -- membership --

    async def create_member(
        self, party_id: uuid.UUID, user_id: uuid.UUID, status: TrainingPartyMemberStatus
    ) -> TrainingPartyMember:
        member = TrainingPartyMember(party_id=party_id, user_id=user_id, status=status)
        self._session.add(member)
        await self._session.flush()
        return member

    async def get_member(
        self, party_id: uuid.UUID, user_id: uuid.UUID
    ) -> TrainingPartyMember | None:
        result = await self._session.execute(
            select(TrainingPartyMember).where(
                TrainingPartyMember.party_id == party_id, TrainingPartyMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_members_with_users(
        self, party_id: uuid.UUID
    ) -> list[tuple[TrainingPartyMember, User]]:
        """Single JOIN rather than one User lookup per member -- same
        avoid-N+1 reasoning as TeamRepository.list_members."""
        result = await self._session.execute(
            select(TrainingPartyMember, User)
            .join(User, User.id == TrainingPartyMember.user_id)
            .where(TrainingPartyMember.party_id == party_id)
            .order_by(TrainingPartyMember.joined_at)
        )
        return [(member, user) for member, user in result.all()]

    async def count_members(self, party_id: uuid.UUID) -> int:
        result = await self._session.execute(
            select(func.count(TrainingPartyMember.id)).where(
                TrainingPartyMember.party_id == party_id
            )
        )
        return result.scalar_one()

    async def list_joined_party_ids_for_user(self, user_id: uuid.UUID) -> list[TrainingPartyMember]:
        """Every party (with membership row) this user has actually joined
        (created or accepted) -- GET /training-parties/me. Invited-but-not-
        yet-responded belongs to list_incoming_invites instead, not here."""
        result = await self._session.execute(
            select(TrainingPartyMember)
            .join(TrainingParty, TrainingParty.id == TrainingPartyMember.party_id)
            .where(
                TrainingPartyMember.user_id == user_id,
                TrainingPartyMember.status == TrainingPartyMemberStatus.JOINED,
            )
            .order_by(TrainingParty.target_date.desc())
        )
        return list(result.scalars().all())

    async def list_incoming_invites(self, user_id: uuid.UUID, today: date) -> list[TrainingPartyMember]:
        result = await self._session.execute(
            select(TrainingPartyMember)
            .join(TrainingParty, TrainingParty.id == TrainingPartyMember.party_id)
            .where(
                TrainingPartyMember.user_id == user_id,
                TrainingPartyMember.status == TrainingPartyMemberStatus.INVITED,
                TrainingParty.status == TrainingPartyStatus.PENDING,
                TrainingParty.target_date >= today,
            )
            .order_by(TrainingParty.target_date)
        )
        return list(result.scalars().all())

    async def delete_member(self, member: TrainingPartyMember) -> None:
        await self._session.delete(member)
        await self._session.flush()
