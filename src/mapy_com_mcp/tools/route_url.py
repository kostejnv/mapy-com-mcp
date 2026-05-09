"""MCP tool: build_route_url."""

from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from ..urls import Language, RouteType
from ..urls import build_route_url as _compose_url


def register(mcp: FastMCP) -> None:
    def build_route_url(
        start_lon: Annotated[
            float,
            Field(description="WGS84 longitude of the start.", ge=-180, le=180),
        ],
        start_lat: Annotated[
            float,
            Field(description="WGS84 latitude of the start.", ge=-90, le=90),
        ],
        end_lon: Annotated[
            float,
            Field(description="WGS84 longitude of the destination.", ge=-180, le=180),
        ],
        end_lat: Annotated[
            float,
            Field(description="WGS84 latitude of the destination.", ge=-90, le=90),
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
        ] = "car_fast",
        waypoints: Annotated[
            list[tuple[float, float]] | None,
            Field(
                description=(
                    "Up to 15 intermediate (lon, lat) stops in visit order. "
                    "Omit for a direct A->B route."
                ),
                max_length=15,
            ),
        ] = None,
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
        """Build a mapy.com URL that opens a planned route between two points.

        Use this when the user asks how to get from A to B, or wants
        directions with intermediate stops. The map style is chosen
        automatically from route_type (car_* uses traffic, foot_*/bike_*
        use outdoor); the LLM does not pick it.

        Do NOT use this to merely show places on a map (use build_points_url).
        Do NOT pass more than 15 waypoints — mapy.com will reject them.

        The map auto-fits to the route, so there is no zoom parameter.
        """
        return _compose_url(
            start_lon=start_lon,
            start_lat=start_lat,
            end_lon=end_lon,
            end_lat=end_lat,
            route_type=route_type,
            waypoints=waypoints,
            language=language,
        )

    mcp.tool(
        build_route_url,
        annotations={
            "title": "Build mapy.com URL for a planned route",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
