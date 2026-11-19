"""Domain and infrastructure exceptions for Currency Converter."""

from typing import Any


class CurrencyConverterException(Exception):
    """Base exception for all Currency Converter domain and infrastructure errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class InvalidCurrencyError(CurrencyConverterException):
    """Raised when an unsupported or malformed currency code is provided."""

    def __init__(self, message: str, currency: str | None = None) -> None:
        super().__init__(
            message=message,
            code="INVALID_CURRENCY",
            status_code=400,
            details={"currency": currency} if currency else None,
        )


class InvalidAmountError(CurrencyConverterException):
    """Raised when an amount is negative, zero, NaN, Infinite, or out of range."""

    def __init__(self, message: str, amount: str | None = None) -> None:
        super().__init__(
            message=message,
            code="INVALID_AMOUNT",
            status_code=400,
            details={"amount": amount} if amount else None,
        )


class ValidationError(CurrencyConverterException):
    """Raised when query or request parameters violate validation constraints."""

    def __init__(self, message: str, param: str | None = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            details={"param": param} if param else None,
        )


class RateNotFoundError(CurrencyConverterException):
    """Raised when an exchange rate is not available for a requested currency pair or date."""

    def __init__(
        self,
        message: str,
        base: str | None = None,
        target: str | None = None,
        date_str: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RATE_NOT_FOUND",
            status_code=404,
            details={"base": base, "target": target, "date": date_str},
        )


class ProviderUnavailableError(CurrencyConverterException):
    """Raised when an upstream provider is offline, unreachable, or times out."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(
            message=message,
            code="PROVIDER_UNAVAILABLE",
            status_code=503,
            details={"provider": provider} if provider else None,
        )


class ProviderResponseError(CurrencyConverterException):
    """Raised when an upstream provider returns unparseable or unexpected payload shapes."""

    def __init__(self, message: str, provider: str | None = None) -> None:
        super().__init__(
            message=message,
            code="PROVIDER_RESPONSE_ERROR",
            status_code=502,
            details={"provider": provider} if provider else None,
        )


class RateSanityError(CurrencyConverterException):
    """Raised when an exchange rate violates physical sanity checks (e.g. <= 0)."""

    def __init__(
        self,
        message: str,
        rate: str | None = None,
        pair: str | None = None,
    ) -> None:
        super().__init__(
            message=message,
            code="RATE_SANITY_ERROR",
            status_code=502,
            details={"rate": rate, "pair": pair},
        )


class UnauthorizedError(CurrencyConverterException):
    """Raised when client provides an invalid, expired, or missing API key."""

    def __init__(self, message: str = "Invalid or expired API key.") -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=401,
        )


class RateLimitExceededError(CurrencyConverterException):
    """Raised when client exceeds their assigned rate limit tier."""

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please try again later.",
        retry_after_seconds: int = 60,
    ) -> None:
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds
