"""team event score

Revision ID: e1a7c3d5f9b2
Revises: d4f2b8a91c6e
Create Date: 2026-10-09 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1a7c3d5f9b2'
down_revision: Union[str, None] = 'd4f2b8a91c6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('team_events', sa.Column('our_score', sa.SmallInteger(), nullable=True))
    op.add_column('team_events', sa.Column('opponent_score', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('team_events', 'opponent_score')
    op.drop_column('team_events', 'our_score')
