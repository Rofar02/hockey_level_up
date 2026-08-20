"""add user_muscle_loads table

Revision ID: b954b69a0fa4
Revises: cf909cbccf74
Create Date: 2026-08-20 12:00:00.000000

Body-muscles map (2026-08-20 planning session, dependent on Stage 2.1's
MuscleGroup taxonomy, already shipped as of this migration). Same shape as
user_stats (user, category, running value, last-touched timestamp) -- see
UserMuscleLoad's own model docstring for why the value's meaning and decay
direction are the opposite of a stat's, not something this migration needs
to encode, purely additive/new table either way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b954b69a0fa4'
down_revision: Union[str, None] = 'cf909cbccf74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MUSCLE_GROUP_VALUES = (
    'quads', 'hamstrings', 'glutes', 'chest', 'back', 'shoulders', 'core', 'calves',
)


def upgrade() -> None:
    op.create_table(
        'user_muscle_loads',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
        ),
        sa.Column(
            'muscle_group',
            sa.Enum(*MUSCLE_GROUP_VALUES, name='muscle_group', native_enum=False),
            nullable=False,
        ),
        sa.Column('current_value', sa.Float(), nullable=False, server_default='0'),
        sa.Column(
            'last_updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint('user_id', 'muscle_group', name='uq_user_muscle_loads_user_muscle_group'),
    )


def downgrade() -> None:
    op.drop_table('user_muscle_loads')
