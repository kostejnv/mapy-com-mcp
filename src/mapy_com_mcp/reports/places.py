"""A map image of labeled places, with numbered markers and a coordinate grid."""

from __future__ import annotations

from ..links.urls import Point, PointsMapset
from ..mapy_api.client import MapyClient, StaticMapset
from ..static_map.render import format_distance, grid_step_m, render
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
    return render(base, viewport, [(p.lon, p.lat) for p in points])


def legend(points: list[Point], viewport: Viewport) -> str:
    """Marker numbers → labels, and the grid spacing."""
    lines = [f"{number}. {p.label}" for number, p in enumerate(points, start=1)]
    lines.append(f"Grid: {format_distance(grid_step_m(viewport))} between lines.")
    return "\n".join(lines)
