"""users: the local date the «день закрыт» praise was last sent

Revision ID: d2e5f8b1c4a7
Revises: c1d4e7a9b3f6
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd2e5f8b1c4a7'
down_revision: Union[str, None] = 'c1d4e7a9b3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('day_done_pushed_on', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'day_done_pushed_on')
