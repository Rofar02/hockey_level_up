"""add team tables

Revision ID: 126b15a1dd07
Revises: a20782ce4f17
Create Date: 2026-08-11 16:54:43.231545

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '126b15a1dd07'
down_revision: Union[str, None] = 'a20782ce4f17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'teams',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('invite_code', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invite_code'),
    )
    op.create_index(op.f('ix_teams_owner_id'), 'teams', ['owner_id'], unique=False)
    op.create_index(op.f('ix_teams_invite_code'), 'teams', ['invite_code'], unique=False)

    op.create_table(
        'team_memberships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'user_id', name='uq_team_memberships_team_user'),
    )
    op.create_index(op.f('ix_team_memberships_team_id'), 'team_memberships', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_memberships_user_id'), 'team_memberships', ['user_id'], unique=False)

    op.create_table(
        'team_join_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('team_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'approved', 'rejected', name='team_join_request_status', native_enum=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_team_join_requests_team_id'), 'team_join_requests', ['team_id'], unique=False)
    op.create_index(op.f('ix_team_join_requests_user_id'), 'team_join_requests', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_team_join_requests_user_id'), table_name='team_join_requests')
    op.drop_index(op.f('ix_team_join_requests_team_id'), table_name='team_join_requests')
    op.drop_table('team_join_requests')

    op.drop_index(op.f('ix_team_memberships_user_id'), table_name='team_memberships')
    op.drop_index(op.f('ix_team_memberships_team_id'), table_name='team_memberships')
    op.drop_table('team_memberships')

    op.drop_index(op.f('ix_teams_invite_code'), table_name='teams')
    op.drop_index(op.f('ix_teams_owner_id'), table_name='teams')
    op.drop_table('teams')
