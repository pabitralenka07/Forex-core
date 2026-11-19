"""Unit tests for health endpoints, request-ID correlation, and error handling."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_success(async_client: AsyncClient) -> None:
    """Test that /health returns a healthy status conforming to the envelope spec."""
    response = await async_client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["error"] is None
    assert payload["data"]["status"] == "healthy"
    assert "version" in payload["data"]
    assert "environment" in payload["data"]

    # Verify envelope meta
    assert "request_id" in payload["meta"]
    assert len(payload["meta"]["request_id"]) > 0
    # Response header check
    assert response.headers.get("X-Request-ID") == payload["meta"]["request_id"]


@pytest.mark.asyncio
async def test_health_check_custom_request_id(async_client: AsyncClient) -> None:
    """Test that an incoming X-Request-ID header is propagated through the response."""
    custom_id = "test-request-id-12345"
    response = await async_client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200

    payload = response.json()
    assert payload["meta"]["request_id"] == custom_id
    assert response.headers.get("X-Request-ID") == custom_id


@pytest.mark.asyncio
async def test_readiness_check_success(async_client: AsyncClient) -> None:
    """Test that /ready returns ready status conforming to the envelope spec."""
    response = await async_client.get("/ready")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["data"]["status"] == "ready"
    assert payload["data"]["components"]["api"] == "ready"
    assert "request_id" in payload["meta"]


@pytest.mark.asyncio
async def test_v1_prefixed_health(async_client: AsyncClient) -> None:
    """Test that health endpoint is accessible under /v1 prefix."""
    response = await async_client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_not_found_envelope(async_client: AsyncClient) -> None:
    """Test that a 404 response returns the standard error envelope with request_id."""
    response = await async_client.get("/nonexistent-endpoint")
    assert response.status_code == 404

    payload = response.json()
    assert payload["success"] is False
    assert payload["data"] is None
    assert payload["error"]["code"] == "NOT_FOUND"
    assert "request_id" in payload["meta"]
    assert response.headers.get("X-Request-ID") == payload["meta"]["request_id"]
