"""convert exercise target_stat to m2m exercise_target_stats

Revision ID: d4355dfb0b0c
Revises: 5fec3e8ccc26
Create Date: 2026-08-14 16:47:42.548762

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4355dfb0b0c'
down_revision: Union[str, None] = '5fec3e8ccc26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TARGET_STAT_VALUES = (
    'strength', 'agility', 'intellect', 'endurance', 'on_ice_skating', 'puck_handling',
)


def upgrade() -> None:
    op.create_table(
        'exercise_target_stats',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column(
            'target_stat',
            sa.Enum(*TARGET_STAT_VALUES, name='target_stat', native_enum=False),
            nullable=False,
        ),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exercise_id', 'target_stat', name='uq_exercise_target_stats_exercise_stat'),
        sa.UniqueConstraint('exercise_id', 'order', name='uq_exercise_target_stats_exercise_order'),
    )
    op.create_index(
        op.f('ix_exercise_target_stats_exercise_id'), 'exercise_target_stats', ['exercise_id'], unique=False
    )

    # Data transfer: every existing exercise's single target_stat becomes its
    # order=0 (primary) row. Generated client-side (uuid.uuid4()) rather than
    # via gen_random_uuid() in SQL, matching how every other table's UUID PK
    # in this project is generated at the ORM layer, not the DB layer -- no
    # dependency on a specific Postgres version/extension being available.
    connection = op.get_bind()
    exercises = sa.table('exercises', sa.column('id', sa.UUID()), sa.column('target_stat', sa.String()))
    exercise_target_stats = sa.table(
        'exercise_target_stats',
        sa.column('id', sa.UUID()),
        sa.column('exercise_id', sa.UUID()),
        sa.column('target_stat', sa.String()),
        sa.column('order', sa.Integer()),
    )
    rows = connection.execute(sa.select(exercises.c.id, exercises.c.target_stat)).fetchall()
    if rows:
        connection.execute(
            exercise_target_stats.insert(),
            [
                {"id": uuid.uuid4(), "exercise_id": row.id, "target_stat": row.target_stat, "order": 0}
                for row in rows
            ],
        )

    op.drop_column('exercises', 'target_stat')


def downgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'target_stat',
            sa.Enum(*TARGET_STAT_VALUES, name='target_stat', native_enum=False),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE exercises AS e
        SET target_stat = ets.target_stat
        FROM exercise_target_stats AS ets
        WHERE ets.exercise_id = e.id AND ets."order" = 0
        """
    )
    op.alter_column('exercises', 'target_stat', nullable=False)

    op.drop_index(op.f('ix_exercise_target_stats_exercise_id'), table_name='exercise_target_stats')
    op.drop_table('exercise_target_stats')
