"""user name search opt-in

Revision ID: b7d1e4f2a9c3
Revises: 6042510902ef
Create Date: 2026-10-08 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b7d1e4f2a9c3'
down_revision: Union[str, None] = '6042510902ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('name_search', sa.Boolean(), nullable=True))
    # The search filters on names; prefix lookups by lower(name).
    op.create_index('ix_users_lower_last_name', 'users', [sa.text('lower(last_name)')])
    op.create_index('ix_users_lower_first_name', 'users', [sa.text('lower(first_name)')])


def downgrade() -> None:
    op.drop_index('ix_users_lower_first_name', table_name='users')
    op.drop_index('ix_users_lower_last_name', table_name='users')
    op.drop_column('users', 'name_search')
