"""weekly coach tasks

Revision ID: c5e1a7b9d4f6
Revises: b4d0f6a8c3e5
Create Date: 2026-10-10 03:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5e1a7b9d4f6'
down_revision: Union[str, None] = 'b4d0f6a8c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'weekly_coach_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('task_type', sa.String(length=32), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('focus_id', sa.String(length=40), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'week_start', 'task_type', name='uq_weekly_coach_tasks_user_week_type'),
    )
    op.create_index(op.f('ix_weekly_coach_tasks_user_id'), 'weekly_coach_tasks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_weekly_coach_tasks_user_id'), table_name='weekly_coach_tasks')
    op.drop_table('weekly_coach_tasks')
