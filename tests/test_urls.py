"""Tests for urls.py — build_points_url and build_route_url pure URL builders."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError
from pydantic import ValidationError

from mapy_com_mcp.urls import Point, build_points_url, build_route_url

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
# build_points_url — basic structure
# ---------------------------------------------------------------------------


def test_build_points_url_empty_list_raises_tool_error() -> None:
    with pytest.raises(ToolError):
        build_points_url([])


def test_build_points_url_single_point_default_starts_correctly() -> None:
    url = build_points_url([_point()])
    assert url.startswith("https://mapy.com/fnc/v1/showmap?")


def test_build_points_url_single_point_uses_showmap_url() -> None:
    """One point dispatches to the showmap endpoint, never to vlastni-body."""
    url = build_points_url([_point()])
    assert url.startswith("https://mapy.com/fnc/v1/showmap?")
    assert "vlastni-body" not in url


def test_build_points_url_two_points_uses_vlastni_body_url() -> None:
    """Two points dispatches to the legacy vlastni-body endpoint, not showmap."""
    p1 = Point(lon=14.0, lat=50.0, label="A")
    p2 = Point(lon=15.0, lat=51.0, label="B")
    url = build_points_url([p1, p2])
    assert "vlastni-body" in url
    assert "/fnc/v1/showmap" not in url


# ---------------------------------------------------------------------------
# build_points_url — mapset (all five)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mapset",
    ["outdoor", "traffic", "winter", "aerial", "basic"],
)
def test_build_points_url_single_point_mapset_stays_english(mapset: str) -> None:
    """Single-point showmap URL keeps the English mapset value unchanged."""
    url = build_points_url([_point()], mapset=mapset)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"mapset={mapset}" in url


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
    """Multi-point vlastni-body URL translates mapset to Czech path segment."""
    p1 = Point(lon=14.0, lat=50.0, label="A")
    p2 = Point(lon=15.0, lat=51.0, label="B")
    url = build_points_url([p1, p2], mapset=mapset)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"/{expected_path_segment}?" in url


# ---------------------------------------------------------------------------
# build_points_url — language (all five)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_points_url_single_point_language_in_query(language: str) -> None:
    """Single-point showmap URL puts language in the query string as lang=."""
    url = build_points_url([_point()], language=language)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"lang={language}" in url


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_points_url_multi_point_language_appears_in_path(language: str) -> None:
    """Multi-point vlastni-body URL puts language as a path prefix."""
    p1 = Point(lon=14.0, lat=50.0, label="A")
    p2 = Point(lon=15.0, lat=51.0, label="B")
    url = build_points_url([p1, p2], language=language)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"https://mapy.com/{language}/" in url


# ---------------------------------------------------------------------------
# build_points_url — auto-fit zoom (matching _auto_fit_zoom thresholds)
# ---------------------------------------------------------------------------


def test_build_points_url_single_point_zoom_is_13() -> None:
    """Single-point showmap URL uses zoom=13 as the query param (not z=13)."""
    url = build_points_url([_point()])
    assert "zoom=13" in url


@pytest.mark.parametrize(
    "lon_span,expected_zoom",
    [
        (0.001, 19),  # span <= 0.005 → z=19
        (0.006, 17),  # 0.005 < span <= 0.02 → z=17
        (0.021, 15),  # 0.02 < span <= 0.1 → z=15
        (0.11, 13),  # 0.1 < span <= 1 → z=13
        (1.1, 11),  # 1 < span <= 5 → z=11
        (5.1, 8),  # 5 < span <= 20 → z=8
        (20.1, 5),  # span > 20 → z=5
    ],
    ids=["tiny", "very_close", "close", "district", "city", "country", "continental"],
)
def test_build_points_url_auto_fit_zoom_buckets(
    lon_span: float, expected_zoom: int
) -> None:
    p1 = Point(lon=14.0, lat=50.0, label="A")
    p2 = Point(lon=14.0 + lon_span, lat=50.0, label="B")
    url = build_points_url([p1, p2])
    assert f"z={expected_zoom}" in url


# ---------------------------------------------------------------------------
# build_points_url — label encoding (multi-point path; showmap has no ut=)
# ---------------------------------------------------------------------------


def test_build_points_url_label_with_space_is_percent_encoded() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="Charles Bridge")
    p2 = Point(lon=14.1, lat=50.1, label="Other")
    url = build_points_url([p1, p2])
    assert "ut=Charles%20Bridge" in url


def test_build_points_url_label_with_accent_is_percent_encoded() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="Café Imperial")
    p2 = Point(lon=14.1, lat=50.1, label="Other")
    url = build_points_url([p1, p2])
    # 'é' encodes as %C3%A9 in UTF-8
    assert "Caf%C3%A9%20Imperial" in url


def test_build_points_url_label_with_ampersand_is_percent_encoded() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="Smith & Sons")
    p2 = Point(lon=14.1, lat=50.1, label="Other")
    url = build_points_url([p1, p2])
    assert "%26" in url


# ---------------------------------------------------------------------------
# build_points_url — description encoding (multi-point path; showmap has no ud=)
# ---------------------------------------------------------------------------


def test_build_points_url_description_none_produces_empty_ud() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="X", description=None)
    p2 = Point(lon=14.1, lat=50.1, label="Y")
    url = build_points_url([p1, p2])
    assert "ud=&" in url or url.endswith("ud=")


def test_build_points_url_description_text_is_url_encoded() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="X", description="opens at 9am")
    p2 = Point(lon=14.1, lat=50.1, label="Y")
    url = build_points_url([p1, p2])
    assert "ud=opens%20at%209am" in url


# ---------------------------------------------------------------------------
# build_points_url — ordering (one ut= and one ud= per point, in input order)
# ---------------------------------------------------------------------------


def test_build_points_url_ut_and_ud_in_input_order() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="First", description="desc_first")
    p2 = Point(lon=15.0, lat=51.0, label="Second", description="desc_second")
    url = build_points_url([p1, p2])
    idx_ut1 = url.index("ut=First")
    idx_ut2 = url.index("ut=Second")
    idx_ud1 = url.index("ud=desc_first")
    idx_ud2 = url.index("ud=desc_second")
    assert idx_ut1 < idx_ut2, "ut= entries are not in input order"
    assert idx_ud1 < idx_ud2, "ud= entries are not in input order"
    # All ut= entries come before all ud= entries
    assert idx_ut2 < idx_ud1, "ut= entries should precede all ud= entries"


def test_build_points_url_one_ut_per_point() -> None:
    points = [Point(lon=14.0 + i * 0.01, lat=50.0, label=f"P{i}") for i in range(3)]
    url = build_points_url(points)
    assert url.count("ut=") == 3


def test_build_points_url_one_ud_per_point() -> None:
    points = [Point(lon=14.0 + i * 0.01, lat=50.0, label=f"P{i}") for i in range(3)]
    url = build_points_url(points)
    assert url.count("ud=") == 3


# ---------------------------------------------------------------------------
# build_points_url — center calculation
# ---------------------------------------------------------------------------


def test_build_points_url_center_is_arithmetic_mean_of_three_points() -> None:
    p1 = Point(lon=14.0, lat=50.0, label="A")
    p2 = Point(lon=15.0, lat=51.0, label="B")
    p3 = Point(lon=16.0, lat=52.0, label="C")
    url = build_points_url([p1, p2, p3])
    # center_lon = (14 + 15 + 16) / 3 = 15.0, center_lat = (50 + 51 + 52) / 3 = 51.0
    assert "x=15.0" in url
    assert "y=51.0" in url


# ---------------------------------------------------------------------------
# build_points_url — 50-point stress case (documented upper bound)
# ---------------------------------------------------------------------------


def test_build_points_url_50_points_composes_successfully() -> None:
    points = [Point(lon=14.0 + 0.001 * i, lat=50.0, label=f"p{i}") for i in range(50)]
    url = build_points_url(points)
    assert url.startswith("https://mapy.com/")
    uc_part = url.split("uc=")[1].split("&")[0]
    assert uc_part  # non-empty


# ---------------------------------------------------------------------------
# build_route_url — docs example (exact match)
# ---------------------------------------------------------------------------


def test_build_route_url_docs_example_exact_match() -> None:
    url = build_route_url(
        start_lon=14.4378,
        start_lat=50.0755,
        end_lon=16.6068,
        end_lat=49.1951,
        route_type="car_fast",
        language="en",
    )
    expected = (
        "https://mapy.com/fnc/v1/route"
        "?start=14.4378,50.0755"
        "&end=16.6068,49.1951"
        "&routeType=car_fast"
        "&mapset=traffic"
        "&lang=en"
    )
    assert url == expected


# ---------------------------------------------------------------------------
# build_route_url — route_type parametrize (all six)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route_type",
    ["car_fast", "car_short", "foot_fast", "foot_hiking", "bike_road", "bike_mountain"],
)
def test_build_route_url_route_type_in_url(route_type: str) -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0, route_type=route_type)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"routeType={route_type}" in url


# ---------------------------------------------------------------------------
# build_route_url — mapset auto-derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_type", ["car_fast", "car_short"])
def test_build_route_url_car_route_uses_traffic_mapset(route_type: str) -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0, route_type=route_type)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert "mapset=traffic" in url


@pytest.mark.parametrize(
    "route_type", ["foot_fast", "foot_hiking", "bike_road", "bike_mountain"]
)
def test_build_route_url_non_car_route_uses_outdoor_mapset(route_type: str) -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0, route_type=route_type)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert "mapset=outdoor" in url


# ---------------------------------------------------------------------------
# build_route_url — language (all five)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "cs", "sk", "de", "pl"])
def test_build_route_url_language_appears_in_query(language: str) -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0, language=language)  # type: ignore[arg-type]  # parametrize feeds plain str; Literal narrowing is what we're testing
    assert f"lang={language}" in url


# ---------------------------------------------------------------------------
# build_route_url — waypoints
# ---------------------------------------------------------------------------


def test_build_route_url_no_waypoints_omits_waypoints_param() -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0)
    assert "waypoints" not in url


def test_build_route_url_one_waypoint_correct_format() -> None:
    url = build_route_url(14.0, 50.0, 16.0, 49.0, waypoints=[(14.45, 50.08)])
    assert "waypoints=14.45,50.08" in url


def test_build_route_url_multiple_waypoints_joined_with_semicolon() -> None:
    url = build_route_url(
        14.0, 50.0, 16.0, 49.0, waypoints=[(14.45, 50.08), (15.0, 49.5)]
    )
    assert "waypoints=14.45,50.08;15.0,49.5" in url


def test_build_route_url_waypoints_in_input_order() -> None:
    """Waypoints appear in the URL in the order they were passed."""
    wp = [(14.0 + i * 0.1, 50.0) for i in range(3)]
    url = build_route_url(14.0, 50.0, 16.0, 49.0, waypoints=wp)
    waypoints_str = url.split("waypoints=")[1]
    parts = waypoints_str.split(";")
    assert parts[0].startswith("14.0,")
    assert parts[1].startswith("14.1,")
    assert parts[2].startswith("14.2,")


def test_build_route_url_15_waypoints_succeeds() -> None:
    wp = [(14.0 + i * 0.05, 50.0) for i in range(15)]
    url = build_route_url(14.0, 50.0, 16.0, 49.0, waypoints=wp)
    assert url.startswith("https://mapy.com/fnc/v1/route")


def test_build_route_url_16_waypoints_raises_tool_error() -> None:
    wp = [(14.0 + i * 0.05, 50.0) for i in range(16)]
    with pytest.raises(ToolError, match="15"):
        build_route_url(14.0, 50.0, 16.0, 49.0, waypoints=wp)
