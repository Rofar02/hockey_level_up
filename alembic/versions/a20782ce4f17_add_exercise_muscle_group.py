"""add exercise muscle_group

Revision ID: a20782ce4f17
Revises: 2b1b533c8ede
Create Date: 2026-08-11 15:55:30.547644

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a20782ce4f17'
down_revision: Union[str, None] = '2b1b533c8ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'muscle_group',
            sa.Enum('push', 'pull', 'legs', 'core', name='muscle_group', native_enum=False),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('exercises', 'muscle_group')
