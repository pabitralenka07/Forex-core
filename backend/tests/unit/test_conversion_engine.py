"""Unit tests for Decimal conversion engine, rounding policies, limits, and cross rates."""

from decimal import Decimal

import pytest

from app.core.currency_data import get_minor_units
from app.core.decimal_utils import (
    MAX_AMOUNT,
    format_display_rate,
    parse_decimal_amount,
    round_amount,
    validate_currency_code,
)
from app.core.exceptions import (
    InvalidAmountError,
    InvalidCurrencyError,
    RateNotFoundError,
)
from app.services.converter import ConversionEngine


def test_minor_units_lookup() -> None:
    """Verify ISO 4217 minor unit exponents."""
    assert get_minor_units("JPY") == 0
    assert get_minor_units("KRW") == 0
    assert get_minor_units("USD") == 2
    assert get_minor_units("EUR") == 2
    assert get_minor_units("GBP") == 2
    assert get_minor_units("KWD") == 3
    assert get_minor_units("BHD") == 3
    assert get_minor_units("CLF") == 4
    # Unknown currencies default to 2
    assert get_minor_units("XYZ") == 2


def test_convert_jpy_zero_decimal_places() -> None:
    """Verify JPY conversion rounds to 0 decimal places."""
    amount = Decimal("100.50")
    rate = Decimal("159.4215")
    # 100.50 * 159.4215 = 16021.86075 -> rounded to 0 decimals = 16022
    result = ConversionEngine.convert(amount, "USD", "JPY", rate)

    assert result.from_currency == "USD"
    assert result.to_currency == "JPY"
    assert result.converted_amount == "16022"
    assert "." not in result.converted_amount
    assert result.target_minor_units == 0


def test_convert_kwd_three_decimal_places() -> None:
    """Verify KWD conversion rounds to 3 decimal places."""
    amount = Decimal("100.00")
    rate = Decimal("0.307567")
    # 100.00 * 0.307567 = 30.7567 -> rounded to 3 decimals = 30.757
    result = ConversionEngine.convert(amount, "USD", "KWD", rate)

    assert result.to_currency == "KWD"
    assert result.converted_amount == "30.757"
    assert result.target_minor_units == 3


def test_convert_same_currency_usd_to_usd() -> None:
    """Verify same currency conversion USD->USD returns rate 1 and formatted amount."""
    amount = Decimal("123.456")
    result = ConversionEngine.convert(amount, "USD", "USD", Decimal("1"))

    assert result.from_currency == "USD"
    assert result.to_currency == "USD"
    assert result.rate == "1"
    assert result.inverse_rate == "1"
    assert result.converted_amount == "123.46"  # Rounded to 2 decimals for USD


def test_reverse_conversion_usd_to_jpy() -> None:
    """Verify reverse conversion calculates how much USD is needed for target JPY."""
    target_amount = Decimal("10000")  # 10,000 JPY
    rate = Decimal("159.42")
    # 10000 / 159.42 = 62.72738677... -> rounded to 2 decimals (USD minor units) = 62.73
    result = ConversionEngine.reverse_convert(target_amount, "USD", "JPY", rate)

    assert result.from_currency == "USD"
    assert result.to_currency == "JPY"
    assert result.target_amount == "10000"
    assert result.required_from_amount == "62.73"
    assert result.from_minor_units == 2


def test_cross_rate_via_eur_pivot() -> None:
    """Verify cross rates computed via EUR pivot currency."""
    pivot = "EUR"
    rates_from_pivot = {
        "USD": Decimal("1.0900"),
        "GBP": Decimal("0.8500"),
        "JPY": Decimal("165.00"),
    }

    # Cross rate USD -> GBP: 0.8500 / 1.0900 = 0.7798165137...
    cross_usd_gbp = ConversionEngine.compute_cross_rate("USD", "GBP", pivot, rates_from_pivot)
    expected = Decimal("0.8500") / Decimal("1.0900")
    assert cross_usd_gbp == expected

    # Pivot to target: EUR -> USD = 1.0900
    assert ConversionEngine.compute_cross_rate("EUR", "USD", pivot, rates_from_pivot) == Decimal(
        "1.0900"
    )

    # Target to pivot: USD -> EUR = 1 / 1.0900
    usd_to_eur = ConversionEngine.compute_cross_rate("USD", "EUR", pivot, rates_from_pivot)
    assert usd_to_eur == Decimal("1") / Decimal("1.0900")

    # Missing currency raises RateNotFoundError
    with pytest.raises(RateNotFoundError):
        ConversionEngine.compute_cross_rate("USD", "XYZ", pivot, rates_from_pivot)


