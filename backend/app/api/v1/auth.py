"""Authentication and API Key management endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.rate_limit import get_tier_rate_limit
from app.core.security import generate_api_key, get_current_api_key, hash_api_key
from app.database.session import get_db
from app.models.api_key import APIKey
from app.schemas.auth import (
    APIKeyInfoResponse,
    CreateAPIKeyRequest,
    CreateAPIKeyResponse,
    RevokeAPIKeyRequest,
)
from app.schemas.envelope import APIResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()


@router.post(
    "/keys",
    response_model=APIResponse[CreateAPIKeyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new API key",
    description="Generate a high-entropy API key with tier-based rate limit privileges.",
)
async def create_new_api_key(
    request: Request,
    body: CreateAPIKeyRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CreateAPIKeyResponse]:
    req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.expires_in_days)

    raw_key, api_key = await generate_api_key(
        client_name=body.client_name,
        plan=body.plan,
        expires_at=expires_at,
        session=db,
    )

    data = CreateAPIKeyResponse(
        api_key=raw_key,
        client_name=api_key.client_name,
        plan=api_key.plan,
        is_active=api_key.is_active,
        created_at=api_key.created_at.isoformat(),
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
    )

    return APIResponse.create_success(
        data=data,
        request_id=req_id,
    )


@router.get(
    "/verify",
    response_model=APIResponse[APIKeyInfoResponse],
    summary="Verify API key validity",
    description="Verify active status, plan tier, and rate limit allocation for X-API-Key.",
)
async def verify_api_key(
    request: Request,
    api_key: APIKey | None = Depends(get_current_api_key),
) -> APIResponse[APIKeyInfoResponse]:
    req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)

    if api_key is None:
        raise UnauthorizedError("No API key provided or key is invalid.")

    plan_limit = get_tier_rate_limit(f"{api_key.plan}:key:{api_key.key_hash}")

    data = APIKeyInfoResponse(
        client_name=api_key.client_name,
        plan=api_key.plan,
        is_active=api_key.is_active,
        created_at=api_key.created_at.isoformat(),
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None,
        rate_limit=plan_limit,
    )

    return APIResponse.create_success(
        data=data,
        request_id=req_id,
    )


@router.post(
    "/revoke",
    response_model=APIResponse[dict[str, bool]],
    summary="Revoke an API key",
    description="Deactivate an API key so subsequent requests fail authentication.",
)
async def revoke_api_key(
    request: Request,
    body: RevokeAPIKeyRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict[str, bool]]:
    req_id: str = getattr(request.state, "request_id", uuid.uuid4().hex)

    hashed = hash_api_key(body.api_key)
    stmt = select(APIKey).where(APIKey.key_hash == hashed)
    res = await db.execute(stmt)
    key_record = res.scalar_one_or_none()

    if key_record is None:
        raise UnauthorizedError("API key not found.")

    key_record.is_active = False
    await db.flush()

    return APIResponse.create_success(
        data={"revoked": True},
        request_id=req_id,
    )
