"""Pydantic schemas for favorite currencies endpoints."""

from pydantic import BaseModel, Field


class FavoriteItem(BaseModel):
    """Favorite currency metadata item."""

    code: str = Field(..., description="ISO 4217 Currency Code (e.g. USD, EUR)")
    name: str = Field(..., description="Full currency name")
    symbol: str | None = Field(None, description="Currency symbol (e.g. $, €)")
    minor_units: int = Field(2, description="Minor units precision (ISO 4217 exponent)")


class FavoritesResponseData(BaseModel):
    """Payload for user favorites query."""

    favorites: list[FavoriteItem] = Field(..., description="List of saved favorite currencies")
    count: int = Field(..., description="Total count of favorites")
    session_id: str = Field(..., description="Client or user session identifier")


class AddFavoriteRequest(BaseModel):
    """Request payload to add a currency to favorites."""

    currency_code: str = Field(..., description="ISO 4217 Currency Code to add")
    session_id: str = Field(..., description="Client session identifier")
