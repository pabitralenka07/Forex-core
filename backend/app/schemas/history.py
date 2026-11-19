"""Pydantic schemas for conversion history endpoints."""

from pydantic import BaseModel, Field


class ConversionHistoryItem(BaseModel):
    """Single recorded conversion in the user's history."""

    id: int = Field(..., description="Unique record identifier")
    session_id: str = Field(..., description="Client or user session identifier")
    from_currency: str = Field(..., alias="from", description="Source currency code (ISO 4217)")
    to_currency: str = Field(..., alias="to", description="Target currency code (ISO 4217)")
    amount: str = Field(..., description="Original input amount")
    converted_amount: str = Field(..., description="Final converted amount")
    rate: str = Field(..., description="Applied exchange rate")
    created_at: str = Field(..., description="ISO 8601 UTC timestamp of conversion")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True,
    }


class ConversionHistoryResponseData(BaseModel):
    """Paginated conversion history response data."""

    items: list[ConversionHistoryItem] = Field(..., description="List of historical conversions")
    total: int = Field(..., description="Total records matching session")
    limit: int = Field(..., description="Page size limit applied")
    offset: int = Field(..., description="Pagination offset applied")
    session_id: str = Field(..., description="Client or user session identifier")


class RecordConversionRequest(BaseModel):
    """Payload to log a conversion record manually or from client."""

    session_id: str = Field(..., description="Client session identifier")
    from_currency: str = Field(..., alias="from", description="Source currency code")
    to_currency: str = Field(..., alias="to", description="Target currency code")
    amount: str = Field(..., description="Original amount converted")
    converted_amount: str = Field(..., description="Converted result amount")
    rate: str = Field(..., description="Applied exchange rate")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True,
    }
