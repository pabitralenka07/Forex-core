"""Integration tests for authentication, API keys, rate limit responses, and security headers."""

import pytest
from httpx import AsyncClient
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from app.core.rate_limit import rate_limit_exceeded_handler


@pytest.mark.asyncio
async def test_auth_create_verify_and_revoke_lifecycle(async_client: AsyncClient) -> None:
    # 1. Create a Pro API Key
    create_res = await async_client.post(
        "/v1/auth/keys",
        json={"client_name": "test-fintech-app", "plan": "pro", "expires_in_days": 30},
    )
    assert create_res.status_code == 201
    created_payload = create_res.json()
    assert created_payload["success"] is True
    raw_key = created_payload["data"]["api_key"]
    assert raw_key.startswith("ak_")
    assert created_payload["data"]["plan"] == "pro"

    # 2. Verify Key
    verify_res = await async_client.get(
        "/v1/auth/verify",
        headers={"X-API-Key": raw_key},
    )
    assert verify_res.status_code == 200
    verify_payload = verify_res.json()
    assert verify_payload["success"] is True
    assert verify_payload["data"]["client_name"] == "test-fintech-app"
    assert verify_payload["data"]["rate_limit"] == "300/minute"

    # 3. Revoke Key
    revoke_res = await async_client.post(
        "/v1/auth/revoke",
        json={"api_key": raw_key},
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()["data"]["revoked"] is True

    # 4. Verify Revoked Key Fails (401 Unauthorized)
    verify_revoked_res = await async_client.get(
        "/v1/auth/verify",
        headers={"X-API-Key": raw_key},
    )
    assert verify_revoked_res.status_code == 401
    revoked_payload = verify_revoked_res.json()
    assert revoked_payload["success"] is False
    assert revoked_payload["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_verify_missing_or_invalid_key(async_client: AsyncClient) -> None:
    # Missing key
    res_missing = await async_client.get("/v1/auth/verify")
    assert res_missing.status_code == 401
    assert res_missing.json()["error"]["code"] == "UNAUTHORIZED"

    # Invalid key
    res_invalid = await async_client.get(
        "/v1/auth/verify",
        headers={"X-API-Key": "ak_invalid_nonexistent_token"},
    )
    assert res_invalid.status_code == 401
    assert res_invalid.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient) -> None:
    res = await async_client.get("/health")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert headers.get("x-xss-protection") == "0"
    assert "max-age=" in headers.get("strict-transport-security", "")
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "camera=()" in headers.get("permissions-policy", "")


def test_rate_limit_exceeded_envelope_and_headers() -> None:
    import json
    from unittest.mock import MagicMock

    from limits import parse
    from slowapi.wrappers import Limit

    mock_request = MagicMock(spec=Request)
    mock_request.state.request_id = "test-req-429"
    rate_item = parse("10/minute")
    limit_obj = Limit(rate_item, lambda: "", None, False, None, None, None, 1, False)
    exc = RateLimitExceeded(limit_obj)

    response = rate_limit_exceeded_handler(mock_request, exc)
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "60"
    assert response.headers.get("X-RateLimit-Limit") == "10 per 1 minute"
    assert response.headers.get("X-Request-ID") == "test-req-429"

    body = json.loads(bytes(response.body).decode("utf-8"))
    assert body["success"] is False
    assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
