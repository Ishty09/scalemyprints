"""
Result<T, E> — typed success/error returns.

Use for operations with predictable failure modes where you want to force
callers to handle both cases. Alternative to raising exceptions for expected
errors (e.g., "user not found" is expected; "database unreachable" isn't).

Example:
    def parse_number(s: str) -> Result[int, str]:
        try:
            return Ok(int(s))
        except ValueError:
            return Err(f"Not a number: {s}")

    result = parse_number("42")
    if result.is_ok():
        print(result.unwrap())
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Successful result with a value."""

    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Failed result with an error."""

    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self) -> T:  # type: ignore[type-var]
        raise ValueError(f"Called unwrap() on Err: {self.error}")

    def unwrap_or(self, default: U) -> U:
        return default


# Type alias for convenience
Result = Ok[T] | Err[E]
