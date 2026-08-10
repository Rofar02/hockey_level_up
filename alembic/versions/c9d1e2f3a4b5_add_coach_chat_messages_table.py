"""add coach_chat_messages table

Revision ID: c9d1e2f3a4b5
Revises: d2ec9db23bcd
Create Date: 2026-08-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, None] = 'd2ec9db23bcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'coach_chat_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('user', 'assistant', name='coach_chat_role', native_enum=False),
            nullable=False,
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_coach_chat_messages_user_id'), 'coach_chat_messages', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_coach_chat_messages_created_at'), 'coach_chat_messages', ['created_at'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_coach_chat_messages_created_at'), table_name='coach_chat_messages')
    op.drop_index(op.f('ix_coach_chat_messages_user_id'), table_name='coach_chat_messages')
    op.drop_table('coach_chat_messages')
