"""Exchange rate provider abstraction and concrete adapters."""

from app.providers.base import RateProvider, RateResult, TimeseriesResult
from app.providers.exchangerate_api import ExchangeRateApiProvider
from app.providers.frankfurter import FrankfurterProvider

__all__ = [
    "RateProvider",
    "RateResult",
    "TimeseriesResult",
    "FrankfurterProvider",
    "ExchangeRateApiProvider",
]
