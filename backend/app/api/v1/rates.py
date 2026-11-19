"""Exchange rates REST endpoints under /v1."""

from fastapi import APIRouter, Depends, Query, Request

from app.schemas.envelope import APIResponse
from app.schemas.rates import RatesResponseData, SinglePairRateResponseData
from app.services.rate_service import RateService

router = APIRouter(tags=["Rates"])


def get_rate_service() -> RateService:
    return RateService()


@router.get(
    "/rates",
    response_model=APIResponse[RatesResponseData],
    summary="Get Latest Exchange Rates",
    description=(
        "Returns latest exchange rates for a specified base currency "
        "and optional target symbol filters."
    ),
)
async def get_latest_rates(
    request: Request,
    base: str = Query(default="USD", description="Base ISO 4217 currency code"),
    symbols: str | None = Query(
        default=None,
        description="Optional comma-separated list of target currency codes (e.g. 'EUR,GBP,JPY')",
    ),
    service: RateService = Depends(get_rate_service),
) -> APIResponse[RatesResponseData]:
    """Fetch latest exchange rates."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    rate_result = await service.get_rates(base=base, symbols=symbol_list)

    rates_str_map = {k: str(v) for k, v in rate_result.rates.items()}

    data = RatesResponseData(
        base=rate_result.base,
        rates=rates_str_map,
        rate_date=rate_result.rate_date,
    )

    return APIResponse.create_success(
        data=data,
        request_id=request_id,
        provider=rate_result.provider,
        rate_date=rate_result.rate_date,
        fetched_at=rate_result.fetched_at,
        stale=rate_result.stale,
        age_seconds=rate_result.age_seconds,
    )


@router.get(
    "/rates/{base}/{target}",
    response_model=APIResponse[SinglePairRateResponseData],
    summary="Get Single Pair Exchange Rate",
    description=(
        "Returns direct and inverse exchange rate between a specific base and target currency pair."
    ),
)
async def get_pair_rate(
    request: Request,
    base: str,
    target: str,
    service: RateService = Depends(get_rate_service),
) -> APIResponse[SinglePairRateResponseData]:
    """Fetch exchange rate for a single currency pair."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    rate, inverse, rate_meta = await service.get_pair_rate(base=base, target=target)

    data = SinglePairRateResponseData(
        base=base.strip().upper(),
        target=target.strip().upper(),
        rate=str(rate),
        inverse_rate=str(inverse),
        rate_date=rate_meta.rate_date,
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
