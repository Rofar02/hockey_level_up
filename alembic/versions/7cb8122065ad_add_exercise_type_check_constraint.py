"""add exercise_type check constraint

Revision ID: 7cb8122065ad
Revises: a23c641d65dc
Create Date: 2026-08-17 04:26:54.352621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cb8122065ad'
down_revision: Union[str, None] = 'a23c641d65dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        'ck_exercises_exercise_type',
        'exercises',
        "exercise_type IN ('sets_reps', 'duration')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_exercises_exercise_type', 'exercises', type_='check')
