"""Tests for links/urls.py — build_points_url and build_route_url pure URL builders."""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from mapy_com_mcp.links.urls import Point, build_points_url, build_route_url
from mapy_com_mcp.static_map.viewport import Viewport

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point(lon: float = 14.4003, lat: float = 50.0907, label: str = "Test") -> Point:
    return Point(lon=lon, lat=lat, label=label)


# ---------------------------------------------------------------------------
# Point model validation
# ---------------------------------------------------------------------------


def test_point_empty_label_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        Point(lon=14.0, lat=50.0, label="")


def test_point_valid_fields_accepted() -> None:
    p = Point(lon=14.4003, lat=50.0907, label="Prague Castle", description="Beautiful")
    assert p.lon == 14.4003
    assert p.lat == 50.0907
    assert p.label == "Prague Castle"
    assert p.description == "Beautiful"


def test_point_description_defaults_to_none() -> None:
    p = Point(lon=14.0, lat=50.0, label="X")
    assert p.description is None


# ---------------------------------------------------------------------------
# build_points_url
# ---------------------------------------------------------------------------

_VIEWPORT = Viewport(width=1024, height=640, zoom=12, center_lon=14.5, center_lat=50.05)


def _two_points() -> list[Point]:
    return [
        Point(lon=14.0, lat=50.0, label="A"),
        Point(lon=15.0, lat=51.0, label="B"),
    ]


def _url(points: list[Point], **kwargs: Any) -> str:
    return build_points_url(points, _VIEWPORT, **kwargs)


def test_build_points_url_empty_list_raises_tool_error() -> None:
    with pytest.raises(ToolError):
        _url([])


def test_build_points_url_single_point_uses_showmap() -> None:
    url = _url([_point()])
    assert url.startswith("https://mapy.com/fnc/v1/showmap?")
    assert "vlastni-body" not in url


def test_build_points_url_single_point_centers_on_the_point_not_the_viewport() -> None:
    """showmap puts its marker at the map center, so center must be the point."""
    url = _url([_point(lon=14.4003, lat=50.0907)])
    assert "center=14.4003,50.0907" in url
    assert "14.5" not in url


def test_build_points_url_single_point_zoom_comes_from_viewport() -> None:
    assert "zoom=12" in _url([_point()])


def test_build_points_url_multi_point_uses_vlastni_body() -> None:
    url = _url(_two_points())
    assert "vlastni-body" in url
    assert "/fnc/v1/showmap" not in url


def test_build_points_url_multi_point_center_and_zoom_come_from_viewport() -> None:
    url = _url(_two_points())
    assert "x=14.5&" in url
    assert "y=50.05&" in url
    assert url.endswith("z=12")


def test_build_points_url_multi_point_center_rounded_to_six_decimals() -> None:
    viewport = Viewport(1024, 640, 10, 14.123456789, 50.987654321)
    url = build_points_url(_two_points(), viewport)
    assert "x=14.123457" in url
    assert "y=50.987654" in url


@pytest.mark.parametrize("mapset", ["outdoor", "traffic", "winter", "aerial", "basic"])
def test_build_points_url_single_point_mapset_stays_english(mapset: str) -> None:
    assert f"mapset={mapset}" in _url([_point()], mapset=mapset)


@pytest.mark.parametrize(
    "mapset,expected_path_segment",
    [
        ("outdoor", "turisticka"),
        ("traffic", "dopravni"),
        ("winter", "zimni"),
        ("aerial", "letecka"),
        ("basic", "zakladni"),
    ],
)
def test_build_points_url_multi_point_mapset_translates_to_czech_path(
    mapset: str, expected_path_segment: str
) -> None:
    url = _url(_two_points(), mapset=mapset)
    assert f"/{expected_path_segment}?" in url


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_points_url_single_point_language_in_query(language: str) -> None:
    assert f"lang={language}" in _url([_point()], language=language)


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_points_url_multi_point_language_appears_in_path(language: str) -> None:
    url = _url(_two_points(), language=language)
    assert f"https://mapy.com/{language}/" in url


def test_build_points_url_multi_point_titles_are_numbered() -> None:
    url = _url(_two_points())
    assert "ut=1.%20A" in url
    assert "ut=2.%20B" in url


def test_build_points_url_label_with_accent_is_percent_encoded() -> None:
    p2 = Point(lon=14.1, lat=50.1, label="Café Imperial")
    assert "2.%20Caf%C3%A9%20Imperial" in _url([_point(), p2])


