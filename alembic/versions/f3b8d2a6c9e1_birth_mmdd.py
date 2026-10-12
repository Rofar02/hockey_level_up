"""users.birth_mmdd: the birth date's MMDD, generated and indexed

Revision ID: f3b8d2a6c9e1
Revises: e7a2c4f9d1b3
Create Date: 2026-10-12 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3b8d2a6c9e1'
down_revision: Union[str, None] = 'e7a2c4f9d1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The greeting loop looks today's birthdays up by it every 5 minutes
    # instead of a to_char() scan of every user.
    op.add_column(
        'users',
        sa.Column(
            'birth_mmdd',
            sa.SmallInteger(),
            sa.Computed(
                "(EXTRACT(month FROM birth_date) * 100 + EXTRACT(day FROM birth_date))::smallint", persisted=True
            ),
            nullable=True,
        ),
    )
    op.create_index('ix_users_birth_mmdd', 'users', ['birth_mmdd'])


def downgrade() -> None:
    op.drop_index('ix_users_birth_mmdd', table_name='users')
    op.drop_column('users', 'birth_mmdd')
