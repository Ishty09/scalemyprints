"""Shared domain primitives used across multiple features."""

from scalemyprints.domain.shared.clock import Clock, SystemClock
from scalemyprints.domain.shared.result import Err, Ok, Result

__all__ = ["Clock", "Err", "Ok", "Result", "SystemClock"]
