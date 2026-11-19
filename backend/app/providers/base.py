"""Abstract base class and contract models for external exchange rate providers."""

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RateResult(BaseModel):
    """Normalized exchange rate result from any provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base: str = Field(..., description="Base currency ISO 4217 code (normalized uppercase)")
    rates: dict[str, Decimal] = Field(..., description="Target currency code to Decimal rate map")
    provider: str = Field(..., description="Identifier of the source provider")
    rate_date: str = Field(..., description="Provider's own published date/timestamp (YYYY-MM-DD)")
    fetched_at: str = Field(..., description="ISO 8601 UTC timestamp when rate was fetched")
    stale: bool = Field(default=False, description="Whether the rate is flagged as stale")
    age_seconds: int = Field(default=0, description="Age in seconds of the cached rate")


class TimeseriesResult(BaseModel):
    """Normalized historical timeseries result from any provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    base: str = Field(..., description="Base currency ISO 4217 code (normalized uppercase)")
    start_date: str = Field(..., description="Start of historical series (YYYY-MM-DD)")
    end_date: str = Field(..., description="End of historical series (YYYY-MM-DD)")
    rates: dict[str, dict[str, Decimal]] = Field(
        ...,
        description="Date (YYYY-MM-DD) -> {target_currency: Decimal rate} mapping",
    )
    provider: str = Field(..., description="Identifier of the source provider")
    fetched_at: str = Field(..., description="ISO 8601 UTC timestamp when timeseries was fetched")


class RateProvider(ABC):
    """Abstract interface that all exchange rate provider adapters must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique provider name identifier."""
        ...

    @abstractmethod
    async def list_currencies(self) -> dict[str, str]:
        """Fetch all supported currencies.

        Returns:
            Dictionary mapping ISO currency code (uppercase) to currency display name.
        """
        ...

    @abstractmethod
    async def get_latest(
        self,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Fetch latest exchange rates for the given base currency.

        Args:
            base: Source currency code (e.g. 'USD').
            symbols: Optional list of target currency codes to filter.

        Returns:
            RateResult containing full precision Decimal exchange rates.
        """
        ...

    @abstractmethod
    async def get_historical(
        self,
        date_str: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Fetch historical exchange rates for a specific calendar date (YYYY-MM-DD).

        Args:
            date_str: ISO format date string (YYYY-MM-DD).
            base: Source currency code.
            symbols: Optional list of target currency codes.

        Returns:
            RateResult for the given historical date.
        """
        ...

    @abstractmethod
    async def get_timeseries(
        self,
        start_date: str,
        end_date: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> TimeseriesResult:
        """Fetch historical exchange rate timeseries across a date range.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).
            base: Source currency code.
            symbols: Optional list of target currency codes.

        Returns:
            TimeseriesResult containing date-to-rate mappings.
        """
        ...
