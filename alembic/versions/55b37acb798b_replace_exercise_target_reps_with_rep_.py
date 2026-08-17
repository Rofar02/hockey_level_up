"""replace exercise target_reps with rep range

Revision ID: 55b37acb798b
Revises: 7cb8122065ad
Create Date: 2026-08-17 08:31:43.560531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '55b37acb798b'
down_revision: Union[str, None] = '7cb8122065ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('exercises', sa.Column('rep_range_min', sa.Integer(), nullable=True))
    op.add_column('exercises', sa.Column('rep_range_max', sa.Integer(), nullable=True))
    op.drop_column('exercises', 'target_reps')


def downgrade() -> None:
    op.add_column('exercises', sa.Column('target_reps', sa.Integer(), nullable=True))
    op.drop_column('exercises', 'rep_range_max')
    op.drop_column('exercises', 'rep_range_min')
