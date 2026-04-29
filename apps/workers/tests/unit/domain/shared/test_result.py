"""Tests for Result type."""

from __future__ import annotations

import pytest

from scalemyprints.domain.shared.result import Err, Ok


class TestOk:
    def test_is_ok_true(self) -> None:
        assert Ok(42).is_ok() is True
        assert Ok(42).is_err() is False

    def test_unwrap_returns_value(self) -> None:
        assert Ok(42).unwrap() == 42

    def test_unwrap_or_returns_value(self) -> None:
        assert Ok(42).unwrap_or(0) == 42

    def test_frozen(self) -> None:
        ok = Ok(42)
        with pytest.raises(AttributeError):
            ok.value = 100  # type: ignore[misc]


class TestErr:
    def test_is_err_true(self) -> None:
        assert Err("bad").is_err() is True
        assert Err("bad").is_ok() is False

    def test_unwrap_raises(self) -> None:
        with pytest.raises(ValueError, match="unwrap"):
            Err("bad").unwrap()

    def test_unwrap_or_returns_default(self) -> None:
        assert Err("bad").unwrap_or(0) == 0
