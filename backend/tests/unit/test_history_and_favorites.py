"""Unit tests for conversion history and favorites database operations."""

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.base import Base
from app.database.repository import RateRepository


@pytest.fixture
async def in_memory_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_conversion_history_lifecycle(in_memory_session: AsyncSession) -> None:
    """Test logging, paginating, and clearing conversion history."""
    repo = RateRepository(in_memory_session)
    session_id = "test_sess_001"

    # Add conversion entries
    await repo.add_conversion_history(
        session_id=session_id,
        from_currency="USD",
        to_currency="EUR",
        amount=Decimal("100.00"),
        converted_amount=Decimal("92.50"),
        rate=Decimal("0.9250000000"),
    )
    await repo.add_conversion_history(
        session_id=session_id,
        from_currency="EUR",
        to_currency="GBP",
        amount=Decimal("50.00"),
        converted_amount=Decimal("43.00"),
        rate=Decimal("0.8600000000"),
    )

    # Fetch history
    items, total = await repo.get_conversion_history(session_id=session_id, limit=10, offset=0)
    assert total == 2
    assert len(items) == 2
    # Verify latest is first
    assert items[0].from_currency == "EUR"
    assert items[0].to_currency == "GBP"
    assert items[1].from_currency == "USD"
    assert items[1].to_currency == "EUR"

    # Test pagination
    paged, total_paged = await repo.get_conversion_history(session_id=session_id, limit=1, offset=1)
    assert total_paged == 2
    assert len(paged) == 1
    assert paged[0].from_currency == "USD"

    # Clear history
    deleted = await repo.clear_conversion_history(session_id=session_id)
    assert deleted == 2

    # Verify cleared
    empty_items, empty_total = await repo.get_conversion_history(session_id=session_id)
    assert empty_total == 0
    assert len(empty_items) == 0


@pytest.mark.asyncio
async def test_favorites_lifecycle(in_memory_session: AsyncSession) -> None:
    """Test adding, listing, idempotency, and removing favorite currencies."""
    repo = RateRepository(in_memory_session)
    session_id = "test_fav_session"

    # Add favorites
    fav1 = await repo.add_favorite(session_id, "USD")
    fav2 = await repo.add_favorite(session_id, "JPY")
    assert fav1.currency_code == "USD"
    assert fav2.currency_code == "JPY"

    # Duplicate add is idempotent
    fav1_dup = await repo.add_favorite(session_id, "USD")
    assert fav1_dup.currency_code == "USD"

    # List favorites
    favs = await repo.get_favorites(session_id)
    assert len(favs) == 2
    codes = [f.code for f in favs]
    assert "USD" in codes
    assert "JPY" in codes

    # Remove favorite
    removed = await repo.remove_favorite(session_id, "USD")
    assert removed is True

    # Verify only JPY remains
    favs_after = await repo.get_favorites(session_id)
    assert len(favs_after) == 1
    assert favs_after[0].code == "JPY"

    # Removing non-existent returns False
    removed_non_existent = await repo.remove_favorite(session_id, "USD")
    assert removed_non_existent is False
