"""add team logo_path

Revision ID: 7d856f2fcfe3
Revises: 126b15a1dd07
Create Date: 2026-08-11 17:14:21.992647

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d856f2fcfe3'
down_revision: Union[str, None] = '126b15a1dd07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('logo_path', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('teams', 'logo_path')
