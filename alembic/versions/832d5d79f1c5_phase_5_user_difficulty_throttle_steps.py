"""phase 5: user difficulty_throttle_steps

Revision ID: 832d5d79f1c5
Revises: 9732cb4e3149
Create Date: 2026-08-15 13:25:23.155671

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '832d5d79f1c5'
down_revision: Union[str, None] = '9732cb4e3149'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('difficulty_throttle_steps', sa.Integer(), server_default='0', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'difficulty_throttle_steps')
