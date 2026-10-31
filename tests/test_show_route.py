"""Tests for tools/show_route.py — url / map / both modes, profile, fallbacks.

All HTTP is mocked with respx; no real network calls are made.
"""

from __future__ import annotations

import io
from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from httpx import Response
from mcp.types import ImageContent, TextContent
from PIL import Image

from mapy_com_mcp.server import create_app

_ROUTE_URL = "https://api.mapy.com/v1/routing/route"
_STATIC_URL = "https://api.mapy.com/v1/static/map"
_ELEVATION_URL = "https://api.mapy.com/v1/elevation"

_POINTS = [
    {"lon": 14.40, "lat": 50.09, "label": "Castle"},
    {"lon": 14.42, "lat": 50.08, "label": "Square"},
]
_THREE_POINTS = [*_POINTS, {"lon": 14.44, "lat": 50.07, "label": "Park"}]


def _route_body(
    *,
    legs: list[tuple[int, int]] | None = None,
    route_points: list[dict[str, Any]] | None = None,
    coords: list[list[float]] | None = None,
) -> dict[str, Any]:
    legs = legs or [(3800, 2940)]
    return {
        "length": sum(length for length, _ in legs),
        "duration": sum(duration for _, duration in legs),
        "parts": [{"length": length, "duration": dur} for length, dur in legs],
        "geometry": {
            "geometry": {
                "coordinates": coords or [[14.40, 50.09], [14.42, 50.08]],
            }
        },
        "routePoints": route_points or [{"snapDistance": 0}] * (len(legs) + 1),
    }


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "#99bb99").save(buf, format="PNG")
    return buf.getvalue()


def _static_response(request: httpx.Request) -> Response:
    p = request.url.params
    return Response(200, content=_png(int(p["width"]), int(p["height"])))


def _elevation_response(request: httpx.Request) -> Response:
    count = len(request.url.params["positions"].split(";"))
    items = [{"elevation": 300 + i * 0.1} for i in range(count)]
    return Response(200, json={"items": items})


@pytest.fixture
def mcp_no_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.delenv("MAPY_API_KEY", raising=False)
    return create_app()


@pytest.fixture
def mcp_with_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.setenv("MAPY_API_KEY", "fake-test-key")
    return create_app()


async def _call(mcp: FastMCP, **args: Any) -> Any:
    async with Client(mcp) as client:
        return await client.call_tool("show_route", args)


def _text(result: Any) -> str:
    return "\n".join(c.text for c in result.content if isinstance(c, TextContent))


def _images(result: Any) -> list[ImageContent]:
    return [c for c in result.content if isinstance(c, ImageContent)]


# ---------------------------------------------------------------------------
# Without an API key
# ---------------------------------------------------------------------------


async def test_without_key_schema_hides_output_and_requires_route_type(
    mcp_no_key: FastMCP,
) -> None:
    async with Client(mcp_no_key) as client:
        tool = next(t for t in await client.list_tools() if t.name == "show_route")
    assert set(tool.inputSchema["properties"]) == {"points", "route_type", "language"}
    assert set(tool.inputSchema["required"]) == {"points", "route_type"}
    assert tool.annotations is not None
    assert tool.annotations.openWorldHint is False


async def test_without_key_returns_url_only(mcp_no_key: FastMCP) -> None:
    result = await _call(mcp_no_key, points=_POINTS, route_type="foot_fast")
    assert len(result.content) == 1
    url = _text(result)
    assert url.startswith(
        "https://mapy.com/fnc/v1/route?start=14.4,50.09&end=14.42,50.08"
    )
    assert "routeType=foot_fast" in url


async def test_without_key_too_few_points_is_rejected(mcp_no_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_no_key, points=_POINTS[:1], route_type="foot_fast")


async def test_build_route_url_tool_is_gone(mcp_no_key: FastMCP) -> None:
    async with Client(mcp_no_key) as client:
        names = {t.name for t in await client.list_tools()}
    assert "build_route_url" not in names
    assert "show_route" in names


# ---------------------------------------------------------------------------
# With a key: schema
# ---------------------------------------------------------------------------


async def test_with_key_schema_exposes_output_default_both(
    mcp_with_key: FastMCP,
) -> None:
    async with Client(mcp_with_key) as client:
        tool = next(t for t in await client.list_tools() if t.name == "show_route")
    props = tool.inputSchema["properties"]
    assert set(props) == {"points", "route_type", "output", "language"}
    assert props["output"]["default"] == "both"
    assert "route_type" in tool.inputSchema["required"]
    assert tool.annotations is not None
    assert tool.annotations.openWorldHint is True


