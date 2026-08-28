"""add session_blocks.skipped_at

Revision ID: a3f9c2e1b7d4
Revises: 497ce111cd6c
Create Date: 2026-08-28 00:00:00.000000

Warmup/cooldown exercises can now be skipped instead of completed (media-
player redesign, 2026-08-28) -- a sibling timestamp to completed_at, same
nullable-column + partial-index shape as
ix_session_blocks_completed_at_not_null.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f9c2e1b7d4'
down_revision: Union[str, None] = '497ce111cd6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'session_blocks',
        sa.Column('skipped_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_session_blocks_skipped_at_not_null',
        'session_blocks',
        ['skipped_at'],
        unique=False,
        postgresql_where=sa.text('skipped_at IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('ix_session_blocks_skipped_at_not_null', table_name='session_blocks')
    op.drop_column('session_blocks', 'skipped_at')
