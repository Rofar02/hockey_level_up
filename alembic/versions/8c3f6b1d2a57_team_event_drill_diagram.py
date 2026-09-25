"""team event drill diagram

Revision ID: 8c3f6b1d2a57
Revises: 5d1e8a4c7b92
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8c3f6b1d2a57'
down_revision: Union[str, None] = '5d1e8a4c7b92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'team_event_drills',
        sa.Column('diagram', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('team_event_drills', 'diagram')
