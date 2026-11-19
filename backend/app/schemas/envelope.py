"""Standard API response envelopes conforming to Section 8 spec."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    """Structured error payload."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")


class ResponseMeta(BaseModel):
    """Metadata envelope present on every response."""

    request_id: str = Field(..., description="Unique request tracing ID")
    provider: str | None = Field(default=None, description="External rate provider source")
    rate_date: str | None = Field(default=None, description="Date/timestamp of exchange rate")
    fetched_at: str | None = Field(default=None, description="ISO timestamp when rate was fetched")
    stale: bool = Field(default=False, description="Whether rate data is stale")
    age_seconds: int = Field(default=0, description="Age in seconds of the cached rate")


class APIResponse(BaseModel, Generic[DataT]):
    """Unified API response envelope."""

    success: bool
    data: DataT | None = None
    meta: ResponseMeta
    error: ErrorDetail | None = None

    @classmethod
    def create_success(
        cls,
        data: DataT,
        request_id: str,
        provider: str | None = None,
        rate_date: str | None = None,
        fetched_at: str | None = None,
        stale: bool = False,
        age_seconds: int = 0,
    ) -> "APIResponse[DataT]":
        """Factory for successful API responses."""
        return cls(
            success=True,
            data=data,
            meta=ResponseMeta(
                request_id=request_id,
                provider=provider,
                rate_date=rate_date,
                fetched_at=fetched_at,
                stale=stale,
                age_seconds=age_seconds,
            ),
            error=None,
        )

    @classmethod
    def create_error(
        cls,
        code: str,
        message: str,
        request_id: str,
    ) -> "APIResponse[Any]":
        """Factory for error responses."""
        return cls(
            success=False,
            data=None,
            meta=ResponseMeta(request_id=request_id),
            error=ErrorDetail(code=code, message=message),
        )
