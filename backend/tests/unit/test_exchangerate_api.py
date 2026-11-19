"""Unit tests for ExchangeRate-API provider adapter using respx."""

from decimal import Decimal

import httpx
import pytest
import respx

from app.core.exceptions import (
    ProviderResponseError,
    ProviderUnavailableError,
    RateSanityError,
)
from app.providers.exchangerate_api import ExchangeRateApiProvider

BASE_URL = "https://open.er-api.com/v6"


@pytest.fixture
def provider() -> ExchangeRateApiProvider:
    return ExchangeRateApiProvider(base_url=BASE_URL, timeout_seconds=2.0)


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_get_latest_success(provider: ExchangeRateApiProvider) -> None:
    """Verify ExchangeRate-API parses rates into Decimal without passing through float."""
    mock_payload = {
        "result": "success",
        "provider": "https://www.exchangerate-api.com",
        "time_last_update_utc": "Thu, 19 Nov 2026 00:02:31 +0000",
        "base_code": "USD",
        "rates": {
            "USD": 1,
            "EUR": 0.91234,
            "GBP": 0.76543,
            "JPY": 159.25,
        },
    }
    respx.get(path="/v6/latest/USD").mock(return_value=httpx.Response(200, json=mock_payload))

    result = await provider.get_latest(base="USD")

    assert result.base == "USD"
    assert result.provider == "exchangerate_api"
    assert "2026-11-19" in result.rate_date
    assert result.stale is False

    for _symbol, rate in result.rates.items():
        assert isinstance(rate, Decimal)
        assert not isinstance(rate, float)

    assert result.rates["EUR"] == Decimal("0.91234")
    assert result.rates["JPY"] == Decimal("159.25")


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_get_latest_with_symbols(provider: ExchangeRateApiProvider) -> None:
    """Verify filtering specific symbols."""
    mock_payload = {
        "result": "success",
        "base_code": "USD",
        "rates": {
            "USD": 1,
            "EUR": 0.912,
            "GBP": 0.765,
        },
    }
    respx.get(path="/v6/latest/USD").mock(return_value=httpx.Response(200, json=mock_payload))

    result = await provider.get_latest(base="USD", symbols=["EUR"])
    assert "EUR" in result.rates
    assert "GBP" not in result.rates


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_timeout_raises_unavailable(
    provider: ExchangeRateApiProvider,
) -> None:
    """Verify timeout triggers ProviderUnavailableError."""
    respx.get(path="/v6/latest/USD").mock(side_effect=httpx.ReadTimeout("Timeout"))

    with pytest.raises(ProviderUnavailableError):
        await provider.get_latest(base="USD")


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_5xx_raises_unavailable(provider: ExchangeRateApiProvider) -> None:
    """Verify 5xx triggers ProviderUnavailableError."""
    respx.get(path="/v6/latest/USD").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    with pytest.raises(ProviderUnavailableError):
        await provider.get_latest(base="USD")


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_negative_rate_raises_sanity_error(
    provider: ExchangeRateApiProvider,
) -> None:
    """Verify negative rate triggers RateSanityError."""
    mock_payload = {
        "result": "success",
        "base_code": "USD",
        "rates": {"EUR": -0.95},
    }
    respx.get(path="/v6/latest/USD").mock(return_value=httpx.Response(200, json=mock_payload))

    with pytest.raises(RateSanityError):
        await provider.get_latest(base="USD")


@pytest.mark.asyncio
@respx.mock
async def test_exchangerate_api_bad_json_raises_response_error(
    provider: ExchangeRateApiProvider,
) -> None:
    """Verify bad JSON triggers ProviderResponseError."""
    respx.get(path="/v6/latest/USD").mock(return_value=httpx.Response(200, text="<invalid json>"))

    with pytest.raises(ProviderResponseError):
        await provider.get_latest(base="USD")
