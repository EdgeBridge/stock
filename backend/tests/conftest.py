"""Shared test fixtures."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.models import Base
from exchange.paper_adapter import PaperAdapter
from config import AppConfig


@pytest.fixture
def app_config():
    """Test configuration with defaults."""
    config = AppConfig()
    config.trading.mode = "paper"
    config.trading.initial_balance_usd = 10_000
    config.database.url = "sqlite+aiosqlite://"  # in-memory
    return config


@pytest_asyncio.fixture
async def db_engine():
    """In-memory SQLite engine for test isolation."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    """Isolated database session per test."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def paper_adapter():
    """Paper trading adapter for tests."""
    adapter = PaperAdapter(initial_balance_usd=10_000)
    await adapter.initialize()
    yield adapter
    await adapter.close()
