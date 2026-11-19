"""ISO 4217 Currency data, minor units specification, and metadata."""

# ISO 4217 currency minor units (exponent) mapping.
# Standard reference: ISO 4217 Amendment updates.
ISO_4217_MINOR_UNITS: dict[str, int] = {
    # 0 decimal places (no minor unit or minor unit not in practical use)
    "BIF": 0,
    "CLP": 0,
    "DJF": 0,
    "GNF": 0,
    "ISK": 0,
    "JPY": 0,
    "KMF": 0,
    "KRW": 0,
    "PYG": 0,
    "RWF": 0,
    "UGX": 0,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
    # 3 decimal places
    "BHD": 3,
    "IQD": 3,
    "JOD": 3,
    "KWD": 3,
    "LYD": 3,
    "OMR": 3,
    "TND": 3,
    # 4 decimal places
    "CLF": 4,
    "UYW": 4,
}

DEFAULT_MINOR_UNITS: int = 2


def get_minor_units(currency_code: str) -> int:
    """Return the ISO 4217 minor unit exponent for a currency code.

    Defaults to 2 for standard world currencies not explicitly listed as 0, 3, or 4.
    """
    normalized = currency_code.strip().upper()
    return ISO_4217_MINOR_UNITS.get(normalized, DEFAULT_MINOR_UNITS)
