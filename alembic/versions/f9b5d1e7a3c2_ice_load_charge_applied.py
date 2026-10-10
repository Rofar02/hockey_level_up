"""ice load charge: what was actually applied, and when the ice ended;
when the player changed the season period

Revision ID: f9b5d1e7a3c2
Revises: e8a4c0d2f6b9
Create Date: 2026-10-10 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f9b5d1e7a3c2'
down_revision: Union[str, None] = 'e8a4c0d2f6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ice_load_charges', sa.Column('applied', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('ice_load_charges', sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('ice_load_charges', sa.Column('ice_ended_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('season_period_changed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'season_period_changed_at')
    op.drop_column('ice_load_charges', 'ice_ended_at')
    op.drop_column('ice_load_charges', 'applied_at')
    op.drop_column('ice_load_charges', 'applied')
