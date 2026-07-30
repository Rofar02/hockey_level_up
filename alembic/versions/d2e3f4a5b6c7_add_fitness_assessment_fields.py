"""add fitness_tier and has_assessment to users

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'fitness_tier',
            sa.Enum('beginner', 'intermediate', 'advanced', name='fitness_tier', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        'users',
        sa.Column('has_assessment', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'has_assessment')
    op.drop_column('users', 'fitness_tier')
