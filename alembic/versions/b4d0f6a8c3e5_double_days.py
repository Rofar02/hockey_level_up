"""double days: extra gym day plan next to an ice/game day

Revision ID: b4d0f6a8c3e5
Revises: a3c9e5f7b2d4
Create Date: 2026-10-10 02:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4d0f6a8c3e5'
down_revision: Union[str, None] = 'a3c9e5f7b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('day_plans', sa.Column('is_extra', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('day_plans', sa.Column('time_of_day', sa.String(length=8), nullable=True))
    op.drop_constraint('uq_day_plans_weekly_plan_date', 'day_plans', type_='unique')
    op.create_unique_constraint(
        'uq_day_plans_weekly_plan_date_extra', 'day_plans', ['weekly_plan_id', 'date', 'is_extra']
    )


def downgrade() -> None:
    op.execute("DELETE FROM day_plans WHERE is_extra")
    op.drop_constraint('uq_day_plans_weekly_plan_date_extra', 'day_plans', type_='unique')
    op.create_unique_constraint('uq_day_plans_weekly_plan_date', 'day_plans', ['weekly_plan_id', 'date'])
    op.drop_column('day_plans', 'time_of_day')
    op.drop_column('day_plans', 'is_extra')
