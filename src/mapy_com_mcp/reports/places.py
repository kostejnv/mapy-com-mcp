"""A map image of labeled places, with numbered markers and a coordinate grid."""

from __future__ import annotations

from ..links.urls import Point, PointsMapset
from ..mapy_api.client import MapyClient, StaticMapset
from ..static_map.render import grid_line, render
from ..static_map.viewport import Viewport

# The static map API has no traffic layer; basic is the closest look.
_STATIC_MAPSET: dict[PointsMapset, StaticMapset] = {
    "outdoor": "outdoor",
    "traffic": "basic",
    "winter": "winter",
    "aerial": "aerial",
    "basic": "basic",
}


async def places_map(
    client: MapyClient,
    points: list[Point],
    viewport: Viewport,
    mapset: PointsMapset,
    language: str,
    *,
    grid: bool = True,
) -> bytes:
    """JPEG of the viewport with the points numbered in input order."""
    base = await client.static_map(
        lon=viewport.center_lon,
        lat=viewport.center_lat,
        zoom=viewport.zoom,
        width=viewport.width,
        height=viewport.height,
        mapset=_STATIC_MAPSET[mapset],
        lang=language,
    )
    return render(base, viewport, [(p.lon, p.lat) for p in points], grid=grid)


def numbered_labels(points: list[Point]) -> str:
    """Marker numbers → labels, one per line."""
    return "\n".join(f"{number}. {p.label}" for number, p in enumerate(points, start=1))


def legend(points: list[Point], viewport: Viewport) -> str:
    """Marker numbers → labels, and the grid spacing."""
    return f"{numbered_labels(points)}\n{grid_line(viewport)}"
