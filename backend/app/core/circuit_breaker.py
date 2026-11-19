"""Per-provider circuit breaker preventing cascading failures and fast-failing dead downstreams."""

import asyncio
import logging
import time
from enum import StrEnum

logger = logging.getLogger(__name__)


class CircuitState(StrEnum):
    """Circuit breaker state representation."""

    CLOSED = "CLOSED"  # Normal operation: requests pass through
    OPEN = "OPEN"  # Tripped: downstream failing, fail fast or failover immediately
    HALF_OPEN = "HALF_OPEN"  # Testing: allowing single probe request to check downstream recovery


class CircuitBreaker:
    """Thread-safe and async-safe circuit breaker."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self._lock = asyncio.Lock()

    async def allow_request(self) -> bool:
        """Check whether the circuit allows a request to proceed."""
        async with self._lock:
            now = time.monotonic()
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if now - self.last_failure_time >= self.recovery_timeout_seconds:
                    logger.info(
                        "Circuit breaker '%s' transition: OPEN -> HALF_OPEN (probing upstream)",
                        self.name,
                    )
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False

            # If HALF_OPEN, allow single probe attempt
            return True

    async def record_success(self) -> None:
        """Record successful upstream request, resetting failure counts."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                logger.info(
                    "Circuit breaker '%s' probe successful! Transition: HALF_OPEN -> CLOSED",
                    self.name,
                )
            self.state = CircuitState.CLOSED
            self.failure_count = 0

    async def record_failure(self) -> None:
        """Record upstream failure, tripping breaker if threshold exceeded."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker '%s' probe failed! Transition: HALF_OPEN -> OPEN",
                    self.name,
                )
                self.state = CircuitState.OPEN
            elif self.failure_count >= self.failure_threshold:
                logger.warning(
                    "Circuit breaker '%s' threshold reached (%d failures). "
                    "Transition: CLOSED -> OPEN",
                    self.name,
                    self.failure_count,
                )
                self.state = CircuitState.OPEN
