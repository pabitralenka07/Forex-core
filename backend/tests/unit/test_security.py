"""Unit tests for security, API key hashing, and rate limiting tier resolution."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi import Request

from app.core.rate_limit import get_rate_limit_key, get_tier_rate_limit
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import APIKey


def test_hash_api_key_deterministic() -> None:
    key = "ak_test_secret_12345"
    h1 = hash_api_key(key)
    h2 = hash_api_key(key)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest length


async def test_generate_api_key_format() -> None:
    raw, key_obj = await generate_api_key(client_name="test-client", plan="pro")
    assert raw.startswith("ak_")
    assert key_obj.client_name == "test-client"
    assert key_obj.plan == "pro"
    assert key_obj.is_active is True
    assert key_obj.key_hash == hash_api_key(raw)


def test_get_rate_limit_key_with_authenticated_state() -> None:
    mock_request = MagicMock(spec=Request)
    mock_key = APIKey(
        key_hash="dummy_hash_abc",
        client_name="partner",
        plan="enterprise",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    mock_request.state.api_key = mock_key
    key_str = get_rate_limit_key(mock_request)
    assert key_str == "enterprise:key:dummy_hash_abc"


def test_get_rate_limit_key_ip_fallback() -> None:
    mock_request = MagicMock(spec=Request)
    mock_request.state.api_key = None
    mock_request.headers.get.return_value = None
    mock_request.client.host = "192.168.1.100"
    key_str = get_rate_limit_key(mock_request)
    assert key_str == "free:ip:192.168.1.100"


def test_get_tier_rate_limit_resolution() -> None:
    assert get_tier_rate_limit("enterprise:key:123") == "1200/minute"
    assert get_tier_rate_limit("pro:key:123") == "300/minute"
    assert get_tier_rate_limit("free:ip:127.0.0.1") == "60/minute"
