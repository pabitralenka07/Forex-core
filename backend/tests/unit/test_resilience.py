"""Unit tests for caching, circuit breakers, request coalescing, and failover resilience."""

import asyncio
from decimal import Decimal

import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.exceptions import ProviderUnavailableError
from app.providers.base import RateProvider, RateResult, TimeseriesResult
from app.services.cache_service import InMemoryTTLCache
from app.services.rate_service import RateService


# Dummy mock providers for resilience failure-injection tests
class MockFailingProvider(RateProvider):
    def __init__(self, name: str = "failing_provider") -> None:
        self._name = name
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    async def list_currencies(self) -> dict[str, str]:
        self.call_count += 1
        raise ProviderUnavailableError("Simulated upstream outage", provider=self.name)

    async def get_latest(self, base: str, symbols: list[str] | None = None) -> RateResult:
        self.call_count += 1
        raise ProviderUnavailableError("Simulated rate failure", provider=self.name)

    async def get_historical(
        self, date_str: str, base: str, symbols: list[str] | None = None
    ) -> RateResult:
        raise ProviderUnavailableError("Simulated failure", provider=self.name)

    async def get_timeseries(
        self, start_date: str, end_date: str, base: str, symbols: list[str] | None = None
    ) -> TimeseriesResult:
        raise ProviderUnavailableError("Simulated failure", provider=self.name)


class MockWorkingProvider(RateProvider):
    def __init__(
        self, name: str = "working_provider", rates: dict[str, Decimal] | None = None
    ) -> None:
        self._name = name
        self.call_count = 0
        self.rates = rates or {"EUR": Decimal("0.9000"), "GBP": Decimal("0.7500")}

    @property
    def name(self) -> str:
        return self._name

    async def list_currencies(self) -> dict[str, str]:
        self.call_count += 1
        return {"USD": "US Dollar", "EUR": "Euro", "GBP": "British Pound"}

    async def get_latest(self, base: str, symbols: list[str] | None = None) -> RateResult:
        self.call_count += 1
        return RateResult(
            base=base,
            rates=self.rates,
            provider=self.name,
            rate_date="2026-11-18",
            fetched_at="2026-11-19T00:00:00Z",
            stale=False,
            age_seconds=0,
        )

    async def get_historical(
        self, date_str: str, base: str, symbols: list[str] | None = None
    ) -> RateResult:
        raise NotImplementedError

    async def get_timeseries(
        self, start_date: str, end_date: str, base: str, symbols: list[str] | None = None
    ) -> TimeseriesResult:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# CACHE TESTS
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cache_ttl_and_stale_retrieval() -> None:
    """Test cache respects TTL and allows stale retrieval after expiration."""
    cache = InMemoryTTLCache(max_size=10, default_ttl=0.1)

    await cache.set("test_key", "sample_value", ttl_seconds=0.05)

    # 1. Immediate retrieval before expiration
    val, is_stale, _ = await cache.get("test_key", allow_stale=False)
    assert val == "sample_value"
    assert is_stale is False

    # 2. Wait for TTL expiration
    await asyncio.sleep(0.08)

    # Retrieval with allow_stale=False returns None
    val_fresh, _, _ = await cache.get("test_key", allow_stale=False)
    assert val_fresh is None

    # Retrieval with allow_stale=True returns expired value flagged as stale
    val_stale, is_stale_flag, age_sec = await cache.get("test_key", allow_stale=True)
    assert val_stale == "sample_value"
    assert is_stale_flag is True
    assert age_sec >= 0


@pytest.mark.asyncio
async def test_cache_lru_eviction() -> None:
    """Test cache evicts least-recently-used item when capacity is exceeded."""
    cache = InMemoryTTLCache(max_size=2, default_ttl=60.0)

    await cache.set("k1", "v1")
    await cache.set("k2", "v2")

    # Access k1 to make it most-recently used
    await cache.get("k1")

    # Insert k3, exceeding max_size of 2 -> k2 should be evicted
    await cache.set("k3", "v3")

    v1, _, _ = await cache.get("k1")
    v2, _, _ = await cache.get("k2")
    v3, _, _ = await cache.get("k3")

    assert v1 == "v1"
    assert v2 is None  # Evicted
    assert v3 == "v3"


