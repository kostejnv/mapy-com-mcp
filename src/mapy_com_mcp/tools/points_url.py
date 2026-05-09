"""MCP tool: build_points_url."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ..urls import Language, Point, PointsMapset
from ..urls import build_points_url as _compose_url


def register(mcp: FastMCP) -> None:
    def build_points_url(
        points: Annotated[
            list[Point],
            Field(
                description=(
                    "One or more points to show. Each point has WGS84 lon/lat, "
                    "a required short label (the marker tooltip), and an "
                    "optional longer description (the info bubble). Tested up "
                    "to 50 points; larger lists may work but are not validated "
                    "and could produce malformed URLs or unreadable maps."
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
                    "UI and label language. 'en' (default) for English, "
                    "'cs' for Czech, 'sk' for Slovak, 'de' for German, "
                    "'pl' for Polish."
                ),
            ),
        ] = "en",
    ) -> str:
        """Build a mapy.com URL that opens the map showing labeled points.

        Use this whenever the user wants to see places on a map — single
        location, search results, a list of POIs, or any 'show me where X
        is'. Works for one point or many; the operation is the same.

        The map zoom is chosen automatically so all points fit in view (a
        single point opens at neighborhood level). The LLM does not pick zoom.

        Tested with up to 50 points. Larger lists may work but are not
        validated; behavior is undefined.

        Do NOT use this to plan a route between points (use build_route_url).
        """
        return _compose_url(points=points, mapset=mapset, language=language)

    mcp.tool(
        build_points_url,
        annotations={
            "title": "Build mapy.com URL for one or more points",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
