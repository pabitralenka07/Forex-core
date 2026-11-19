"""Rate service coordinating exchange rate providers, caching, resilience, and conversion."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.config import get_settings
from app.core.circuit_breaker import CircuitBreaker
from app.core.currency_data import get_minor_units
from app.core.decimal_utils import (
    calculate_inverse_rate,
    parse_decimal_amount,
    validate_currency_code,
)
from app.core.exceptions import (
    CurrencyConverterException,
    InvalidAmountError,
    ProviderUnavailableError,
    RateNotFoundError,
)
from app.core.validators import validate_date_range, validate_iso_date
from app.database.repository import RateRepository
from app.providers.base import RateProvider, RateResult, TimeseriesResult
from app.providers.exchangerate_api import ExchangeRateApiProvider
from app.providers.frankfurter import FrankfurterProvider
from app.schemas.convert import BatchConvertRequest
from app.schemas.currencies import CurrencyItem
from app.schemas.historical import (
    HistoricalRatesResponseData,
    TimeseriesResponseData,
)
from app.services.cache_service import InMemoryTTLCache, get_cache_service
from app.services.converter import ConversionEngine, ConversionResult, ReverseConversionResult
from app.services.timeseries_stats import compute_timeseries_statistics

logger = logging.getLogger(__name__)


class RateService:
    """Service layer coordinating rate retrieval, caching, failover, and conversion math."""

    def __init__(
        self,
        primary_provider: RateProvider | None = None,
        secondary_provider: RateProvider | None = None,
        cache: InMemoryTTLCache | None = None,
    ) -> None:
        self.settings = get_settings()
        self.primary_provider = primary_provider or FrankfurterProvider()
        self.secondary_provider = secondary_provider or ExchangeRateApiProvider()
        self.cache = cache or get_cache_service()

        # Per-provider circuit breakers
        self.primary_breaker = CircuitBreaker(
            name=self.primary_provider.name,
            failure_threshold=self.settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=self.settings.circuit_breaker_recovery_timeout_seconds,
        )
        self.secondary_breaker = CircuitBreaker(
            name=self.secondary_provider.name,
            failure_threshold=self.settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=self.settings.circuit_breaker_recovery_timeout_seconds,
        )

    async def list_currencies(self) -> list[CurrencyItem]:
        """Fetch all supported currencies enriched with ISO 4217 minor unit metadata."""
        cache_key = "currencies:list"
        cached_val, is_stale, _ = await self.cache.get(cache_key, allow_stale=False)
        if cached_val is not None and isinstance(cached_val, list):
            return cached_val

        async def _fetch() -> list[CurrencyItem]:
            try:
                raw_dict = await self.primary_provider.list_currencies()
            except Exception as exc:
                logger.warning("Primary provider list_currencies failed: %s; trying secondary", exc)
                raw_dict = await self.secondary_provider.list_currencies()

            items: list[CurrencyItem] = []
            for code, name in sorted(raw_dict.items()):
                try:
                    norm_code = validate_currency_code(code)
                    items.append(
                        CurrencyItem(
                            code=norm_code,
                            name=name,
                            minor_units=get_minor_units(norm_code),
                        )
                    )
                except Exception:
                    continue
            await self.cache.set(cache_key, items, ttl_seconds=86400.0)  # Currencies valid 24h
            return items

        return await self.cache.coalesce(cache_key, _fetch)

    async def get_currency(self, code: str) -> CurrencyItem:
        """Fetch metadata for a single currency code."""
        norm_code = validate_currency_code(code)
        currencies = await self.list_currencies()
        for item in currencies:
            if item.code == norm_code:
                return item

        raise RateNotFoundError(
            f"Currency '{norm_code}' is not supported.",
            base=norm_code,
        )

    def _check_large_movements(
        self,
        base: str,
        new_rates: dict[str, Decimal],
        last_rates: dict[str, Decimal],
    ) -> None:
        """Log audit warnings for unusual market movements without silently rejecting them."""
        threshold = Decimal(str(self.settings.large_movement_threshold_pct)) / Decimal("100")
        for sym, new_val in new_rates.items():
            if sym in last_rates:
                old_val = last_rates[sym]
                if old_val > Decimal("0"):
                    diff = abs(new_val - old_val) / old_val
                    if diff > threshold:
                        pct = diff * Decimal("100")
                        logger.warning(
                            "UNUSUAL MOVEMENT DETECTED: Pair %s/%s moved %.2f%% "
                            "(old: %s, new: %s, threshold: %.1f%%)",
                            base,
                            sym,
                            float(pct),
                            old_val,
                            new_val,
                            float(self.settings.large_movement_threshold_pct),
                        )

    async def _fetch_from_provider_with_retry(
        self,
        provider: RateProvider,
        base: str,
    ) -> RateResult:
        """Execute provider get_latest wrapped with exponential backoff and jitter."""

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.settings.retry_max_attempts),
            wait=wait_exponential_jitter(
                multiplier=self.settings.retry_min_wait_seconds,
                max=self.settings.retry_max_wait_seconds,
            ),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, ProviderUnavailableError)
            ),
        )
        async def _do_fetch() -> RateResult:
            return await provider.get_latest(base=base)

        return await _do_fetch()

    async def _fetch_rates_with_failover(self, base: str) -> RateResult:
        """Execute primary -> secondary -> last-known-good stale serving pipeline."""
        cache_key = f"rates:{base}"
        last_known_entry, _, _ = await self.cache.get(cache_key, allow_stale=True)
        last_known_rates = (
            last_known_entry.rates if isinstance(last_known_entry, RateResult) else {}
        )

        # 1. Attempt Primary Provider
        if await self.primary_breaker.allow_request():
            try:
                result = await self._fetch_from_provider_with_retry(self.primary_provider, base)
                await self.primary_breaker.record_success()
                if last_known_rates:
                    self._check_large_movements(base, result.rates, last_known_rates)
                await self.cache.set(cache_key, result)
                return result
            except Exception as exc:
                await self.primary_breaker.record_failure()
                logger.warning(
                    "Primary provider '%s' failed for base '%s': %s. Failing over to secondary.",
                    self.primary_provider.name,
                    base,
                    exc,
                )
        else:
            logger.warning(
                "Circuit breaker for '%s' is OPEN. Bypassing to secondary.",
                self.primary_provider.name,
            )

        # 2. Attempt Secondary Provider
        if await self.secondary_breaker.allow_request():
            try:
                result = await self._fetch_from_provider_with_retry(self.secondary_provider, base)
                await self.secondary_breaker.record_success()
                if last_known_rates:
                    self._check_large_movements(base, result.rates, last_known_rates)
                await self.cache.set(cache_key, result)
                return result
            except Exception as exc:
                await self.secondary_breaker.record_failure()
                logger.warning(
                    "Secondary provider '%s' failed for base '%s': %s.",
                    self.secondary_provider.name,
                    base,
                    exc,
                )
        else:
            logger.warning(
                "Circuit breaker for '%s' is OPEN.",
                self.secondary_provider.name,
            )

        # 3. Last-Known-Good Stale Serving (Rule 8)
        cached_result, is_stale, age_sec = await self.cache.get(cache_key, allow_stale=True)
        if cached_result is not None and isinstance(cached_result, RateResult):
            logger.warning(
                "All providers failed for base '%s'. Serving stale rate (age: %ds)",
                base,
                age_sec,
            )
            return cached_result.model_copy(update={"stale": True, "age_seconds": age_sec})

        # 4. Total Outage
        raise ProviderUnavailableError(
            f"All exchange rate providers are unavailable for base '{base}' "
            "and no cached rate is available.",
            provider="all",
        )

    async def get_rates(
        self,
        base: str,
        symbols: list[str] | None = None,
        session: AsyncSession | None = None,
    ) -> RateResult:
        """Fetch latest exchange rates with caching, coalescing, and DB persistence."""
        norm_base = validate_currency_code(base)
        norm_symbols = [validate_currency_code(s) for s in symbols] if symbols else None
        cache_key = f"rates:{norm_base}"

        # Check hot cache
        cached_val, is_stale, age_sec = await self.cache.get(cache_key, allow_stale=False)
        if cached_val is not None and isinstance(cached_val, RateResult):
            rates = cached_val.rates
            if norm_symbols:
                rates = {k: v for k, v in rates.items() if k in norm_symbols}
            return cached_val.model_copy(update={"rates": rates, "age_seconds": age_sec})

        # Request coalescing for in-flight requests
        rate_result = await self.cache.coalesce(
            cache_key,
            lambda: self._fetch_rates_with_failover(norm_base),
        )

        # If DB session provided, persist rates to SQLite
        if session:
            try:
                repo = RateRepository(session)
                rate_date_obj = datetime.strptime(rate_result.rate_date, "%Y-%m-%d").date()
                await repo.save_rates(
                    base=norm_base,
                    rates=rate_result.rates,
                    rate_date=rate_date_obj,
                    provider=rate_result.provider,
                )
            except Exception as exc:
                logger.warning("Failed to persist latest rates to DB: %s", exc)

        rates = rate_result.rates
        if norm_symbols:
            rates = {k: v for k, v in rates.items() if k in norm_symbols}
        return rate_result.model_copy(update={"rates": rates})

    async def get_pair_rate(
        self,
        base: str,
        target: str,
    ) -> tuple[Decimal, Decimal, RateResult]:
        """Fetch exchange rate and inverse rate for a currency pair."""
        norm_base = validate_currency_code(base)
        norm_target = validate_currency_code(target)

        # Same currency USD -> USD
        if norm_base == norm_target:
            latest = await self.get_rates(base=norm_base)
            return Decimal("1"), Decimal("1"), latest

        latest = await self.get_rates(base=norm_base)
        if norm_target in latest.rates:
            rate = latest.rates[norm_target]
            inverse = calculate_inverse_rate(rate)
            return rate, inverse, latest

        # Fall back to synthetic cross-rate via configured pivot
        pivot = self.settings.pivot_currency
        pivot_result = await self.get_rates(base=pivot)
        cross_rate = ConversionEngine.compute_cross_rate(
            norm_base,
            norm_target,
            pivot,
            pivot_result.rates,
        )
        inverse_cross = calculate_inverse_rate(cross_rate)
        return cross_rate, inverse_cross, pivot_result

    async def convert(
        self,
        from_currency: str,
        to_currency: str,
        amount_str: str,
    ) -> tuple[ConversionResult, RateResult]:
        """Execute forward conversion with full resilience pipeline."""
        norm_from = validate_currency_code(from_currency)
        norm_to = validate_currency_code(to_currency)
        amount = parse_decimal_amount(amount_str)

        rate, _, rate_meta = await self.get_pair_rate(norm_from, norm_to)
        result = ConversionEngine.convert(
            amount=amount,
            from_currency=norm_from,
            to_currency=norm_to,
            rate=rate,
        )
        return result, rate_meta

    async def reverse_convert(
        self,
        from_currency: str,
        to_currency: str,
        target_amount_str: str,
    ) -> tuple[ReverseConversionResult, RateResult]:
        """Execute reverse conversion with full resilience pipeline."""
        norm_from = validate_currency_code(from_currency)
        norm_to = validate_currency_code(to_currency)
        target_amount = parse_decimal_amount(target_amount_str)

        rate, _, rate_meta = await self.get_pair_rate(norm_from, norm_to)
        result = ConversionEngine.reverse_convert(
            target_amount=target_amount,
            from_currency=norm_from,
            to_currency=norm_to,
            rate=rate,
        )
        return result, rate_meta

    async def batch_convert(
        self,
        request: BatchConvertRequest,
    ) -> tuple[list[ConversionResult], RateResult]:
        """Execute batch conversion."""
        results: list[ConversionResult] = []

        if request.base and request.amount and request.targets:
            norm_base = validate_currency_code(request.base)
            amount = parse_decimal_amount(request.amount)
            norm_targets = [validate_currency_code(t) for t in request.targets]

            rate_result = await self.get_rates(base=norm_base)

            for target in norm_targets:
                if target == norm_base:
                    rate = Decimal("1")
                elif target in rate_result.rates:
                    rate = rate_result.rates[target]
                else:
                    pivot = self.settings.pivot_currency
                    pivot_res = await self.get_rates(base=pivot)
                    rate = ConversionEngine.compute_cross_rate(
                        norm_base, target, pivot, pivot_res.rates
                    )

                res = ConversionEngine.convert(
                    amount=amount,
                    from_currency=norm_base,
                    to_currency=target,
                    rate=rate,
                )
                results.append(res)

            return results, rate_result

        if request.conversions:
            last_rate_result: RateResult | None = None
            for item in request.conversions:
                conv, rate_res = await self.convert(
                    from_currency=item.from_currency,
                    to_currency=item.to_currency,
                    amount_str=item.amount,
                )
                results.append(conv)
                last_rate_result = rate_res

            if last_rate_result is None:
                raise InvalidAmountError("Conversions list cannot be empty.")

            return results, last_rate_result

        raise CurrencyConverterException(
            message=(
                "Batch request must provide either (base, amount, targets) or (conversions list)."
            ),
            code="VALIDATION_ERROR",
            status_code=400,
        )

    async def get_historical(
        self,
        date_str: str,
        base: str = "EUR",
        symbols: list[str] | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[HistoricalRatesResponseData, RateResult]:
        """Fetch historical rates for date, checking DB cache and saving upstream rates."""
        parsed_date = validate_iso_date(date_str)
        norm_base = validate_currency_code(base)
        norm_symbols = [validate_currency_code(s) for s in symbols] if symbols else None

        # Check DB cache first if session is available
        if session:
            repo = RateRepository(session)
            db_rates = await repo.get_historical_rates(norm_base, parsed_date, norm_symbols)
            if db_rates and (not norm_symbols or len(db_rates) == len(norm_symbols)):
                rates_dict = {r.target_currency: str(r.rate) for r in db_rates}
                rate_result = RateResult(
                    base=norm_base,
                    rates={r.target_currency: r.rate for r in db_rates},
                    provider="database",
                    rate_date=parsed_date.isoformat(),
                    fetched_at=datetime.now(UTC).isoformat(),
                    stale=False,
                    age_seconds=0,
                )
                data = HistoricalRatesResponseData(
                    base=norm_base,
                    rate_date=parsed_date.isoformat(),
                    rates=rates_dict,
                    provider="database",
                )
                return data, rate_result

        # Fetch from primary provider
        rate_result = await self.primary_provider.get_historical(
            date_str=parsed_date.isoformat(),
            base=norm_base,
            symbols=norm_symbols,
        )

        # Persist to database if session is available
        if session:
            try:
                repo = RateRepository(session)
                await repo.save_rates(
                    base=norm_base,
                    rates=rate_result.rates,
                    rate_date=parsed_date,
                    provider=rate_result.provider,
                )
            except Exception as exc:
                logger.warning("Failed to persist historical rates to DB: %s", exc)

        data = HistoricalRatesResponseData(
            base=norm_base,
            rate_date=rate_result.rate_date,
            rates={k: str(v) for k, v in rate_result.rates.items()},
            provider=rate_result.provider,
        )
        return data, rate_result

    async def get_timeseries(
        self,
        start_date_str: str,
        end_date_str: str,
        base: str = "EUR",
        symbols: list[str] | None = None,
        session: AsyncSession | None = None,
    ) -> tuple[TimeseriesResponseData, TimeseriesResult]:
        """Fetch historical timeseries rates across a date range and compute statistical metrics."""
        start_d, end_d = validate_date_range(start_date_str, end_date_str)
        norm_base = validate_currency_code(base)
        norm_symbols = [validate_currency_code(s) for s in symbols] if symbols else None

        timeseries_res = await self.primary_provider.get_timeseries(
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            base=norm_base,
            symbols=norm_symbols,
        )

        # Persist to DB if session available
        if session:
            try:
                repo = RateRepository(session)
                for d_str, d_rates in timeseries_res.rates.items():
                    d_parsed = datetime.strptime(d_str, "%Y-%m-%d").date()
                    await repo.save_rates(
                        base=norm_base,
                        rates=d_rates,
                        rate_date=d_parsed,
                        provider=timeseries_res.provider,
                    )
            except Exception as exc:
                logger.warning("Failed to persist timeseries rates to DB: %s", exc)

        # Compute statistics in Decimal
        stats = compute_timeseries_statistics(timeseries_res.rates)

        # Format rates as string representation
        rates_str_map = {
            d: {s: str(r) for s, r in symbol_map.items()}
            for d, symbol_map in timeseries_res.rates.items()
        }

        data = TimeseriesResponseData(
            base=norm_base,
            start_date=timeseries_res.start_date,
            end_date=timeseries_res.end_date,
            rates=rates_str_map,
            statistics=stats,
            count_dates=len(timeseries_res.rates),
            provider=timeseries_res.provider,
        )
        return data, timeseries_res
