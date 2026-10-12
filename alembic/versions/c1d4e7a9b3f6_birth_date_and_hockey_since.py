"""users: birth date, the year hockey started, the last birthday greeted

Revision ID: c1d4e7a9b3f6
Revises: b7d3f9a5c2e4
Create Date: 2026-10-12 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1d4e7a9b3f6'
down_revision: Union[str, None] = 'b7d3f9a5c2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('hockey_since_year', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('last_birthday_greeted_year', sa.Integer(), nullable=True))
    # The years typed in were true when the profile was last saved.
    op.execute(
        "UPDATE users SET hockey_since_year = "
        "EXTRACT(YEAR FROM updated_at)::int - ROUND(years_of_experience)::int "
        "WHERE years_of_experience IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('users', 'last_birthday_greeted_year')
    op.drop_column('users', 'hockey_since_year')
    op.drop_column('users', 'birth_date')
