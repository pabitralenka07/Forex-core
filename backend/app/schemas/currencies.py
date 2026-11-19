"""Pydantic schemas for currency listing endpoints."""

from pydantic import BaseModel, Field


class CurrencyItem(BaseModel):
    """Metadata for an individual supported currency."""

    code: str = Field(..., description="ISO 4217 3-letter currency code")
    name: str = Field(..., description="Full display name of the currency")
    minor_units: int = Field(..., description="ISO 4217 minor unit decimal places")


class CurrenciesResponseData(BaseModel):
    """Data payload for currency list endpoint."""

    currencies: list[CurrencyItem] = Field(..., description="List of supported currencies")
    count: int = Field(..., description="Total count of supported currencies")
