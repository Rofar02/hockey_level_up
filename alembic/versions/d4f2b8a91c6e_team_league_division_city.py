"""team league, division and city

Revision ID: d4f2b8a91c6e
Revises: c3e8a1f5d2b7
Create Date: 2026-10-09 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4f2b8a91c6e'
down_revision: Union[str, None] = 'c3e8a1f5d2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column(
        'teams',
        sa.Column('league_code', sa.String(length=32), server_default='none', nullable=False),
    )
    op.add_column('teams', sa.Column('division_code', sa.String(length=32), nullable=True))
    op.add_column('teams', sa.Column('league_other_name', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('teams', 'league_other_name')
    op.drop_column('teams', 'division_code')
    op.drop_column('teams', 'league_code')
    op.drop_column('teams', 'city')
