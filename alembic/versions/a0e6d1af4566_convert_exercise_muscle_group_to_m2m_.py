"""convert exercise muscle_group to weighted m2m exercise_muscle_groups

Revision ID: a0e6d1af4566
Revises: a3c7e9d1f204
Create Date: 2026-08-20 05:40:00.000000

Stage 2.1 (2026-08-20 planning session): the old push/pull/legs/core
grouping couldn't distinguish a squat from a lunge (both "legs") even
though they load different muscles. Replaced by a detailed anatomical
taxonomy and a weighted per-exercise list (see ExerciseMuscleGroup),
mirroring skill_stat_weights' shape.

The backfill below is a best-effort placeholder mapping (weight 1.0, one
group per exercise) from the old 4 values -- real anatomical accuracy
across the ~210-exercise catalog is Stage 4's job (manual retagging), not
this migration's. Nothing here blocks on that; an exercise this backfill
maps imprecisely just sits at the coarse old-equivalent group until
someone retags it in the admin panel.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0e6d1af4566'
down_revision: Union[str, None] = 'a3c7e9d1f204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MUSCLE_GROUP_VALUES = (
    'quads', 'hamstrings', 'glutes', 'chest', 'back', 'shoulders', 'core', 'calves',
)

# Old value -> new value, used both directions by this migration only (not
# a general-purpose mapping) -- downgrade's reverse direction is lossy by
# construction once real per-exercise retagging happens post-upgrade, same
# accepted tradeoff as d4355dfb0b0c's target_stat downgrade only
# reconstructing order=0.
OLD_TO_NEW = {
    'push': 'chest',
    'pull': 'back',
    'legs': 'quads',
    'core': 'core',
}


def upgrade() -> None:
    op.create_table(
        'exercise_muscle_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column(
            'muscle_group',
            sa.Enum(*MUSCLE_GROUP_VALUES, name='muscle_group', native_enum=False),
            nullable=False,
        ),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.CheckConstraint(
            'weight >= 0.0 AND weight <= 1.0', name='ck_exercise_muscle_groups_weight_range'
        ),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'exercise_id', 'muscle_group', name='uq_exercise_muscle_groups_exercise_group'
        ),
    )
    op.create_index(
        op.f('ix_exercise_muscle_groups_exercise_id'), 'exercise_muscle_groups', ['exercise_id'],
        unique=False,
    )

    connection = op.get_bind()
    exercises = sa.table('exercises', sa.column('id', sa.UUID()), sa.column('muscle_group', sa.String()))
    exercise_muscle_groups = sa.table(
        'exercise_muscle_groups',
        sa.column('id', sa.UUID()),
        sa.column('exercise_id', sa.UUID()),
        sa.column('muscle_group', sa.String()),
        sa.column('weight', sa.Float()),
    )
    rows = connection.execute(
        sa.select(exercises.c.id, exercises.c.muscle_group).where(exercises.c.muscle_group.isnot(None))
    ).fetchall()
    if rows:
        connection.execute(
            exercise_muscle_groups.insert(),
            [
                {
                    "id": uuid.uuid4(),
                    "exercise_id": row.id,
                    "muscle_group": OLD_TO_NEW[row.muscle_group],
                    "weight": 1.0,
                }
                for row in rows
            ],
        )

    op.drop_column('exercises', 'muscle_group')


def downgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'muscle_group',
            sa.Enum('push', 'pull', 'legs', 'core', name='muscle_group', native_enum=False),
            nullable=True,
        ),
    )
    # Lossy on purpose (see module docstring): picks each exercise's
    # highest-weight row and maps it back to the coarse old value. An
    # exercise with several groups tied at the max weight picks whichever
    # Postgres returns first for that tie -- acceptable for a downgrade
    # path that's only ever meant to unwind this same migration, not to
    # preserve post-Stage-4 retagging data.
    op.execute(
        """
        UPDATE exercises AS e
        SET muscle_group = CASE emg.muscle_group
            WHEN 'chest' THEN 'push'
            WHEN 'shoulders' THEN 'push'
            WHEN 'back' THEN 'pull'
            WHEN 'core' THEN 'core'
            ELSE 'legs'
        END
        FROM (
            SELECT DISTINCT ON (exercise_id) exercise_id, muscle_group
            FROM exercise_muscle_groups
            ORDER BY exercise_id, weight DESC
        ) AS emg
        WHERE emg.exercise_id = e.id
        """
    )

    op.drop_index(op.f('ix_exercise_muscle_groups_exercise_id'), table_name='exercise_muscle_groups')
    op.drop_table('exercise_muscle_groups')
