"""Unit tests for timeseries statistical calculations."""

from decimal import Decimal

from app.services.timeseries_stats import compute_timeseries_statistics


def test_compute_timeseries_statistics_basic() -> None:
    """Test min, max, avg, start, end, and % change on a predictable dataset."""
    rates_by_date = {
        "2024-01-01": {"USD": Decimal("1.1000")},
        "2024-01-02": {"USD": Decimal("1.2000")},
        "2024-01-03": {"USD": Decimal("1.0500")},
        "2024-01-04": {"USD": Decimal("1.1500")},
    }

    stats = compute_timeseries_statistics(rates_by_date)
    assert "USD" in stats
    usd_stats = stats["USD"]

    # Start: 1.1000 on 2024-01-01, End: 1.1500 on 2024-01-04
    assert usd_stats.start_rate == "1.1000"
    assert usd_stats.end_rate == "1.1500"

    # Min: 1.0500 on 2024-01-03
    assert usd_stats.min_rate == "1.0500"
    assert usd_stats.min_date == "2024-01-03"

    # Max: 1.2000 on 2024-01-02
    assert usd_stats.max_rate == "1.2000"
    assert usd_stats.max_date == "2024-01-02"

    # Sum = 1.10 + 1.20 + 1.05 + 1.15 = 4.50
    # Avg = 4.50 / 4 = 1.12500000
    assert usd_stats.avg_rate == "1.12500000"

    # % Change = ((1.1500 - 1.1000) / 1.1000) * 100 = (0.05 / 1.10) * 100 = 4.545454...% -> 4.5455%
    assert usd_stats.change_pct == "4.5455"


def test_compute_timeseries_statistics_empty() -> None:
    """Empty mapping returns empty stats."""
    assert compute_timeseries_statistics({}) == {}


def test_compute_timeseries_statistics_multiple_symbols() -> None:
    """Test statistics computed independently for multiple currencies."""
    rates_by_date = {
        "2024-01-01": {"USD": Decimal("1.10"), "GBP": Decimal("0.85")},
        "2024-01-02": {"USD": Decimal("1.15"), "GBP": Decimal("0.80")},
    }

    stats = compute_timeseries_statistics(rates_by_date)
    assert "USD" in stats
    assert "GBP" in stats

    assert stats["USD"].change_pct == "4.5455"
    # GBP: ((0.80 - 0.85) / 0.85) * 100 = (-0.05 / 0.85) * 100 = -5.8824%
    assert stats["GBP"].change_pct == "-5.8824"
