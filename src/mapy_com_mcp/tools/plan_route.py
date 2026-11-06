"""MCP tool: plan_route."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from pydantic import Field

from ..links.urls import MAX_ROUTE_POINTS, Language, Point
from ..mapy_api.client import MapyAPIError, MapyClient
from ..mapy_api.routing import RouteType
from ..reports.route import (
    PROFILE_ROUTE_TYPES,
    NoElevationDataError,
    elevation,
    route_map,
    route_summary,
    route_viewport,
    route_warnings,
)
from ..static_map.render import grid_line


def register(mcp: FastMCP, *, client: MapyClient, **_: object) -> None:
    async def plan_route(
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
        language: Annotated[
            Language,
            Field(
                description=(
                    "Map label language. 'en' (default) for English, 'cs' "
                    "for Czech, 'sk' for Slovak, 'de' for German, 'pl' for "
                    "Polish."
                ),
            ),
        ] = "en",
    ) -> list[Image | str]:
        """Plan a route for yourself; the user sees nothing.

        Use this to work out a trip before you answer: how long a walk,
        ride or drive takes, whether stops fit into a day, how hilly it is.
        Returns the total and per-leg distance and time, warnings about
        points moved onto the network or lying in restricted areas, and a
        map image with the route and numbered points over a coordinate
        grid. On foot and by bike it adds an elevation profile with min/max
        and total ascent/descent.

        To show a route to the user, use show_route.
        """
        coords = [(p.lon, p.lat) for p in points]
        try:
            route = await client.route(coords, route_type=route_type, lang=language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            raise ToolError(f"Route planning failed: {exc}") from exc

        lines = route_summary(points, route_type, route)
        images: list[Image | str] = []
        notes: list[str] = []
        viewport = route_viewport(points, route)
        try:
            map_jpeg = await route_map(
                client, points, route_type, route, viewport, language
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            notes.append(f"Map image unavailable ({exc}).")
        else:
            images.append(Image(data=map_jpeg, format="jpeg"))
            notes.append(grid_line(viewport))

        if route_type in PROFILE_ROUTE_TYPES:
            try:
                profile = await elevation(client, route)
            except (MapyAPIError, httpx.HTTPError, NoElevationDataError) as exc:
                notes.append(f"Elevation profile unavailable ({exc}).")
            else:
                images.append(Image(data=profile.profile_jpeg, format="jpeg"))
                lines.append(profile.summary_line)

        text = [*lines, *route_warnings(points, route), *notes]
        return [*images, "\n".join(text)]

    mcp.tool(
        plan_route,
        annotations={
            "title": "Plan a route for yourself",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
