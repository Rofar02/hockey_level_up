"""add times_chosen to user_movement_pattern_variants

Revision ID: a7b8c9d0e1f2
Revises: 5a6b7c8d9e0f
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = '5a6b7c8d9e0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_movement_pattern_variants',
        sa.Column('times_chosen', sa.Integer(), server_default=sa.text('0'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('user_movement_pattern_variants', 'times_chosen')
