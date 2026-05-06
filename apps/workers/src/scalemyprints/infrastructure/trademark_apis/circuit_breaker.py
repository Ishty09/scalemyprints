"""
Circuit breaker for trademark provider chains.

Per-provider failure tracking with half-open recovery. When a provider
fails N times within a window, the breaker opens and short-circuits
subsequent calls for `cooldown_seconds`. After cooldown, one trial call is
allowed (half-open); success closes, failure reopens.

This module is pure logic — no I/O, fully testable. The chain runner uses
a breaker per (jurisdiction, provider) pair.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Too many failures; short-circuit
    HALF_OPEN = "half_open"  # Probationary single-call test


@dataclass
class CircuitBreakerConfig:
    """Tunable thresholds for the breaker."""

    # Number of consecutive failures before opening
    failure_threshold: int = 3
    # Seconds the breaker stays open before allowing a probe call
    cooldown_seconds: float = 60.0
    # Successful probes needed to close (we keep this at 1 — one good call wins)
    success_threshold: int = 1


@dataclass
class _State:
    """Mutable per-breaker state."""

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    """
    Async-safe circuit breaker.

    Usage:
        breaker = CircuitBreaker(name="us:markbase")
        if not await breaker.allow():
            return None  # short-circuit
        try:
            result = await provider.call()
        except Exception:
            await breaker.record_failure()
            raise
        else:
            await breaker.record_success()
            return result
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.name = name
        self._config = config or CircuitBreakerConfig()
        self._lock = asyncio.Lock()
        self._s = _State()

    async def allow(self) -> bool:
        """Return True if a call is permitted right now."""
        async with self._lock:
            now = time.monotonic()
            if self._s.state == CircuitState.CLOSED:
                return True
            if self._s.state == CircuitState.OPEN:
                # Cooldown elapsed?
                if now - self._s.opened_at >= self._config.cooldown_seconds:
                    self._s.state = CircuitState.HALF_OPEN
                    self._s.consecutive_successes = 0
                    logger.info("breaker_half_open", name=self.name)
                    return True
                return False
            # HALF_OPEN: allow exactly one probe at a time. To keep it simple
            # and since chains are sequential per request, we let it through.
            return True

    async def record_success(self) -> None:
        async with self._lock:
            if self._s.state == CircuitState.HALF_OPEN:
                self._s.consecutive_successes += 1
                if self._s.consecutive_successes >= self._config.success_threshold:
                    self._s.state = CircuitState.CLOSED
                    self._s.consecutive_failures = 0
                    self._s.consecutive_successes = 0
                    logger.info("breaker_closed", name=self.name)
            elif self._s.state == CircuitState.CLOSED:
                self._s.consecutive_failures = 0

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if self._s.state == CircuitState.HALF_OPEN:
                # Probe failed — back to OPEN, reset timer
                self._s.state = CircuitState.OPEN
                self._s.opened_at = now
                self._s.consecutive_successes = 0
                logger.warning("breaker_reopened", name=self.name)
                return
            if self._s.state == CircuitState.CLOSED:
                self._s.consecutive_failures += 1
                if self._s.consecutive_failures >= self._config.failure_threshold:
                    self._s.state = CircuitState.OPEN
                    self._s.opened_at = now
                    logger.warning(
                        "breaker_opened",
                        name=self.name,
                        consecutive_failures=self._s.consecutive_failures,
                        cooldown_seconds=self._config.cooldown_seconds,
                    )

    @property
    def state(self) -> CircuitState:
        return self._s.state
