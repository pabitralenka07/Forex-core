"""Pydantic schemas for currency conversion endpoints."""

from pydantic import BaseModel, Field


class ConvertResponseData(BaseModel):
    """Data payload for currency conversion result."""

    from_currency: str = Field(..., alias="from", description="Source currency code (ISO 4217)")
    to_currency: str = Field(..., alias="to", description="Target currency code (ISO 4217)")
    amount: str = Field(..., description="Original amount converted (string representation)")
    rate: str = Field(..., description="Exchange rate applied (full provider precision)")
    inverse_rate: str = Field(..., description="Inverse exchange rate applied")
    converted_amount: str = Field(
        ...,
        description="Converted amount rounded to target currency minor units",
    )
    target_minor_units: int = Field(..., description="Minor units used for rounding")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True,
    }


class ReverseConvertResponseData(BaseModel):
    """Data payload for reverse currency conversion."""

    from_currency: str = Field(..., alias="from", description="Source currency code (ISO 4217)")
    to_currency: str = Field(..., alias="to", description="Target currency code (ISO 4217)")
    target_amount: str = Field(..., description="Desired target amount (string representation)")
    required_from_amount: str = Field(
        ...,
        description="Amount of from_currency required to receive target_amount",
    )
    rate: str = Field(..., description="Exchange rate (from -> to)")
    inverse_rate: str = Field(..., description="Inverse exchange rate (to -> from)")
    from_minor_units: int = Field(..., description="Minor units used for rounding from_currency")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True,
    }


class SingleConversionRequest(BaseModel):
    """Single item conversion request within a batch."""

    from_currency: str = Field(..., alias="from", description="Source currency code")
    to_currency: str = Field(..., alias="to", description="Target currency code")
    amount: str = Field(..., description="Amount to convert")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True,
    }


class BatchConvertRequest(BaseModel):
    """Request schema for batch conversion endpoint."""

    # Mode 1: One base amount -> many targets
    base: str | None = Field(
        default=None, description="Base currency code for 1-to-many conversion"
    )
    amount: str | None = Field(
        default=None, description="Amount to convert for 1-to-many conversion"
    )
    targets: list[str] | None = Field(default=None, description="List of target currency codes")

    # Mode 2: List of independent conversions
    conversions: list[SingleConversionRequest] | None = Field(
        default=None,
        description="List of independent conversion items",
    )


class BatchConvertResponseData(BaseModel):
    """Data payload for batch conversion results."""

    conversions: list[ConvertResponseData] = Field(
        ...,
        description="List of executed conversions",
    )
    count: int = Field(..., description="Total conversions completed")