def test_build_points_url_label_with_ampersand_is_percent_encoded() -> None:
    p2 = Point(lon=14.1, lat=50.1, label="Smith & Sons")
    assert "Smith%20%26%20Sons" in _url([_point(), p2])


def test_build_points_url_description_none_produces_empty_ud() -> None:
    url = _url(_two_points())
    assert "ud=&ud=&" in url


def test_build_points_url_description_text_is_url_encoded() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="X", description="opens at 9am")
    p2 = Point(lon=14.1, lat=50.1, label="Y")
    assert "ud=opens%20at%209am" in _url([p1, p2])


def test_build_points_url_ut_and_ud_in_input_order() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="First", description="desc_first")
    p2 = Point(lon=15.0, lat=51.0, label="Second", description="desc_second")
    url = _url([p1, p2])
    assert url.index("ut=1.%20First") < url.index("ut=2.%20Second")
    assert url.index("ud=desc_first") < url.index("ud=desc_second")
    assert url.index("ut=2.%20Second") < url.index("ud=desc_first")


def test_build_points_url_one_ut_and_ud_per_point() -> None:
    points = [Point(lon=14.0 + i * 0.01, lat=50.0, label=f"P{i}") for i in range(3)]
    url = _url(points)
    assert url.count("ut=") == 3
    assert url.count("ud=") == 3


def test_build_points_url_50_points_composes_successfully() -> None:
    points = [Point(lon=14.0 + 0.001 * i, lat=50.0, label=f"p{i}") for i in range(50)]
    url = _url(points)
    assert url.startswith("https://mapy.com/")
    assert url.split("uc=")[1].split("&")[0]


# ---------------------------------------------------------------------------
# build_route_url
# ---------------------------------------------------------------------------

_ROUTE_TYPES = [
    "car_fast",
    "car_short",
    "foot_fast",
    "foot_hiking",
    "bike_road",
    "bike_mountain",
]


def _route_points(count: int) -> list[Point]:
    return [_point(lon=14.0 + i * 0.1, lat=50.0, label=f"P{i}") for i in range(count)]


def test_build_route_url_two_points_exact_url_without_waypoints() -> None:
    url = build_route_url(
        [_point(14.4378, 50.0755, "Prague"), _point(16.6068, 49.1951, "Brno")],
        "car_fast",
    )
    assert url == (
        "https://mapy.com/fnc/v1/route"
        "?start=14.4378,50.0755"
        "&end=16.6068,49.1951"
        "&routeType=car_fast"
        "&mapset=traffic"
        "&lang=en"
    )


@pytest.mark.parametrize("route_type", _ROUTE_TYPES)
def test_build_route_url_route_type_in_url(route_type: Any) -> None:
    assert f"routeType={route_type}" in build_route_url(_route_points(2), route_type)


@pytest.mark.parametrize("route_type", ["car_fast", "car_short"])
def test_build_route_url_car_route_uses_traffic_mapset(route_type: Any) -> None:
    assert "mapset=traffic" in build_route_url(_route_points(2), route_type)


@pytest.mark.parametrize(
    "route_type", ["foot_fast", "foot_hiking", "bike_road", "bike_mountain"]
)
def test_build_route_url_non_car_route_uses_outdoor_mapset(route_type: Any) -> None:
    assert "mapset=outdoor" in build_route_url(_route_points(2), route_type)


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_route_url_language_appears_in_query(language: Any) -> None:
    url = build_route_url(_route_points(2), "foot_fast", language)
    assert f"lang={language}" in url


def test_build_route_url_middle_points_become_waypoints_in_order() -> None:
    points = [
        _point(14.0, 50.0),
        _point(14.1, 50.1),
        _point(14.2, 50.2),
        _point(14.3, 50.3),
    ]
    url = build_route_url(points, "foot_fast")
    assert "start=14.0,50.0&end=14.3,50.3" in url
    assert "waypoints=14.1,50.1;14.2,50.2" in url


def test_build_route_url_17_points_succeeds() -> None:
    url = build_route_url(_route_points(17), "foot_fast")
    assert len(url.split("waypoints=")[1].split("&")[0].split(";")) == 15


@pytest.mark.parametrize("count", [0, 1])
def test_build_route_url_too_few_points_raises_tool_error(count: int) -> None:
    with pytest.raises(ToolError, match="start"):
        build_route_url(_route_points(count), "foot_fast")


def test_build_route_url_18_points_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="15"):
        build_route_url(_route_points(18), "foot_fast")
