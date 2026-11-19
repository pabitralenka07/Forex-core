"""Unit tests for the background rate refresh scheduler."""

import pytest

from app.services.scheduler import RateRefreshScheduler


@pytest.mark.asyncio
async def test_scheduler_start_and_stop() -> None:
    """Test clean startup and teardown of the scheduler."""
    scheduler = RateRefreshScheduler(interval_seconds=60)
    scheduler.start()
    assert scheduler._task is not None
    assert not scheduler._task.done()

    await scheduler.stop()
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_scheduler_disabled_via_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that scheduler does not launch task when disabled."""
    scheduler = RateRefreshScheduler(interval_seconds=60)
    monkeypatch.setattr(scheduler.settings, "background_refresh_enabled", False)

    scheduler.start()
    assert scheduler._task is None
