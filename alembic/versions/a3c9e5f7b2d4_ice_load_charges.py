"""ice load charges

Revision ID: a3c9e5f7b2d4
Revises: f2b8d4e6a1c3
Create Date: 2026-10-10 01:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a3c9e5f7b2d4'
down_revision: Union[str, None] = 'f2b8d4e6a1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ice_load_charges',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('training_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scale', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['training_session_id'], ['training_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('training_session_id'),
    )
    op.create_index(op.f('ix_ice_load_charges_user_id'), 'ice_load_charges', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ice_load_charges_user_id'), table_name='ice_load_charges')
    op.drop_table('ice_load_charges')
