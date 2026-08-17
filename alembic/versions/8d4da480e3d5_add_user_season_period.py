"""add user season period

Revision ID: 8d4da480e3d5
Revises: 0770d1384e00
Create Date: 2026-08-17 11:20:31.797920

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8d4da480e3d5'
down_revision: Union[str, None] = '0770d1384e00'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'season_period',
            sa.Enum('offseason', 'preseason', 'season', 'playoffs', name='season_period', native_enum=False),
            server_default='offseason', nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'season_period')
