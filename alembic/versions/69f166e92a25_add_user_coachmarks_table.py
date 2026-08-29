"""add user coachmarks table

Revision ID: 69f166e92a25
Revises: c7e4a1f9d2b3
Create Date: 2026-08-30 00:00:00.000000

Backs the reusable coachmark tour overlay (2026-08-30 discoverability pass)
-- replaces the earlier localStorage-only per-device "seen" flag with one
row per (user, hint_id) so a first-touch hint stays dismissed across
devices, matching how has_seen_onboarding_tour/has_seen_weight_hint already
persist per-user, just without needing a new users column per hint.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '69f166e92a25'
down_revision: Union[str, None] = 'c7e4a1f9d2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_coachmarks',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('hint_id', sa.String(length=100), nullable=False),
    sa.Column('seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'hint_id', name='uq_user_coachmarks_user_hint')
    )
    op.create_index(op.f('ix_user_coachmarks_user_id'), 'user_coachmarks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_coachmarks_user_id'), table_name='user_coachmarks')
    op.drop_table('user_coachmarks')
