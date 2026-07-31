"""add user_skill_preferences table

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-31 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_skill_preferences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('skill_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'skill_id', name='uq_user_skill_preferences_user_skill'),
    )
    op.create_index(
        op.f('ix_user_skill_preferences_user_id'), 'user_skill_preferences', ['user_id'], unique=False
    )
    op.create_index(
        op.f('ix_user_skill_preferences_skill_id'), 'user_skill_preferences', ['skill_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_user_skill_preferences_skill_id'), table_name='user_skill_preferences')
    op.drop_index(op.f('ix_user_skill_preferences_user_id'), table_name='user_skill_preferences')
    op.drop_table('user_skill_preferences')
