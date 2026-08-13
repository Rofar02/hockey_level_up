"""Migration f5a6b7c8d9e0's data backfill: every user row that existed
before email_verified was added must end up True (see the model docstring
-- nobody already using the app should be made to verify retroactively),
while a user created *without* going through that backfill (i.e. anything
created afterward, the normal case) still defaults to False.

The DDL half (ADD COLUMN ... server_default=false()) is plain, unremarkable
alembic/SQLAlchemy behavior -- what's actually worth verifying is the data
migration's own UPDATE statement, so this runs that exact statement
(`UPDATE users SET email_verified = true`, copied from the migration) against
rows seeded to look like they'd just gotten the server_default (False),
scoped to this test's own savepoint via the db_session fixture so it can't
touch real data.
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.models.user import User


def _make_user(**overrides) -> User:
    unique = uuid.uuid4().hex[:8]
    defaults = dict(
        id=uuid.uuid4(),
        username=f"backfill_{unique}",
        email=f"backfill_{unique}@example.com",
        password_hash="irrelevant",
        email_verified=False,
    )
    defaults.update(overrides)
    return User(**defaults)


@pytest.mark.asyncio
async def test_migration_backfill_statement_verifies_pre_existing_users(db_session) -> None:
    pre_existing_users = [_make_user() for _ in range(3)]
    db_session.add_all(pre_existing_users)
    await db_session.flush()
    assert all(user.email_verified is False for user in pre_existing_users)

    # Exact statement from f5a6b7c8d9e0's upgrade().
    await db_session.execute(text("UPDATE users SET email_verified = true"))

    ids = [user.id for user in pre_existing_users]
    result = await db_session.execute(select(User.email_verified).where(User.id.in_(ids)))
    assert all(verified is True for verified in result.scalars().all())


@pytest.mark.asyncio
async def test_new_user_without_explicit_value_defaults_to_unverified(db_session) -> None:
    """Sanity check for the other half of the design: a row created the
    normal way (not touched by the one-time backfill) starts False, which is
    what makes the backfill meaningful in the first place."""
    user = User(
        id=uuid.uuid4(),
        username=f"fresh_{uuid.uuid4().hex[:8]}",
        email=f"fresh_{uuid.uuid4().hex[:8]}@example.com",
        password_hash="irrelevant",
    )
    db_session.add(user)
    await db_session.flush()

    assert user.email_verified is False
