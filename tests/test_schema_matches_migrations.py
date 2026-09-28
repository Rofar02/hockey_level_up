"""Models vs. the migrated schema -- the same comparison `alembic
--autogenerate` runs, as a test.

Guards the class of drift found 2026-09-28: the AuthToken model wasn't
imported in app/models/__init__.py (the only place alembic's env.py loads
models from), and Team.invite_code described a different unique shape than
the database had. Every autogenerate since 2026-08-27 proposed DROPPING
auth_tokens, and it was only ever hand-trimmed out of each new migration --
one careless autogenerate would have shipped that drop to prod.

Runs against the same local, fully-migrated Postgres as every other DB
test (see conftest.py), so a new model without its migration fails here
too.
"""
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

import app.models  # noqa: F401 -- same registration path alembic/env.py uses
from app.db.base import Base


@pytest.mark.asyncio
async def test_models_match_migrated_schema(db_session) -> None:
    connection = await db_session.connection()

    def _diff(sync_connection):
        return compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)

    diff = await connection.run_sync(_diff)

    assert diff == [], f"Models and migrated schema disagree: {diff}"
