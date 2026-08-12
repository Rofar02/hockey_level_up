"""add training parties (co-op training invites)

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'training_parties',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'completed', 'cancelled', name='training_party_status', native_enum=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_training_parties_created_by'), 'training_parties', ['created_by'], unique=False)
    op.create_index(op.f('ix_training_parties_target_date'), 'training_parties', ['target_date'], unique=False)

    op.create_table(
        'training_party_members',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('party_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('invited', 'joined', 'declined', name='training_party_member_status', native_enum=False),
            nullable=False,
        ),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['party_id'], ['training_parties.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('party_id', 'user_id', name='uq_training_party_members_party_user'),
    )
    op.create_index(op.f('ix_training_party_members_party_id'), 'training_party_members', ['party_id'], unique=False)
    op.create_index(op.f('ix_training_party_members_user_id'), 'training_party_members', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_training_party_members_user_id'), table_name='training_party_members')
    op.drop_index(op.f('ix_training_party_members_party_id'), table_name='training_party_members')
    op.drop_table('training_party_members')

    op.drop_index(op.f('ix_training_parties_target_date'), table_name='training_parties')
    op.drop_index(op.f('ix_training_parties_created_by'), table_name='training_parties')
    op.drop_table('training_parties')
