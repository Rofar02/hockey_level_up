"""day plan team event link

Revision ID: 3b7c9d2e1f40
Revises: 88854acf4813
Create Date: 2026-09-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3b7c9d2e1f40'
down_revision: Union[str, None] = '88854acf4813'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('day_plans', sa.Column('team_event_id', sa.UUID(), nullable=True))
    op.add_column(
        'day_plans',
        sa.Column(
            'replaced_session_type',
            sa.Enum('on_ice', 'off_ice', 'rest', 'game', name='day_session_type', native_enum=False),
            nullable=True,
        ),
    )
    op.create_index(op.f('ix_day_plans_team_event_id'), 'day_plans', ['team_event_id'], unique=False)
    op.create_foreign_key(
        'fk_day_plans_team_event_id_team_events',
        'day_plans',
        'team_events',
        ['team_event_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_day_plans_team_event_id_team_events', 'day_plans', type_='foreignkey')
    op.drop_index(op.f('ix_day_plans_team_event_id'), table_name='day_plans')
    op.drop_column('day_plans', 'replaced_session_type')
    op.drop_column('day_plans', 'team_event_id')
