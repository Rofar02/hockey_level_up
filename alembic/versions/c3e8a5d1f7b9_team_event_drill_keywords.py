"""team_event_drills.keywords -- cues for the players' plan reel (В, 2026-10-13)

Revision ID: c3e8a5d1f7b9
Revises: b7d4e1f9a2c6
Create Date: 2026-10-14 01:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3e8a5d1f7b9'
down_revision: Union[str, None] = 'b7d4e1f9a2c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('team_event_drills', sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    # Added 2026-10-14 before this migration ever reached production.
    op.add_column('drill_templates', sa.Column('keywords', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('drill_templates', 'keywords')
    op.drop_column('team_event_drills', 'keywords')
