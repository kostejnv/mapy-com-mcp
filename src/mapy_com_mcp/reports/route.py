"""A planned route as text, a map image and an elevation profile."""

from __future__ import annotations

import asyncio

from ..links.urls import Point
from ..mapy_api.client import MapyClient, StaticMapset
from ..mapy_api.routing import Route, RouteType
from ..static_map.profile import (
    ELEVATION_BATCH,
    climb_stats,
    render_profile,
    sample_positions,
)
from ..static_map.render import format_distance, grid_step_m, render
from ..static_map.viewport import fit_viewport

# The static map API has no traffic layer; basic is the closest look for cars.
_STATIC_MAPSET: dict[RouteType, StaticMapset] = {
    "car_fast": "basic",
    "car_short": "basic",
    "foot_fast": "outdoor",
    "foot_hiking": "outdoor",
    "bike_road": "outdoor",
    "bike_mountain": "outdoor",
}
# Elevation matters on foot and by bike; for cars it is noise and extra cost.
PROFILE_ROUTE_TYPES: frozenset[RouteType] = frozenset(
    {"foot_fast", "foot_hiking", "bike_road", "bike_mountain"}
)
_SNAP_WARNING_M = 50
_MIN_VALID_ELEVATION_M = -1000  # the API marks missing data as -100000


class NoElevationDataError(Exception):
    """The route has no usable elevation profile (too short, or no data)."""


def route_summary(
    points: list[Point], route_type: RouteType, route: Route
) -> list[str]:
    """Total length and time, then one line per leg."""
    lines = [
        f"Route ({route_type}): {_format_length(route.length_m)}, "
        f"{_format_duration(route.duration_s)}"
    ]
    # One line per leg, also for a single leg: it ties the marker numbers to
    # the labels.
    for number, leg in enumerate(route.legs, start=1):
        lines.append(
            f"{number}. {points[number - 1].label} → "
            f"{number + 1}. {points[number].label}: "
            f"{_format_length(leg.length_m)}, {_format_duration(leg.duration_s)}"
        )
    return lines


def route_warnings(points: list[Point], route: Route) -> list[str]:
    """Points moved onto the network or lying in restricted areas, if any."""
    found: list[str] = []
    for number, (point, info) in enumerate(
        zip(points, route.points, strict=True), start=1
    ):
        name = f"{number}. {point.label}"
        if info.snap_distance_m > _SNAP_WARNING_M:
            moved = f"{info.snap_distance_m} m"
            found.append(f"{name} was moved {moved} to the nearest road or path.")
        if info.restriction is not None:
            kind = info.restriction.replace("_", " ").lower()
            found.append(f"{name} lies in a restricted area ({kind}).")
    return [f"Warnings: {' '.join(found)}"] if found else []


async def route_map(
    client: MapyClient,
    points: list[Point],
    route_type: RouteType,
    route: Route,
    language: str,
) -> tuple[bytes, str]:
    """JPEG of the route with numbered points, and the grid-spacing line."""
    coords = [(p.lon, p.lat) for p in points]
    viewport = fit_viewport([*route.geometry, *coords])
    base = await client.static_map(
        lon=viewport.center_lon,
        lat=viewport.center_lat,
        zoom=viewport.zoom,
        width=viewport.width,
        height=viewport.height,
        mapset=_STATIC_MAPSET[route_type],
        lang=language,
    )
    grid = format_distance(grid_step_m(viewport))
    return render(
        base, viewport, coords, route.geometry
    ), f"Grid: {grid} between lines."


async def elevation(client: MapyClient, route: Route) -> tuple[bytes, str]:
    """Profile image and the summary line, from sampled route elevations.

    Raises NoElevationDataError when there is nothing to plot.
    """
    if route.length_m == 0 or len(route.geometry) < 2:
        raise NoElevationDataError("route too short for a profile")
    samples = sample_positions(route.geometry)
    batches = [
        [(lon, lat) for lon, lat, _ in samples[i : i + ELEVATION_BATCH]]
        for i in range(0, len(samples), ELEVATION_BATCH)
    ]
    heights = [
        h
        for batch in await asyncio.gather(*map(client.elevation, batches))
        for h in batch
    ]
    profile = [
        (d, h)
        for (_, _, d), h in zip(samples, heights, strict=True)
        if h > _MIN_VALID_ELEVATION_M
    ]
    if len(profile) < 2:
        raise NoElevationDataError("no elevation data for this area")

    # Route points sit at the cumulative leg lengths, scaled from the router's
    # length to the sampled line's length so they land on the same axis.
    scale = samples[-1][2] / route.length_m
    point_distances = [0.0]
    for leg in route.legs:
        point_distances.append(point_distances[-1] + leg.length_m * scale)

    stats = climb_stats([h for _, h in profile])
    line = (
        f"Elevation: min {stats.min_m:.0f} m, max {stats.max_m:.0f} m, "
        f"ascent +{stats.ascent_m:.0f} m, descent -{stats.descent_m:.0f} m"
    )
    return render_profile(profile, point_distances, stats), line


def _format_length(meters: int) -> str:
    rounded = round(meters, -1)
    return f"{meters / 1000:.1f} km" if rounded >= 1000 else f"{rounded} m"


def _format_duration(seconds: int) -> str:
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"
