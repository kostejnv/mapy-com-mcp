"""Tests for static_map/viewport.py — Web Mercator math and fit_viewport."""

from __future__ import annotations

import pytest

from mapy_com_mcp.static_map.viewport import (
    MAX_ZOOM,
    MIN_ZOOM,
    SINGLE_POINT_ZOOM,
    Viewport,
    fit_viewport,
    lon_lat,
    world_px,
)

_PRAGUE = (14.4378, 50.0755)
_BRNO = (16.6068, 49.1951)


@pytest.mark.parametrize(
    "lon,lat,zoom",
    [(14.4378, 50.0755, 0), (-122.4, 37.8, 12), (179.9, -60.0, 5), (0.0, 0.0, 19)],
)
def test_world_px_and_lon_lat_round_trip(lon: float, lat: float, zoom: int) -> None:
    x, y = world_px(lon, lat, zoom)
    back_lon, back_lat = lon_lat(x, y, zoom)
    assert back_lon == pytest.approx(lon, abs=1e-9)
    assert back_lat == pytest.approx(lat, abs=1e-9)


def test_world_px_origin_and_world_size() -> None:
    assert world_px(-180, 0, 0)[0] == pytest.approx(0)
    assert world_px(180, 0, 0)[0] == pytest.approx(256)
    assert world_px(0, 0, 0) == pytest.approx((128, 128))


def test_viewport_center_maps_to_image_center() -> None:
    vp = Viewport(1024, 640, 12, 14.5, 50.05)
    assert vp.to_pixel(14.5, 50.05) == pytest.approx((512, 320))


def test_viewport_to_pixel_and_to_lon_lat_round_trip() -> None:
    vp = Viewport(1024, 640, 12, 14.5, 50.05)
    x, y = vp.to_pixel(14.52, 50.03)
    assert vp.to_lon_lat(x, y) == pytest.approx((14.52, 50.03), abs=1e-9)


def test_viewport_meters_per_px_halves_per_zoom_and_shrinks_with_latitude() -> None:
    equator = Viewport(100, 100, 10, 0, 0)
    assert equator.meters_per_px == pytest.approx(152.874, rel=1e-3)
    assert Viewport(100, 100, 11, 0, 0).meters_per_px == pytest.approx(
        equator.meters_per_px / 2
    )
    assert Viewport(100, 100, 10, 0, 60).meters_per_px == pytest.approx(
        equator.meters_per_px / 2, rel=1e-3
    )


def test_fit_viewport_single_point_uses_single_point_zoom() -> None:
    vp = fit_viewport([_PRAGUE])
    assert vp.zoom == SINGLE_POINT_ZOOM == 16


def test_fit_viewport_single_point_is_square_and_centered() -> None:
    """Zero extent gives a square image whose 10% margins already exceed the
    minimum left/top margins, so the point sits at the image center."""
    vp = fit_viewport([_PRAGUE])
    assert (vp.width, vp.height) == (1024, 1024)
    assert vp.to_pixel(*_PRAGUE) == pytest.approx((512, 512), abs=1e-6)


def test_fit_viewport_portrait_shifts_points_right_of_center_for_left_margin() -> None:
    """In the 640 px wide image the 70 px minimum left margin beats 10%, so
    the bbox is centered right of the image center."""
    vp = fit_viewport([(14.0, 48.0), (14.0, 51.0)])
    x, _ = vp.to_pixel(14.0, 48.0)
    assert x == pytest.approx((70 + 640 - 64) / 2)


def test_fit_viewport_identical_points_behave_like_single_point() -> None:
    assert fit_viewport([_PRAGUE, _PRAGUE]).zoom == SINGLE_POINT_ZOOM


def test_fit_viewport_wide_spread_picks_landscape() -> None:
    vp = fit_viewport([(14.0, 50.0), (16.0, 50.0)])
    assert (vp.width, vp.height) == (1024, 640)


def test_fit_viewport_tall_spread_picks_portrait() -> None:
    vp = fit_viewport([(14.0, 48.0), (14.0, 51.0)])
    assert (vp.width, vp.height) == (640, 1024)


def test_fit_viewport_balanced_spread_picks_square() -> None:
    vp = fit_viewport([(14.0, 50.0), (14.1, 50.0643)])
    assert (vp.width, vp.height) == (1024, 1024)


@pytest.mark.parametrize(
    "points",
    [
        [_PRAGUE, _BRNO],
        [(14.0, 50.0), (14.0, 51.0)],
        [(14.0, 50.0), (14.05, 50.0), (14.02, 50.03)],
        [(-170.0, -40.0), (170.0, 60.0)],
        [(14.4, 50.0), (14.4001, 50.0001)],
    ],
)
def test_fit_viewport_keeps_all_points_inside_margins(
    points: list[tuple[float, float]],
) -> None:
    vp = fit_viewport(points)
    for lon, lat in points:
        x, y = vp.to_pixel(lon, lat)
        assert 70 - 1e-6 <= x <= vp.width - 0.1 * vp.width + 1e-6
        assert 76 - 1e-6 <= y <= vp.height - max(0.1 * vp.height, 64) + 1e-6


def test_fit_viewport_picks_largest_zoom_that_fits() -> None:
    """One zoom step higher would push a point out of the usable area."""
    points = [_PRAGUE, _BRNO]
    vp = fit_viewport(points)
    zoomed = Viewport(vp.width, vp.height, vp.zoom + 1, vp.center_lon, vp.center_lat)
    xs = [zoomed.to_pixel(*p)[0] for p in points]
    ys = [zoomed.to_pixel(*p)[1] for p in points]
    assert (max(xs) - min(xs) > vp.width * 0.8 - 70) or (
        max(ys) - min(ys) > vp.height * 0.9 - 76
    )


def test_fit_viewport_zoom_clamped_at_max_for_near_identical_points() -> None:
    assert fit_viewport([(14.4, 50.0), (14.4000001, 50.0000001)]).zoom == MAX_ZOOM


def test_fit_viewport_zoom_clamped_at_min_for_world_spread() -> None:
    vp = fit_viewport([(-179.0, -80.0), (179.0, 80.0)])
    assert vp.zoom == MIN_ZOOM


def test_fit_viewport_point_order_does_not_matter() -> None:
    assert fit_viewport([_PRAGUE, _BRNO]) == fit_viewport([_BRNO, _PRAGUE])


def test_fit_viewport_landscape_keeps_points_out_of_bottom_64_px() -> None:
    """The bottom margin floor keeps markers above the legend and footer."""
    points = [(14.0, 50.0), (16.0, 50.3)]
    vp = fit_viewport(points)
    assert (vp.width, vp.height) == (1024, 640)
    for lon, lat in points:
        assert vp.to_pixel(lon, lat)[1] <= vp.height - 64 + 1e-6


@pytest.mark.parametrize("lat", [90.0, -90.0])
def test_world_px_clamps_poles_instead_of_raising(lat: float) -> None:
    _, y = world_px(14.0, lat, 3)
    assert 0 <= y <= 256 * 2**3


@pytest.mark.parametrize("lat", [90.0, -90.0])
def test_fit_viewport_accepts_pole_point(lat: float) -> None:
    vp = fit_viewport([(14.0, lat), (14.0, 50.0)])
    assert MIN_ZOOM <= vp.zoom <= MAX_ZOOM
