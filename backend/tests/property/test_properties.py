"""Hypothesis property-based tests for financial conversion logic."""

from decimal import Decimal

import hypothesis.strategies as st
from hypothesis import given, settings

from app.core.currency_data import get_minor_units
from app.core.decimal_utils import calculate_inverse_rate, round_amount
from app.services.converter import ConversionEngine

# Strategy for realistic positive financial amounts (between 0.01 and 10,000,000)
st_amount = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("10000000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

# Strategy for positive exchange rates (between 0.0001 and 50000)
st_rate = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("50000"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)

# Supported currency codes
st_currency = st.sampled_from(["USD", "EUR", "GBP", "JPY", "KWD", "AUD", "CAD"])


@given(amount=st_amount, rate=st_rate, curr_from=st_currency, curr_to=st_currency)
@settings(max_examples=100)
def test_conversion_round_trip_within_tolerance(
    amount: Decimal,
    rate: Decimal,
    curr_from: str,
    curr_to: str,
) -> None:
    """Property: Round-trip conversion (convert then convert back) returns original amount

    within theoretical minor-unit quantization bounds.
    """
    effective_rate = Decimal("1") if curr_from == curr_to else rate

    # 1. Forward conversion
    forward = ConversionEngine.convert(amount, curr_from, curr_to, rate)
    converted_amount = Decimal(forward.converted_amount)

    # If the converted amount quantizes to 0 in the target currency,
    # then the amount is below target resolution:
    # (amount * effective_rate < 0.5 * 10^-target_minor_units)
    if converted_amount == Decimal("0"):
        target_minor = get_minor_units(curr_to)
        half_target_unit = (
            Decimal("0.5") if target_minor == 0 else Decimal("0.5e-" + str(target_minor))
        )
        assert amount * effective_rate <= half_target_unit
        return

    # 2. Convert back using inverse rate
    inverse_rate = Decimal(forward.inverse_rate)
    back = ConversionEngine.convert(converted_amount, curr_to, curr_from, inverse_rate)
    roundtrip_amount = Decimal(back.converted_amount)

    # 3. Maximum theoretical rounding error:
    # Converting to target currency introduces at most 0.5 * 10^-m_target rounding error.
    # When inverted back, this error scales by 1/rate.
    # In addition, rounding in source currency introduces at most 0.5 * 10^-m_source error.
    m_source = get_minor_units(curr_from)
    m_target = get_minor_units(curr_to)

    unit_target = Decimal("1") if m_target == 0 else Decimal("1e-" + str(m_target))
    unit_source = Decimal("1") if m_source == 0 else Decimal("1e-" + str(m_source))

    # Add small epsilon for floating inverse precision
    max_error = (
        (Decimal("0.5") * unit_target / effective_rate)
        + (Decimal("0.5") * unit_source)
        + Decimal("1e-6")
    )

    delta = abs(roundtrip_amount - amount)
    assert delta <= max_error


@given(rate=st_rate)
@settings(max_examples=100)
def test_inverse_rate_consistency(rate: Decimal) -> None:
    """Property: 1 / (1 / rate) == rate within 12 digits of precision."""
    inv = calculate_inverse_rate(rate)
    inv_inv = calculate_inverse_rate(inv)

    relative_error = abs(inv_inv - rate) / rate
    assert relative_error < Decimal("1e-12")


@given(a1=st_amount, a2=st_amount, rate=st_rate)
@settings(max_examples=100)
def test_conversion_monotonicity(a1: Decimal, a2: Decimal, rate: Decimal) -> None:
    """Property: If Amount A1 <= Amount A2, then Converted(A1) <= Converted(A2)."""
    low, high = (a1, a2) if a1 <= a2 else (a2, a1)

    res_low = ConversionEngine.convert(low, "USD", "EUR", rate)
    res_high = ConversionEngine.convert(high, "USD", "EUR", rate)

    assert Decimal(res_low.converted_amount) <= Decimal(res_high.converted_amount)


@given(amount=st_amount, curr=st_currency)
@settings(max_examples=50)
def test_same_currency_identity(amount: Decimal, curr: str) -> None:
    """Property: Converting from currency C to C preserves the amount up to minor units."""
    result = ConversionEngine.convert(amount, curr, curr, Decimal("1"))
    expected = round_amount(amount, get_minor_units(curr))

    assert result.rate == "1"
    assert result.inverse_rate == "1"
    assert Decimal(result.converted_amount) == expected
