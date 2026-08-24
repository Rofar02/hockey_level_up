"""add user coach personality

Revision ID: c38ac539e5ce
Revises: bd7f3a5067e9
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c38ac539e5ce'
down_revision: Union[str, None] = 'bd7f3a5067e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'coach_personality',
            sa.Enum('calm', 'strict', 'humor', 'vibe', name='coach_personality', native_enum=False),
            server_default='calm', nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'coach_personality')
