"""Unit tests for Frankfurter provider using respx for HTTP mocking."""

from decimal import Decimal

import httpx
import pytest
import respx

from app.core.exceptions import (
    ProviderResponseError,
    ProviderUnavailableError,
    RateNotFoundError,
    RateSanityError,
)
from app.providers.frankfurter import FrankfurterProvider

BASE_URL = "https://api.frankfurter.dev/v1"


@pytest.fixture
def provider() -> FrankfurterProvider:
    return FrankfurterProvider(base_url=BASE_URL, timeout_seconds=2.0)


@pytest.mark.asyncio
@respx.mock
async def test_list_currencies_success(provider: FrankfurterProvider) -> None:
    """Verify listing currencies parses JSON mapping into uppercase keys."""
    respx.get(f"{BASE_URL}/currencies").mock(
        return_value=httpx.Response(
            200,
            json={"USD": "United States Dollar", "EUR": "Euro", "GBP": "British Pound"},
        )
    )

    currencies = await provider.list_currencies()
    assert currencies == {
        "USD": "United States Dollar",
        "EUR": "Euro",
        "GBP": "British Pound",
    }


@pytest.mark.asyncio
@respx.mock
async def test_get_latest_success_decimal_precision(provider: FrankfurterProvider) -> None:
    """Verify latest rates are parsed directly into Decimal without passing through float."""
    mock_payload = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-11-18",
        "rates": {
            "EUR": 0.91174,
            "GBP": 0.75939,
            "JPY": 159.42,
        },
    }
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(200, json=mock_payload))

    result = await provider.get_latest(base="USD")

    assert result.base == "USD"
    assert result.provider == "frankfurter"
    assert result.rate_date == "2026-11-18"
    assert result.stale is False
    assert result.age_seconds == 0

    # Ensure all rates are Decimals and none are float
    for symbol, rate in result.rates.items():
        assert isinstance(rate, Decimal), f"Expected Decimal for {symbol}, got {type(rate)}"
        assert not isinstance(rate, float)

    assert result.rates["EUR"] == Decimal("0.91174")
    assert result.rates["GBP"] == Decimal("0.75939")
    assert result.rates["JPY"] == Decimal("159.42")


@pytest.mark.asyncio
@respx.mock
async def test_get_latest_with_symbols(provider: FrankfurterProvider) -> None:
    """Verify passing symbols parameter formats query string properly."""
    route = respx.get(f"{BASE_URL}/latest").mock(
        return_value=httpx.Response(
            200,
            json={"amount": 1.0, "base": "EUR", "date": "2026-11-18", "rates": {"USD": 1.0968}},
        )
    )

    result = await provider.get_latest(base="EUR", symbols=["usd"])
    assert route.called
    assert route.calls[0].request.url.query.decode() == "base=EUR&symbols=USD"
    assert result.rates["USD"] == Decimal("1.0968")


@pytest.mark.asyncio
@respx.mock
async def test_get_historical_success(provider: FrankfurterProvider) -> None:
    """Verify historical exchange rates are retrieved for a specific calendar date."""
    respx.get(f"{BASE_URL}/2026-01-15").mock(
        return_value=httpx.Response(
            200,
            json={"amount": 1.0, "base": "USD", "date": "2026-01-15", "rates": {"EUR": 0.86029}},
        )
    )

    result = await provider.get_historical(date_str="2026-01-15", base="USD")
    assert result.rate_date == "2026-01-15"
    assert result.rates["EUR"] == Decimal("0.86029")
    assert isinstance(result.rates["EUR"], Decimal)


