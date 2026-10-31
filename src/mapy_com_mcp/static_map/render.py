"""Draw the coordinate grid and numbered markers onto a static map image.

The grid lets the model read coordinates and distances straight off the
picture. Markers are drawn here, above the grid, rather than by mapy.com,
whose markers would end up underneath the grid lines.
"""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

from .viewport import Viewport

_METERS_PER_DEG_LAT = 111_320.0
_JPEG_QUALITY = 85

_GRID_STEP_MULTIPLIERS = (1, 2, 3, 5)
_TARGET_GRID_LINES = 6
_MAX_GRID_LINES = 7
_GRID_COLOR = (0, 0, 0, 200)
_GRID_WIDTH = 3
# A white halo keeps the black line visible on dark aerial imagery.
_HALO_COLOR = (255, 255, 255, 160)
_HALO_WIDTH = 5

_LABEL_W_PX, _LABEL_H_PX = 60, 18
_FOOTER_H_PX = 28  # mapy.com logo and attribution — must stay visible

_MARKER_COLOR = (215, 25, 32, 255)
_MARKER_RADIUS_PX = 14
_MARKER_SUPERSAMPLE = 4  # smooth edges

_ROUTE_COLOR = _MARKER_COLOR
_ROUTE_WIDTH = 5
_ROUTE_HALO = (255, 255, 255, 230)
_ROUTE_HALO_WIDTH = 9
_ROUTE_SUPERSAMPLE = 2


def format_distance(meters: float) -> str:
    return f"{meters / 1000:g} km" if meters >= 1000 else f"{round(meters)} m"


