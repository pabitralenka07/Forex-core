"""Integration tests for all /v1 REST endpoints using a mocked provider via respx."""

import httpx
import pytest
import respx
from httpx import AsyncClient

BASE_URL = "https://api.frankfurter.dev/v1"


@pytest.fixture(autouse=True)
async def mock_frankfurter(respx_mock: respx.MockRouter) -> None:
    """Mock standard Frankfurter provider endpoints for integration testing and clear cache."""
    from app.services.cache_service import get_cache_service

    await get_cache_service().clear()

    # Currencies mock
    respx_mock.get(path="/v1/currencies").mock(
        return_value=httpx.Response(
            200,
            json={
                "USD": "United States Dollar",
                "EUR": "Euro",
                "GBP": "British Pound",
                "JPY": "Japanese Yen",
                "INR": "Indian Rupee",
                "KWD": "Kuwaiti Dinar",
            },
        )
    )

    # Latest rates mock for USD
    respx_mock.get(path="/v1/latest").mock(
        return_value=httpx.Response(
            200,
            json={
                "amount": 1.0,
                "base": "USD",
                "date": "2026-11-18",
                "rates": {
                    "EUR": 0.91174,
                    "GBP": 0.75939,
                    "JPY": 159.42,
                    "INR": 83.25,
                    "KWD": 0.3075,
                },
            },
        )
    )


@pytest.mark.asyncio
async def test_convert_endpoint_success(async_client: AsyncClient) -> None:
    """Test GET /v1/convert returns standard envelope with stringified amounts."""
    response = await async_client.get("/v1/convert?from=USD&to=EUR&amount=100.50")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None

    data = payload["data"]
    assert data["from"] == "USD"
    assert data["to"] == "EUR"
    assert data["amount"] == "100.50"
    assert data["rate"] == "0.91174"
    assert "converted_amount" in data
    # 100.50 * 0.91174 = 91.62987 -> rounded to 2 decimals for EUR = 91.63
    assert data["converted_amount"] == "91.63"
    assert data["target_minor_units"] == 2

    # Meta verification
    meta = payload["meta"]
    assert meta["provider"] == "frankfurter"
    assert meta["rate_date"] == "2026-11-18"
    assert "request_id" in meta


@pytest.mark.asyncio
async def test_convert_to_jpy_zero_decimals(async_client: AsyncClient) -> None:
    """Test GET /v1/convert to JPY rounds to 0 decimal places."""
    response = await async_client.get("/v1/convert?from=USD&to=JPY&amount=100")
    assert response.status_code == 200

    data = response.json()["data"]
    # 100 * 159.42 = 15942
    assert data["converted_amount"] == "15942"
    assert "." not in data["converted_amount"]
    assert data["target_minor_units"] == 0


@pytest.mark.asyncio
async def test_convert_reverse_endpoint(async_client: AsyncClient) -> None:
    """Test GET /v1/convert/reverse calculates required from amount."""
    response = await async_client.get("/v1/convert/reverse?from=USD&to=INR&target_amount=10000")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["from"] == "USD"
    assert data["to"] == "INR"
    assert data["target_amount"] == "10000"
    # 10000 / 83.25 = 120.12012... -> rounded to 2 decimals (USD) = 120.12
    assert data["required_from_amount"] == "120.12"
    assert data["from_minor_units"] == 2


@pytest.mark.asyncio
async def test_convert_batch_one_to_many(async_client: AsyncClient) -> None:
    """Test POST /v1/convert/batch mode 1: one base to many targets."""
    payload = {
        "base": "USD",
        "amount": "100",
        "targets": ["EUR", "GBP", "JPY"],
    }
    response = await async_client.post("/v1/convert/batch", json=payload)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["count"] == 3
    targets_converted = [c["to"] for c in data["conversions"]]
    assert targets_converted == ["EUR", "GBP", "JPY"]


@pytest.mark.asyncio
async def test_convert_batch_independent_list(async_client: AsyncClient) -> None:
    """Test POST /v1/convert/batch mode 2: list of independent conversions."""
    payload = {
        "conversions": [
            {"from": "USD", "to": "EUR", "amount": "50"},
            {"from": "USD", "to": "JPY", "amount": "75"},
        ]
    }
    response = await async_client.post("/v1/convert/batch", json=payload)
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["count"] == 2
    assert data["conversions"][0]["converted_amount"] == "45.59"  # 50 * 0.91174 = 45.587 -> 45.59


