"""Health and readiness check endpoints."""

from typing import Any

from fastapi import APIRouter, Request

from app.config import get_settings
from app.schemas.envelope import APIResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=APIResponse[dict[str, Any]],
    summary="Service Liveness Check",
    description="Returns service liveness status and environment information.",
)
async def health_check(request: Request) -> APIResponse[dict[str, Any]]:
    """Check service liveness."""
    settings = get_settings()
    request_id: str = getattr(request.state, "request_id", "unknown")

    return APIResponse.create_success(
        data={
            "status": "healthy",
            "version": settings.app_version,
            "environment": settings.app_env,
        },
        request_id=request_id,
    )


@router.get(
    "/ready",
    response_model=APIResponse[dict[str, Any]],
    summary="Service Readiness Check",
    description="Returns readiness status of the application components and configured providers.",
)
async def readiness_check(request: Request) -> APIResponse[dict[str, Any]]:
    """Check service readiness."""
    settings = get_settings()
    request_id: str = getattr(request.state, "request_id", "unknown")

    return APIResponse.create_success(
        data={
            "status": "ready",
            "version": settings.app_version,
            "environment": settings.app_env,
            "components": {
                "api": "ready",
                "primary_provider": settings.primary_provider,
            },
        },
        request_id=request_id,
    )
