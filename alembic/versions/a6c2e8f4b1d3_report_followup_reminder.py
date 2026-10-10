"""day plan: the next morning's follow-up report reminder

Revision ID: a6c2e8f4b1d3
Revises: f9b5d1e7a3c2
Create Date: 2026-10-10 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6c2e8f4b1d3'
down_revision: Union[str, None] = 'f9b5d1e7a3c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('day_plans', sa.Column('report_followup_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('day_plans', 'report_followup_sent_at')
