"""training session: the ice day's focus, fixed when first shown

Revision ID: b7d3f9a5c2e4
Revises: a6c2e8f4b1d3
Create Date: 2026-10-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d3f9a5c2e4'
down_revision: Union[str, None] = 'a6c2e8f4b1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('training_sessions', sa.Column('ice_focus_id', sa.String(length=40), nullable=True))
    op.add_column('training_sessions', sa.Column('ice_focus_reason', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('training_sessions', 'ice_focus_reason')
    op.drop_column('training_sessions', 'ice_focus_id')