def grid_step_m(viewport: Viewport) -> float:
    """Round step (1/2/3/5 x 10^n m) giving ~6 lines on the longer side."""
    span_m = max(viewport.width, viewport.height) * viewport.meters_per_px
    candidates = [
        mult * 10**exponent
        for exponent in range(8)
        for mult in _GRID_STEP_MULTIPLIERS
        if 3 <= span_m // (mult * 10**exponent) <= _MAX_GRID_LINES
    ]
    return min(candidates, key=lambda step: abs(span_m // step - _TARGET_GRID_LINES))


def render(
    base_image: bytes,
    viewport: Viewport,
    points: list[tuple[float, float]],
    route: list[tuple[float, float]] | None = None,
) -> bytes:
    """Overlay grid, legend, an optional route line and numbered markers.

    Returns JPEG bytes. The route sits between the grid and the markers.
    """
    img = Image.open(io.BytesIO(base_image)).convert("RGBA")
    img = _draw_grid(img, viewport)
    if route:
        img = _draw_route(img, viewport, route)
    for number, (lon, lat) in enumerate(points, start=1):
        _draw_marker(img, viewport.to_pixel(lon, lat), str(number))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
    return buf.getvalue()


def _draw_grid(img: Image.Image, viewport: Viewport) -> Image.Image:
    w, h = img.size
    step_m = grid_step_m(viewport)
    m_per_px = viewport.meters_per_px
    # Enough decimals that neighbouring lines get distinct labels.
    decimals = max(2, min(6, math.ceil(-math.log10(step_m / _METERS_PER_DEG_LAT)) + 1))
    font = ImageFont.load_default(size=12)

    # Separate layers so each line composites over its halo instead of
    # replacing it: halo → line → labels.
    halo, lines, labels = (Image.new("RGBA", (w, h), (0, 0, 0, 0)) for _ in range(3))
    halo_draw, line_draw, label_draw = (
        ImageDraw.Draw(layer) for layer in (halo, lines, labels)
    )

    def grid_line(start: tuple[int, int], end: tuple[int, int]) -> None:
        halo_draw.line([start, end], fill=_HALO_COLOR, width=_HALO_WIDTH)
        line_draw.line([start, end], fill=_GRID_COLOR, width=_GRID_WIDTH)

    # The grid stops above the footer so the logo and attribution stay clear.
    grid_bottom = h - _FOOTER_H_PX

    # Vertical lines: metric offsets along the center parallel.
    k_max = math.ceil(w / 2 * m_per_px / step_m)
    for k in range(-k_max, k_max + 1):
        x = round(w / 2 + k * step_m / m_per_px)
        if not 0 <= x < w:
            continue
        grid_line((x, 0), (x, grid_bottom))
        lon, _ = viewport.to_lon_lat(x, h / 2)
        label_x = max(2, min(w - _LABEL_W_PX - 2, x - _LABEL_W_PX // 2))
        _draw_label(label_draw, (label_x, 2), f"{lon:.{decimals}f}", font)

    # Horizontal lines: metric offsets along the meridian give latitudes
    # (linear on the ground); Mercator then places them, unevenly spaced.
    k_max = math.ceil(h * m_per_px / step_m)
    for k in range(-k_max, k_max + 1):
        lat = viewport.center_lat + k * step_m / _METERS_PER_DEG_LAT
        if not -85 < lat < 85:
            continue
        y = round(viewport.to_pixel(viewport.center_lon, lat)[1])
        if not 0 <= y < grid_bottom:
            continue
        grid_line((0, y), (w - 1, y))
        lowest = grid_bottom - _LABEL_H_PX
        label_y = max(_LABEL_H_PX + 4, min(lowest, y - _LABEL_H_PX // 2))
        _draw_label(label_draw, (2, label_y), f"{lat:.{decimals}f}", font)

    _draw_legend(label_draw, (w, h), f"grid {format_distance(step_m)}")

    for layer in (halo, lines, labels):
        img = Image.alpha_composite(img, layer)
    return img


def _draw_route(
    img: Image.Image, viewport: Viewport, route: list[tuple[float, float]]
) -> Image.Image:
    ss = _ROUTE_SUPERSAMPLE
    layer = Image.new("RGBA", (img.width * ss, img.height * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    pixels = [viewport.to_pixel(lon, lat) for lon, lat in route]
    line = [(x * ss, y * ss) for x, y in pixels]
    draw.line(line, fill=_ROUTE_HALO, width=_ROUTE_HALO_WIDTH * ss, joint="curve")
    draw.line(line, fill=_ROUTE_COLOR, width=_ROUTE_WIDTH * ss, joint="curve")
    return Image.alpha_composite(img, layer.reduce(ss))


def _draw_label(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    x, y = xy
    draw.rectangle((x, y, x + _LABEL_W_PX, y + _LABEL_H_PX), fill=(255, 255, 255, 220))
    draw.text((x + 4, y + 3), text, fill="black", font=font)


def _draw_legend(draw: ImageDraw.ImageDraw, size: tuple[int, int], text: str) -> None:
    w, h = size
    font = ImageFont.load_default(size=16)
    box_w = int(draw.textlength(text, font=font)) + 16
    top = h - _FOOTER_H_PX - 30
    draw.rectangle(
        (w - box_w - 6, top, w - 6, top + 26), fill=(20, 20, 20, 235), outline="white"
    )
    draw.text((w - box_w + 2, top + 4), text, fill="white", font=font)


def _draw_marker(img: Image.Image, tip: tuple[float, float], label: str) -> None:
    """Red pin with a white number and outline, its tip on the point."""
    ss = _MARKER_SUPERSAMPLE
    r = _MARKER_RADIUS_PX * ss
    w, h = 2 * r + 4 * ss, 2 * r + 22 * ss
    sprite = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sprite)
    cx, cy = w / 2, r + 2 * ss
    # White outline first (slightly bigger), then the red body on top.
    for grow, color, tip_y in (
        (2 * ss, (255, 255, 255, 255), h - 1),
        (0, _MARKER_COLOR, h - 1 - 2 * ss),
    ):
        draw.ellipse(
            (cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow), fill=color
        )
        draw.polygon(
            [
                (cx - r * 0.7 - grow, cy + r * 0.6),
                (cx + r * 0.7 + grow, cy + r * 0.6),
                (cx, tip_y),
            ],
            fill=color,
        )
    draw.text(
        (cx, cy),
        label,
        fill="white",
        font=ImageFont.load_default(size=16 * ss),
        anchor="mm",
    )
    sprite = sprite.reduce(ss)
    img.paste(
        sprite,
        (round(tip[0] - sprite.width / 2), round(tip[1] - sprite.height)),
        sprite,
    )
