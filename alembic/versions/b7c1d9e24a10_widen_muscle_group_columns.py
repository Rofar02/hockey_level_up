"""widen muscle_group columns to VARCHAR(32)

The three muscle_group columns were sized by SQLAlchemy to the longest value
at the time (VARCHAR(10), "hamstrings"). New groups ("adductors", and
"hip_flexors" at 11 characters) do not all fit, so the columns are widened
once to a roomy size; the models now pin length=32 (app/db/enum_column.py).
Widening a VARCHAR in Postgres is a metadata-only change: instant, no rewrite,
no data loss.

Revision ID: b7c1d9e24a10
Revises: ac105a1a4ea6
Create Date: 2026-10-03 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d9e24a10'
down_revision: Union[str, None] = 'ac105a1a4ea6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, nullable)
_COLUMNS = [
    ('exercise_muscle_groups', False),
    ('user_muscle_loads', False),
    ('user_temporary_restrictions', True),
]


def upgrade() -> None:
    for table, nullable in _COLUMNS:
        op.alter_column(
            table, 'muscle_group',
            existing_type=sa.String(length=10), type_=sa.String(length=32),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    # Fails by design if a row already holds a value longer than 10 characters
    # ("hip_flexors"): remove those rows first.
    for table, nullable in _COLUMNS:
        op.alter_column(
            table, 'muscle_group',
            existing_type=sa.String(length=32), type_=sa.String(length=10),
            existing_nullable=nullable,
        )
