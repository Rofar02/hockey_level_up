"""add user_quest_completions.claimed_at

Revision ID: 9b3f4c7d2e15
Revises: 4f8d29b6c1a7
Create Date: 2026-08-30 00:00:00.000000

Splits "criteria satisfied" from "XP claimed" (2026-08-30 follow-up to the
quest system) -- see app.models.quest.UserQuestCompletion's docstring.
Existing rows all predate this change and were granted the moment they
were inserted under the old always-auto-grant design, so they backfill as
already claimed at their own completed_at rather than reappearing as
claimable.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3f4c7d2e15'
down_revision: Union[str, None] = '4f8d29b6c1a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_quest_completions',
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.execute('UPDATE user_quest_completions SET claimed_at = completed_at')


def downgrade() -> None:
    op.drop_column('user_quest_completions', 'claimed_at')
