"""idempotency_keys -- offline workout queue (Б2, 2026-10-13)

Revision ID: b7d4e1f9a2c6
Revises: a9c3e5f7b2d4
Create Date: 2026-10-13 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7d4e1f9a2c6'
down_revision: Union[str, None] = 'a9c3e5f7b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('response_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_idempotency_keys_user_key'),
    )
    op.create_index('ix_idempotency_keys_created_at', 'idempotency_keys', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_idempotency_keys_created_at', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
