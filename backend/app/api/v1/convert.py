"""Currency conversion REST endpoints under /v1."""

import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repository import RateRepository
from app.database.session import get_db
from app.schemas.convert import (
    BatchConvertRequest,
    BatchConvertResponseData,
    ConvertResponseData,
    ReverseConvertResponseData,
)
from app.schemas.envelope import APIResponse
from app.services.rate_service import RateService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Conversion"])


def get_rate_service() -> RateService:
    """Dependency injector for RateService singleton/instance."""
    return RateService()


@router.get(
    "/convert",
    response_model=APIResponse[ConvertResponseData],
    summary="Convert Currency Amount",
    description=(
        "Converts a monetary decimal amount from one currency to another "
        "using latest reference rates."
    ),
)
async def convert_currency(
    request: Request,
    from_currency: str = Query(..., alias="from", description="Source ISO 4217 currency code"),
    to_currency: str = Query(..., alias="to", description="Target ISO 4217 currency code"),
    amount: str = Query(..., description="Monetary amount to convert (positive decimal)"),
    session_id: str | None = Query(
        None, description="Optional client session ID to record history"
    ),
    service: RateService = Depends(get_rate_service),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[ConvertResponseData]:
    """Execute currency conversion."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    result, rate_meta = await service.convert(
        from_currency=from_currency,
        to_currency=to_currency,
        amount_str=amount,
    )

    # Automatically record conversion to history if session_id is provided
    effective_session = session_id or request.headers.get("X-Session-ID")
    if effective_session:
        try:
            repo = RateRepository(db)
            await repo.add_conversion_history(
                session_id=effective_session.strip(),
                from_currency=result.from_currency,
                to_currency=result.to_currency,
                amount=Decimal(result.amount),
                converted_amount=Decimal(result.converted_amount),
                rate=Decimal(result.rate),
            )
        except Exception as hist_err:
            logger.warning("Failed to automatically record conversion to history: %s", hist_err)

    data = ConvertResponseData.model_validate(
        {
            "from": result.from_currency,
            "to": result.to_currency,
            "amount": result.amount,
            "rate": result.rate,
            "inverse_rate": result.inverse_rate,
            "converted_amount": result.converted_amount,
            "target_minor_units": result.target_minor_units,
        }
    )

    return APIResponse.create_success(
        data=data,
        request_id=request_id,
        provider=rate_meta.provider,
        rate_date=rate_meta.rate_date,
        fetched_at=rate_meta.fetched_at,
        stale=rate_meta.stale,
        age_seconds=rate_meta.age_seconds,
    )


@router.get(
    "/convert/reverse",
    response_model=APIResponse[ReverseConvertResponseData],
    summary="Reverse Currency Conversion",
    description=(
        "Calculates how much source currency (from) is needed to yield "
        "a specific target amount (to)."
    ),
)
async def reverse_convert_currency(
    request: Request,
    from_currency: str = Query(..., alias="from", description="Source ISO 4217 currency code"),
    to_currency: str = Query(..., alias="to", description="Target ISO 4217 currency code"),
    target_amount: str = Query(..., description="Desired target monetary amount"),
    service: RateService = Depends(get_rate_service),
) -> APIResponse[ReverseConvertResponseData]:
    """Execute reverse currency conversion."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    result, rate_meta = await service.reverse_convert(
        from_currency=from_currency,
        to_currency=to_currency,
        target_amount_str=target_amount,
    )

    data = ReverseConvertResponseData.model_validate(
        {
            "from": result.from_currency,
            "to": result.to_currency,
            "target_amount": result.target_amount,
            "required_from_amount": result.required_from_amount,
            "rate": result.rate,
            "inverse_rate": result.inverse_rate,
            "from_minor_units": result.from_minor_units,
        }
    )

    return APIResponse.create_success(
        data=data,
        request_id=request_id,
        provider=rate_meta.provider,
        rate_date=rate_meta.rate_date,
        fetched_at=rate_meta.fetched_at,
        stale=rate_meta.stale,
        age_seconds=rate_meta.age_seconds,
    )


@router.post(
    "/convert/batch",
    response_model=APIResponse[BatchConvertResponseData],
    summary="Batch Currency Conversion",
    description=(
        "Executes multiple conversions in a single batch "
        "(1-to-many or independent conversion items)."
    ),
)
async def batch_convert_currency(
    request: Request,
    body: BatchConvertRequest,
    service: RateService = Depends(get_rate_service),
) -> APIResponse[BatchConvertResponseData]:
    """Execute batch currency conversions."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    results, rate_meta = await service.batch_convert(body)

    items = [
        ConvertResponseData.model_validate(
            {
                "from": r.from_currency,
                "to": r.to_currency,
                "amount": r.amount,
                "rate": r.rate,
                "inverse_rate": r.inverse_rate,
                "converted_amount": r.converted_amount,
                "target_minor_units": r.target_minor_units,
            }
        )
        for r in results
    ]

    return APIResponse.create_success(
        data=BatchConvertResponseData(conversions=items, count=len(items)),
        request_id=request_id,
        provider=rate_meta.provider,
        rate_date=rate_meta.rate_date,
        fetched_at=rate_meta.fetched_at,
        stale=rate_meta.stale,
        age_seconds=rate_meta.age_seconds,
    )
