"""MCP tool: show_places."""

from __future__ import annotations

from typing import Annotated, Literal

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools import Tool
from fastmcp.tools.tool_transform import ArgTransform
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations
from pydantic import Field

from ..links.urls import Language, Point, PointsMapset, build_points_url
from ..mapy_api.client import MapyAPIError, MapyClient, StaticMapset
from ..static_map.render import format_distance, grid_step_m, render
from ..static_map.viewport import Viewport, fit_viewport

Output = Literal["url", "map", "both"]

# The static map API has no traffic layer; basic is the closest look.
_STATIC_MAPSET: dict[PointsMapset, StaticMapset] = {
    "outdoor": "outdoor",
    "traffic": "basic",
    "winter": "winter",
    "aerial": "aerial",
    "basic": "basic",
}

# Without an API key there is no map image, so `output` is hidden and fixed
# to "url" — the model never sees a choice that cannot work.
_URL_ONLY = {"output": ArgTransform(hide=True, default="url")}


def register(mcp: FastMCP, *, client: MapyClient | None = None, **_: object) -> None:
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
                    "mapy.com link for the user. 'map': only the image, e.g. "
                    "while you reason about where places are. 'url': only the "
                    "link, when you don't need to see the map."
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

        When map images are available (the `output` parameter is offered),
        it can also return a map image for you: points numbered in input
        order and a coordinate grid (line spacing given in the reply), so
        you can read positions and distances straight off it. The link
        opens at the same zoom, with the same numbers.

        Do NOT use this to plan a route between points (use show_route).
        """
        coords = [(p.lon, p.lat) for p in points]
        viewport = fit_viewport(coords)
        url = build_points_url(points, viewport, mapset, language)
        if output == "url":
            return url

        assert client is not None  # `output` is fixed to "url" without a key
        legend = _legend(points, viewport)
        try:
            base = await client.static_map(
                lon=viewport.center_lon,
                lat=viewport.center_lat,
                zoom=viewport.zoom,
                width=viewport.width,
                height=viewport.height,
                mapset=_STATIC_MAPSET[mapset],
                lang=language,
            )
        except (MapyAPIError, httpx.HTTPError) as exc:
            if output == "map":
                raise ToolError(f"Map image unavailable: {exc}") from exc
            return f"Map image unavailable ({exc}).\nMap link for the user: {url}"

        image = Image(data=render(base, viewport, coords), format="jpeg")
        if output == "map":
            return [image, legend]
        return [image, f"{legend}\nMap link for the user: {url}"]

    mcp.add_tool(
        Tool.from_tool(
            show_places,
            transform_args=_URL_ONLY if client is None else None,
            annotations=ToolAnnotations(
                title="Show places on a map",
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=client is not None,
            ),
        )
    )


def _legend(points: list[Point], viewport: Viewport) -> str:
    lines = [f"{number}. {p.label}" for number, p in enumerate(points, start=1)]
    lines.append(f"Grid: {format_distance(grid_step_m(viewport))} between lines.")
    return "\n".join(lines)
