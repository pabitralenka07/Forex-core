"""Validation helpers for currency codes, amounts, and dates."""

import re
from datetime import UTC, date, datetime

from app.core.exceptions import ValidationError

ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EARLIEST_PROVIDER_DATE = date(1999, 1, 4)  # European Central Bank reference rate inception


def validate_iso_date(date_str: str) -> date:
    """Validate and parse an ISO 8601 date string (YYYY-MM-DD).

    Enforces that date:
    1. Matches YYYY-MM-DD format strictly.
    2. Is a valid calendar date.
    3. Is not in the future (compared to current UTC date).
    4. Is not earlier than the provider's earliest coverage (1999-01-04).
    """
    if not isinstance(date_str, str) or not ISO_DATE_REGEX.match(date_str.strip()):
        raise ValidationError(
            f"Invalid date format '{date_str}'. Expected ISO format 'YYYY-MM-DD'.",
            param="date",
        )

    try:
        parsed_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError(
            f"Invalid calendar date '{date_str}': {exc}",
            param="date",
        ) from exc

    today_utc = datetime.now(UTC).date()
    if parsed_date > today_utc:
        raise ValidationError(
            f"Date '{date_str}' is in the future. Today is '{today_utc.isoformat()}'.",
            param="date",
        )

    if parsed_date < EARLIEST_PROVIDER_DATE:
        raise ValidationError(
            f"Date '{date_str}' is before provider coverage "
            f"({EARLIEST_PROVIDER_DATE.isoformat()}).",
            param="date",
        )

    return parsed_date


def validate_date_range(start_str: str, end_str: str) -> tuple[date, date]:
    """Validate that start_date and end_date form a valid non-inverted historical range."""
    start_d = validate_iso_date(start_str)
    end_d = validate_iso_date(end_str)

    if start_d > end_d:
        raise ValidationError(
            f"Start date '{start_str}' must be on or before end date '{end_str}'.",
            param="start_date",
        )

    return start_d, end_d
