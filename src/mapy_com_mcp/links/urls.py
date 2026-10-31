"""Pure URL builders for mapy.com. No HTTP, no API key, no I/O."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from ..mapy_api.routing import RouteType
from ..static_map.viewport import Viewport
from .uc_encoder import encode_uc

Language = Literal["en", "cs", "sk", "de", "pl"]
PointsMapset = Literal["outdoor", "traffic", "winter", "aerial", "basic"]

_LEGACY_PATH: dict[PointsMapset, str] = {
    "outdoor": "turisticka",
    "traffic": "dopravni",
    "winter": "zimni",
    "aerial": "letecka",
    "basic": "zakladni",
}
_MAX_WAYPOINTS = 15
MAX_ROUTE_POINTS = _MAX_WAYPOINTS + 2  # start + waypoints + end


class Point(BaseModel):
    lon: float = Field(
        description="WGS84 longitude in decimal degrees.",
        ge=-180,
        le=180,
    )
    lat: float = Field(
        description="WGS84 latitude in decimal degrees.",
        ge=-90,
        le=90,
    )
    label: str = Field(
        description="Marker tooltip — short place name (e.g. 'Charles Bridge').",
        min_length=1,
    )
    description: str | None = Field(
        default=None,
        description=(
            "Optional longer text shown in the marker's info bubble — "
            "e.g. why this place is on the list, hours, notes."
        ),
    )


def build_points_url(
    points: list[Point],
    viewport: Viewport,
    mapset: PointsMapset = "outdoor",
    language: Language = "en",
) -> str:
    """Compose a mapy.com URL that opens the map showing labeled points.

    Pure function — no HTTP, no API key. Center and zoom come from
    `viewport`, the same one the static map image uses. Raises ToolError on
    empty input.
    """
    if not points:
        raise ToolError("points must contain at least one point.")
    if len(points) == 1:
        return _build_single_point_url(points[0], viewport, mapset, language)
    return _build_multi_point_url(points, viewport, mapset, language)


def _build_single_point_url(
    point: Point,
    viewport: Viewport,
    mapset: PointsMapset,
    language: Language,
) -> str:
    """Compose the official `/fnc/v1/showmap` URL for one point.

    Stable, documented endpoint. Trade-off vs. the multi-point path: showmap
    does not support per-marker label/description, so `point.label` and
    `point.description` are not rendered — they still serve as inputs the
    LLM is forced to think about.
    """
    # showmap draws its marker at the map center, so center stays on the
    # point; only the zoom comes from the shared viewport.
    parts = [
        f"center={point.lon},{point.lat}",
        f"zoom={viewport.zoom}",
        "marker=true",
        f"mapset={mapset}",
        f"lang={language}",
    ]
    return "https://mapy.com/fnc/v1/showmap?" + "&".join(parts)


def _build_multi_point_url(
    points: list[Point],
    viewport: Viewport,
    mapset: PointsMapset,
    language: Language,
) -> str:
    """Compose the legacy `vlastni-body` URL for two or more points.

    Undocumented but the only mapy.com URL pattern that renders multiple
    custom markers with labels and descriptions. Marker titles are numbered
    to match the markers in the static map image.
    """
    uc = encode_uc([(p.lon, p.lat) for p in points])

    parts: list[str] = ["vlastni-body"]
    for number, p in enumerate(points, start=1):
        parts.append("ut=" + quote(f"{number}. {p.label}"))
    parts.append("uc=" + quote(uc))
    for p in points:
        parts.append("ud=" + quote(p.description or ""))
    parts.append(f"x={round(viewport.center_lon, 6)}")
    parts.append(f"y={round(viewport.center_lat, 6)}")
    parts.append(f"z={viewport.zoom}")
    return f"https://mapy.com/{language}/{_LEGACY_PATH[mapset]}?" + "&".join(parts)


def build_route_url(
    points: list[Point],
    route_type: RouteType,
    language: Language = "en",
) -> str:
    """Compose a mapy.com URL that opens a planned route through `points`.

    First point is the start, last the end, the rest are waypoints in visit
    order. Map style is auto-derived from `route_type` (car_* uses traffic,
    foot_*/bike_* uses outdoor). Map auto-fits to the route, so there is
    no zoom argument. Raises ToolError for fewer than 2 points or more than
    15 waypoints.
    """
    if not 2 <= len(points) <= MAX_ROUTE_POINTS:
        raise ToolError(
            f"A route needs a start, an end and at most {_MAX_WAYPOINTS} "
            f"waypoints, got {len(points)} points."
        )
    start, *waypoints, end = points
    mapset = "traffic" if route_type.startswith("car_") else "outdoor"
    parts = [
        f"start={start.lon},{start.lat}",
        f"end={end.lon},{end.lat}",
        f"routeType={route_type}",
        f"mapset={mapset}",
        f"lang={language}",
    ]
    if waypoints:
        joined = ";".join(f"{p.lon},{p.lat}" for p in waypoints)
        parts.append(f"waypoints={quote(joined, safe=',;')}")
    return "https://mapy.com/fnc/v1/route?" + "&".join(parts)
