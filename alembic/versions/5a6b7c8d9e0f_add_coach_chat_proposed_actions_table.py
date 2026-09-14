"""add coach_chat_proposed_actions table

Revision ID: 5a6b7c8d9e0f
Revises: 1885fef8ec02
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5a6b7c8d9e0f'
down_revision: Union[str, None] = '1885fef8ec02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coach_chat_proposed_actions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'action_type',
            sa.Enum(
                'skill_priority_add',
                'set_tournament_date',
                'report_restriction',
                name='coach_action_type',
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'pending', 'confirmed', 'dismissed', 'expired',
                name='coach_action_status',
                native_enum=False,
            ),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['message_id'], ['coach_chat_messages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_coach_chat_proposed_actions_user_id'),
        'coach_chat_proposed_actions',
        ['user_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_coach_chat_proposed_actions_user_id'), table_name='coach_chat_proposed_actions'
    )
    op.drop_table('coach_chat_proposed_actions')
