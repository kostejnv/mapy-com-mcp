"""MCP tool: show_route."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import MAX_ROUTE_POINTS, Language, Point, build_route_url
from ..map_view import MAP_VIEW_TOOL_META, client_shows_map_view, map_view_meta
from ..mapy_api.client import MapyAPIError, MapyClient
from ..mapy_api.routing import RouteType
from ..reports.route import (
    PROFILE_ROUTE_TYPES,
    Elevation,
    NoElevationDataError,
    elevation,
    route_map,
    route_summary,
    route_viewport,
    route_warnings,
)


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
        language: Annotated[
            Language,
            Field(
                description=(
                    "Language of the map labels and the link: 'en' (default) "
                    "for English, 'cs' for Czech, 'sk' for Slovak, 'de' for "
                    "German, 'pl' for Polish. Use the user's language. The "
                    "inline map's own text is Czech for 'cs', else English."
                ),
            ),
        ] = "en",
    ) -> ToolResult:
        """Show the user a route through points, with distance and time.

        Use this when the user asks how to get from A to B, how long a walk,
        ride or drive takes, or wants a trip with stops. The map area is
        chosen automatically; you never pick a zoom or map style.

        You get the total and per-leg distance and time and warnings about
        points moved onto the network or lying in restricted areas. In
        clients that can show it, the user sees the route on a map right in
        the chat — on foot and by bike with an elevation profile — and a
        button that opens it on mapy.com; elsewhere you get a mapy.com link
        to give the user. The reply says which happened.

        Do NOT use this to merely show places on a map (use show_places).
        To plan a route for yourself without showing the user, use
        plan_route.
        """
        url = build_route_url(points, route_type, language)
        shows_view = client_shows_map_view()
        coords = [(p.lon, p.lat) for p in points]
        try:
            route = await client.route(coords, route_type=route_type, lang=language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            if not shows_view:
                return ToolResult(
                    f"Route planning failed ({exc}). Give the user this mapy.com "
                    f"link to the route: {url}"
                )
            return ToolResult(
                f"Route planning failed ({exc}); the user sees only an "
                '"Open on Mapy.com" button for the route.',
                meta=map_view_meta(url, language),
            )

        lines = route_summary(points, route_type, route)
        warnings = route_warnings(points, route)
        if not shows_view:
            link = f"Give the user this mapy.com link to the route: {url}"
            return ToolResult("\n".join([*lines, *warnings, link]))

        notes: list[str] = []
        viewport = route_viewport(points, route, landscape_only=True)
        map_jpeg: bytes | None = None
        try:
            map_jpeg = await route_map(
                client, points, route_type, route, viewport, language, grid=False
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            notes.append(f"The map image could not be drawn ({exc}).")

        profile: Elevation | None = None
        if route_type in PROFILE_ROUTE_TYPES:
            try:
                profile = await elevation(client, route)
            except (MapyAPIError, httpx.HTTPError, NoElevationDataError) as exc:
                notes.append(f"Elevation profile unavailable ({exc}).")
            else:
                lines.append(profile.summary_line)

        # The view draws the elevation profile on top of the map: no map, no profile.
        profile_shown = profile if map_jpeg is not None else None
        meta = map_view_meta(
            url,
            language,
            map_jpeg=map_jpeg,
            route_length_m=route.length_m,
            route_duration_s=route.duration_s,
            profile_jpeg=profile_shown.profile_jpeg if profile_shown else None,
            elevation_sparkline=profile_shown.sparkline if profile_shown else None,
        )
        shown = _what_the_user_sees(
            has_map=map_jpeg is not None, has_profile=profile_shown is not None
        )
        return ToolResult("\n".join([*lines, *warnings, *notes, shown]), meta=meta)

    mcp.add_tool(
        Tool.from_tool(
            show_route,
            meta=MAP_VIEW_TOOL_META,
            annotations=ToolAnnotations(
                title="Show a route on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
    )


def _what_the_user_sees(*, has_map: bool, has_profile: bool) -> str:
    parts = ["the route on a map"] if has_map else []
    parts.append("its length and time")
    if has_profile:
        parts.append("an elevation profile")
    return (
        f"The user now sees, in the chat, {', '.join(parts)} and an "
        '"Open on Mapy.com" button. Don\'t repeat the link or restate these '
        "numbers; add only what helps, e.g. whether the route fits their plans."
    )
