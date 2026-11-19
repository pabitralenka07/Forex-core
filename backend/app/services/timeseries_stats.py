"""High-precision Decimal statistics computation for exchange rate timeseries."""

from decimal import ROUND_HALF_UP, Decimal

from app.schemas.historical import TimeseriesStatsItem


def compute_timeseries_statistics(
    rates_by_date: dict[str, dict[str, Decimal]],
) -> dict[str, TimeseriesStatsItem]:
    """Calculate min, max, avg, start, end, and % change for each currency in Decimal.

    Args:
        rates_by_date: Mapping of date strings (YYYY-MM-DD) to {target_currency: Decimal rate}.

    Returns:
        Mapping of target_currency to TimeseriesStatsItem with string-serialized metrics.
    """
    if not rates_by_date:
        return {}

    # Sort dates chronologically
    sorted_dates = sorted(rates_by_date.keys())

    # Find all unique currency symbols across all dates
    all_symbols: set[str] = set()
    for rates in rates_by_date.values():
        all_symbols.update(rates.keys())

    statistics: dict[str, TimeseriesStatsItem] = {}

    for symbol in sorted(all_symbols):
        # Extract pairs for this symbol
        pairs: list[tuple[str, Decimal]] = [
            (d, rates_by_date[d][symbol]) for d in sorted_dates if symbol in rates_by_date[d]
        ]

        if not pairs:
            continue

        start_date, start_rate = pairs[0]
        end_date, end_rate = pairs[-1]

        min_date, min_rate = min(pairs, key=lambda p: p[1])
        max_date, max_rate = max(pairs, key=lambda p: p[1])

        # Compute arithmetic mean
        total_sum = sum((r for _, r in pairs), Decimal(0))
        count = Decimal(len(pairs))
        avg_rate = (total_sum / count).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

        # Compute percentage change
        if start_rate > Decimal(0):
            change_pct = (((end_rate - start_rate) / start_rate) * Decimal(100)).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        else:
            change_pct = Decimal(0)

        statistics[symbol] = TimeseriesStatsItem(
            min_rate=str(min_rate),
            min_date=min_date,
            max_rate=str(max_rate),
            max_date=max_date,
            avg_rate=str(avg_rate),
            start_rate=str(start_rate),
            end_rate=str(end_rate),
            change_pct=str(change_pct),
        )

    return statistics
