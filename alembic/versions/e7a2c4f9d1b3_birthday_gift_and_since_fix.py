"""users: the birthday gift year, the team birthdays switch; the estimated
start year fixed (review 12.10, 2-3, 5)

Revision ID: e7a2c4f9d1b3
Revises: d2e5f8b1c4a7
Create Date: 2026-10-12 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e7a2c4f9d1b3'
down_revision: Union[str, None] = 'd2e5f8b1c4a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('birthday_gift_year', sa.Integer(), nullable=True))
    op.add_column(
        'users', sa.Column('team_birthdays', sa.Boolean(), nullable=False, server_default=sa.true())
    )
    # c1d4e7a9b3f6 dated the typed-in years by updated_at, which moves on any
    # profile save; the years were typed at registration. Only rows still
    # holding that estimate are redone.
    op.execute(
        "UPDATE users SET hockey_since_year = "
        "EXTRACT(YEAR FROM created_at)::int - ROUND(years_of_experience)::int "
        "WHERE years_of_experience IS NOT NULL "
        "AND hockey_since_year = EXTRACT(YEAR FROM updated_at)::int - ROUND(years_of_experience)::int"
    )
    # An estimate before the player was born (by the birth date, else the
    # earliest birth year the old age allows) or before 1930 is no year at
    # all -- the typed-in years stay the fallback.
    op.execute(
        "UPDATE users SET hockey_since_year = NULL "
        "WHERE hockey_since_year IS NOT NULL AND ("
        "hockey_since_year < 1930 "
        "OR (birth_date IS NOT NULL AND hockey_since_year < EXTRACT(YEAR FROM birth_date)::int) "
        "OR (birth_date IS NULL AND age IS NOT NULL "
        "AND hockey_since_year < EXTRACT(YEAR FROM created_at)::int - age - 1))"
    )


def downgrade() -> None:
    op.drop_column('users', 'team_birthdays')
    op.drop_column('users', 'birthday_gift_year')
