"""MCP tool: show_places."""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import Language, Point, PointsMapset, build_points_url
from ..mapy_api.client import MapyAPIError, MapyClient
from ..reports.places import legend, places_map
from ..static_map.viewport import fit_viewport

Output = Literal["url", "map", "both"]


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
        output: Annotated[
            Output,
            Field(
                description=(
                    "'both' (default): a map image for you to look at plus a "
                    "mapy.com link for the user. 'map': only the image. "
                    "'url': only the link, when you don't need to see the map."
                ),
            ),
        ] = "both",
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
                    "UI and label language. 'en' (default) for English, "
                    "'cs' for Czech, 'sk' for Slovak, 'de' for German, "
                    "'pl' for Polish."
                ),
            ),
        ] = "en",
    ) -> str | list[Image | str]:
        """Show places on a map: a mapy.com link for the user.

        Use this whenever places should be seen on a map — a single
        location, search results, a list of POIs, or 'are these close to
        each other?'. The map area and zoom are chosen automatically so all
        points fit; you never pick a zoom.

        It can also return a map image for you: points numbered in input
        order and a coordinate grid (line spacing given in the reply), so
        you can read positions and distances straight off it. The link
        opens at the same zoom, with the same numbers.

        Do NOT use this to plan a route between points (use show_route).
        To look at places yourself without showing the user, use
        inspect_places.
        """
        viewport = fit_viewport([(p.lon, p.lat) for p in points])
        url = build_points_url(points, viewport, mapset, language)
        if output == "url":
            return url

        try:
            jpeg = await places_map(client, points, viewport, mapset, language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Map image unavailable: {exc}") from exc
            return f"Map image unavailable ({exc}).\nMap link for the user: {url}"

        image = Image(data=jpeg, format="jpeg")
        text = legend(points, viewport)
        if output == "map":
            return [image, text]
        return [image, f"{text}\nMap link for the user: {url}"]

    mcp.add_tool(
        Tool.from_tool(
            show_places,
            annotations=ToolAnnotations(
                title="Show places on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=True,
            ),
        )
    )
