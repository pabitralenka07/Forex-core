"""Integration tests for /v1/historical and /v1/timeseries endpoints."""

from decimal import Decimal

import pytest
import respx
from httpx import AsyncClient, Response

BASE_URL = "https://api.frankfurter.dev/v1"


@pytest.mark.asyncio
@respx.mock
async def test_get_historical_success(async_client: AsyncClient) -> None:
    """Test successful historical rate retrieval."""
    respx.get(f"{BASE_URL}/2024-01-15").mock(
        return_value=Response(
            200,
            json={
                "amount": 1.0,
                "base": "EUR",
                "date": "2024-01-15",
                "rates": {"USD": 1.0945, "GBP": 0.8612},
            },
        )
    )

    response = await async_client.get(
        "/v1/historical",
        params={"date": "2024-01-15", "base": "EUR", "symbols": "USD,GBP"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["base"] == "EUR"
    assert payload["data"]["rate_date"] == "2024-01-15"
    assert Decimal(payload["data"]["rates"]["USD"]) == Decimal("1.0945")
    assert Decimal(payload["data"]["rates"]["GBP"]) == Decimal("0.8612")
    assert payload["meta"]["provider"] in ["frankfurter", "database"]


@pytest.mark.asyncio
async def test_get_historical_invalid_date_format(async_client: AsyncClient) -> None:
    """Test rejection of non-ISO formatted date."""
    response = await async_client.get(
        "/v1/historical",
        params={"date": "15-01-2024", "base": "EUR"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_historical_future_date_rejected(async_client: AsyncClient) -> None:
    """Test rejection of future date."""
    response = await async_client.get(
        "/v1/historical",
        params={"date": "2099-01-01", "base": "EUR"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "future" in payload["error"]["message"].lower()


@pytest.mark.asyncio
async def test_get_historical_date_before_coverage_rejected(async_client: AsyncClient) -> None:
    """Test rejection of date before 1999-01-04 (ECB inception)."""
    response = await async_client.get(
        "/v1/historical",
        params={"date": "1995-05-10", "base": "EUR"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "before provider coverage" in payload["error"]["message"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_get_timeseries_success(async_client: AsyncClient) -> None:
    """Test timeseries retrieval and statistical metrics calculation."""
    respx.get(f"{BASE_URL}/2024-01-01..2024-01-04").mock(
        return_value=Response(
            200,
            json={
                "amount": 1.0,
                "base": "EUR",
                "start_date": "2024-01-01",
                "end_date": "2024-01-04",
                "rates": {
                    "2024-01-01": {"USD": 1.1000},
                    "2024-01-02": {"USD": 1.2000},
                    "2024-01-03": {"USD": 1.0500},
                    "2024-01-04": {"USD": 1.1500},
                },
            },
        )
    )

    response = await async_client.get(
        "/v1/timeseries",
        params={"start": "2024-01-01", "end": "2024-01-04", "base": "EUR", "symbols": "USD"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["base"] == "EUR"
    assert data["start_date"] == "2024-01-01"
    assert data["end_date"] == "2024-01-04"
    assert data["count_dates"] == 4

    # Verify statistical calculations
    usd_stats = data["statistics"]["USD"]
    assert usd_stats["start_rate"] == "1.1" or usd_stats["start_rate"] == "1.1000"
    assert usd_stats["min_rate"] == "1.05" or usd_stats["min_rate"] == "1.0500"
    assert usd_stats["min_date"] == "2024-01-03"
    assert usd_stats["max_rate"] == "1.2" or usd_stats["max_rate"] == "1.2000"
    assert usd_stats["max_date"] == "2024-01-02"
    assert usd_stats["avg_rate"] == "1.12500000"
    assert usd_stats["change_pct"] == "4.5455"


@pytest.mark.asyncio
async def test_get_timeseries_start_after_end_rejected(async_client: AsyncClient) -> None:
    """Test validation error when start_date is later than end_date."""
    response = await async_client.get(
        "/v1/timeseries",
        params={"start": "2024-01-10", "end": "2024-01-01", "base": "EUR"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "VALIDATION_ERROR"
