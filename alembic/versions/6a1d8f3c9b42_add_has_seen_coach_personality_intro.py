"""add users.has_seen_coach_personality_intro

Revision ID: 6a1d8f3c9b42
Revises: 9b3f4c7d2e15
Create Date: 2026-08-30 00:00:00.000000

One-time explainer flag for the first /coach visit -- see
app.models.user.User's own comment on why coach_personality itself was
never actually explained to players before this.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a1d8f3c9b42'
down_revision: Union[str, None] = '9b3f4c7d2e15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column(
            'has_seen_coach_personality_intro',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'has_seen_coach_personality_intro')