# ---------------------------------------------------------------------------
# url mode
# ---------------------------------------------------------------------------


@respx.mock
async def test_url_mode_one_routing_call_no_images_no_elevation(
    mcp_with_key: FastMCP,
) -> None:
    routing = respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="foot_hiking", output="url"
    )
    assert routing.call_count == 1
    assert not static.called and not elevation.called
    assert _images(result) == []
    text = _text(result)
    assert "Route (foot_hiking): 3.8 km, 49 min" in text
    assert "Elevation" not in text
    assert "Map link for the user: https://mapy.com/fnc/v1/route" in text


@respx.mock
async def test_routing_request_params(mcp_with_key: FastMCP) -> None:
    routing = respx.get(_ROUTE_URL).respond(
        200, json=_route_body(legs=[(1000, 600), (2000, 1200)])
    )
    await _call(
        mcp_with_key,
        points=_THREE_POINTS,
        route_type="car_short",
        output="url",
        language="cs",
    )
    params = routing.calls.last.request.url.params
    assert params["routeType"] == "car_short"
    assert params["lang"] == "cs"
    assert params["waypoints"] == "14.42,50.08"


# ---------------------------------------------------------------------------
# Summary formatting
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    "length,seconds,expected",
    [
        (604, 540, "Route (car_fast): 600 m, 9 min"),
        (999, 60, "Route (car_fast): 1.0 km, 1 min"),
        (3800, 3900, "Route (car_fast): 3.8 km, 1 h 05 min"),
        (120_000, 7200, "Route (car_fast): 120.0 km, 2 h 00 min"),
    ],
)
async def test_summary_distance_and_duration_formats(
    mcp_with_key: FastMCP, length: int, seconds: int, expected: str
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body(legs=[(length, seconds)]))
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="car_fast", output="url"
    )
    assert expected in _text(result)


