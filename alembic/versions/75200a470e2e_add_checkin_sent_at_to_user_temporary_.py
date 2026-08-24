"""add checkin_sent_at to user_temporary_restrictions

Revision ID: 75200a470e2e
Revises: c38ac539e5ce
Create Date: 2026-08-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75200a470e2e'
down_revision: Union[str, None] = 'c38ac539e5ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_temporary_restrictions',
        sa.Column('checkin_sent_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_temporary_restrictions', 'checkin_sent_at')
