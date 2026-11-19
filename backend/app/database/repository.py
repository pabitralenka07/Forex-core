"""Database repository for persisting and querying currencies and exchange rates."""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.currency_data import get_minor_units
from app.models.conversion_history import ConversionHistory
from app.models.currency import Currency
from app.models.exchange_rate import ExchangeRate
from app.models.favorite import FavoriteCurrency

logger = logging.getLogger("currency_converter.database")


class RateRepository:
    """Async repository for database persistence and querying of rates and currencies."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_currency_exists(self, code: str, name: str | None = None) -> Currency:
        """Ensure a currency record exists in the currencies table."""
        normalized_code = code.strip().upper()
        stmt = select(Currency).where(Currency.code == normalized_code)
        result = await self.session.execute(stmt)
        curr = result.scalar_one_or_none()

        if curr is None:
            curr = Currency(
                code=normalized_code,
                name=name or normalized_code,
                minor_units=get_minor_units(normalized_code),
                is_active=True,
            )
            self.session.add(curr)
            await self.session.flush()
        return curr

    async def seed_currencies(self, currencies: dict[str, str]) -> None:
        """Seed or update supported currencies table."""
        for code, name in currencies.items():
            normalized = code.strip().upper()
            stmt = select(Currency).where(Currency.code == normalized)
            result = await self.session.execute(stmt)
            curr = result.scalar_one_or_none()
            if curr is None:
                self.session.add(
                    Currency(
                        code=normalized,
                        name=name,
                        minor_units=get_minor_units(normalized),
                        is_active=True,
                    )
                )
            else:
                curr.name = name
                curr.minor_units = get_minor_units(normalized)
        await self.session.flush()

    async def save_rates(
        self,
        base: str,
        rates: dict[str, Decimal],
        rate_date: date,
        provider: str,
    ) -> None:
        """Persist exchange rates using SQLite upsert with full Decimal precision."""
        normalized_base = base.strip().upper()
        await self.ensure_currency_exists(normalized_base)

        now = datetime.now(UTC)

        for target, rate in rates.items():
            normalized_target = target.strip().upper()
            await self.ensure_currency_exists(normalized_target)

            stmt = sqlite_upsert(ExchangeRate).values(
                base_currency=normalized_base,
                target_currency=normalized_target,
                rate=rate,
                rate_date=rate_date,
                provider=provider,
                fetched_at=now,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["base_currency", "target_currency", "rate_date", "provider"],
                set_={
                    "rate": stmt.excluded.rate,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
            await self.session.execute(stmt)

        await self.session.flush()

    async def get_historical_rates(
        self,
        base: str,
        rate_date: date,
        symbols: list[str] | None = None,
    ) -> Sequence[ExchangeRate]:
        """Fetch persisted rates for a given base and date."""
        normalized_base = base.strip().upper()
        stmt = select(ExchangeRate).where(
            ExchangeRate.base_currency == normalized_base,
            ExchangeRate.rate_date == rate_date,
        )
        if symbols:
            norm_symbols = [s.strip().upper() for s in symbols]
            stmt = stmt.where(ExchangeRate.target_currency.in_(norm_symbols))

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_timeseries_rates(
        self,
        base: str,
        target: str,
        start_date: date,
        end_date: date,
    ) -> Sequence[ExchangeRate]:
        """Fetch persisted rates for a specific pair over a date range, sorted by date."""
        stmt = (
            select(ExchangeRate)
            .where(
                ExchangeRate.base_currency == base.strip().upper(),
                ExchangeRate.target_currency == target.strip().upper(),
                ExchangeRate.rate_date >= start_date,
                ExchangeRate.rate_date <= end_date,
            )
            .order_by(ExchangeRate.rate_date.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_conversion_history(
        self,
        session_id: str,
        from_currency: str,
        to_currency: str,
        amount: Decimal,
        converted_amount: Decimal,
        rate: Decimal,
    ) -> ConversionHistory:
        """Log a completed currency conversion."""
        await self.ensure_currency_exists(from_currency)
        await self.ensure_currency_exists(to_currency)

        record = ConversionHistory(
            session_id=session_id.strip(),
            from_currency=from_currency.strip().upper(),
            to_currency=to_currency.strip().upper(),
            amount=amount,
            converted_amount=converted_amount,
            rate=rate,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_conversion_history(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[ConversionHistory], int]:
        """Fetch paginated conversion history for a session along with total count."""
        clean_session = session_id.strip()
        count_stmt = select(func.count(ConversionHistory.id)).where(
            ConversionHistory.session_id == clean_session
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(ConversionHistory)
            .where(ConversionHistory.session_id == clean_session)
            .order_by(ConversionHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    async def clear_conversion_history(self, session_id: str) -> int:
        """Delete all conversion history entries for a given session ID."""
        stmt = delete(ConversionHistory).where(ConversionHistory.session_id == session_id.strip())
        res = await self.session.execute(stmt)
        await self.session.flush()
        rowcount = getattr(res, "rowcount", 0)
        return int(rowcount or 0)

    async def add_favorite(self, session_id: str, currency_code: str) -> FavoriteCurrency:
        """Add a currency to user's favorites list idempotently."""
        normalized = currency_code.strip().upper()
        await self.ensure_currency_exists(normalized)
        clean_session = session_id.strip()

        stmt = select(FavoriteCurrency).where(
            FavoriteCurrency.session_id == clean_session,
            FavoriteCurrency.currency_code == normalized,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        fav = FavoriteCurrency(session_id=clean_session, currency_code=normalized)
        self.session.add(fav)
        await self.session.flush()
        return fav

    async def get_favorites(self, session_id: str) -> Sequence[Currency]:
        """Fetch list of user's favorite currencies ordered by added time."""
        stmt = (
            select(Currency)
            .join(FavoriteCurrency, FavoriteCurrency.currency_code == Currency.code)
            .where(FavoriteCurrency.session_id == session_id.strip())
            .order_by(FavoriteCurrency.created_at.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()

    async def remove_favorite(self, session_id: str, currency_code: str) -> bool:
        """Remove a currency from user's favorites list."""
        stmt = delete(FavoriteCurrency).where(
            FavoriteCurrency.session_id == session_id.strip(),
            FavoriteCurrency.currency_code == currency_code.strip().upper(),
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        rowcount = getattr(res, "rowcount", 0)
        return bool(rowcount and rowcount > 0)
