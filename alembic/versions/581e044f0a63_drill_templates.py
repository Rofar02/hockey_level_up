"""drill templates

A coach's own saved drills (title, description, minutes, rink scheme),
reusable across teams. New table only -- nothing existing is touched.

Revision ID: 581e044f0a63
Revises: 8c3f6b1d2a57
Create Date: 2026-09-26 05:04:46.585017

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '581e044f0a63'
down_revision: Union[str, None] = '8c3f6b1d2a57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('drill_templates',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), nullable=True),
    sa.Column('diagram', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_drill_templates_user_id'), 'drill_templates', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_drill_templates_user_id'), table_name='drill_templates')
    op.drop_table('drill_templates')
