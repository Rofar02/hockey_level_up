"""add avatar ring accent and jersey color

Revision ID: 7c2b91a4e6f3
Revises: 69f166e92a25
Create Date: 2026-08-30 00:00:00.000000

Level-gated cosmetics (item 6, 2026-08-30 gamification pass) -- see
app.core.level_unlocks for the level thresholds (avatar ring choice at 10,
jersey color choice at 15). Both nullable: NULL means "no choice made yet,
use the automatic default".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2b91a4e6f3'
down_revision: Union[str, None] = '69f166e92a25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'avatar_ring_accent',
            sa.Enum('ice', 'persimmon', 'mix', name='avatar_ring_accent', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'jersey_color',
            sa.Enum('white', 'ice', 'persimmon', 'gold', name='jersey_color', native_enum=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'jersey_color')
    op.drop_column('users', 'avatar_ring_accent')
