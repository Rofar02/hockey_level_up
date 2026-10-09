"""lineup slot position

Revision ID: f2b8d4e6a1c3
Revises: e1a7c3d5f9b2
Create Date: 2026-10-10 00:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b8d4e6a1c3'
down_revision: Union[str, None] = 'e1a7c3d5f9b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('team_event_lineup_slots', sa.Column('slot_position', sa.String(length=3), nullable=True))


def downgrade() -> None:
    op.drop_column('team_event_lineup_slots', 'slot_position')
