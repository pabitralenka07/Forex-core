"""Financial conversion engine executing high-precision Decimal conversions."""

from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.currency_data import get_minor_units
from app.core.decimal_utils import (
    calculate_inverse_rate,
    round_amount,
    validate_currency_code,
)
from app.core.exceptions import RateNotFoundError, RateSanityError


class ConversionResult(BaseModel):
    """Result of a forward currency conversion."""

    from_currency: str = Field(..., description="Source currency code (normalized ISO 4217)")
    to_currency: str = Field(..., description="Target currency code (normalized ISO 4217)")
    amount: str = Field(..., description="Original input amount (serialized string)")
    rate: str = Field(..., description="Exchange rate used (full provider precision string)")
    inverse_rate: str = Field(..., description="Inverse exchange rate (serialized string)")
    converted_amount: str = Field(
        ...,
        description="Converted amount rounded to target currency minor units",
    )
    target_minor_units: int = Field(..., description="Minor units used for final rounding")


class ReverseConversionResult(BaseModel):
    """Result of a reverse currency conversion (how much FROM is needed for target TO)."""

    from_currency: str = Field(..., description="Source currency code (normalized ISO 4217)")
    to_currency: str = Field(..., description="Target currency code (normalized ISO 4217)")
    target_amount: str = Field(..., description="Desired target amount (serialized string)")
    required_from_amount: str = Field(
        ...,
        description="Amount of from_currency required to receive target_amount",
    )
    rate: str = Field(..., description="Exchange rate (from -> to) used")
    inverse_rate: str = Field(..., description="Inverse exchange rate (to -> from) used")
    from_minor_units: int = Field(..., description="Minor units used for final rounding")


class ConversionEngine:
    """Core financial conversion engine strictly operating on Decimals."""

    @staticmethod
    def convert(
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        rounding_policy: str | None = None,
    ) -> ConversionResult:
        """Convert a source amount to target currency.

        Only the FINAL amount is rounded to the target currency's minor units.
        Same-currency conversion explicitly returns rate=1 and inverse_rate=1.
        """
        source = validate_currency_code(from_currency)
        target = validate_currency_code(to_currency)
        target_minor_units = get_minor_units(target)

        # Same-currency conversion handling (USD -> USD)
        if source == target:
            final_amount = round_amount(amount, target_minor_units, rounding_policy)
            return ConversionResult(
                from_currency=source,
                to_currency=target,
                amount=str(amount),
                rate="1",
                inverse_rate="1",
                converted_amount=str(final_amount),
                target_minor_units=target_minor_units,
            )

        if rate <= Decimal("0") or rate.is_nan() or rate.is_infinite():
            raise RateSanityError(
                f"Cannot convert with invalid exchange rate: {rate}",
                rate=str(rate),
                pair=f"{source}/{target}",
            )

        # High-precision raw conversion, rounding ONLY the final amount
        raw_converted = amount * rate
        final_amount = round_amount(raw_converted, target_minor_units, rounding_policy)
        inverse_rate = calculate_inverse_rate(rate)

        return ConversionResult(
            from_currency=source,
            to_currency=target,
            amount=str(amount),
            rate=str(rate),
            inverse_rate=str(inverse_rate),
            converted_amount=str(final_amount),
            target_minor_units=target_minor_units,
        )

    @staticmethod
    def reverse_convert(
        target_amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate: Decimal,
        rounding_policy: str | None = None,
    ) -> ReverseConversionResult:
        """Determine how much FROM currency is required to obtain target_amount of TO currency.

        Required FROM amount is rounded to from_currency's minor units.
        """
        source = validate_currency_code(from_currency)
        target = validate_currency_code(to_currency)
        from_minor_units = get_minor_units(source)

        if source == target:
            final_required = round_amount(target_amount, from_minor_units, rounding_policy)
            return ReverseConversionResult(
                from_currency=source,
                to_currency=target,
                target_amount=str(target_amount),
                required_from_amount=str(final_required),
                rate="1",
                inverse_rate="1",
                from_minor_units=from_minor_units,
            )

        if rate <= Decimal("0") or rate.is_nan() or rate.is_infinite():
            raise RateSanityError(
                f"Cannot reverse convert with invalid exchange rate: {rate}",
                rate=str(rate),
                pair=f"{source}/{target}",
            )

        # target_amount = required_amount * rate  =>  required_amount = target_amount / rate
        raw_required = target_amount / rate
        final_required = round_amount(raw_required, from_minor_units, rounding_policy)
        inverse_rate = calculate_inverse_rate(rate)

        return ReverseConversionResult(
            from_currency=source,
            to_currency=target,
            target_amount=str(target_amount),
            required_from_amount=str(final_required),
            rate=str(rate),
            inverse_rate=str(inverse_rate),
            from_minor_units=from_minor_units,
        )

    @staticmethod
    def compute_cross_rate(
        from_currency: str,
        to_currency: str,
        pivot: str,
        rates_from_pivot: dict[str, Decimal],
    ) -> Decimal:
        """Compute cross rate between from_currency and to_currency using a pivot currency.

        Assumes rates_from_pivot maps target currencies relative to 1 unit of pivot.
        For example: pivot=EUR, rates_from_pivot={'USD': 1.09, 'GBP': 0.85}
        Cross rate USD -> GBP = rate(EUR->GBP) / rate(EUR->USD) = 0.85 / 1.09.
        """
        source = validate_currency_code(from_currency)
        target = validate_currency_code(to_currency)
        pivot_norm = validate_currency_code(pivot)

        if source == target:
            return Decimal("1")

        # Pivot to source rate
        if source == pivot_norm:
            rate_pivot_to_source = Decimal("1")
        elif source in rates_from_pivot:
            rate_pivot_to_source = rates_from_pivot[source]
        else:
            raise RateNotFoundError(
                f"Pivot rate missing for base currency '{source}' via pivot '{pivot_norm}'",
                base=pivot_norm,
                target=source,
            )

        # Pivot to target rate
        if target == pivot_norm:
            rate_pivot_to_target = Decimal("1")
        elif target in rates_from_pivot:
            rate_pivot_to_target = rates_from_pivot[target]
        else:
            raise RateNotFoundError(
                f"Pivot rate missing for target currency '{target}' via pivot '{pivot_norm}'",
                base=pivot_norm,
                target=target,
            )

        if rate_pivot_to_source <= Decimal("0"):
            raise RateSanityError(
                f"Non-positive pivot rate encountered for '{source}': {rate_pivot_to_source}",
                rate=str(rate_pivot_to_source),
                pair=f"{pivot_norm}/{source}",
            )

        cross_rate = rate_pivot_to_target / rate_pivot_to_source
        if cross_rate <= Decimal("0") or cross_rate.is_nan() or cross_rate.is_infinite():
            raise RateSanityError(
                f"Invalid calculated cross rate: {cross_rate}",
                rate=str(cross_rate),
                pair=f"{source}/{target}",
            )

        return cross_rate
