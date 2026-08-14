"""add exercise stimulus_type exercise_type and movement_patterns

Revision ID: 7d3154c63b35
Revises: f5a6b7c8d9e0
Create Date: 2026-08-14 14:48:10.196629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d3154c63b35'
down_revision: Union[str, None] = 'f5a6b7c8d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'stimulus_type',
            sa.Enum(
                'strength', 'power', 'endurance', 'skill', 'mobility',
                name='stimulus_type', native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        'exercises',
        sa.Column(
            'exercise_type',
            sa.Enum('sets_reps', 'duration', name='exercise_type', native_enum=False),
            nullable=True,
        ),
    )
    op.create_table(
        'exercise_movement_patterns',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column(
            'movement_pattern',
            sa.Enum(
                'hip_hinge', 'squat', 'push', 'pull', 'rotation', 'ankle_mobility',
                'hip_mobility', 'core', 'locomotion',
                name='movement_pattern', native_enum=False,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'exercise_id', 'movement_pattern', name='uq_exercise_movement_patterns_exercise_pattern'
        ),
    )
    op.create_index(
        op.f('ix_exercise_movement_patterns_exercise_id'),
        'exercise_movement_patterns',
        ['exercise_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_exercise_movement_patterns_exercise_id'), table_name='exercise_movement_patterns'
    )
    op.drop_table('exercise_movement_patterns')
    op.drop_column('exercises', 'exercise_type')
    op.drop_column('exercises', 'stimulus_type')
