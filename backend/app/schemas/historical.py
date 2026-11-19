"""Pydantic schemas for historical exchange rates and timeseries endpoints."""

from pydantic import BaseModel, Field


class HistoricalRatesResponseData(BaseModel):
    """Data payload for historical exchange rates on a specific date."""

    base: str = Field(..., description="Base currency ISO 4217 code")
    rate_date: str = Field(..., description="Historical reference date (YYYY-MM-DD)")
    rates: dict[str, str] = Field(
        ...,
        description="Target currency to exchange rate string mapping at full provider precision",
    )
    provider: str = Field(..., description="Source provider identifier")


class TimeseriesStatsItem(BaseModel):
    """Statistical metrics for a single currency in a timeseries range."""

    min_rate: str = Field(..., description="Minimum observed rate over the period")
    min_date: str = Field(..., description="Date of minimum observed rate")
    max_rate: str = Field(..., description="Maximum observed rate over the period")
    max_date: str = Field(..., description="Date of maximum observed rate")
    avg_rate: str = Field(
        ..., description="Arithmetic mean rate over the period (8 decimal places)"
    )
    start_rate: str = Field(..., description="Rate on the first available date in the period")
    end_rate: str = Field(..., description="Rate on the last available date in the period")
    change_pct: str = Field(
        ...,
        description="Percentage change from start to end: ((end - start) / start) * 100",
    )


class TimeseriesResponseData(BaseModel):
    """Data payload for timeseries rates across a date range with statistics."""

    base: str = Field(..., description="Base currency ISO 4217 code")
    start_date: str = Field(..., description="Requested start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="Requested end date (YYYY-MM-DD)")
    rates: dict[str, dict[str, str]] = Field(
        ...,
        description="Date (YYYY-MM-DD) -> {target_currency: rate_string} mapping",
    )
    statistics: dict[str, TimeseriesStatsItem] = Field(
        ...,
        description="Statistical summary per target currency (min, max, avg, % change)",
    )
    count_dates: int = Field(..., description="Total number of dates with published rates")
    provider: str = Field(..., description="Source provider identifier")
