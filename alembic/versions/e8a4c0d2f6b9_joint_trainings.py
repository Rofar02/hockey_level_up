"""joint trainings: guest teams on an event and on a recurring slot

Revision ID: e8a4c0d2f6b9
Revises: d7f3b9c1e5a8
Create Date: 2026-10-10 04:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8a4c0d2f6b9'
down_revision: Union[str, None] = 'd7f3b9c1e5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _guest_table(name: str, parent_column: str, parent_table: str, unique_name: str) -> None:
    op.create_table(
        name,
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(parent_column, postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('invited', 'accepted', 'declined', name='guest_team_status', native_enum=False, length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint([parent_column], [f'{parent_table}.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(parent_column, 'team_id', name=unique_name),
    )
    op.create_index(op.f(f'ix_{name}_{parent_column}'), name, [parent_column], unique=False)
    op.create_index(op.f(f'ix_{name}_team_id'), name, ['team_id'], unique=False)


def upgrade() -> None:
    _guest_table('team_event_guest_teams', 'team_event_id', 'team_events', 'uq_team_event_guest_teams_event_team')
    _guest_table(
        'team_ice_template_guest_teams', 'template_id', 'team_ice_schedule_templates',
        'uq_team_ice_template_guest_teams_template_team',
    )


def downgrade() -> None:
    for name, parent in (('team_ice_template_guest_teams', 'template_id'), ('team_event_guest_teams', 'team_event_id')):
        op.drop_index(op.f(f'ix_{name}_team_id'), table_name=name)
        op.drop_index(op.f(f'ix_{name}_{parent}'), table_name=name)
        op.drop_table(name)
