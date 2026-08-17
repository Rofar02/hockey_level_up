"""add user tournament date

Revision ID: 65c9038fc907
Revises: 8d4da480e3d5
Create Date: 2026-08-17 13:31:47.021043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65c9038fc907'
down_revision: Union[str, None] = '8d4da480e3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('tournament_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'tournament_date')
