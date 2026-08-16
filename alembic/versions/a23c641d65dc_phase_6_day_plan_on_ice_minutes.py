"""phase 6: day_plan on_ice_minutes

Revision ID: a23c641d65dc
Revises: 832d5d79f1c5
Create Date: 2026-08-16 12:09:26.564476

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a23c641d65dc'
down_revision: Union[str, None] = '832d5d79f1c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('day_plans', sa.Column('on_ice_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('day_plans', 'on_ice_minutes')
