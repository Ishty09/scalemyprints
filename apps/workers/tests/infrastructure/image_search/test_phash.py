"""Tests for the perceptual-hash helpers (no image loading — pure math)."""

from __future__ import annotations

from scalemyprints.infrastructure.image_search.phash import hamming_distance


def test_identical_distance_is_zero() -> None:
    assert hamming_distance(0xDEADBEEFCAFEBABE, 0xDEADBEEFCAFEBABE) == 0


def test_single_bit_flip() -> None:
    assert hamming_distance(0b101010, 0b101000) == 1


def test_full_difference_is_64() -> None:
    a = 0xFFFFFFFFFFFFFFFF
    b = 0x0000000000000000
    assert hamming_distance(a, b) == 64
