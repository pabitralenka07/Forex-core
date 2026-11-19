"""Schemas for API key issuance, verification, and revocation."""

from typing import Literal

from pydantic import BaseModel, Field


class CreateAPIKeyRequest(BaseModel):
    """Payload to request issuance of a new API key."""

    client_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Name of the consuming application or client.",
        examples=["mobile-app-prod"],
    )
    plan: Literal["free", "pro", "enterprise"] = Field(
        default="free",
        description="Subscription tier defining rate limit allowances.",
        examples=["pro"],
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Optional lifetime in days. None implies no expiry.",
        examples=[90],
    )


class CreateAPIKeyResponse(BaseModel):
    """Response returned upon key creation containing plaintext key once."""

    api_key: str = Field(
        ...,
        description="Plaintext API key. Store safely; not recoverable after this response.",
        examples=["ak_dGhpcy1pcy1hLXNhbXBsZS1rZXk"],
    )
    client_name: str
    plan: str
    is_active: bool
    created_at: str
    expires_at: str | None = None
    message: str = "Store this API key safely. It will not be shown again."


class APIKeyInfoResponse(BaseModel):
    """Public metadata of an authenticated API key."""

    client_name: str
    plan: str
    is_active: bool
    created_at: str
    expires_at: str | None = None
    rate_limit: str


class RevokeAPIKeyRequest(BaseModel):
    """Payload to revoke an API key."""

    api_key: str = Field(..., description="Raw API key to revoke.")
