"""MCP tool: show_route."""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import MAX_ROUTE_POINTS, Language, Point, build_route_url
from ..mapy_api.client import MapyAPIError, MapyClient, StaticMapset
from ..mapy_api.routing import Route, RouteType
from ..static_map.profile import (
    ELEVATION_BATCH,
    climb_stats,
    render_profile,
    sample_positions,
)
from ..static_map.render import format_distance, grid_step_m, render
from ..static_map.viewport import fit_viewport

Output = Literal["url", "map", "both"]

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
_PROFILE_ROUTE_TYPES: frozenset[RouteType] = frozenset(
    {"foot_fast", "foot_hiking", "bike_road", "bike_mountain"}
)
_SNAP_WARNING_M = 50
_MIN_VALID_ELEVATION_M = -1000  # the API marks missing data as -100000


class _NoElevationDataError(Exception):
    """The route has no usable elevation profile (too short, or no data)."""


# Without an API key nothing can be planned or drawn, so `output` is hidden
# and fixed to "url" — the model never sees a choice that cannot work.
_URL_ONLY = {"output": ArgTransform(hide=True, default="url")}


def register(mcp: FastMCP, *, client: MapyClient | None = None, **_: object) -> None:
    async def show_route(
        points: Annotated[
            list[Point],
            Field(
                description=(
                    "The route in visit order: first point is the start, last "
                    "is the destination, anything between is a waypoint (at "
                    "most 15). Each point has WGS84 lon/lat and a short label."
                ),
                min_length=2,
                max_length=MAX_ROUTE_POINTS,
            ),
        ],
        route_type: Annotated[
            RouteType,
            Field(
                description=(
                    "Transport mode and optimization. car_fast / car_short for "
                    "driving; foot_fast for walking on streets; foot_hiking "
                    "for trails; bike_road for paved cycling; bike_mountain "
                    "for off-road."
                ),
            ),
        ],
        output: Annotated[
            Output,
            Field(
                description=(
                    "'both' (default): route summary, map image and elevation "
                    "profile for you, plus a mapy.com link for the user. 'map': "
                    "summary and images only. 'url': summary and link only — "
                    "no images, no elevation."
                ),
            ),
        ] = "both",
        language: Annotated[
            Language,
            Field(
                description=(
                    "UI and label language. 'en' (default) for English, "
                    "'cs' for Czech, 'sk' for Slovak, 'de' for German, "
                    "'pl' for Polish."
                ),
            ),
        ] = "en",
    ) -> str | list[Image | str]:
        """Plan a route through points, usually with a mapy.com link for the user.

        Use this when the user asks how to get from A to B, how long a walk,
        ride or drive takes, or wants a trip with stops. The map area is
        chosen automatically; you never pick a zoom or map style.

        When route planning is available (the `output` parameter is
        offered), it also returns the total and per-leg distance and time,
        warnings about points moved onto the network or lying in restricted
        areas, and — in 'map'/'both' — a map image with the route and
        numbered points over a coordinate grid. On foot and by bike it adds
        an elevation profile with min/max and total ascent/descent.

        Do NOT use this to merely show places on a map (use show_places).
        """
        url = build_route_url(points, route_type, language)
        if client is None:
            return url

        coords = [(p.lon, p.lat) for p in points]
        try:
            route = await client.route(coords, route_type=route_type, lang=language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Route planning failed: {exc}") from exc
            return f"Route planning failed ({exc}).\nMap link for the user: {url}"

        lines = _summary(points, route_type, route)
        warnings = _warnings(points, route)
        if output == "url":
            return "\n".join([*lines, *warnings, f"Map link for the user: {url}"])

        images: list[Image | str] = []
        notes: list[str] = []
        viewport = fit_viewport([*route.geometry, *coords])
        try:
            base = await client.static_map(
                lon=viewport.center_lon,
                lat=viewport.center_lat,
                zoom=viewport.zoom,
                width=viewport.width,
                height=viewport.height,
                mapset=_STATIC_MAPSET[route_type],
                lang=language,
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Map image unavailable: {exc}") from exc
            notes.append(f"Map image unavailable ({exc}).")
        else:
            map_jpeg = render(base, viewport, coords, route.geometry)
            images.append(Image(data=map_jpeg, format="jpeg"))
            grid = format_distance(grid_step_m(viewport))
            notes.append(f"Grid: {grid} between lines.")

        if route_type in _PROFILE_ROUTE_TYPES:
            try:
                profile_jpeg, elevation_line = await _elevation(client, route)
            except (MapyAPIError, httpx.HTTPError, _NoElevationDataError) as exc:
                notes.append(f"Elevation profile unavailable ({exc}).")
            else:
                images.append(Image(data=profile_jpeg, format="jpeg"))
                lines.append(elevation_line)

        text = [*lines, *warnings, *notes]
        if output == "both":
            text.append(f"Map link for the user: {url}")
        return [*images, "\n".join(text)]

    mcp.add_tool(
        Tool.from_tool(
            show_route,
            transform_args=_URL_ONLY if client is None else None,
            annotations=ToolAnnotations(
                title="Plan a route on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=client is not None,
            ),
        )
    )


def _summary(points: list[Point], route_type: RouteType, route: Route) -> list[str]:
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


def _warnings(points: list[Point], route: Route) -> list[str]:
    warnings: list[str] = []
    for number, (point, info) in enumerate(
        zip(points, route.points, strict=True), start=1
    ):
        name = f"{number}. {point.label}"
        if info.snap_distance_m > _SNAP_WARNING_M:
            moved = f"{info.snap_distance_m} m"
            warnings.append(f"{name} was moved {moved} to the nearest road or path.")
        if info.restriction is not None:
            kind = info.restriction.replace("_", " ").lower()
            warnings.append(f"{name} lies in a restricted area ({kind}).")
    return [f"Warnings: {' '.join(warnings)}"] if warnings else []


async def _elevation(client: MapyClient, route: Route) -> tuple[bytes, str]:
    """Profile image and the summary line, from sampled route elevations.

    Raises _NoElevationDataError when there is nothing to plot.
    """
    if route.length_m == 0 or len(route.geometry) < 2:
        raise _NoElevationDataError("route too short for a profile")
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
        raise _NoElevationDataError("no elevation data for this area")

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
