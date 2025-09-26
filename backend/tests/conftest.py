import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from booking.config import Settings
from booking.infra.db.session import make_engine
from booking.seed import seed
from booking.services.booking import BookingService
from booking.services.clock import FixedClock
from booking.services.payments import PaymentService

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://booking:booking@localhost:5447/booking_test"
)
# Monday 10:00 in Yerevan: the shop is open, part of the day is already in the past.
NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(database_url=TEST_DB_URL, env="test", bot_token=None, demo_mode=True)


async def _recreate_database() -> None:
    dsn = TEST_DB_URL.replace("+asyncpg", "")
    base, name = dsn.rsplit("/", 1)
    conn = await asyncpg.connect(f"{base}/postgres")
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return _settings()


@pytest.fixture(scope="session")
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    await _recreate_database()
    config = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DB_URL)
    # Alembic's env.py runs its own event loop, so it goes to a worker thread.
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = make_engine(TEST_DB_URL)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await seed(session, settings, now=NOW)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Every test runs inside a transaction that is rolled back afterwards."""
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def bookings(session: AsyncSession, clock: FixedClock, settings: Settings) -> BookingService:
    return BookingService(session, clock, PaymentService(session, clock, settings))
