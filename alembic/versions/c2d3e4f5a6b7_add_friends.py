"""add friends: friend_requests table and User.friend_code backfill

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-12 00:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('friend_code', sa.String(length=16), nullable=True))
    op.create_index(op.f('ix_users_friend_code'), 'users', ['friend_code'], unique=True)

    # Data migration: every user who already existed before this column did
    # still needs a real code, not just new signups going forward
    # (AuthService.register generates one at registration time from here on
    # -- see User.friend_code). Same secrets.token_hex(4).upper() shape as
    # TeamService._generate_invite_code; used_codes guards against a
    # same-run collision (astronomically unlikely at this scale, but cheap
    # to rule out rather than trust).
    connection = op.get_bind()
    users_table = sa.table('users', sa.column('id', sa.UUID()), sa.column('friend_code', sa.String()))
    user_ids = [row[0] for row in connection.execute(sa.text('SELECT id FROM users')).fetchall()]

    used_codes: set[str] = set()
    for user_id in user_ids:
        code = secrets.token_hex(4).upper()
        while code in used_codes:
            code = secrets.token_hex(4).upper()
        used_codes.add(code)
        connection.execute(
            users_table.update().where(users_table.c.id == user_id).values(friend_code=code)
        )

    op.create_table(
        'friend_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('sender_id', sa.UUID(), nullable=False),
        sa.Column('receiver_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'accepted', 'declined', name='friend_request_status', native_enum=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['receiver_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sender_id', 'receiver_id', name='uq_friend_requests_sender_receiver'),
    )
    op.create_index(op.f('ix_friend_requests_sender_id'), 'friend_requests', ['sender_id'], unique=False)
    op.create_index(op.f('ix_friend_requests_receiver_id'), 'friend_requests', ['receiver_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_friend_requests_receiver_id'), table_name='friend_requests')
    op.drop_index(op.f('ix_friend_requests_sender_id'), table_name='friend_requests')
    op.drop_table('friend_requests')

    op.drop_index(op.f('ix_users_friend_code'), table_name='users')
    op.drop_column('users', 'friend_code')
