"""Historical and timeseries exchange rate REST endpoints under /v1."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.envelope import APIResponse
from app.schemas.historical import (
    HistoricalRatesResponseData,
    TimeseriesResponseData,
)
from app.services.rate_service import RateService

router = APIRouter(tags=["Historical & Timeseries"])


def get_rate_service() -> RateService:
    return RateService()


@router.get(
    "/historical",
    response_model=APIResponse[HistoricalRatesResponseData],
    summary="Get Historical Exchange Rates",
    description="Fetch published ECB reference rates for a specific past date (YYYY-MM-DD).",
)
async def get_historical_rates(
    request: Request,
    date: str = Query(
        ..., description="Historical date in YYYY-MM-DD format", examples=["2024-01-15"]
    ),
    base: str = Query("EUR", description="Base currency ISO 4217 code", examples=["EUR"]),
    symbols: str | None = Query(
        None,
        description="Comma-separated target currency codes (e.g. USD,GBP,JPY)",
        examples=["USD,GBP"],
    ),
    service: RateService = Depends(get_rate_service),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[HistoricalRatesResponseData]:
    """Fetch historical rates for a specific calendar date."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None

    data, rate_result = await service.get_historical(
        date_str=date,
        base=base,
        symbols=symbol_list,
        session=db,
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
    "/timeseries",
    response_model=APIResponse[TimeseriesResponseData],
    summary="Get Historical Timeseries & Statistics",
    description=(
        "Fetch historical rates across a date range (start to end) and calculate "
        "comprehensive summary metrics (min, max, average, % change)."
    ),
)
async def get_timeseries_rates(
    request: Request,
    start: str = Query(..., description="Start date in YYYY-MM-DD format", examples=["2024-01-01"]),
    end: str = Query(..., description="End date in YYYY-MM-DD format", examples=["2024-01-31"]),
    base: str = Query("EUR", description="Base currency ISO 4217 code", examples=["EUR"]),
    symbols: str | None = Query(
        None,
        description="Comma-separated target currency codes",
        examples=["USD,GBP"],
    ),
    service: RateService = Depends(get_rate_service),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TimeseriesResponseData]:
    """Fetch timeseries rates over a date range with full Decimal statistical analysis."""
    request_id: str = getattr(request.state, "request_id", "unknown")
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None

    data, timeseries_res = await service.get_timeseries(
        start_date_str=start,
        end_date_str=end,
        base=base,
        symbols=symbol_list,
        session=db,
    )

    return APIResponse.create_success(
        data=data,
        request_id=request_id,
        provider=timeseries_res.provider,
        rate_date=timeseries_res.end_date,
        fetched_at=timeseries_res.fetched_at,
        stale=False,
        age_seconds=0,
    )
