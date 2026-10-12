"""users.token_version, refresh_sessions -- token revocation (step 8,
security, 2)

Revision ID: a9c3e5f7b2d4
Revises: f3b8d2a6c9e1
Create Date: 2026-10-12 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9c3e5f7b2d4'
down_revision: Union[str, None] = 'f3b8d2a6c9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'))
    op.create_table(
        'refresh_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('current_jti', sa.String(length=32), nullable=False),
        sa.Column('previous_jti', sa.String(length=32), nullable=True),
        sa.Column('rotated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_refresh_sessions_user_id'), 'refresh_sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_refresh_sessions_user_id'), table_name='refresh_sessions')
    op.drop_table('refresh_sessions')
    op.drop_column('users', 'token_version')
