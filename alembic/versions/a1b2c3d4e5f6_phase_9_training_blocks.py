"""phase 9: training_blocks table, weekly_plans.training_block_id, users.suggested_reassessment

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f4a5b6c7d8e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'training_blocks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('block_number', sa.Integer(), nullable=False),
        sa.Column('week_in_block', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            'week_in_block >= 1 AND week_in_block <= 4', name='ck_training_blocks_week_in_block_range'
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'block_number', name='uq_training_blocks_user_block_number'),
    )
    op.create_index(
        op.f('ix_training_blocks_user_id'), 'training_blocks', ['user_id'], unique=False
    )

    op.add_column('weekly_plans', sa.Column('training_block_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_weekly_plans_training_block_id',
        'weekly_plans',
        'training_blocks',
        ['training_block_id'],
        ['id'],
        ondelete='SET NULL',
    )

    op.add_column(
        'users',
        sa.Column('suggested_reassessment', sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'suggested_reassessment')

    op.drop_constraint('fk_weekly_plans_training_block_id', 'weekly_plans', type_='foreignkey')
    op.drop_column('weekly_plans', 'training_block_id')

    op.drop_index(op.f('ix_training_blocks_user_id'), table_name='training_blocks')
    op.drop_table('training_blocks')