@pytest.mark.asyncio
@respx.mock
async def test_get_timeseries_success(provider: FrankfurterProvider) -> None:
    """Verify timeseries rates are parsed into nested date->symbol->Decimal maps."""
    mock_payload = {
        "amount": 1.0,
        "base": "USD",
        "start_date": "2026-01-01",
        "end_date": "2026-01-03",
        "rates": {
            "2026-01-01": {"EUR": 0.85106, "GBP": 0.74264},
            "2026-01-02": {"EUR": 0.85317, "GBP": 0.74388},
        },
    }
    respx.get(f"{BASE_URL}/2026-01-01..2026-01-03").mock(
        return_value=httpx.Response(200, json=mock_payload)
    )

    result = await provider.get_timeseries(
        start_date="2026-01-01",
        end_date="2026-01-03",
        base="USD",
    )

    assert result.base == "USD"
    assert result.start_date == "2026-01-01"
    assert result.end_date == "2026-01-03"
    assert "2026-01-01" in result.rates
    assert isinstance(result.rates["2026-01-01"]["EUR"], Decimal)
    assert result.rates["2026-01-01"]["EUR"] == Decimal("0.85106")
    assert result.rates["2026-01-02"]["GBP"] == Decimal("0.74388")


@pytest.mark.asyncio
@respx.mock
async def test_timeout_raises_provider_unavailable(provider: FrankfurterProvider) -> None:
    """Verify timeout throws ProviderUnavailableError."""
    respx.get(f"{BASE_URL}/latest").mock(side_effect=httpx.ReadTimeout("Connection timed out"))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.get_latest(base="USD")
    assert "timed out" in str(exc_info.value).lower()
    assert exc_info.value.code == "PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
@respx.mock
async def test_network_error_raises_provider_unavailable(provider: FrankfurterProvider) -> None:
    """Verify network connection failures throw ProviderUnavailableError."""
    respx.get(f"{BASE_URL}/latest").mock(side_effect=httpx.ConnectError("Network unreachable"))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.get_latest(base="USD")
    assert "failed to connect" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_upstream_500_raises_provider_unavailable(provider: FrankfurterProvider) -> None:
    """Verify 5xx response throws ProviderUnavailableError."""
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(502, text="Bad Gateway"))

    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.get_latest(base="USD")
    assert "server error" in str(exc_info.value).lower()


@pytest.mark.asyncio
@respx.mock
async def test_unsupported_currency_404_raises_rate_not_found(
    provider: FrankfurterProvider,
) -> None:
    """Verify 404 response throws RateNotFoundError."""
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(404, text="Not Found"))

    with pytest.raises(RateNotFoundError) as exc_info:
        await provider.get_latest(base="XYZ")
    assert exc_info.value.code == "RATE_NOT_FOUND"


@pytest.mark.asyncio
@respx.mock
async def test_bad_json_raises_provider_response_error(provider: FrankfurterProvider) -> None:
    """Verify malformed JSON payload throws ProviderResponseError."""
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(200, text="<not valid json>"))

    with pytest.raises(ProviderResponseError) as exc_info:
        await provider.get_latest(base="USD")
    assert exc_info.value.code == "PROVIDER_RESPONSE_ERROR"


@pytest.mark.asyncio
@respx.mock
async def test_negative_rate_raises_rate_sanity_error(provider: FrankfurterProvider) -> None:
    """Verify negative exchange rates violate sanity checks."""
    mock_payload = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-11-18",
        "rates": {"EUR": -0.91174},
    }
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(200, json=mock_payload))

    with pytest.raises(RateSanityError) as exc_info:
        await provider.get_latest(base="USD")
    assert exc_info.value.code == "RATE_SANITY_ERROR"
    assert "zero or negative" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_zero_rate_raises_rate_sanity_error(provider: FrankfurterProvider) -> None:
    """Verify zero exchange rates violate sanity checks."""
    mock_payload = {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-11-18",
        "rates": {"EUR": 0.0},
    }
    respx.get(f"{BASE_URL}/latest").mock(return_value=httpx.Response(200, json=mock_payload))

    with pytest.raises(RateSanityError) as exc_info:
        await provider.get_latest(base="USD")
    assert exc_info.value.code == "RATE_SANITY_ERROR"
    assert "zero or negative" in str(exc_info.value)
