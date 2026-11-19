"""API Key generation, verification, and security dependencies."""

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.database.session import get_db
from app.models.api_key import APIKey

settings = get_settings()


def hash_api_key(raw_key: str) -> str:
    """Compute deterministic SHA-256 digest of raw API key for secure storage."""
    return hashlib.sha256(raw_key.strip().encode("utf-8")).hexdigest()


async def generate_api_key(
    client_name: str,
    plan: str = "free",
    expires_at: datetime | None = None,
    session: AsyncSession | None = None,
) -> tuple[str, APIKey]:
    """Generate a high-entropy API key, hash it for DB storage, and persist it."""
    # Prefix helps identify key type in logs and headers without exposing entropy
    raw_key = f"ak_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw_key)

    api_key = APIKey(
        key_hash=key_hash,
        client_name=client_name.strip(),
        plan=plan.strip().lower(),
        is_active=True,
        expires_at=expires_at,
        created_at=datetime.now(UTC),
    )

    if session:
        session.add(api_key)
        await session.flush()

    return raw_key, api_key


async def get_current_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> APIKey | None:
    """FastAPI dependency to verify X-API-Key header against hashed DB keys.

    If X-API-Key is provided:
        - Verifies hash, active status, and expiry.
        - Sets request.state.api_key.
        - Returns APIKey instance.
    If X-API-Key is missing:
        - If require_api_key is True -> raises UnauthorizedError.
        - Else -> returns None (falls back to IP tier).
    """
    if x_api_key:
        hashed = hash_api_key(x_api_key)
        stmt = select(APIKey).where(APIKey.key_hash == hashed)
        res = await db.execute(stmt)
        api_key = res.scalar_one_or_none()

        if api_key is None or not api_key.is_active:
            raise UnauthorizedError("Invalid or inactive API key.")

        if api_key.expires_at is not None:
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < datetime.now(UTC):
                raise UnauthorizedError("API key has expired.")

        request.state.api_key = api_key
        return api_key

    if settings.require_api_key:
        raise UnauthorizedError("API key required via X-API-Key header.")

    request.state.api_key = None
    return None
