"""Frontend API client for interacting with the Currency Converter backend."""

import os
from typing import Any

import httpx


class BackendAPIClient:
    """Client for the Currency Converter FastAPI backend."""

    def __init__(self, base_url: str | None = None) -> None:
        resolved_url = base_url or os.getenv("BACKEND_URL") or "http://127.0.0.1:8000"
        self.base_url = resolved_url.rstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        timeout_seconds: float = 6.0,
    ) -> dict[str, Any]:
        """Execute HTTP request to the backend and return the parsed envelope."""
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                )
                try:
                    return response.json()  # type: ignore[no-any-return]
                except ValueError:
                    return {
                        "success": False,
                        "data": None,
                        "meta": {"request_id": "client-invalid-json"},
                        "error": {
                            "code": f"HTTP_{response.status_code}",
                            "message": response.text
                            or f"HTTP {response.status_code} error",
                        },
                    }
        except httpx.ConnectError:
            return {
                "success": False,
                "data": None,
                "meta": {"request_id": "client-connection-failed"},
                "error": {
                    "code": "CONNECTION_ERROR",
                    "message": f"Unable to connect to backend at {self.base_url}. Is Uvicorn running?",
                },
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "data": None,
                "meta": {"request_id": "client-timeout"},
                "error": {
                    "code": "TIMEOUT_ERROR",
                    "message": "Request to backend timed out.",
                },
            }
        except httpx.HTTPError as exc:
            return {
                "success": False,
                "data": None,
                "meta": {"request_id": "client-error"},
                "error": {
                    "code": "HTTPX_ERROR",
                    "message": f"HTTP request failed: {exc}",
                },
            }

    def get_health(self) -> dict[str, Any]:
        """Fetch backend health status."""
        return self._request("GET", "/health")

    def get_currencies(self) -> dict[str, Any]:
        """Fetch supported currency list and minor unit metadata."""
        return self._request("GET", "/v1/currencies")

    def convert(
        self,
        from_currency: str,
        to_currency: str,
        amount: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute forward currency conversion."""
        params: dict[str, Any] = {
            "from": from_currency,
            "to": to_currency,
            "amount": amount,
        }
        if session_id:
            params["session_id"] = session_id
        return self._request("GET", "/v1/convert", params=params)

    def reverse_convert(
        self, from_currency: str, to_currency: str, target_amount: str
    ) -> dict[str, Any]:
        """Execute reverse currency conversion."""
        return self._request(
            "GET",
            "/v1/convert/reverse",
            params={
                "from": from_currency,
                "to": to_currency,
                "target_amount": target_amount,
            },
        )

    def get_rates(
        self, base: str = "EUR", symbols: list[str] | None = None
    ) -> dict[str, Any]:
        """Fetch latest exchange rates for base currency."""
        params: dict[str, Any] = {"base": base}
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._request("GET", "/v1/rates", params=params)

    def get_historical(
        self, date_str: str, base: str = "EUR", symbols: list[str] | None = None
    ) -> dict[str, Any]:
        """Fetch historical exchange rates for a specific calendar date."""
        params: dict[str, Any] = {"date": date_str, "base": base}
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._request("GET", "/v1/historical", params=params)

    def get_timeseries(
        self,
        start_date: str,
        end_date: str,
        base: str = "EUR",
        symbols: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch timeseries rates and summary statistics across a date range."""
        params: dict[str, Any] = {
            "start": start_date,
            "end": end_date,
            "base": base,
        }
        if symbols:
            params["symbols"] = ",".join(symbols)
        return self._request(
            "GET", "/v1/timeseries", params=params, timeout_seconds=12.0
        )

    def get_history(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """Fetch paginated conversion history for this session."""
        return self._request(
            "GET",
            "/v1/history",
            params={"session_id": session_id, "limit": limit, "offset": offset},
        )

    def record_history(
        self,
        session_id: str,
        from_currency: str,
        to_currency: str,
        amount: str,
        converted_amount: str,
        rate: str,
    ) -> dict[str, Any]:
        """Manually record a conversion event into the history log."""
        return self._request(
            "POST",
            "/v1/history",
            json_data={
                "session_id": session_id,
                "from": from_currency,
                "to": to_currency,
                "amount": amount,
                "converted_amount": converted_amount,
                "rate": rate,
            },
        )

    def clear_history(self, session_id: str) -> dict[str, Any]:
        """Clear all conversion history for this session."""
        return self._request(
            "DELETE",
            "/v1/history",
            params={"session_id": session_id},
        )

    def export_history_csv_url(self, session_id: str) -> str:
        """Return the export download URL for session history CSV."""
        return f"{self.base_url}/v1/history/export?session_id={session_id}"

    def get_favorites(self, session_id: str) -> dict[str, Any]:
        """Fetch list of user's favorite currencies."""
        return self._request(
            "GET",
            "/v1/favorites",
            params={"session_id": session_id},
        )

    def add_favorite(self, session_id: str, currency_code: str) -> dict[str, Any]:
        """Add a currency to user's favorites list."""
        return self._request(
            "POST",
            "/v1/favorites",
            json_data={"session_id": session_id, "currency_code": currency_code},
        )

    def remove_favorite(self, session_id: str, currency_code: str) -> dict[str, Any]:
        """Remove a currency from user's favorites list."""
        return self._request(
            "DELETE",
            f"/v1/favorites/{currency_code}",
            params={"session_id": session_id},
        )
