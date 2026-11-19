"""Async database engine, session lifecycle, and dependency injection."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.database.base import Base

settings = get_settings()

# Engine creation
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    future=True,
)

# Async session factory
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional asynchronous database session for FastAPI endpoints."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables in the database if they do not exist."""
    import app.models  # noqa: F401 - ensure models are registered with Base metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
