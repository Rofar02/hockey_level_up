"""team event attendance

Revision ID: 488274884ebf
Revises: 041e63fae262
Create Date: 2026-09-24 10:58:27.620847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '488274884ebf'
down_revision: Union[str, None] = '041e63fae262'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('team_event_attendances',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('going', 'not_going', name='team_event_attendance_status', native_enum=False), nullable=False),
    sa.Column('reason', sa.Enum('work', 'injury', 'study', 'other', name='team_event_absence_reason', native_enum=False), nullable=True),
    sa.Column('reason_note', sa.Text(), nullable=True),
    sa.Column('responded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('team_event_id', 'user_id', name='uq_team_event_attendances_event_user')
    )
    op.create_index(op.f('ix_team_event_attendances_team_event_id'), 'team_event_attendances', ['team_event_id'], unique=False)
    op.create_index(op.f('ix_team_event_attendances_user_id'), 'team_event_attendances', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_event_attendances_user_id'), table_name='team_event_attendances')
    op.drop_index(op.f('ix_team_event_attendances_team_event_id'), table_name='team_event_attendances')
    op.drop_table('team_event_attendances')
