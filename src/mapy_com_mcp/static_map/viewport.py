"""Pick the map view (size, zoom, center) that fits a set of points.

All geometry is done in Web Mercator pixel space, the projection mapy.com
tiles use. The same viewport drives the static image and the mapy.com link,
so both show the same area at the same scale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_TILE_SIZE_PX = 256
_EARTH_CIRCUMFERENCE_M = 40_075_016.686

MIN_ZOOM = 1
MAX_ZOOM = 19  # static map API limit
SINGLE_POINT_ZOOM = 16  # ~1.6 km wide at lat 50 — a neighborhood

# (width, height), picked by the points' aspect ratio.
_LANDSCAPE = (1024, 640)
_SQUARE = (1024, 1024)
_PORTRAIT = (640, 1024)
_ASPECT_THRESHOLD = 1.3

# Mercator is undefined at the poles; tiles stop at this latitude.
_MAX_LAT = 85.0511

# Space kept free of points. Top and left also hold room for the marker pin
# and the grid labels, bottom for the legend and footer drawn by render.py.
_MARGIN_FRACTION = 0.10
_MIN_LEFT_MARGIN_PX = 70
_MIN_TOP_MARGIN_PX = 76
_MIN_BOTTOM_MARGIN_PX = 64


def world_px(lon: float, lat: float, zoom: float) -> tuple[float, float]:
    """WGS84 → Web Mercator pixel coordinates at the given zoom."""
    size = _TILE_SIZE_PX * 2**zoom
    x = (lon + 180) / 360 * size
    sin_lat = math.sin(math.radians(max(-_MAX_LAT, min(_MAX_LAT, lat))))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * size
    return x, y


def lon_lat(x: float, y: float, zoom: float) -> tuple[float, float]:
    """Web Mercator pixel coordinates at the given zoom → WGS84."""
    size = _TILE_SIZE_PX * 2**zoom
    lon = x / size * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size))))
    return lon, lat


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    zoom: int
    center_lon: float
    center_lat: float

    @property
    def meters_per_px(self) -> float:
        """Ground distance of one pixel along the center parallel."""
        return (
            _EARTH_CIRCUMFERENCE_M
            * math.cos(math.radians(self.center_lat))
            / (_TILE_SIZE_PX * 2**self.zoom)
        )

    def to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """WGS84 → pixel position in the image (origin top-left)."""
        cx, cy = world_px(self.center_lon, self.center_lat, self.zoom)
        x, y = world_px(lon, lat, self.zoom)
        return x - cx + self.width / 2, y - cy + self.height / 2

    def to_lon_lat(self, x: float, y: float) -> tuple[float, float]:
        """Pixel position in the image → WGS84."""
        cx, cy = world_px(self.center_lon, self.center_lat, self.zoom)
        return lon_lat(cx - self.width / 2 + x, cy - self.height / 2 + y, self.zoom)


def fit_viewport(points: list[tuple[float, float]]) -> Viewport:
    """Fit (lon, lat) points: image shape, largest zoom that fits, center.

    The agent never picks a zoom. A single point (zero extent) gets
    SINGLE_POINT_ZOOM.
    """
    xs, ys = zip(*(world_px(lon, lat, 0) for lon, lat in points), strict=True)
    extent_x, extent_y = max(xs) - min(xs), max(ys) - min(ys)
    width, height = _pick_size(extent_x, extent_y)

    left = max(_MARGIN_FRACTION * width, _MIN_LEFT_MARGIN_PX)
    top = max(_MARGIN_FRACTION * height, _MIN_TOP_MARGIN_PX)
    usable_w = width - left - _MARGIN_FRACTION * width
    usable_h = height - top - max(_MARGIN_FRACTION * height, _MIN_BOTTOM_MARGIN_PX)

    if extent_x == 0 and extent_y == 0:
        zoom = SINGLE_POINT_ZOOM
    else:
        scale = min(
            usable_w / extent_x if extent_x else math.inf,
            usable_h / extent_y if extent_y else math.inf,
        )
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, math.floor(math.log2(scale))))

    # Put the points' bbox center in the middle of the usable area, then
    # shift to the image center, which is what the map API takes.
    factor = 2**zoom
    bbox_cx = (min(xs) + max(xs)) / 2 * factor
    bbox_cy = (min(ys) + max(ys)) / 2 * factor
    image_cx = bbox_cx - (left + usable_w / 2 - width / 2)
    image_cy = bbox_cy - (top + usable_h / 2 - height / 2)
    center_lon, center_lat = lon_lat(image_cx, image_cy, zoom)
    return Viewport(width, height, zoom, center_lon, center_lat)


def _pick_size(extent_x: float, extent_y: float) -> tuple[int, int]:
    ratio = (extent_x + 1e-12) / (extent_y + 1e-12)
    if ratio >= _ASPECT_THRESHOLD:
        return _LANDSCAPE
    if ratio <= 1 / _ASPECT_THRESHOLD:
        return _PORTRAIT
    return _SQUARE
