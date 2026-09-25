"""team event diary entries

Revision ID: 88854acf4813
Revises: 6e0a4014ca88
Create Date: 2026-09-24 11:25:04.765715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '88854acf4813'
down_revision: Union[str, None] = '6e0a4014ca88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('team_event_diary_entries',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('team_event_id', 'user_id', name='uq_team_event_diary_entries_event_user')
    )
    op.create_index(op.f('ix_team_event_diary_entries_team_event_id'), 'team_event_diary_entries', ['team_event_id'], unique=False)
    op.create_index(op.f('ix_team_event_diary_entries_user_id'), 'team_event_diary_entries', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_event_diary_entries_user_id'), table_name='team_event_diary_entries')
    op.drop_index(op.f('ix_team_event_diary_entries_team_event_id'), table_name='team_event_diary_entries')
    op.drop_table('team_event_diary_entries')
