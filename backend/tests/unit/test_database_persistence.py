"""Unit tests for SQLite database persistence and RateRepository."""

from collections.abc import AsyncGenerator
from datetime import date
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
async def test_seed_and_ensure_currencies(in_memory_session: AsyncSession) -> None:
    """Test seeding and automatic insertion of currencies."""
    repo = RateRepository(in_memory_session)

    # Seed initial currencies
    await repo.seed_currencies({"EUR": "Euro", "USD": "US Dollar", "JPY": "Japanese Yen"})

    usd = await repo.ensure_currency_exists("USD")
    assert usd.code == "USD"
    assert usd.minor_units == 2

    jpy = await repo.ensure_currency_exists("JPY")
    assert jpy.code == "JPY"
    assert jpy.minor_units == 0  # ISO 4217 zero decimals lookup


@pytest.mark.asyncio
async def test_save_and_retrieve_historical_rates(in_memory_session: AsyncSession) -> None:
    """Test saving rates with Decimal precision and querying historical rates."""
    repo = RateRepository(in_memory_session)
    rate_date = date(2024, 1, 15)

    rates = {
        "USD": Decimal("1.0945000000"),
        "JPY": Decimal("158.4200000000"),
    }

    # Save rates (upsert)
    await repo.save_rates("EUR", rates, rate_date, provider="frankfurter")

    # Fetch all historical rates for EUR on that date
    results = await repo.get_historical_rates("EUR", rate_date)
    assert len(results) == 2
    res_dict = {r.target_currency: r.rate for r in results}

    assert res_dict["USD"] == Decimal("1.0945000000")
    assert res_dict["JPY"] == Decimal("158.4200000000")

    # Fetch with symbol filter
    usd_only = await repo.get_historical_rates("EUR", rate_date, symbols=["USD"])
    assert len(usd_only) == 1
    assert usd_only[0].target_currency == "USD"


@pytest.mark.asyncio
async def test_upsert_updates_existing_rate(in_memory_session: AsyncSession) -> None:
    """Test that duplicate insertion updates the rate cleanly without error."""
    repo = RateRepository(in_memory_session)
    rate_date = date(2024, 1, 15)

    # First insert
    await repo.save_rates("EUR", {"USD": Decimal("1.0900")}, rate_date, provider="frankfurter")

    # Second insert with updated rate
    await repo.save_rates("EUR", {"USD": Decimal("1.0950")}, rate_date, provider="frankfurter")

    results = await repo.get_historical_rates("EUR", rate_date, symbols=["USD"])
    assert len(results) == 1
    assert results[0].rate == Decimal("1.0950")


@pytest.mark.asyncio
async def test_get_timeseries_rates_chronological(in_memory_session: AsyncSession) -> None:
    """Test querying timeseries rates sorted by date."""
    repo = RateRepository(in_memory_session)

    # Insert non-chronologically
    await repo.save_rates("EUR", {"USD": Decimal("1.09")}, date(2024, 1, 3), provider="frankfurter")
    await repo.save_rates("EUR", {"USD": Decimal("1.07")}, date(2024, 1, 1), provider="frankfurter")
    await repo.save_rates("EUR", {"USD": Decimal("1.08")}, date(2024, 1, 2), provider="frankfurter")

    series = await repo.get_timeseries_rates("EUR", "USD", date(2024, 1, 1), date(2024, 1, 3))
    assert len(series) == 3
    dates = [r.rate_date for r in series]
    assert dates == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
