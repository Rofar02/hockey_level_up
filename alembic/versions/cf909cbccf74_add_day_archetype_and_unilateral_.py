"""add day-archetype rotation columns and unilateral flag

Revision ID: cf909cbccf74
Revises: 72b50a73e77b
Create Date: 2026-08-20 09:40:00.000000

Stage 2.4 (2026-08-20 planning session): role-based MAIN assembly +
day-archetype rotation for squat/hip_hinge/push/pull.

- exercises.is_unilateral: nullable bool, NULL means "not yet classified"
  same contract as stimulus_type/warmup_stage.
- user_movement_pattern_variants gets `archetype` (StimulusType, reused
  rather than a new enum -- see the model docstring) and `last_chosen_at`,
  and its unique constraint widens to include archetype. Purely additive:
  archetype is nullable and every existing row keeps archetype=NULL, which
  preserves its current one-row-per-pattern meaning exactly -- no backfill
  needed, no existing row's semantics change.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf909cbccf74'
down_revision: Union[str, None] = '72b50a73e77b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STIMULUS_TYPE_VALUES = ('strength', 'power', 'endurance', 'skill', 'mobility')


def upgrade() -> None:
    op.add_column('exercises', sa.Column('is_unilateral', sa.Boolean(), nullable=True))

    op.add_column(
        'user_movement_pattern_variants',
        sa.Column(
            'archetype',
            sa.Enum(*STIMULUS_TYPE_VALUES, name='stimulus_type', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        'user_movement_pattern_variants', sa.Column('last_chosen_at', sa.Date(), nullable=True)
    )

    op.drop_constraint(
        'uq_user_movement_pattern_variants_user_category_pattern',
        'user_movement_pattern_variants',
        type_='unique',
    )
    op.create_unique_constraint(
        'uq_ump_variants_user_category_pattern_archetype',
        'user_movement_pattern_variants',
        ['user_id', 'category', 'movement_pattern', 'archetype'],
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_ump_variants_user_category_pattern_archetype',
        'user_movement_pattern_variants',
        type_='unique',
    )
    # Lossy on purpose: if Stage 2.4 ever produced more than one row per
    # (user, category, pattern) -- i.e. real archetype-split rows -- this
    # can't restore the old single-row-per-pattern constraint without
    # picking a winner. Keeps the most recently touched row per pattern
    # (by last_chosen_at, nulls last) and drops the rest, same "downgrade
    # only ever needs to unwind this migration, not preserve everything"
    # tradeoff as the Stage 2.1/2.2 migrations' own downgrades.
    op.execute(
        """
        DELETE FROM user_movement_pattern_variants AS v
        WHERE v.id NOT IN (
            SELECT DISTINCT ON (user_id, category, movement_pattern) id
            FROM user_movement_pattern_variants
            ORDER BY user_id, category, movement_pattern, last_chosen_at DESC NULLS LAST
        )
        """
    )
    op.create_unique_constraint(
        'uq_user_movement_pattern_variants_user_category_pattern',
        'user_movement_pattern_variants',
        ['user_id', 'category', 'movement_pattern'],
    )
    op.drop_column('user_movement_pattern_variants', 'last_chosen_at')
    op.drop_column('user_movement_pattern_variants', 'archetype')
    op.drop_column('exercises', 'is_unilateral')
