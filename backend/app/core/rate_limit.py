"""Rate limiting configuration, SlowAPI integration, and tier enforcement."""

import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.core.security import hash_api_key
from app.schemas.envelope import APIResponse

settings = get_settings()


def get_rate_limit_key(request: Request) -> str:
    """Derive rate-limit key prioritizing authenticated API key over client IP.

    Prefixes key with plan tier (free, pro, enterprise) for direct tier evaluation.
    """
    api_key = getattr(request.state, "api_key", None)
    if api_key is not None:
        plan = getattr(api_key, "plan", "free").lower()
        key_hash = getattr(api_key, "key_hash", "")
        return f"{plan}:key:{key_hash}"

    api_key_header = request.headers.get("X-API-Key")
    if api_key_header:
        return f"free:key:{hash_api_key(api_key_header)}"

    client_ip = "127.0.0.1"
    if request.client and request.client.host:
        client_ip = request.client.host
    elif request.headers.get("X-Forwarded-For"):
        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()

    return f"free:ip:{client_ip}"


def get_tier_rate_limit(key: str) -> str:
    """Resolve rate limit string dynamically based on plan prefix in the rate limit key."""
    if key.startswith("enterprise:"):
        return settings.rate_limit_enterprise
    if key.startswith("pro:"):
        return settings.rate_limit_pro
    return settings.rate_limit_free


# Global Limiter instance
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[settings.rate_limit_free],
    headers_enabled=True,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Format HTTP 429 response strictly adhering to Section 8 envelope and headers."""
    req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)

    # SlowAPI limit object inspection
    retry_after = 60
    limit_obj = exc.limit
    if limit_obj is not None and hasattr(limit_obj, "limit"):
        limit_str = str(limit_obj.limit)
    elif limit_obj is not None:
        limit_str = str(limit_obj)
    else:
        limit_str = "60/minute"

    error_response = APIResponse.create_error(
        code="RATE_LIMIT_EXCEEDED",
        message=f"Rate limit exceeded: {limit_str}. Try again in {retry_after} seconds.",
        request_id=req_id,
    )

    headers = {
        "Retry-After": str(retry_after),
        "X-RateLimit-Limit": limit_str,
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(int(time.time() + retry_after)),
        "X-Request-ID": req_id,
    }

    return JSONResponse(
        status_code=429,
        content=error_response.model_dump(),
        headers=headers,
    )
