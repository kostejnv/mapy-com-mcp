"""MCP tool: show_places."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.tools import Tool, ToolResult
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import Language, Point, PointsMapset, build_points_url
from ..map_view import MAP_VIEW_TOOL_META, client_shows_map_view, map_view_meta
from ..mapy_api.client import MapyAPIError, MapyClient
from ..reports.places import numbered_labels, places_map
from ..static_map.viewport import fit_viewport

_SHOWN = (
    "The user now sees these places on a map in the chat, numbered as below, "
    'with an "Open on Mapy.com" button. Don\'t repeat the link or describe '
    "the map; add only what helps, e.g. a short answer or next steps."
)


def register(mcp: FastMCP, *, client: MapyClient, **_: object) -> None:
    async def show_places(
        points: Annotated[
            list[Point],
            Field(
                description=(
                    "One or more points to show. Each point has WGS84 lon/lat, "
                    "a required short label, and an optional longer description "
                    "(shown in the link's info bubble). Tested up to 50 points."
                ),
                min_length=1,
            ),
        ],
        mapset: Annotated[
            PointsMapset,
            Field(
                description=(
                    "Map style. Pick by what the user is doing: 'outdoor' "
                    "(default) for walking, biking, hiking, and city "
                    "sightseeing; 'traffic' for driving or car-related plans; "
                    "'winter' for skiing and winter-sports areas; 'aerial' "
                    "for satellite/photographic imagery; 'basic' for a plain "
                    "street map. When in doubt, use 'outdoor'."
                ),
            ),
        ] = "outdoor",
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
        """Show places to the user on a map.

        Use this whenever the user should see places on a map — a single
        location, search results, a list of POIs, or 'are these close to
        each other?'. The map area and zoom are chosen automatically so all
        points fit; you never pick a zoom.

        In clients that can show it, the user sees the map right in the
        chat, with numbered markers and a button that opens it on
        mapy.com; elsewhere you get a mapy.com link to give the user. The
        reply says which happened and lists the marker numbers.

        Do NOT use this to plan a route between points (use show_route).
        To look at places yourself without showing the user, use
        inspect_places.
        """
        labels = numbered_labels(points)
        coords = [(p.lon, p.lat) for p in points]
        if not client_shows_map_view():
            url = build_points_url(points, fit_viewport(coords), mapset, language)
            return ToolResult(
                f"Give the user this mapy.com link to the places: {url}\n{labels}"
            )

        viewport = fit_viewport(coords, landscape_only=True)
        url = build_points_url(points, viewport, mapset, language)
        try:
            jpeg = await places_map(
                client, points, viewport, mapset, language, grid=False
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            return ToolResult(
                f"The map image could not be drawn ({exc}); the user sees only "
                f'an "Open on Mapy.com" button for these places.\n{labels}',
                meta=map_view_meta(url, language),
            )
        return ToolResult(
            f"{_SHOWN}\n{labels}",
            meta=map_view_meta(url, language, map_jpeg=jpeg),
        )

    mcp.add_tool(
        Tool.from_tool(
            show_places,
            meta=MAP_VIEW_TOOL_META,
            annotations=ToolAnnotations(
                title="Show places on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
    )
