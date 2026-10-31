"""Tests for static_map/profile.py — sampling, climb stats, profile chart."""

from __future__ import annotations

import io
import itertools

import pytest
from PIL import Image

from mapy_com_mcp.static_map.profile import (
    ELEVATION_BATCH,
    climb_stats,
    render_profile,
    sample_positions,
)

# One degree of longitude at lat 50 is about 71.5 km.
_SHORT = [(14.40, 50.0), (14.41, 50.0)]  # ~0.7 km
_20_KM = [(14.0, 50.0), (14.28, 50.0)]
_200_KM = [(14.0, 50.0), (16.8, 50.0)]


@pytest.mark.parametrize(
    "line,expected",
    [(_SHORT, 256), (_20_KM, 512), (_200_KM, 1024)],
)
def test_sample_count_is_whole_batches_capped_at_four(
    line: list[tuple[float, float]], expected: int
) -> None:
    samples = sample_positions(line)
    assert len(samples) == expected
    assert len(samples) % ELEVATION_BATCH == 0


def test_sample_distances_start_at_zero_end_at_total_and_increase() -> None:
    samples = sample_positions(_20_KM)
    distances = [d for _, _, d in samples]
    assert distances[0] == 0
    assert distances[-1] == pytest.approx(20_000, rel=0.02)
    assert all(a < b for a, b in itertools.pairwise(distances))


def test_sample_ends_match_route_ends() -> None:
    samples = sample_positions(_SHORT)
    assert samples[0][:2] == pytest.approx(_SHORT[0])
    assert samples[-1][:2] == pytest.approx(_SHORT[-1])


def test_samples_are_evenly_spaced_across_unequal_segments() -> None:
    line = [(14.0, 50.0), (14.01, 50.0), (14.11, 50.0)]  # 0.7 km then 7 km
    samples = sample_positions(line)
    gaps = [b[2] - a[2] for a, b in itertools.pairwise(samples)]
    assert max(gaps) == pytest.approx(min(gaps))


def test_samples_lie_on_bent_line() -> None:
    line = [(14.0, 50.0), (14.1, 50.0), (14.1, 50.1)]
    for lon, lat, _ in sample_positions(line):
        assert lat == pytest.approx(50.0) or lon == pytest.approx(14.1)


def test_climb_stats_ignores_noise_below_dead_band() -> None:
    stats = climb_stats([100, 101, 100, 101, 100, 101, 100])
    assert stats.ascent_m == 0
    assert stats.descent_m == 0
    assert (stats.min_m, stats.max_m) == (100, 101)


def test_climb_stats_counts_a_ten_meter_climb() -> None:
    stats = climb_stats([100, 105, 110])
    assert stats.ascent_m == 10
    assert stats.descent_m == 0


def test_climb_stats_counts_ascent_and_descent_separately() -> None:
    stats = climb_stats([100, 120, 90, 95])
    assert stats.ascent_m == 25
    assert stats.descent_m == 30
    assert (stats.min_m, stats.max_m) == (90, 120)


def test_climb_stats_slow_drift_accumulates() -> None:
    stats = climb_stats([100 + 0.5 * i for i in range(41)])  # +20 m in tiny steps
    assert stats.ascent_m == pytest.approx(20, abs=2)


@pytest.mark.parametrize("heights", [[300.0, 310.0], [200.0] * 5, [0.0, 50.0, 20.0]])
def test_render_profile_returns_1024x280_jpeg(heights: list[float]) -> None:
    profile = [(i * 1000.0, h) for i, h in enumerate(heights)]
    stats = climb_stats(heights)
    out = render_profile(profile, [0.0, profile[-1][0]], stats)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (1024, 280)
