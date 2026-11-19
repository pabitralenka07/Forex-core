"""Pydantic schemas for exchange rate endpoints."""

from pydantic import BaseModel, Field


class RatesResponseData(BaseModel):
    """Data payload for exchange rates listing."""

    base: str = Field(..., description="Base currency code (ISO 4217)")
    rates: dict[str, str] = Field(
        ...,
        description="Target currency to exchange rate mapping (strings at full precision)",
    )
    rate_date: str = Field(..., description="Provider rate publication date (YYYY-MM-DD)")


class SinglePairRateResponseData(BaseModel):
    """Data payload for single currency pair exchange rate."""

    base: str = Field(..., description="Base currency code (ISO 4217)")
    target: str = Field(..., description="Target currency code (ISO 4217)")
    rate: str = Field(..., description="Direct exchange rate base -> target")
    inverse_rate: str = Field(..., description="Inverse exchange rate target -> base")
    rate_date: str = Field(..., description="Provider rate publication date (YYYY-MM-DD)")
