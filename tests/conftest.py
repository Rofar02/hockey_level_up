"""Shared fixtures for tests that need a real database.

Runs against the local Postgres from docker-compose (same DATABASE_URL the
app itself uses). Each test gets its own outer transaction + savepoint via
`join_transaction_mode="create_savepoint"`, so code under test can freely
call `session.commit()` (savepoint-level) while the fixture rolls back the
outer transaction at teardown -- nothing written by a test is ever
persisted.
"""
from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(settings.database_url, future=True)
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        session_factory = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            class_=AsyncSession,
            join_transaction_mode="create_savepoint",
        )
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()
    await engine.dispose()