@pytest.mark.asyncio
async def test_get_rates_endpoint(async_client: AsyncClient) -> None:
    """Test GET /v1/rates returns rate dictionary."""
    response = await async_client.get("/v1/rates?base=USD&symbols=EUR,GBP")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["base"] == "USD"
    assert "EUR" in data["rates"]
    assert "GBP" in data["rates"]
    assert data["rate_date"] == "2026-11-18"


@pytest.mark.asyncio
async def test_get_pair_rate_endpoint(async_client: AsyncClient) -> None:
    """Test GET /v1/rates/{base}/{target} returns rate and inverse rate."""
    response = await async_client.get("/v1/rates/USD/EUR")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["base"] == "USD"
    assert data["target"] == "EUR"
    assert data["rate"] == "0.91174"
    assert "inverse_rate" in data


@pytest.mark.asyncio
async def test_list_currencies_endpoint(async_client: AsyncClient) -> None:
    """Test GET /v1/currencies returns currency list enriched with minor units."""
    response = await async_client.get("/v1/currencies")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["count"] > 0
    usd_item = next(c for c in data["currencies"] if c["code"] == "USD")
    assert usd_item["name"] == "United States Dollar"
    assert usd_item["minor_units"] == 2

    jpy_item = next(c for c in data["currencies"] if c["code"] == "JPY")
    assert jpy_item["minor_units"] == 0


@pytest.mark.asyncio
async def test_get_currency_detail_success(async_client: AsyncClient) -> None:
    """Test GET /v1/currencies/{code} returns specific currency."""
    response = await async_client.get("/v1/currencies/USD")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["code"] == "USD"
    assert data["minor_units"] == 2


@pytest.mark.asyncio
async def test_get_currency_detail_not_found(async_client: AsyncClient) -> None:
    """Test GET /v1/currencies/{code} with unsupported code returns 404."""
    response = await async_client.get("/v1/currencies/XYZ")
    assert response.status_code == 404

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "RATE_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_currency_code_returns_400(async_client: AsyncClient) -> None:
    """Test invalid currency code returns 400 INVALID_CURRENCY error envelope."""
    response = await async_client.get("/v1/convert?from=USDD&to=EUR&amount=100")
    assert response.status_code == 400

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_CURRENCY"
    assert "request_id" in payload["meta"]


@pytest.mark.asyncio
async def test_negative_amount_returns_400(async_client: AsyncClient) -> None:
    """Test negative amount returns 400 INVALID_AMOUNT error envelope."""
    response = await async_client.get("/v1/convert?from=USD&to=EUR&amount=-50")
    assert response.status_code == 400

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_scientific_notation_amount_returns_400(async_client: AsyncClient) -> None:
    """Test scientific notation amount is rejected with 400 INVALID_AMOUNT."""
    response = await async_client.get("/v1/convert?from=USD&to=EUR&amount=1e5")
    assert response.status_code == 400

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_provider_unavailable_returns_503(
    async_client: AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """Test upstream provider failure returns 503 PROVIDER_UNAVAILABLE envelope."""
    # Override latest mock to simulate upstream failure on all providers
    respx_mock.get(path="/v1/latest").mock(
        side_effect=httpx.ConnectError("Connection refused by primary")
    )
    respx_mock.get(path__startswith="/v6/latest").mock(
        side_effect=httpx.ConnectError("Connection refused by secondary")
    )

    response = await async_client.get("/v1/convert?from=USD&to=EUR&amount=100")
    assert response.status_code == 503

    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert "request_id" in payload["meta"]


@pytest.mark.asyncio
async def test_openapi_schema_contains_v1_endpoints(async_client: AsyncClient) -> None:
    """Test that OpenAPI JSON schema documents all required v1 endpoints."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    paths = schema["paths"]
    assert "/v1/convert" in paths
    assert "/v1/convert/reverse" in paths
    assert "/v1/convert/batch" in paths
    assert "/v1/rates" in paths
    assert "/v1/rates/{base}/{target}" in paths
    assert "/v1/currencies" in paths
    assert "/v1/currencies/{code}" in paths
    assert "/health" in paths
    assert "/ready" in paths
