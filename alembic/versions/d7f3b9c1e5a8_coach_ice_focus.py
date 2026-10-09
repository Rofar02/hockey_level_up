"""coach ice focus on user

Revision ID: d7f3b9c1e5a8
Revises: c5e1a7b9d4f6
Create Date: 2026-10-10 03:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd7f3b9c1e5a8'
down_revision: Union[str, None] = 'c5e1a7b9d4f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('coach_ice_focus_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('users', sa.Column('coach_ice_focus_until', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'coach_ice_focus_until')
    op.drop_column('users', 'coach_ice_focus_ids')
