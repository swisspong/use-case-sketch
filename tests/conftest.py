"""Test DB: real Postgres. TEST_DATABASE_URL if set, otherwise a testcontainer.

- schema created once per test session
- every test runs inside a transaction that is rolled back (fast, isolated)
- handler code that calls session.begin()/commit works via SAVEPOINTs
"""
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401  (registers all tables)
from app.shared.db import Base


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        yield url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def engine(database_url):
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    """Level-3 tests: a session whose work is rolled back after the test."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            await s.close()
            await trans.rollback()


@pytest.fixture
def uow(session):
    """For handlers that take a unit-of-work factory (multi-transaction flows).
    `uow(ThingRepo)` mirrors `uow_factory(res, ThingRepo)`; each block is a savepoint."""
    def make(make_repo):
        @asynccontextmanager
        async def _uow():
            async with session.begin_nested():
                yield make_repo(session)
        return _uow
    return make


@pytest_asyncio.fixture
async def client(session) -> AsyncIterator[AsyncClient]:
    """Endpoint tests: real app, test session, override only what you must."""
    from app.main import create_app
    from app.shared.deps import get_session

    app = create_app()

    async def _session():
        yield session

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.app = app  # tests can add more dependency_overrides
        yield c
