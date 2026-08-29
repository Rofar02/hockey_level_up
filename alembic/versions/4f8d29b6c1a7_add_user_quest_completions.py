"""add user quest completions

Revision ID: 4f8d29b6c1a7
Revises: 7c2b91a4e6f3
Create Date: 2026-08-30 00:00:00.000000

Backs the quest system (item 6, 2026-08-30 gamification pass) -- one row
per (user, quest, period) grant. See app.models.quest.UserQuestCompletion
for why `period_key` is a real date, not a string, and how one_time vs
weekly/long_term quests use it differently.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f8d29b6c1a7'
down_revision: Union[str, None] = '7c2b91a4e6f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_quest_completions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('quest_id', sa.String(length=50), nullable=False),
    sa.Column('period_key', sa.Date(), nullable=False),
    sa.Column('xp_awarded', sa.Integer(), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'quest_id', 'period_key', name='uq_user_quest_completions_period')
    )
    op.create_index(op.f('ix_user_quest_completions_user_id'), 'user_quest_completions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_quest_completions_user_id'), table_name='user_quest_completions')
    op.drop_table('user_quest_completions')
