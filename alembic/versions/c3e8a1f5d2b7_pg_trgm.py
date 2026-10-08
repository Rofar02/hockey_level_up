"""pg_trgm for the spelling-tolerant friend search

Revision ID: c3e8a1f5d2b7
Revises: 571d9162b2b6
Create Date: 2026-10-08 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3e8a1f5d2b7'
down_revision: Union[str, None] = '571d9162b2b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # similarity() for "похожие" in the name search (FriendDiscoveryService).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
