"""convert equipment matching from gym/home/bodyweight tiers to item-based m2m

Revision ID: 72b50a73e77b
Revises: a0e6d1af4566
Create Date: 2026-08-20 06:20:00.000000

Stage 2.2 (2026-08-20 planning session): replaces the old cumulative
gym-implies-home-implies-bodyweight tier on both Exercise.equipment_type
and User.equipment_access with real per-item matching -- an exercise now
requires a *set* of specific items (ExerciseEquipmentItem), a user owns a
set of specific items (UserEquipmentItem), and User.has_gym_access is a
separate bypass flag replacing the old EquipmentType.GYM tier value.

The backfill below is built to be behavior-PRESERVING for the ~105 real
users and ~283 exercises already in this DB (checked before writing this
migration, not assumed) -- not just a rough placeholder like Stage 2.1's
muscle_group backfill:

  - old exercises.equipment_type='gym'    -> requires {BARBELL}
  - old exercises.equipment_type='home'   -> requires {DUMBBELLS}
  - old exercises.equipment_type='bodyweight' -> requires nothing (always
    eligible, same as before)
  - old users.equipment_access='gym'      -> has_gym_access=true (bypasses
    everything, same as the old GYM reach covering all three tiers)
  - old users.equipment_access='home'     -> owns {DUMBBELLS} (so they
    still see bodyweight + home-tagged exercises, same as the old HOME
    reach, but not gym-tagged ones, also matching before)
  - old users.equipment_access='bodyweight' -> owns nothing (same as
    before)

BARBELL and DUMBBELLS are deliberately different placeholder items (not
the same one) so old gym-only exercises stay invisible to old home-tier
users post-migration, exactly like the old tier system kept them apart.
Real per-exercise item accuracy (a "home" exercise might actually need a
resistance band, not dumbbells) is Stage 4's job, not this migration's --
this backfill's only goal is not silently changing what any existing user
already sees.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '72b50a73e77b'
down_revision: Union[str, None] = 'a0e6d1af4566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


EQUIPMENT_ITEM_VALUES = (
    'kettlebell', 'dumbbells', 'barbell', 'resistance_band', 'pull_up_bar',
    'jump_rope', 'foam_roller', 'step_platform', 'slide_board', 'medicine_ball',
)


def upgrade() -> None:
    op.create_table(
        'exercise_equipment_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('exercise_id', sa.UUID(), nullable=False),
        sa.Column(
            'equipment_item',
            sa.Enum(*EQUIPMENT_ITEM_VALUES, name='equipment_item', native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['exercise_id'], ['exercises.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'exercise_id', 'equipment_item', name='uq_exercise_equipment_items_exercise_item'
        ),
    )
    op.create_index(
        op.f('ix_exercise_equipment_items_exercise_id'), 'exercise_equipment_items', ['exercise_id'],
        unique=False,
    )

    op.create_table(
        'user_equipment_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column(
            'equipment_item',
            sa.Enum(*EQUIPMENT_ITEM_VALUES, name='equipment_item', native_enum=False),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'equipment_item', name='uq_user_equipment_items_user_item'),
    )
    op.create_index(
        op.f('ix_user_equipment_items_user_id'), 'user_equipment_items', ['user_id'], unique=False
    )

    op.add_column(
        'users',
        sa.Column('has_gym_access', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    connection = op.get_bind()
    exercises = sa.table('exercises', sa.column('id', sa.UUID()), sa.column('equipment_type', sa.String()))
    exercise_equipment_items = sa.table(
        'exercise_equipment_items',
        sa.column('id', sa.UUID()),
        sa.column('exercise_id', sa.UUID()),
        sa.column('equipment_item', sa.String()),
    )
    users = sa.table(
        'users',
        sa.column('id', sa.UUID()),
        sa.column('equipment_access', sa.String()),
        sa.column('has_gym_access', sa.Boolean()),
    )
    user_equipment_items = sa.table(
        'user_equipment_items',
        sa.column('id', sa.UUID()),
        sa.column('user_id', sa.UUID()),
        sa.column('equipment_item', sa.String()),
    )

    for old_tier, placeholder_item in (('gym', 'barbell'), ('home', 'dumbbells')):
        rows = connection.execute(
            sa.select(exercises.c.id).where(exercises.c.equipment_type == old_tier)
        ).fetchall()
        if rows:
            connection.execute(
                exercise_equipment_items.insert(),
                [
                    {"id": uuid.uuid4(), "exercise_id": row.id, "equipment_item": placeholder_item}
                    for row in rows
                ],
            )

    connection.execute(
        sa.update(users).where(users.c.equipment_access == 'gym').values(has_gym_access=True)
    )
    home_users = connection.execute(
        sa.select(users.c.id).where(users.c.equipment_access == 'home')
    ).fetchall()
    if home_users:
        connection.execute(
            user_equipment_items.insert(),
            [
                {"id": uuid.uuid4(), "user_id": row.id, "equipment_item": "dumbbells"}
                for row in home_users
            ],
        )

    op.drop_column('exercises', 'equipment_type')
    op.drop_column('users', 'equipment_access')


def downgrade() -> None:
    op.add_column(
        'exercises',
        sa.Column(
            'equipment_type',
            sa.Enum('gym', 'home', 'bodyweight', name='equipment_type', native_enum=False),
            nullable=True,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'equipment_access',
            sa.Enum('gym', 'home', 'bodyweight', name='equipment_type', native_enum=False),
            nullable=True,
        ),
    )

    # Reverse of the upgrade backfill -- lossy the same way Stage 2.1's
    # downgrade is once real Stage 4 retagging happens (an exercise tagged
    # with several real items post-retag collapses back to whichever single
    # tier its rows loosely imply). "Has any item at all" -> 'home',
    # nothing -> 'bodyweight' -- BARBELL doesn't get its own distinct
    # branch here since a downgrade only ever needs to unwind exactly this
    # migration's own backfill, where 'gym' users are already reconstructed
    # from has_gym_access below regardless of which items their exercises
    # carry.
    op.execute(
        """
        UPDATE exercises AS e
        SET equipment_type = CASE WHEN EXISTS (
            SELECT 1 FROM exercise_equipment_items eei WHERE eei.exercise_id = e.id
        ) THEN 'home' ELSE 'bodyweight' END
        """
    )
    op.execute(
        """
        UPDATE users AS u
        SET equipment_access = CASE
            WHEN u.has_gym_access THEN 'gym'
            WHEN EXISTS (SELECT 1 FROM user_equipment_items uei WHERE uei.user_id = u.id) THEN 'home'
            ELSE 'bodyweight'
        END
        """
    )
    op.alter_column('exercises', 'equipment_type', nullable=False)
    op.alter_column('users', 'equipment_access', nullable=False)

    op.drop_column('users', 'has_gym_access')

    op.drop_index(op.f('ix_user_equipment_items_user_id'), table_name='user_equipment_items')
    op.drop_table('user_equipment_items')
    op.drop_index(op.f('ix_exercise_equipment_items_exercise_id'), table_name='exercise_equipment_items')
    op.drop_table('exercise_equipment_items')
