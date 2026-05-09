"""Tests for _uc_encoder.py — delta-encoded coordinate stream for mapy.com."""

from __future__ import annotations

import pytest

from mapy_com_mcp._uc_encoder import (
    _ALPHABET,  # type: ignore[reportPrivateUsage]
    _serialize_number,  # type: ignore[reportPrivateUsage]
    encode_uc,
)

# ---------------------------------------------------------------------------
# encode_uc — top-level function
# ---------------------------------------------------------------------------


def test_encode_uc_empty_list_returns_empty_string() -> None:
    assert encode_uc([]) == ""


def test_encode_uc_known_fixture_prague_castle() -> None:
    """Byte-for-byte match against the output verified with the reference snippet."""
    assert encode_uc([(14.4003, 50.0907)]) == "9gy-5xXyYv"


def test_encode_uc_all_output_chars_in_alphabet() -> None:
    points = [(14.4003, 50.0907), (14.4145, 50.0876)]
    result = encode_uc(points)
    assert all(ch in _ALPHABET for ch in result), (
        f"Unexpected chars in output: {set(result) - set(_ALPHABET)}"
    )


def test_encode_uc_50_points_produces_non_empty_valid_string() -> None:
    """Upper-documented bound of 50 points: output is non-empty and all chars valid."""
    points = [(14.0 + 0.001 * i, 50.0 + 0.0005 * i) for i in range(50)]
    result = encode_uc(points)
    assert result
    assert all(ch in _ALPHABET for ch in result)


def test_encode_uc_single_point_is_10_chars() -> None:
    """Any single point encodes from prev=(0,0); both axes use absolute branch.

    5 chars per axis → 10 total.
    """
    result = encode_uc([(0.0, 0.0)])
    assert len(result) == 10


# ---------------------------------------------------------------------------
# Branch coverage: _serialize_number
#
# Three branches:
#   small  : -1024 <= delta < 1024   → 2 chars
#   medium : -32768 <= delta < 32768 → 3 chars  (exclusive of small range)
#   absolute: otherwise               → 5 chars
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delta",
    [0, 1, -1, 1023, -1023, -1024],
    ids=["zero", "pos_small", "neg_small", "upper_bound", "lower_bound", "exact_lower"],
)
def test_serialize_number_small_delta_produces_2_chars(delta: int) -> None:
    result = _serialize_number(delta, abs(delta) + 100_000)
    assert len(result) == 2, f"Expected 2 chars for delta={delta}, got {len(result)}"


@pytest.mark.parametrize(
    "delta",
    [1024, -1025, 32767, -32767],
    ids=[
        "just_above_small",
        "just_below_small_neg",
        "upper_medium",
        "lower_medium_neg",
    ],
)
def test_serialize_number_medium_delta_produces_3_chars(delta: int) -> None:
    result = _serialize_number(delta, abs(delta) + 100_000)
    assert len(result) == 3, f"Expected 3 chars for delta={delta}, got {len(result)}"


@pytest.mark.parametrize(
    "delta,absolute",
    [(32768, 50_000), (-32769, 100_000), (1_000_000, 5_000_000)],
    ids=["just_above_medium", "just_below_medium_neg", "large_absolute"],
)
def test_serialize_number_absolute_fallback_produces_5_chars(
    delta: int, absolute: int
) -> None:
    result = _serialize_number(delta, absolute)
    assert len(result) == 5, f"Expected 5 chars for delta={delta}, got {len(result)}"


def test_serialize_number_small_delta_output_chars_in_alphabet() -> None:
    result = _serialize_number(0, 100_000)
    assert all(ch in _ALPHABET for ch in result)


def test_serialize_number_medium_delta_output_chars_in_alphabet() -> None:
    result = _serialize_number(1024, 100_000)
    assert all(ch in _ALPHABET for ch in result)


def test_serialize_number_absolute_output_chars_in_alphabet() -> None:
    result = _serialize_number(32768, 50_000)
    assert all(ch in _ALPHABET for ch in result)


# ---------------------------------------------------------------------------
# Branch reachability via encode_uc (per-axis, second point)
#
# First point always triggers absolute (delta = huge raw value).
# Second point's per-axis branch depends on coordinate gap.
#   small   (<0.00138°) → 2-char x-contribution, output = 10 + 2 + 2 = 14
#   medium  (~0.003°)   → 3-char x-contribution, output = 10 + 3 + 2 = 15
#   absolute (>0.044°)  → 5-char x-contribution, output = 10 + 5 + 2 = 17
# ---------------------------------------------------------------------------


def test_encode_uc_second_point_small_delta_branch() -> None:
    """0.001° lon gap → small branch (2 chars) for x-axis of second point.

    Total: first-point abs+abs (10) + second-point small+small (2+2) = 14.
    """
    points = [(0.0, 0.0), (0.001, 0.0)]
    result = encode_uc(points)
    assert len(result) == 14


def test_encode_uc_second_point_medium_delta_branch() -> None:
    """0.003° lon gap → medium branch (3 chars) for x-axis of second point.

    Total: first-point abs+abs (10) + second-point medium+small (3+2) = 15.
    """
    points = [(0.0, 0.0), (0.003, 0.0)]
    result = encode_uc(points)
    assert len(result) == 15


def test_encode_uc_second_point_absolute_fallback_branch() -> None:
    """0.05° lon gap → absolute branch (5 chars) for x-axis of second point.

    Total: first-point abs+abs (10) + second-point abs+small (5+2) = 17.
    """
    points = [(0.0, 0.0), (0.05, 0.0)]
    result = encode_uc(points)
    assert len(result) == 17
