"""Currencies metadata REST endpoints under /v1."""

from fastapi import APIRouter, Depends, Request

from app.schemas.currencies import CurrenciesResponseData, CurrencyItem
from app.schemas.envelope import APIResponse
from app.services.rate_service import RateService

router = APIRouter(tags=["Currencies"])


def get_rate_service() -> RateService:
    return RateService()


@router.get(
    "/currencies",
    response_model=APIResponse[CurrenciesResponseData],
    summary="List Supported Currencies",
    description="Returns all supported currencies along with ISO 4217 minor unit metadata.",
)
async def list_currencies(
    request: Request,
    service: RateService = Depends(get_rate_service),
) -> APIResponse[CurrenciesResponseData]:
    """Fetch list of all supported currencies."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    currencies = await service.list_currencies()

    data = CurrenciesResponseData(
        currencies=currencies,
        count=len(currencies),
    )

    return APIResponse.create_success(
        data=data,
        request_id=request_id,
    )


@router.get(
    "/currencies/{code}",
    response_model=APIResponse[CurrencyItem],
    summary="Get Currency Metadata",
    description="Returns metadata and minor unit precision for a specific currency code.",
)
async def get_currency_detail(
    request: Request,
    code: str,
    service: RateService = Depends(get_rate_service),
) -> APIResponse[CurrencyItem]:
    """Fetch details for a single currency."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    item = await service.get_currency(code)

    return APIResponse.create_success(
        data=item,
        request_id=request_id,
    )
