"""phase 4: training block session-driven phase progression

Revision ID: 9732cb4e3149
Revises: d4355dfb0b0c
Create Date: 2026-08-15 12:48:18.478388

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9732cb4e3149'
down_revision: Union[str, None] = 'd4355dfb0b0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'training_blocks',
        sa.Column(
            'phase',
            sa.Enum('accumulation', 'intensification', 'deload', name='block_phase', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column('training_blocks', sa.Column('phase_started_at', sa.Date(), nullable=True))

    # Backfill 'phase' from the old week_in_block, mirroring
    # app.core.training_block.get_phase's since-removed mapping
    # (1,2 -> accumulation; 3 -> intensification; 4 -> deload).
    op.execute(
        """
        UPDATE training_blocks
        SET phase = CASE
            WHEN week_in_block IN (1, 2) THEN 'accumulation'
            WHEN week_in_block = 3 THEN 'intensification'
            WHEN week_in_block = 4 THEN 'deload'
            ELSE 'accumulation'
        END
        """
    )
    # Backfill 'phase_started_at': best-effort -- anchor_week_start_date was
    # "the real calendar week week_in_block currently reflects", the
    # closest existing data to "when did the current phase start". Falls
    # back to the block's created_at date, then today, for the (rare, dev-
    # only) rows that predate even that column.
    op.execute(
        """
        UPDATE training_blocks
        SET phase_started_at = COALESCE(anchor_week_start_date, created_at::date, CURRENT_DATE)
        """
    )

    op.alter_column('training_blocks', 'phase', nullable=False)
    op.alter_column('training_blocks', 'phase_started_at', nullable=False)

    op.drop_constraint('ck_training_blocks_week_in_block_range', 'training_blocks', type_='check')
    op.drop_column('training_blocks', 'week_in_block')
    op.drop_column('training_blocks', 'anchor_week_start_date')


def downgrade() -> None:
    op.add_column('training_blocks', sa.Column('anchor_week_start_date', sa.Date(), nullable=True))
    op.add_column('training_blocks', sa.Column('week_in_block', sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE training_blocks
        SET week_in_block = CASE phase
            WHEN 'accumulation' THEN 1
            WHEN 'intensification' THEN 3
            WHEN 'deload' THEN 4
        END,
        anchor_week_start_date = phase_started_at
        """
    )

    op.alter_column('training_blocks', 'week_in_block', nullable=False)
    op.create_check_constraint(
        'ck_training_blocks_week_in_block_range',
        'training_blocks',
        'week_in_block >= 1 AND week_in_block <= 4',
    )

    op.drop_column('training_blocks', 'phase_started_at')
    op.drop_column('training_blocks', 'phase')
