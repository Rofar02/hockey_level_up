"""add user temporary restrictions

Revision ID: bd7f3a5067e9
Revises: e43f3d09a13a
Create Date: 2026-08-23 08:01:40.470115

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd7f3a5067e9'
down_revision: Union[str, None] = 'e43f3d09a13a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('user_temporary_restrictions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('movement_pattern', sa.Enum(
        'hip_hinge', 'squat', 'push', 'pull', 'rotation', 'ankle_mobility',
        'hip_mobility', 'shoulder_mobility', 'wrist_mobility', 'core',
        'locomotion', 'stick_handling', 'coordination',
        name='movement_pattern', native_enum=False,
    ), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.Date(), nullable=False),
    sa.Column('lifted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_temporary_restrictions_user_id'), 'user_temporary_restrictions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_temporary_restrictions_user_id'), table_name='user_temporary_restrictions')
    op.drop_table('user_temporary_restrictions')
