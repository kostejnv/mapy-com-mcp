"""MCP tool: inspect_places."""

from __future__ import annotations

from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from pydantic import Field

from ..links.urls import Language, Point, PointsMapset
from ..mapy_api.client import MapyAPIError, MapyClient
from ..reports.places import legend, places_map
from ..static_map.viewport import fit_viewport


def register(mcp: FastMCP, *, client: MapyClient, **_: object) -> None:
    async def inspect_places(
        points: Annotated[
            list[Point],
            Field(
                description=(
                    "One or more points to look at. Each point has WGS84 "
                    "lon/lat and a required short label. Tested up to 50 "
                    "points."
                ),
                min_length=1,
            ),
        ],
        mapset: Annotated[
            PointsMapset,
            Field(
                description=(
                    "Map style: 'outdoor' (default) for terrain, paths and "
                    "sights; 'aerial' for satellite imagery; 'winter' for "
                    "ski areas; 'basic' or 'traffic' for a plain street map."
                ),
            ),
        ] = "outdoor",
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
        """Look at places on a map yourself; the user sees nothing.

        Use this to check how places relate before you answer: are they
        close, which side of the river or the hill, is one on the way to
        another. Returns a map image with the points numbered in input order
        and a coordinate grid (line spacing given in the reply), so you can
        read positions and distances straight off it. The map area and zoom
        are chosen automatically.

        To show places to the user, use show_places. To check a route
        between them, use plan_route.
        """
        viewport = fit_viewport([(p.lon, p.lat) for p in points])
        try:
            jpeg = await places_map(client, points, viewport, mapset, language)
        except (MapyAPIError, httpx.HTTPError) as exc:
            raise ToolError(f"Map image unavailable: {exc}") from exc
        return [Image(data=jpeg, format="jpeg"), legend(points, viewport)]

    mcp.tool(
        inspect_places,
        annotations={
            "title": "Look at places on a map",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
