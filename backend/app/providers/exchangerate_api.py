"""ExchangeRate-API provider adapter (Secondary failover provider)."""

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


class ExchangeRateApiProvider(RateProvider):
    """Adapter for ExchangeRate-API (https://www.exchangerate-api.com).

    Serves as the secondary failover provider with broad currency coverage (160+ currencies).
    Operates without API key on the public open tier (open.er-api.com) or with optional API key.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.exchangerate_api_base_url).rstrip("/")
        self.api_key = api_key or settings.exchangerate_api_key
        self.timeout_seconds = timeout_seconds or settings.provider_timeout_seconds
        self._external_client = client

    @property
    def name(self) -> str:
        return "exchangerate_api"

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

    async def _execute_request(self, endpoint_path: str) -> Any:
        client = await self._get_client()
        should_close = self._external_client is None
        url = f"{self.base_url}{endpoint_path}"

        try:
            response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise ProviderUnavailableError(
                f"ExchangeRate-API request timed out after {self.timeout_seconds}s: {url}",
                provider=self.name,
            ) from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                f"Failed to connect to ExchangeRate-API at {url}: {exc}",
                provider=self.name,
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailableError(
                f"HTTP communication error with ExchangeRate-API: {exc}",
                provider=self.name,
            ) from exc
        finally:
            if should_close:
                await client.aclose()

        if response.status_code == 404:
            raise RateNotFoundError(
                f"ExchangeRate-API returned 404 for {url}",
                base=endpoint_path.split("/")[-1],
            )

        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"ExchangeRate-API server error (HTTP {response.status_code}): {response.text}",
                provider=self.name,
            )

        if response.status_code != 200:
            raise ProviderResponseError(
                f"Unexpected HTTP status {response.status_code}: {response.text}",
                provider=self.name,
            )

        try:
            # Parse numbers into Decimal directly without passing through float
            return json.loads(response.text, parse_float=Decimal)
        except Exception as exc:
            raise ProviderResponseError(
                f"Failed to decode JSON from ExchangeRate-API: {response.text[:200]}",
                provider=self.name,
            ) from exc

    async def list_currencies(self) -> dict[str, str]:
        """Fetch available currencies from ExchangeRate-API."""
        data = await self._execute_request("/latest/USD")
        if not isinstance(data, dict) or "rates" not in data:
            raise ProviderResponseError(
                "ExchangeRate-API did not return rates dictionary for currency listing",
                provider=self.name,
            )

        return {str(k).upper(): f"{k} (ExchangeRate-API)" for k in data["rates"]}

    async def get_latest(
        self,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Fetch latest exchange rates for base currency."""
        norm_base = base.strip().upper()
        data = await self._execute_request(f"/latest/{norm_base}")

        if not isinstance(data, dict) or data.get("result") != "success" or "rates" not in data:
            error_type = data.get("error-type", "unknown") if isinstance(data, dict) else "unknown"
            if error_type == "unsupported-code":
                raise RateNotFoundError(
                    f"Unsupported currency code '{norm_base}'",
                    base=norm_base,
                )
            raise ProviderResponseError(
                f"ExchangeRate-API failed: {error_type}",
                provider=self.name,
            )

        all_rates = self._parse_and_validate_rates(data["rates"], norm_base)

        if symbols:
            filter_symbols = {s.strip().upper() for s in symbols}
            rates = {k: v for k, v in all_rates.items() if k in filter_symbols}
        else:
            rates = all_rates

        rate_date_utc = str(data.get("time_last_update_utc", ""))
        rate_date = datetime.now(UTC).strftime("%Y-%m-%d")
        if rate_date_utc:
            try:
                # Format: "Thu, 19 Nov 2026 00:02:31 +0000"
                parsed = datetime.strptime(rate_date_utc[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                rate_date = parsed.strftime("%Y-%m-%d")
            except Exception:
                pass

        return RateResult(
            base=norm_base,
            rates=rates,
            provider=self.name,
            rate_date=rate_date,
            fetched_at=datetime.now(UTC).isoformat(),
            stale=False,
            age_seconds=0,
        )

    async def get_historical(
        self,
        date_str: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> RateResult:
        """Historical data on free open tier is limited; fall back to latest or error."""
        raise ProviderUnavailableError(
            "Historical lookup requires authenticated tier on ExchangeRate-API.",
            provider=self.name,
        )

    async def get_timeseries(
        self,
        start_date: str,
        end_date: str,
        base: str,
        symbols: list[str] | None = None,
    ) -> TimeseriesResult:
        """Timeseries lookup requires authenticated tier on ExchangeRate-API."""
        raise ProviderUnavailableError(
            "Timeseries lookup requires authenticated tier on ExchangeRate-API.",
            provider=self.name,
        )
