"""Background periodic rate refresh scheduler."""

import asyncio
import contextlib
import logging
from datetime import datetime

from app.config import get_settings
from app.database.repository import RateRepository
from app.database.session import async_session_factory
from app.services.rate_service import RateService

logger = logging.getLogger("currency_converter.scheduler")

# High-volume currencies to keep persistently warm in DB cache
BACKGROUND_REFRESH_CURRENCIES: list[str] = ["EUR", "USD", "GBP", "JPY", "CHF"]


class RateRefreshScheduler:
    """Manages asynchronous periodic background rate synchronization."""

    def __init__(self, interval_seconds: int | None = None) -> None:
        self.settings = get_settings()
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else self.settings.background_refresh_interval_seconds
        )
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def _refresh_worker(self) -> None:
        """Periodic background refresh worker loop."""
        logger.info(
            "Background rate refresh scheduler started (interval: %ds).",
            self.interval_seconds,
        )
        service = RateService()

        while not self._stop_event.is_set():
            try:
                logger.info(
                    "Executing scheduled rate refresh for currencies: %s",
                    BACKGROUND_REFRESH_CURRENCIES,
                )
                async with async_session_factory() as session:
                    repo = RateRepository(session)
                    for base in BACKGROUND_REFRESH_CURRENCIES:
                        try:
                            rate_result = await service.get_rates(base=base)
                            rate_date = datetime.strptime(rate_result.rate_date, "%Y-%m-%d").date()
                            await repo.save_rates(
                                base=base,
                                rates=rate_result.rates,
                                rate_date=rate_date,
                                provider=rate_result.provider,
                            )
                        except Exception as curr_err:
                            logger.warning(
                                "Scheduled refresh failed for base '%s': %s",
                                base,
                                curr_err,
                            )
                    await session.commit()
                logger.info("Scheduled rate refresh cycle completed successfully.")
            except Exception as loop_err:
                logger.error("Error during scheduled rate refresh cycle: %s", loop_err)

            # Wait for interval or stop event
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=float(self.interval_seconds),
                )
            except TimeoutError:
                continue

        logger.info("Background rate refresh scheduler stopped.")

    def start(self) -> None:
        """Start the background refresh task if enabled."""
        if not self.settings.background_refresh_enabled:
            logger.info("Background rate refresh scheduler is disabled by configuration.")
            return

        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._refresh_worker())

    async def stop(self) -> None:
        """Signal the background task to stop and wait for termination."""
        if self._task and not self._task.done():
            self._stop_event.set()
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


# Module singleton
_scheduler_instance: RateRefreshScheduler | None = None


def get_scheduler() -> RateRefreshScheduler:
    """Return singleton instance of the RateRefreshScheduler."""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = RateRefreshScheduler()
    return _scheduler_instance
