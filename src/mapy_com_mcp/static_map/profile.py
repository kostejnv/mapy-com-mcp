"""Elevation profile of a route: where to sample, climb stats, the chart.

No HTTP — the caller fetches elevations for the planned positions.
"""

from __future__ import annotations

import io
import itertools
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

ELEVATION_BATCH = 256  # positions per elevation API call
_TARGET_SPACING_M = 50
_MAX_BATCHES = 4  # caps cost; longer routes get a coarser profile instead
_NOISE_M = 2.0  # elevation-model wiggles below this don't count as climbing

_EARTH_RADIUS_M = 6_371_000
_JPEG_QUALITY = 88

_WIDTH, _HEIGHT = 1024, 280
_PAD_LEFT, _PAD_RIGHT, _PAD_TOP, _PAD_BOTTOM = 72, 230, 42, 34
_AXIS_TEXT = (90, 90, 90, 255)
_GRIDLINE = (225, 225, 225, 255)
_LINE = (30, 100, 230, 255)
_FILL = (205, 222, 248, 255)
_MARKER = (215, 25, 32, 255)
_PANEL = (245, 245, 245, 255)


@dataclass(frozen=True)
class ClimbStats:
    min_m: float
    max_m: float
    ascent_m: float
    descent_m: float


def sample_positions(
    route: list[tuple[float, float]],
) -> list[tuple[float, float, float]]:
    """Evenly spaced (lon, lat, distance_m) samples along the route line.

    Every elevation call costs the same however many positions it carries, so
    the first call is always filled; more calls only when the spacing would
    exceed _TARGET_SPACING_M, up to _MAX_BATCHES.
    """
    cumulative = [0.0]
    for a, b in itertools.pairwise(route):
        cumulative.append(cumulative[-1] + _haversine(a, b))
    total = cumulative[-1]
    batches = max(
        1, min(_MAX_BATCHES, math.ceil(total / (ELEVATION_BATCH * _TARGET_SPACING_M)))
    )
    count = ELEVATION_BATCH * batches

    samples: list[tuple[float, float, float]] = []
    segment = 0
    for i in range(count):
        target = total * i / (count - 1)
        while segment < len(route) - 2 and cumulative[segment + 1] < target:
            segment += 1
        seg_len = cumulative[segment + 1] - cumulative[segment]
        t = (target - cumulative[segment]) / seg_len if seg_len else 0.0
        (lon0, lat0), (lon1, lat1) = route[segment], route[segment + 1]
        samples.append((lon0 + (lon1 - lon0) * t, lat0 + (lat1 - lat0) * t, target))
    return samples


def climb_stats(elevations: list[float]) -> ClimbStats:
    """Min, max and total ascent/descent, ignoring noise below _NOISE_M."""
    ascent = descent = 0.0
    reference = elevations[0]
    for h in elevations[1:]:
        if h - reference >= _NOISE_M:
            ascent += h - reference
            reference = h
        elif reference - h >= _NOISE_M:
            descent += reference - h
            reference = h
    return ClimbStats(min(elevations), max(elevations), ascent, descent)


def render_profile(
    profile: list[tuple[float, float]], point_distances: list[float], stats: ClimbStats
) -> bytes:
    """Chart of (distance_m, elevation_m) with numbered route points; JPEG.

    `point_distances` are the route points' positions along the line, in the
    same order as their numbers on the map.
    """
    img = Image.new("RGBA", (_WIDTH, _HEIGHT), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    small, medium, large = (ImageFont.load_default(size=s) for s in (12, 14, 16))

    total = profile[-1][0]
    span = max(stats.max_m - stats.min_m, 20)
    low, high = stats.min_m - span * 0.1, stats.max_m + span * 0.15
    plot_w = _WIDTH - _PAD_LEFT - _PAD_RIGHT
    plot_h = _HEIGHT - _PAD_TOP - _PAD_BOTTOM
    bottom = _PAD_TOP + plot_h

    def x_of(distance: float) -> float:
        return _PAD_LEFT + distance / total * plot_w

    def y_of(elevation: float) -> float:
        return _PAD_TOP + (high - elevation) / (high - low) * plot_h

    step = _nice_step(high - low, 4)
    elevation = math.ceil(low / step) * step
    while elevation <= high:
        y = y_of(elevation)
        draw.line([(_PAD_LEFT, y), (_WIDTH - _PAD_RIGHT, y)], fill=_GRIDLINE, width=1)
        draw.text(
            (_PAD_LEFT - 14, y),  # clear of the start marker on the axis
            f"{elevation:.0f} m",
            fill=_AXIS_TEXT,
            font=small,
            anchor="rm",
        )
        elevation += step
    step = _nice_step(total, 6)
    distance = 0.0
    while distance <= total + 1:
        draw.text(
            (x_of(distance), bottom + 6),
            _format_km(distance),
            fill=_AXIS_TEXT,
            font=small,
            anchor="mt",
        )
        distance += step

    curve = [(x_of(d), y_of(e)) for d, e in profile]
    draw.polygon([*curve, (x_of(total), bottom), (x_of(0), bottom)], fill=_FILL)
    draw.line(curve, fill=_LINE, width=3, joint="curve")
    draw.line(
        [(_PAD_LEFT, bottom), (_WIDTH - _PAD_RIGHT, bottom)], fill=_AXIS_TEXT, width=1
    )

    for number, at in enumerate(point_distances, start=1):
        nearest = min(profile, key=lambda sample: abs(sample[0] - at))
        cx, cy = x_of(at), y_of(nearest[1])
        draw.ellipse(
            (cx - 11, cy - 11, cx + 11, cy + 11), fill=_MARKER, outline="white", width=2
        )
        draw.text((cx, cy), str(number), fill="white", font=medium, anchor="mm")

    panel_x = _WIDTH - _PAD_RIGHT + 18
    draw.rounded_rectangle(
        (panel_x, _PAD_TOP - 10, _WIDTH - 12, _HEIGHT - 16), radius=8, fill=_PANEL
    )
    rows = [
        ("min", f"{stats.min_m:.0f} m"),
        ("max", f"{stats.max_m:.0f} m"),
        ("ascent", f"+{stats.ascent_m:.0f} m"),
        ("descent", f"-{stats.descent_m:.0f} m"),
        ("distance", _format_km(total)),
    ]
    for row, (name, value) in enumerate(rows):
        y = _PAD_TOP + 8 + row * 30
        draw.text((panel_x + 14, y), name, fill=_AXIS_TEXT, font=medium)
        draw.text((_WIDTH - 26, y), value, fill="black", font=large, anchor="ra")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat0, lat1 = math.radians(a[1]), math.radians(b[1])
    d_lat, d_lon = lat1 - lat0, math.radians(b[0] - a[0])
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat0) * math.cos(lat1) * math.sin(d_lon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _nice_step(span: float, target_lines: int) -> float:
    magnitude = 10 ** math.floor(math.log10(span / target_lines))
    candidates = [m * magnitude for m in (1, 2, 5, 10)]
    return min(candidates, key=lambda step: abs(span / step - target_lines))


def _format_km(meters: float) -> str:
    return f"{meters / 1000:.1f} km" if meters >= 1000 else f"{round(meters)} m"