@respx.mock
async def test_per_leg_lines_tie_marker_numbers_to_labels(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(
        200, json=_route_body(legs=[(1200, 900), (2600, 2040)])
    )
    text = _text(
        await _call(
            mcp_with_key, points=_THREE_POINTS, route_type="car_fast", output="url"
        )
    )
    assert "Route (car_fast): 3.8 km, 49 min" in text
    assert "1. Castle → 2. Square: 1.2 km, 15 min" in text
    assert "2. Square → 3. Park: 2.6 km, 34 min" in text


@respx.mock
async def test_warnings_for_snapped_and_restricted_points(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(
        200,
        json=_route_body(
            legs=[(1200, 900), (2600, 2040)],
            route_points=[
                {"snapDistance": 50},  # at the threshold: no warning
                {"snapDistance": 120, "restrictionType": "PEDESTRIAN_ZONE"},
                {"snapDistance": 2, "restrictionType": "CLOSURE"},
            ],
        ),
    )
    text = _text(
        await _call(
            mcp_with_key, points=_THREE_POINTS, route_type="car_fast", output="url"
        )
    )
    warnings = next(line for line in text.splitlines() if line.startswith("Warnings:"))
    assert "1. Castle" not in warnings
    assert "2. Square was moved 120 m to the nearest road or path." in warnings
    assert "2. Square lies in a restricted area (pedestrian zone)." in warnings
    assert "3. Park lies in a restricted area (closure)." in warnings
    assert text.count("Warnings:") == 1


@respx.mock
async def test_no_warnings_line_when_all_clear(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    text = _text(
        await _call(mcp_with_key, points=_POINTS, route_type="car_fast", output="url")
    )
    assert "Warnings" not in text


# ---------------------------------------------------------------------------
# both / map modes
# ---------------------------------------------------------------------------


@respx.mock
async def test_both_mode_foot_returns_map_profile_and_text(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")

    kinds: list[type] = [type(c) for c in result.content]
    assert kinds == [ImageContent, ImageContent, TextContent]
    sizes = [Image.open(io.BytesIO(_decode(i))).size for i in _images(result)]
    assert sizes[1] == (1024, 280)
    assert static.calls.last.request.url.params["mapset"] == "outdoor"
    assert elevation.call_count == 1
    text = _text(result)
    assert "Elevation: min 300 m, max 326 m" in text
    assert "Grid:" in text
    assert text.splitlines()[-1].startswith("Map link for the user: https://mapy.com/")


def _decode(image: ImageContent) -> bytes:
    import base64

    return base64.b64decode(image.data)


@respx.mock
async def test_both_mode_car_has_single_image_and_no_elevation(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="car_fast")
    assert len(_images(result)) == 1
    assert not elevation.called
    assert static.calls.last.request.url.params["mapset"] == "basic"
    assert "Elevation" not in _text(result)


@respx.mock
async def test_map_mode_has_no_link(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="car_fast", output="map"
    )
    assert len(_images(result)) == 1
    assert "Map link" not in _text(result)


@respx.mock
async def test_long_route_uses_multiple_elevation_batches(
    mcp_with_key: FastMCP,
) -> None:
    # ~20 km line -> 512 samples -> two calls of 256 positions
    respx.get(_ROUTE_URL).respond(
        200,
        json=_route_body(legs=[(20000, 18000)], coords=[[14.0, 50.0], [14.28, 50.0]]),
    )
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="bike_road")
    assert elevation.call_count == 2
    requests: list[httpx.Request] = [call.request for call in elevation.calls]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    for request in requests:
        assert len(request.url.params["positions"].split(";")) == 256
    assert len(_images(result)) == 2


@respx.mock
async def test_no_data_elevations_are_dropped(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)

    def with_gaps(request: httpx.Request) -> Response:
        count = len(request.url.params["positions"].split(";"))
        items = [
            {"elevation": -100000 if i % 2 else 400 + i * 0.01} for i in range(count)
        ]
        return Response(200, json={"items": items})

    respx.get(_ELEVATION_URL).mock(side_effect=with_gaps)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    text = _text(result)
    assert "Elevation: min 400 m" in text
    assert "-100000" not in text


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("output", ["url", "both"])
async def test_routing_failure_falls_back_to_link(
    mcp_with_key: FastMCP, output: str
) -> None:
    respx.get(_ROUTE_URL).respond(500)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="foot_fast", output=output
    )
    text = _text(result)
    assert text.startswith("Route planning failed (")
    assert "Map link for the user: https://mapy.com/fnc/v1/route" in text
    assert _images(result) == []


@respx.mock
async def test_routing_failure_in_map_mode_raises(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(401)
    with pytest.raises(ToolError, match="Route planning failed"):
        await _call(mcp_with_key, points=_POINTS, route_type="foot_fast", output="map")


@respx.mock
async def test_routing_timeout_falls_back_to_link(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    text = _text(await _call(mcp_with_key, points=_POINTS, route_type="foot_fast"))
    assert "Route planning failed" in text
    assert "Map link for the user" in text


@respx.mock
async def test_static_map_failure_in_both_keeps_summary_and_profile(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).respond(503)
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    text = _text(result)
    assert len(_images(result)) == 1  # profile only
    assert "Route (foot_fast): 3.8 km" in text
    assert "Map image unavailable (" in text
    assert "Elevation: min" in text
    assert "Map link for the user" in text


@respx.mock
async def test_static_map_failure_in_map_mode_raises(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).respond(503)
    with pytest.raises(ToolError, match="Map image unavailable"):
        await _call(mcp_with_key, points=_POINTS, route_type="car_fast", output="map")


@respx.mock
@pytest.mark.parametrize("output", ["map", "both"])
async def test_elevation_failure_is_a_note_not_fatal(
    mcp_with_key: FastMCP, output: str
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).respond(500)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="foot_fast", output=output
    )
    text = _text(result)
    assert len(_images(result)) == 1  # map only
    assert "Elevation profile unavailable (" in text
    assert "Elevation:" not in text
    assert "Route (foot_fast)" in text


@respx.mock
async def test_single_leg_route_still_lists_the_leg(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    text = _text(
        await _call(mcp_with_key, points=_POINTS, route_type="car_fast", output="url")
    )
    assert "1. Castle → 2. Square: 3.8 km, 49 min" in text


@respx.mock
async def test_all_no_data_elevations_give_note_and_no_profile(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)

    def no_data(request: httpx.Request) -> Response:
        count = len(request.url.params["positions"].split(";"))
        return Response(200, json={"items": [{"elevation": -100000}] * count})

    respx.get(_ELEVATION_URL).mock(side_effect=no_data)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert len(_images(result)) == 1
    assert "Elevation profile unavailable (" in _text(result)
    assert "Elevation:" not in _text(result)


@respx.mock
async def test_zero_length_route_skips_profile_without_error(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(
        200,
        json=_route_body(legs=[(0, 0)], coords=[[14.4, 50.09], [14.4, 50.09]]),
    )
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert not elevation.called
    assert "Elevation profile unavailable (" in _text(result)