def test_rounding_policies_half_up_vs_half_even() -> None:
    """Verify ROUND_HALF_UP vs ROUND_HALF_EVEN (Banker's rounding)."""
    # 2.505 to 2 decimal places:
    # HALF_UP rounds to 2.51
    # HALF_EVEN rounds to 2.50 (nearest even last digit '0')
    val1 = Decimal("2.505")
    assert round_amount(val1, 2, "ROUND_HALF_UP") == Decimal("2.51")
    assert round_amount(val1, 2, "ROUND_HALF_EVEN") == Decimal("2.50")

    # 2.515 to 2 decimal places:
    # HALF_EVEN rounds to 2.52 (nearest even last digit '2')
    val2 = Decimal("2.515")
    assert round_amount(val2, 2, "ROUND_HALF_EVEN") == Decimal("2.52")


def test_parse_decimal_amount_valid_and_locale() -> None:
    """Verify parsing valid amounts and standard locale thousands separators."""
    assert parse_decimal_amount("100") == Decimal("100")
    assert parse_decimal_amount("1000.50") == Decimal("1000.50")
    assert parse_decimal_amount("1,000.50") == Decimal("1000.50")
    assert parse_decimal_amount("1,234,567.89") == Decimal("1234567.89")
    assert parse_decimal_amount(Decimal("50.25")) == Decimal("50.25")
    assert parse_decimal_amount(100) == Decimal("100")


def test_parse_decimal_amount_rejections() -> None:
    """Verify rejection of floats, negatives, scientific notation, and ambiguous formats."""
    # Rejects float
    with pytest.raises(InvalidAmountError, match="Float inputs are prohibited"):
        parse_decimal_amount(100.50)

    # Rejects negative and zero
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        parse_decimal_amount("-10.00")
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        parse_decimal_amount("0")

    # Rejects scientific notation
    with pytest.raises(InvalidAmountError, match="Scientific notation"):
        parse_decimal_amount("1e5")
    with pytest.raises(InvalidAmountError, match="Scientific notation"):
        parse_decimal_amount("2.5E-3")

    # Rejects ambiguous locale formats
    with pytest.raises(InvalidAmountError, match="Ambiguous or invalid"):
        parse_decimal_amount("1.000,50")
    with pytest.raises(InvalidAmountError, match="Ambiguous or invalid"):
        parse_decimal_amount("1,00.50")

    # Rejects over limits
    with pytest.raises(InvalidAmountError, match="exceeds maximum allowed limit"):
        parse_decimal_amount(str(MAX_AMOUNT + Decimal("1")))

    # Rejects more than 8 decimal places
    with pytest.raises(InvalidAmountError, match="exceeds maximum allowed decimal places"):
        parse_decimal_amount("1.123456789")


def test_validate_currency_code() -> None:
    """Verify 3-letter uppercase ISO currency code validation."""
    assert validate_currency_code("usd") == "USD"
    assert validate_currency_code(" EUR ") == "EUR"

    with pytest.raises(InvalidCurrencyError):
        validate_currency_code("US")
    with pytest.raises(InvalidCurrencyError):
        validate_currency_code("USDD")
    with pytest.raises(InvalidCurrencyError):
        validate_currency_code("123")


def test_format_display_rate() -> None:
    """Verify formatting exchange rates to 8 decimal places."""
    rate = Decimal("0.91174")
    assert format_display_rate(rate) == "0.91174000"
    rate_precise = Decimal("0.123456789")
    assert format_display_rate(rate_precise) == "0.12345679"
