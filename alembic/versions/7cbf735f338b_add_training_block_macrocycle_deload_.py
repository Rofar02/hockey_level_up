"""add training block macrocycle deload flag

Revision ID: 7cbf735f338b
Revises: 55b37acb798b
Create Date: 2026-08-17 09:38:53.671651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cbf735f338b'
down_revision: Union[str, None] = '55b37acb798b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'training_blocks',
        sa.Column('is_macrocycle_deload', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('training_blocks', 'is_macrocycle_deload')
