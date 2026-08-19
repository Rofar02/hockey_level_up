"""clamp user_stats to the new 100 hard cap

Revision ID: a3c7e9d1f204
Revises: 9b2e1c4f7a3d
Create Date: 2026-08-19 00:00:00.000000

Data-only migration: stat_consumer's diminishing-returns curve used to
asymptote toward 120 (DIMINISHING_CAP); a handful of long-running synthetic
users from the overnight simulation grew past the new 100 hard cap before
this cap existed (2026-08-19: "максимум характеристик не больше 100"). The
new upsert already clamps every future gain via SQL LEAST(...), this just
backfills the rows that got there under the old formula.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3c7e9d1f204'
down_revision: Union[str, None] = '9b2e1c4f7a3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE user_stats SET current_value = 100 WHERE current_value > 100")


def downgrade() -> None:
    # Original values above 100 aren't recoverable -- this is a one-way
    # clamp, matching the new hard cap being a real product rule going
    # forward, not a transient migration artifact.
    pass
