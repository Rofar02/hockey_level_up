"""add user movement pattern variants table

Revision ID: 0770d1384e00
Revises: 7cbf735f338b
Create Date: 2026-08-17 10:34:13.532325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0770d1384e00'
down_revision: Union[str, None] = '7cbf735f338b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_movement_pattern_variants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'category',
            sa.Enum('on_ice', 'off_ice', name='exercise_category', native_enum=False),
            nullable=False,
        ),
        sa.Column(
            'movement_pattern',
            sa.Enum(
                'hip_hinge', 'squat', 'push', 'pull', 'rotation', 'ankle_mobility',
                'hip_mobility', 'shoulder_mobility', 'wrist_mobility', 'core', 'locomotion',
                name='movement_pattern', native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'category', 'movement_pattern',
            name='uq_user_movement_pattern_variants_user_category_pattern',
        ),
    )
    op.create_index(
        op.f('ix_user_movement_pattern_variants_user_id'),
        'user_movement_pattern_variants', ['user_id'], unique=False,
    )
    op.create_index(
        op.f('ix_user_movement_pattern_variants_exercise_id'),
        'user_movement_pattern_variants', ['exercise_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_user_movement_pattern_variants_exercise_id'),
        table_name='user_movement_pattern_variants',
    )
    op.drop_index(
        op.f('ix_user_movement_pattern_variants_user_id'),
        table_name='user_movement_pattern_variants',
    )
    op.drop_table('user_movement_pattern_variants')
