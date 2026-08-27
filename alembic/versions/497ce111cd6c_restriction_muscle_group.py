"""restriction muscle group

Revision ID: 497ce111cd6c
Revises: 75200a470e2e
Create Date: 2026-08-27 09:07:16.253403

RestrictionsPage's new body-avatar picker (2026-08-27) reports a
`muscle_group` directly instead of approximating a tapped body region into
a `movement_pattern` -- see UserTemporaryRestriction's own docstring.
`movement_pattern` becomes nullable since a row now carries exactly one of
the two (enforced by the new CHECK constraint), not always the former.

Autogenerate also picked up unrelated pre-existing drift (a stray
`auth_tokens` table and `teams.invite_code` index/constraint shape) --
hand-trimmed out of this file; not this migration's concern.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '497ce111cd6c'
down_revision: Union[str, None] = '75200a470e2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_temporary_restrictions',
        sa.Column(
            'muscle_group',
            sa.Enum(
                'quads', 'hamstrings', 'glutes', 'chest', 'back', 'shoulders', 'core',
                'calves', 'forearms', name='muscle_group', native_enum=False,
            ),
            nullable=True,
        ),
    )
    op.alter_column(
        'user_temporary_restrictions', 'movement_pattern',
        existing_type=sa.VARCHAR(length=17),
        nullable=True,
    )
    op.create_check_constraint(
        'ck_user_temporary_restrictions_exactly_one_target',
        'user_temporary_restrictions',
        '(movement_pattern IS NOT NULL) <> (muscle_group IS NOT NULL)',
    )


def downgrade() -> None:
    op.drop_constraint(
        'ck_user_temporary_restrictions_exactly_one_target',
        'user_temporary_restrictions',
        type_='check',
    )
    op.alter_column(
        'user_temporary_restrictions', 'movement_pattern',
        existing_type=sa.VARCHAR(length=17),
        nullable=False,
    )
    op.drop_column('user_temporary_restrictions', 'muscle_group')
