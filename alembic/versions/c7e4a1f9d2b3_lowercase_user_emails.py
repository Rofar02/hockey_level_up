"""lowercase existing user emails

Revision ID: c7e4a1f9d2b3
Revises: a3f9c2e1b7d4
Create Date: 2026-08-29 00:00:00.000000

Login/registration now treat email case-insensitively (2026-08-29:
"Lexa95k@mail.ru и lexa95k@mail.ru разные почты" -- get_by_email/create both
normalize to lowercase from now on). Existing rows still have whatever case
they were originally typed with, so this backfills them to match. Guarded
with a pre-check: if lowercasing would collide two existing rows (two
different accounts that only differ by case), the migration aborts instead
of silently merging/dropping one -- that needs a human decision, not an
automatic one.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7e4a1f9d2b3'
down_revision: Union[str, None] = 'a3f9c2e1b7d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    collisions = connection.execute(
        sa.text(
            "SELECT lower(email) FROM users GROUP BY lower(email) HAVING count(*) > 1"
        )
    ).fetchall()
    if collisions:
        colliding = ", ".join(row[0] for row in collisions)
        raise RuntimeError(
            "Cannot lowercase user emails -- these would collide and need "
            f"manual resolution first: {colliding}"
        )
    connection.execute(sa.text("UPDATE users SET email = lower(email) WHERE email <> lower(email)"))


def downgrade() -> None:
    # Original casing isn't recoverable -- this migration is one-directional.
    pass
