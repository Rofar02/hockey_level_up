"""team event lineup groups and slots

Revision ID: 6e0a4014ca88
Revises: 488274884ebf
Create Date: 2026-09-24 11:05:33.059932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6e0a4014ca88'
down_revision: Union[str, None] = '488274884ebf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('team_event_lineup_groups',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=True),
    sa.Column('color', sa.String(length=20), nullable=True),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_team_event_lineup_groups_team_event_id'), 'team_event_lineup_groups', ['team_event_id'], unique=False)
    op.create_table('team_event_lineup_slots',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('group_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['group_id'], ['team_event_lineup_groups.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('team_event_id', 'user_id', name='uq_team_event_lineup_slots_event_user')
    )
    op.create_index(op.f('ix_team_event_lineup_slots_group_id'), 'team_event_lineup_slots', ['group_id'], unique=False)
    op.create_index(op.f('ix_team_event_lineup_slots_team_event_id'), 'team_event_lineup_slots', ['team_event_id'], unique=False)
    op.create_index(op.f('ix_team_event_lineup_slots_user_id'), 'team_event_lineup_slots', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_event_lineup_slots_user_id'), table_name='team_event_lineup_slots')
    op.drop_index(op.f('ix_team_event_lineup_slots_team_event_id'), table_name='team_event_lineup_slots')
    op.drop_index(op.f('ix_team_event_lineup_slots_group_id'), table_name='team_event_lineup_slots')
    op.drop_table('team_event_lineup_slots')
    op.drop_index(op.f('ix_team_event_lineup_groups_team_event_id'), table_name='team_event_lineup_groups')
    op.drop_table('team_event_lineup_groups')