# -----------------------------------------------------------------------------
# REQUEST COALESCING TEST
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_coalescing_single_flight() -> None:
    """Test 10 concurrent requests for the same key trigger the underlying fetcher exactly once."""
    cache = InMemoryTTLCache(max_size=10, default_ttl=60.0)
    execution_counter = 0

    async def slow_fetch() -> str:
        nonlocal execution_counter
        execution_counter += 1
        await asyncio.sleep(0.05)
        return "coalesced_data"

    # Launch 10 concurrent tasks querying the same key
    tasks = [cache.coalesce("shared_key", slow_fetch) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # All 10 tasks received the same result
    assert all(r == "coalesced_data" for r in results)
    # The slow fetcher was executed exactly ONCE
    assert execution_counter == 1


# -----------------------------------------------------------------------------
# CIRCUIT BREAKER TESTS
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_circuit_breaker_transitions() -> None:
    """Test circuit breaker transitions: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""
    cb = CircuitBreaker("test_breaker", failure_threshold=2, recovery_timeout_seconds=0.05)

    # Initial state CLOSED
    assert cb.state == CircuitState.CLOSED
    assert await cb.allow_request() is True

    # 1st failure
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    assert await cb.allow_request() is True

    # 2nd failure -> reaches threshold 2 -> trips to OPEN
    await cb.record_failure()
    open_state: CircuitState = cb.state
    assert open_state == CircuitState.OPEN
    assert await cb.allow_request() is False  # Rejects immediate requests

    # Wait for recovery timeout
    await asyncio.sleep(0.06)

    # Should now transition to HALF_OPEN to allow probe request
    assert await cb.allow_request() is True
    half_open_state: CircuitState = cb.state
    assert half_open_state == CircuitState.HALF_OPEN

    # Successful probe resets breaker to CLOSED
    await cb.record_success()
    closed_state: CircuitState = cb.state
    assert closed_state == CircuitState.CLOSED
    assert cb.failure_count == 0


# -----------------------------------------------------------------------------
# FAILOVER & RESILIENCE PIPELINE TESTS
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_primary_failover_to_secondary_provider() -> None:
    """Test primary provider failure automatically falls over to secondary provider."""
    primary = MockFailingProvider(name="primary_failing")
    secondary = MockWorkingProvider(name="secondary_working")
    cache = InMemoryTTLCache(max_size=10)

    service = RateService(primary_provider=primary, secondary_provider=secondary, cache=cache)

    result = await service.get_rates(base="USD")

    # Primary failed and secondary succeeded
    assert result.provider == "secondary_working"
    assert result.rates["EUR"] == Decimal("0.9000")
    assert primary.call_count >= 1
    assert secondary.call_count == 1
    assert result.stale is False


@pytest.mark.asyncio
async def test_last_known_good_stale_serving_on_total_provider_failure() -> None:
    """Test Rule 8: If all providers fail, serve last known good rate flagged with stale=true."""
    cache = InMemoryTTLCache(max_size=10, default_ttl=0.01)

    # 1. Prime cache with last known good rates
    initial_rate = RateResult(
        base="USD",
        rates={"EUR": Decimal("0.9100")},
        provider="frankfurter",
        rate_date="2026-11-17",
        fetched_at="2026-11-17T00:00:00Z",
        stale=False,
        age_seconds=0,
    )
    await cache.set("rates:USD", initial_rate, ttl_seconds=0.01)

    # Wait to ensure cache entry becomes stale
    await asyncio.sleep(0.03)

    # 2. Both providers now fail
    primary = MockFailingProvider(name="primary_failing")
    secondary = MockFailingProvider(name="secondary_failing")
    service = RateService(primary_provider=primary, secondary_provider=secondary, cache=cache)

    result = await service.get_rates(base="USD")

    # Verified: Stale data served with stale=True and positive age_seconds
    assert result.stale is True
    assert result.age_seconds >= 0
    assert result.rates["EUR"] == Decimal("0.9100")
    assert result.provider == "frankfurter"


@pytest.mark.asyncio
async def test_total_outage_raises_provider_unavailable_when_no_cache() -> None:
    """Test that when all providers fail and cache has no last known good, error is raised."""
    cache = InMemoryTTLCache(max_size=10)  # Empty cache
    primary = MockFailingProvider(name="primary")
    secondary = MockFailingProvider(name="secondary")

    service = RateService(primary_provider=primary, secondary_provider=secondary, cache=cache)

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await service.get_rates(base="USD")

    assert "all exchange rate providers are unavailable" in str(exc_info.value).lower()
