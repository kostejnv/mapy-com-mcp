"""MCP tool: show_route."""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import MAX_ROUTE_POINTS, Language, Point, build_route_url
from ..mapy_api.client import MapyAPIError, MapyClient
from ..mapy_api.routing import RouteType
from ..reports.route import (
    PROFILE_ROUTE_TYPES,
    NoElevationDataError,
    elevation,
    route_map,
    route_summary,
    route_warnings,
)

Output = Literal["url", "map", "both"]


def register(mcp: FastMCP, *, client: MapyClient, **_: object) -> None:
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

        It returns the total and per-leg distance and time,
        warnings about points moved onto the network or lying in restricted
        areas, and — in 'map'/'both' — a map image with the route and
        numbered points over a coordinate grid. On foot and by bike it adds
        an elevation profile with min/max and total ascent/descent.

        Do NOT use this to merely show places on a map (use show_places).
        To plan a route for yourself without showing the user, use
        plan_route.
        """
        url = build_route_url(points, route_type, language)
        coords = [(p.lon, p.lat) for p in points]
        try:
            route = await client.route(coords, route_type=route_type, lang=language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Route planning failed: {exc}") from exc
            return f"Route planning failed ({exc}).\nMap link for the user: {url}"

        lines = route_summary(points, route_type, route)
        warnings = route_warnings(points, route)
        if output == "url":
            return "\n".join([*lines, *warnings, f"Map link for the user: {url}"])

        images: list[Image | str] = []
        notes: list[str] = []
        try:
            map_jpeg, grid_line = await route_map(
                client, points, route_type, route, language
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Map image unavailable: {exc}") from exc
            notes.append(f"Map image unavailable ({exc}).")
        else:
            images.append(Image(data=map_jpeg, format="jpeg"))
            notes.append(grid_line)

        if route_type in PROFILE_ROUTE_TYPES:
            try:
                profile_jpeg, elevation_line = await elevation(client, route)
            except (MapyAPIError, httpx.HTTPError, NoElevationDataError) as exc:
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
            annotations=ToolAnnotations(
                title="Plan a route on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
    )
