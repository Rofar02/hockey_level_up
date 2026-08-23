"""add training diary entries

Revision ID: e43f3d09a13a
Revises: b30cb6c0e2af
Create Date: 2026-08-23 07:11:02.476066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e43f3d09a13a'
down_revision: Union[str, None] = 'b30cb6c0e2af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('training_diary_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('training_session_id', sa.UUID(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['training_session_id'], ['training_sessions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('training_session_id', name='uq_training_diary_entries_session')
    )
    op.create_index(op.f('ix_training_diary_entries_training_session_id'), 'training_diary_entries', ['training_session_id'], unique=False)
    op.create_index(op.f('ix_training_diary_entries_user_id'), 'training_diary_entries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_training_diary_entries_user_id'), table_name='training_diary_entries')
    op.drop_index(op.f('ix_training_diary_entries_training_session_id'), table_name='training_diary_entries')
    op.drop_table('training_diary_entries')
