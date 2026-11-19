"""Frankfurter exchange rate provider adapter (ECB reference rates)."""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from app.config import get_settings
from app.core.exceptions import (
    ProviderResponseError,
    ProviderUnavailableError,
    RateNotFoundError,
    RateSanityError,
)
from app.providers.base import RateProvider, RateResult, TimeseriesResult

logger = logging.getLogger(__name__)


class FrankfurterProvider(RateProvider):
    """Adapter for the Frankfurter API providing European Central Bank (ECB) reference rates."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.frankfurter_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.provider_timeout_seconds
        self._external_client = client

    @property
    def name(self) -> str:
        return "frankfurter"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._external_client is not None:
            return self._external_client
        return httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
        )

    def _parse_and_validate_rates(
        self,
        raw_rates: dict[str, Any],
        base: str,
    ) -> dict[str, Decimal]:
        """Convert all rate numbers into Decimal and execute sanity checks."""
        validated: dict[str, Decimal] = {}
        for symbol, raw_val in raw_rates.items():
            symbol_clean = str(symbol).strip().upper()
            try:
                # Handle Decimal from parse_float or int/str directly
                rate = Decimal(str(raw_val))
            except Exception as exc:
                raise ProviderResponseError(
                    f"Malformed rate value for {symbol_clean}: {raw_val}",
                    provider=self.name,
                ) from exc

            if rate.is_nan() or rate.is_infinite():
                raise RateSanityError(
                    f"Rate for {base}->{symbol_clean} is NaN or Infinite: {rate}",
                    rate=str(rate),
                    pair=f"{base}/{symbol_clean}",
                )

            if rate <= Decimal("0"):
                raise RateSanityError(
                    f"Rate for {base}->{symbol_clean} is zero or negative: {rate}",
                    rate=str(rate),
                    pair=f"{base}/{symbol_clean}",
                )

            validated[symbol_clean] = rate

        return validated

    async def _execute_request(self, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        client = await self._get_client()
        should_close = self._external_client is None

        try:
            response = await client.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"Frankfurter request timed out after {self.timeout_seconds}s: {url}",
                provider=self.name,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                f"Failed to connect to Frankfurter at {url}: {exc}",
                provider=self.name,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"HTTP communication error with Frankfurter: {exc}",
                provider=self.name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 404:
            raise RateNotFoundError(
                f"Frankfurter returned 404 for request: {url}",
                base=params.get("base") if params else None,
            )

        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Frankfurter upstream server error (HTTP {response.status_code}): {response.text}",
                provider=self.name,
            )

        if response.status_code != 200:
            raise ProviderResponseError(
                f"Unexpected HTTP status {response.status_code} from Frankfurter: {response.text}",
                provider=self.name,
            )

        try:
            # Decimal only: parse numbers directly to Decimal without float conversion
            return json.loads(response.text, parse_float=Decimal)
        except Exception as exc:
            raise ProviderResponseError(
                f"Failed to decode JSON response from Frankfurter: {response.text[:200]}",
                provider=self.name,
            ) from exc

    async def list_currencies(self) -> dict[str, str]:
        """Fetch currency codes and names from Frankfurter."""
        data = await self._execute_request("/currencies")
        if not isinstance(data, dict):
            raise ProviderResponseError(
                f"Expected currency mapping dict, received {type(data)}",
                provider=self.name,
            )
        return {str(k).upper(): str(v) for k, v in data.items()}

    async def get_latest(
        self,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Fetch latest ECB reference rates for the requested base currency."""
        normalized_base = base.strip().upper()
        params: dict[str, str] = {"base": normalized_base}
        if symbols:
            params["symbols"] = ",".join(s.strip().upper() for s in symbols)

        data = await self._execute_request("/latest", params=params)

        if not isinstance(data, dict) or "rates" not in data or "date" not in data:
            raise ProviderResponseError(
                f"Frankfurter latest response missing expected keys: {data}",
                provider=self.name,
            )

        rates = self._parse_and_validate_rates(data["rates"], normalized_base)
        now_utc = datetime.now(UTC).isoformat()

        return RateResult(
            base=normalized_base,
            rates=rates,
            provider=self.name,
            rate_date=str(data["date"]),
            fetched_at=now_utc,
            stale=False,
            age_seconds=0,
        )

    async def get_historical(
        self,
        date_str: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Fetch historical ECB reference rates for a given date (YYYY-MM-DD)."""
        normalized_base = base.strip().upper()
        params: dict[str, str] = {"base": normalized_base}
        if symbols:
            params["symbols"] = ",".join(s.strip().upper() for s in symbols)

        data = await self._execute_request(f"/{date_str}", params=params)

        if not isinstance(data, dict) or "rates" not in data or "date" not in data:
            raise ProviderResponseError(
                f"Frankfurter historical response missing expected keys: {data}",
                provider=self.name,
            )

        rates = self._parse_and_validate_rates(data["rates"], normalized_base)
        now_utc = datetime.now(UTC).isoformat()

        return RateResult(
            base=normalized_base,
            rates=rates,
            provider=self.name,
            rate_date=str(data["date"]),
            fetched_at=now_utc,
            stale=False,
            age_seconds=0,
        )

    async def get_timeseries(
        self,
        start_date: str,
        end_date: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> TimeseriesResult:
        """Fetch historical timeseries rates across a date range."""
        normalized_base = base.strip().upper()
        params: dict[str, str] = {"base": normalized_base}
        if symbols:
            params["symbols"] = ",".join(s.strip().upper() for s in symbols)

        data = await self._execute_request(f"/{start_date}..{end_date}", params=params)

        if not isinstance(data, dict) or "rates" not in data:
            raise ProviderResponseError(
                f"Frankfurter timeseries response missing expected keys: {data}",
                provider=self.name,
            )

        # rates in timeseries is a mapping: { "YYYY-MM-DD": { "EUR": rate, ... }, ... }
        daily_rates: dict[str, dict[str, Decimal]] = {}
        for date_key, day_map in data["rates"].items():
            if isinstance(day_map, dict):
                daily_rates[str(date_key)] = self._parse_and_validate_rates(
                    day_map,
                    normalized_base,
                )

        now_utc = datetime.now(UTC).isoformat()

        return TimeseriesResult(
            base=normalized_base,
            start_date=str(data.get("start_date", start_date)),
            end_date=str(data.get("end_date", end_date)),
            rates=daily_rates,
            provider=self.name,
            fetched_at=now_utc,
        )
