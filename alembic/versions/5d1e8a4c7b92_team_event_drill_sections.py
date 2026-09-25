"""team event drill sections + drill duration

Revision ID: 5d1e8a4c7b92
Revises: 3b7c9d2e1f40
Create Date: 2026-09-25 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5d1e8a4c7b92'
down_revision: Union[str, None] = '3b7c9d2e1f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('team_event_drill_sections',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('team_event_id', sa.UUID(), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['team_event_id'], ['team_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_team_event_drill_sections_team_event_id'), 'team_event_drill_sections', ['team_event_id'], unique=False)

    op.add_column('team_event_drills', sa.Column('section_id', sa.UUID(), nullable=True))
    op.add_column('team_event_drills', sa.Column('duration_minutes', sa.Integer(), nullable=True))

    # Every event that already has drills gets one "Основная часть" section
    # holding all of them, in their existing order.
    op.execute(
        """
        INSERT INTO team_event_drill_sections (id, team_event_id, "order", name)
        SELECT gen_random_uuid(), team_event_id, 0, 'Основная часть'
        FROM team_event_drills
        GROUP BY team_event_id
        """
    )
    op.execute(
        """
        UPDATE team_event_drills AS d
        SET section_id = s.id
        FROM team_event_drill_sections AS s
        WHERE s.team_event_id = d.team_event_id
        """
    )

    op.alter_column('team_event_drills', 'section_id', nullable=False)
    op.create_index(op.f('ix_team_event_drills_section_id'), 'team_event_drills', ['section_id'], unique=False)
    op.create_foreign_key(
        'fk_team_event_drills_section_id_team_event_drill_sections',
        'team_event_drills',
        'team_event_drill_sections',
        ['section_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_team_event_drills_section_id_team_event_drill_sections', 'team_event_drills', type_='foreignkey'
    )
    op.drop_index(op.f('ix_team_event_drills_section_id'), table_name='team_event_drills')
    op.drop_column('team_event_drills', 'duration_minutes')
    op.drop_column('team_event_drills', 'section_id')
    op.drop_index(op.f('ix_team_event_drill_sections_team_event_id'), table_name='team_event_drill_sections')
    op.drop_table('team_event_drill_sections')
