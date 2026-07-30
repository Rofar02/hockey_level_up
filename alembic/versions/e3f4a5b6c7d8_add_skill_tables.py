"""add skill, skill_stat_weight, skill_tag, skill_milestone tables

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-30 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'skills',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'skill_stat_weights',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('skill_id', sa.UUID(), nullable=False),
        sa.Column(
            'stat_type',
            sa.Enum('strength', 'agility', 'intellect', 'endurance', name='target_stat', native_enum=False),
            nullable=False,
        ),
        sa.Column('weight', sa.Float(), nullable=False),
        sa.CheckConstraint(
            'weight >= 0.0 AND weight <= 1.0', name='ck_skill_stat_weights_weight_range'
        ),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('skill_id', 'stat_type', name='uq_skill_stat_weights_skill_stat'),
    )
    op.create_index(
        op.f('ix_skill_stat_weights_skill_id'), 'skill_stat_weights', ['skill_id'], unique=False
    )

    op.create_table(
        'skill_tags',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column('skill_id', sa.UUID(), nullable=False),
        sa.Column('transfer_note', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exercise_id', 'skill_id', name='uq_skill_tags_exercise_skill'),
    )
    op.create_index(op.f('ix_skill_tags_exercise_id'), 'skill_tags', ['exercise_id'], unique=False)
    op.create_index(op.f('ix_skill_tags_skill_id'), 'skill_tags', ['skill_id'], unique=False)

    op.create_table(
        'skill_milestones',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('skill_id', sa.UUID(), nullable=False),
        sa.Column('threshold', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.CheckConstraint(
            'threshold >= 0 AND threshold <= 100', name='ck_skill_milestones_threshold_range'
        ),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_skill_milestones_skill_id'), 'skill_milestones', ['skill_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_skill_milestones_skill_id'), table_name='skill_milestones')
    op.drop_table('skill_milestones')
    op.drop_index(op.f('ix_skill_tags_skill_id'), table_name='skill_tags')
    op.drop_index(op.f('ix_skill_tags_exercise_id'), table_name='skill_tags')
    op.drop_table('skill_tags')
    op.drop_index(op.f('ix_skill_stat_weights_skill_id'), table_name='skill_stat_weights')
    op.drop_table('skill_stat_weights')
    op.drop_table('skills')
