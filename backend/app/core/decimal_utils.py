"""Precision Decimal financial arithmetic, validation, and rounding utilities."""

import decimal
import re
from decimal import Decimal
from typing import Any

from app.config import get_settings
from app.core.exceptions import InvalidAmountError, InvalidCurrencyError, RateSanityError

# System limits
MAX_AMOUNT: Decimal = Decimal("1000000000000")  # 1 Trillion
MIN_AMOUNT: Decimal = Decimal("0.00000001")  # 10^-8
MAX_DECIMAL_PLACES: int = 8
DISPLAY_RATE_PRECISION: int = 8

# Regular expression matching standard thousands comma grouping: e.g. 1,000.50 or -1,234,567
_STANDARD_LOCALE_PATTERN = re.compile(r"^-?(\d{1,3}(,\d{3})+)(\.\d+)?$")
_STANDARD_PLAIN_PATTERN = re.compile(r"^-?\d+(\.\d+)?$")


def validate_currency_code(code: str) -> str:
    """Validate and normalize a 3-letter ISO 4217 currency code."""
    if not isinstance(code, str):
        raise InvalidCurrencyError(
            f"Currency code must be a string, received {type(code).__name__}"
        )

    normalized = code.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise InvalidCurrencyError(
            f"Invalid currency code '{code}'. Must be exactly 3 alphabetic letters (ISO 4217).",
            currency=code,
        )
    return normalized


def parse_decimal_amount(value: Any) -> Decimal:
    """Parse and validate an amount into a positive Decimal without float coercion.

    Rejects:
      - float instances (to avoid precision contamination)
      - Negative or zero amounts
      - NaN or Infinite values
      - Scientific notation (e.g. 1e5, 1E-3)
      - Ambiguous locale formatting (e.g. 1.000,50 or misplaced commas)
      - Amounts exceeding MAX_AMOUNT
      - Amounts with more than MAX_DECIMAL_PLACES
    """
    if value is None:
        raise InvalidAmountError("Amount cannot be null or empty.")

    if isinstance(value, float):
        raise InvalidAmountError(
            "Float inputs are prohibited to prevent binary floating-point precision loss. "
            "Pass amounts as strings, integers, or Decimal."
        )

    raw_str = str(value).strip()
    if not raw_str:
        raise InvalidAmountError("Amount string cannot be empty.")

    # Reject scientific notation
    if "e" in raw_str or "E" in raw_str:
        raise InvalidAmountError(
            f"Scientific notation is not permitted: '{raw_str}'. Provide standard decimal format.",
            amount=raw_str,
        )

    # Process locale grouping and ambiguity
    cleaned_str = raw_str
    if "," in raw_str:
        if _STANDARD_LOCALE_PATTERN.match(raw_str):
            cleaned_str = raw_str.replace(",", "")
        else:
            raise InvalidAmountError(
                f"Ambiguous or invalid number format: '{raw_str}'. "
                "Use standard format (e.g. 1000.50 or 1,000.50).",
                amount=raw_str,
            )
    elif not _STANDARD_PLAIN_PATTERN.match(raw_str):
        raise InvalidAmountError(
            f"Malformed amount string: '{raw_str}'.",
            amount=raw_str,
        )

    try:
        dec = Decimal(cleaned_str)
    except decimal.InvalidOperation as exc:
        raise InvalidAmountError(
            f"Invalid numeric value: '{raw_str}'.",
            amount=raw_str,
        ) from exc

    if dec.is_nan() or dec.is_infinite():
        raise InvalidAmountError("Amount must be a finite number.", amount=raw_str)

    if dec <= Decimal("0"):
        raise InvalidAmountError(
            f"Amount must be strictly positive (> 0), received: {raw_str}",
            amount=raw_str,
        )

    if dec > MAX_AMOUNT:
        raise InvalidAmountError(
            f"Amount exceeds maximum allowed limit of {MAX_AMOUNT:,}: {raw_str}",
            amount=raw_str,
        )

    # Check decimal places
    exponent = dec.as_tuple().exponent
    fractional_digits = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    if fractional_digits > MAX_DECIMAL_PLACES:
        raise InvalidAmountError(
            f"Amount exceeds maximum allowed decimal places ({MAX_DECIMAL_PLACES}): {raw_str}",
            amount=raw_str,
        )

    return dec


def round_amount(
    amount: Decimal,
    minor_units: int,
    rounding_policy: str | None = None,
) -> Decimal:
    """Round the final converted amount using the target currency's minor units.

    Policies:
      - ROUND_HALF_UP (default): Standard financial rounding (0.5 rounds up)
      - ROUND_HALF_EVEN: Banker's rounding (rounds to nearest even digit)
    """
    policy = rounding_policy or get_settings().rounding_policy
    rounding_mode = (
        decimal.ROUND_HALF_EVEN if policy == "ROUND_HALF_EVEN" else decimal.ROUND_HALF_UP
    )

    exp = Decimal("1") if minor_units <= 0 else Decimal("1e-" + str(minor_units))

    return amount.quantize(exp, rounding=rounding_mode)


def calculate_inverse_rate(rate: Decimal) -> Decimal:
    """Calculate the inverse rate (1 / rate) at high precision."""
    if rate <= Decimal("0") or rate.is_nan() or rate.is_infinite():
        raise RateSanityError(
            f"Cannot invert invalid rate: {rate}",
            rate=str(rate),
        )

    with decimal.localcontext() as ctx:
        ctx.prec = 28
        return Decimal("1") / rate


def format_display_rate(rate: Decimal, decimal_places: int = DISPLAY_RATE_PRECISION) -> str:
    """Format rate for display rounded to the specified precision (default 8 decimals)."""
    exp = Decimal("1e-" + str(decimal_places))
    return str(rate.quantize(exp, rounding=decimal.ROUND_HALF_UP))
