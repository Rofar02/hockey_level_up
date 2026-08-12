"""add team score supporting indexes

Revision ID: b1c2d3e4f5a6
Revises: 7d856f2fcfe3
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '7d856f2fcfe3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Supports TeamRatingService's "completed trainings in the last 7 days"
    # aggregate, which filters day_plans by date across many users' plans at
    # once (see app/services/team_rating_service.py).
    op.create_index(op.f('ix_day_plans_date'), 'day_plans', ['date'], unique=False)
    # Partial index -- only completed_at IS NOT NULL rows are ever queried
    # (has_missed_training_day, TeamRatingService), same idiom as the
    # existing ix_outbox_events_unpublished partial index.
    op.create_index(
        'ix_session_blocks_completed_at_not_null',
        'session_blocks',
        ['completed_at'],
        unique=False,
        postgresql_where=sa.text('completed_at IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_session_blocks_completed_at_not_null', table_name='session_blocks')
    op.drop_index(op.f('ix_day_plans_date'), table_name='day_plans')
