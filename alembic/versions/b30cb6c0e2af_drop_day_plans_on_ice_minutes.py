"""drop day_plans on_ice_minutes

Revision ID: b30cb6c0e2af
Revises: b954b69a0fa4
Create Date: 2026-08-23 06:33:34.461270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b30cb6c0e2af'
down_revision: Union[str, None] = 'b954b69a0fa4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Never consumed by exercise selection since it was added (Phase 6,
    # a23c641d65dc) -- content for ON_ICE has since moved to a fixed
    # warmup+cooldown wrapped around a coach-run practice (no MAIN block,
    # see ScheduleService._build_on_ice_day_session), which needs no
    # user-stated rink-time budget.
    op.drop_column('day_plans', 'on_ice_minutes')


def downgrade() -> None:
    op.add_column('day_plans', sa.Column('on_ice_minutes', sa.Integer(), nullable=True))
