"""Pure URL builders for mapy.com. No HTTP, no API key, no I/O."""

from __future__ import annotations

from typing import Literal
from urllib.parse import quote

from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from ._uc_encoder import encode_uc

Language = Literal["en", "cs", "sk", "de", "pl"]
PointsMapset = Literal["outdoor", "traffic", "winter", "aerial", "basic"]
RouteType = Literal[
    "car_fast",
    "car_short",
    "foot_fast",
    "foot_hiking",
    "bike_road",
    "bike_mountain",
]

_LEGACY_PATH: dict[PointsMapset, str] = {
    "outdoor": "turisticka",
    "traffic": "dopravni",
    "winter": "zimni",
    "aerial": "letecka",
    "basic": "zakladni",
}
_MAX_WAYPOINTS = 15


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


def _auto_fit_zoom(points: list[Point]) -> int:
    """Pick a zoom level that fits all points with margin.

    Single point falls back to 13 (neighborhood-level), the default for
    'show me where this is'. Multiple points use the larger of lon/lat
    bounding-box span to drop into the right zoom bucket.
    """
    if len(points) == 1:
        return 13
    lon_span = max(p.lon for p in points) - min(p.lon for p in points)
    lat_span = max(p.lat for p in points) - min(p.lat for p in points)
    span = max(lon_span, lat_span)
    if span > 20:
        return 5
    if span > 5:
        return 8
    if span > 1:
        return 11
    if span > 0.1:
        return 13
    if span > 0.02:
        return 15
    if span > 0.005:
        return 17
    return 19


def build_points_url(
    points: list[Point],
    mapset: PointsMapset = "outdoor",
    language: Language = "en",
) -> str:
    """Compose a mapy.com URL that opens the map showing labeled points.

    Pure function — no HTTP, no API key. Map zoom is chosen automatically
    so all points fit. Raises ToolError on empty input.
    """
    if not points:
        raise ToolError("points must contain at least one point.")
    if len(points) == 1:
        return _build_single_point_url(points[0], mapset, language)
    return _build_multi_point_url(points, mapset, language)


def _build_single_point_url(
    point: Point,
    mapset: PointsMapset,
    language: Language,
) -> str:
    """Compose the official `/fnc/v1/showmap` URL for one point.

    Stable, documented endpoint. Trade-off vs. the multi-point path: showmap
    does not support per-marker label/description, so `point.label` and
    `point.description` are not rendered — they still serve as inputs the
    LLM is forced to think about.
    """
    parts = [
        f"center={point.lon},{point.lat}",
        f"zoom={_auto_fit_zoom([point])}",
        "marker=true",
        f"mapset={mapset}",
        f"lang={language}",
    ]
    return "https://mapy.com/fnc/v1/showmap?" + "&".join(parts)


def _build_multi_point_url(
    points: list[Point],
    mapset: PointsMapset,
    language: Language,
) -> str:
    """Compose the legacy `vlastni-body` URL for two or more points.

    Undocumented but the only mapy.com URL pattern that renders multiple
    custom markers with labels and descriptions.
    """
    center_lon = round(sum(p.lon for p in points) / len(points), 6)
    center_lat = round(sum(p.lat for p in points) / len(points), 6)
    zoom = _auto_fit_zoom(points)
    uc = encode_uc([(p.lon, p.lat) for p in points])

    parts: list[str] = ["vlastni-body"]
    for p in points:
        parts.append("ut=" + quote(p.label))
    parts.append("uc=" + quote(uc))
    for p in points:
        parts.append("ud=" + quote(p.description or ""))
    parts.append(f"x={center_lon}")
    parts.append(f"y={center_lat}")
    parts.append(f"z={zoom}")
    return f"https://mapy.com/{language}/{_LEGACY_PATH[mapset]}?" + "&".join(parts)


def build_route_url(
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    route_type: RouteType = "car_fast",
    waypoints: list[tuple[float, float]] | None = None,
    language: Language = "en",
) -> str:
    """Compose a mapy.com URL that opens a planned route between two points.

    Map style is auto-derived from `route_type` (car_* uses traffic,
    foot_*/bike_* uses outdoor). Map auto-fits to the route, so there is
    no zoom argument. Raises ToolError if more than 15 waypoints.
    """
    if waypoints is not None and len(waypoints) > _MAX_WAYPOINTS:
        raise ToolError(
            f"mapy.com supports at most {_MAX_WAYPOINTS} waypoints, "
            f"got {len(waypoints)}."
        )
    mapset = "traffic" if route_type.startswith("car_") else "outdoor"
    parts = [
        f"start={start_lon},{start_lat}",
        f"end={end_lon},{end_lat}",
        f"routeType={route_type}",
        f"mapset={mapset}",
        f"lang={language}",
    ]
    if waypoints:
        joined = ";".join(f"{lon},{lat}" for lon, lat in waypoints)
        parts.append(f"waypoints={quote(joined, safe=',;')}")
    return "https://mapy.com/fnc/v1/route?" + "&".join(parts)
