"""add shoulder_mobility and wrist_mobility movement patterns

Revision ID: 5fec3e8ccc26
Revises: 7d3154c63b35
Create Date: 2026-08-14 16:39:23.884942

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5fec3e8ccc26'
down_revision: Union[str, None] = '7d3154c63b35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'exercise_movement_patterns', 'movement_pattern',
        existing_type=sa.VARCHAR(length=14),
        type_=sa.Enum(
            'hip_hinge', 'squat', 'push', 'pull', 'rotation', 'ankle_mobility',
            'hip_mobility', 'shoulder_mobility', 'wrist_mobility', 'core', 'locomotion',
            name='movement_pattern', native_enum=False,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'exercise_movement_patterns', 'movement_pattern',
        existing_type=sa.Enum(
            'hip_hinge', 'squat', 'push', 'pull', 'rotation', 'ankle_mobility',
            'hip_mobility', 'shoulder_mobility', 'wrist_mobility', 'core', 'locomotion',
            name='movement_pattern', native_enum=False,
        ),
        type_=sa.VARCHAR(length=14),
        existing_nullable=False,
    )
