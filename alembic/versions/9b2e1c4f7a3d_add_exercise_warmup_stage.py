"""add exercise warmup_stage

Revision ID: 9b2e1c4f7a3d
Revises: 65c9038fc907
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b2e1c4f7a3d'
down_revision: Union[str, None] = '65c9038fc907'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'warmup_stage',
            sa.Enum(
                'soft_tissue', 'raise', 'joint_mobility', 'activation', 'dynamic',
                name='warmup_stage', native_enum=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('exercises', 'warmup_stage')
