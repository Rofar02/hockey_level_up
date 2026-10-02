"""event retention indexes

Indexes for the daily purge in app/services/event_retention.py, which
deletes outbox_events by published_at and processed_events by
processed_at -- neither was indexed. Both tables are small on prod today
(hundreds of rows), so a plain CREATE INDEX is instant.

Revision ID: ac105a1a4ea6
Revises: 581e044f0a63
Create Date: 2026-10-02 06:01:43.568989

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac105a1a4ea6'
down_revision: Union[str, None] = '581e044f0a63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_outbox_events_published_at',
        'outbox_events',
        ['published_at'],
        postgresql_where=sa.text('published_at IS NOT NULL'),
    )
    op.create_index('ix_processed_events_processed_at', 'processed_events', ['processed_at'])


def downgrade() -> None:
    op.drop_index('ix_processed_events_processed_at', table_name='processed_events')
    op.drop_index('ix_outbox_events_published_at', table_name='outbox_events')
