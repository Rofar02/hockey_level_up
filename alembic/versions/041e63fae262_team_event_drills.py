"""team event drills

Revision ID: 041e63fae262
Revises: 904bf6990e49
Create Date: 2026-09-24 10:51:14.442834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '041e63fae262'
down_revision: Union[str, None] = '904bf6990e49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('team_event_drills',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_team_event_drills_team_event_id'), 'team_event_drills', ['team_event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_event_drills_team_event_id'), table_name='team_event_drills')
    op.drop_table('team_event_drills')
