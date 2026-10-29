"""Tests for static_map/render.py — grid step choice and image overlay."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from mapy_com_mcp.static_map.render import format_distance, grid_step_m, render
from mapy_com_mcp.static_map.viewport import Viewport, fit_viewport

_SERIES = {1, 2, 3, 5}


def _base_png(width: int, height: int, color: str = "#88aa88") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    "meters,expected",
    [
        (50, "50 m"),
        (999.4, "999 m"),
        (1000, "1 km"),
        (2500, "2.5 km"),
        (20000, "20 km"),
    ],
)
def test_format_distance(meters: float, expected: str) -> None:
    assert format_distance(meters) == expected


@pytest.mark.parametrize("zoom", range(1, 20))
@pytest.mark.parametrize("lat", [0.0, 50.0, 70.0])
@pytest.mark.parametrize("size", [(1024, 640), (1024, 1024), (640, 1024)])
def test_grid_step_gives_between_3_and_7_lines_on_longer_side(
    zoom: int, lat: float, size: tuple[int, int]
) -> None:
    vp = Viewport(size[0], size[1], zoom, 14.0, lat)
    step = grid_step_m(vp)
    span = max(vp.width, vp.height) * vp.meters_per_px
    assert 3 <= span // step <= 7


@pytest.mark.parametrize("zoom", [3, 8, 12, 16, 19])
def test_grid_step_is_a_1_2_3_5_series_value(zoom: int) -> None:
    step = grid_step_m(Viewport(1024, 640, zoom, 14.0, 50.0))
    mantissa = step
    while mantissa >= 10:
        mantissa /= 10
    while mantissa < 1:
        mantissa *= 10
    assert round(mantissa) in _SERIES
    assert mantissa == pytest.approx(round(mantissa))


@pytest.mark.parametrize("count", [1, 2, 15])
def test_render_returns_valid_jpeg_of_base_size(count: int) -> None:
    points = [(14.4 + 0.01 * i, 50.0 + 0.005 * i) for i in range(count)]
    vp = fit_viewport(points)
    out = render(_base_png(vp.width, vp.height), vp, points)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (vp.width, vp.height)


@pytest.mark.parametrize("size", [(1024, 640), (640, 1024), (300, 300)])
def test_render_works_for_other_base_sizes(size: tuple[int, int]) -> None:
    vp = Viewport(size[0], size[1], 14, 14.4, 50.08)
    out = render(_base_png(*size), vp, [(14.4, 50.08)])
    assert Image.open(io.BytesIO(out)).size == size


def test_render_draws_red_marker_at_the_point() -> None:
    vp = fit_viewport([(14.4, 50.08)])
    out = render(_base_png(vp.width, vp.height, "#ffffff"), vp, [(14.4, 50.08)])
    img = Image.open(io.BytesIO(out)).convert("RGB")
    x, y = vp.to_pixel(14.4, 50.08)
    pixel = img.getpixel((round(x), round(y) - 20))
    assert isinstance(pixel, tuple)
    r, g, b = pixel[:3]
    assert r > 150 and g < 100 and b < 100


def test_render_leaves_footer_free_of_grid_lines() -> None:
    vp = Viewport(1024, 640, 14, 14.4, 50.08)
    out = render(_base_png(1024, 640, "#ffffff"), vp, [])
    img = Image.open(io.BytesIO(out)).convert("L")
    footer = img.crop((0, 640 - 26, 1024, 640))
    assert min(footer.tobytes()) > 240
