"""Tests for tools/show_route.py — link-only vs inline map view paths.

All HTTP is mocked with respx; no real network calls are made. The UI path is
driven with the ui_client fixture (conftest), which makes the client look
like one that advertises the MCP Apps extension.
"""

from __future__ import annotations

import base64
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

from mapy_com_mcp.map_view import MAP_VIEW_URI
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


def _jpeg_size(b64: str) -> tuple[int, int]:
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


# ---------------------------------------------------------------------------
# Input validation and registration
# ---------------------------------------------------------------------------


async def test_too_few_points_is_rejected(mcp_with_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_with_key, points=_POINTS[:1], route_type="foot_fast")


async def test_schema_has_no_output_and_is_open_world(mcp_with_key: FastMCP) -> None:
    async with Client(mcp_with_key) as client:
        tool = next(t for t in await client.list_tools() if t.name == "show_route")
    assert set(tool.inputSchema["properties"]) == {"points", "route_type", "language"}
    assert "route_type" in tool.inputSchema["required"]
    assert tool.annotations is not None
    assert tool.annotations.openWorldHint is True
    assert tool.meta is not None
    assert tool.meta["ui"]["resourceUri"] == MAP_VIEW_URI


async def test_build_route_url_tool_is_gone(mcp_with_key: FastMCP) -> None:
    async with Client(mcp_with_key) as client:
        names = {t.name for t in await client.list_tools()}
    assert "build_route_url" not in names
    assert "show_route" in names


# ---------------------------------------------------------------------------
# Client without the UI extension: summary + link, one routing call
# ---------------------------------------------------------------------------


@respx.mock
async def test_without_ui_one_routing_call_no_images_no_elevation_no_meta(
    mcp_with_key: FastMCP,
) -> None:
    routing = respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_hiking")
    assert routing.call_count == 1
    assert not static.called and not elevation.called
    assert _images(result) == []
    assert not result.meta
    assert result.structured_content is None
    text = _text(result)
    assert "Route (foot_hiking): 3.8 km, 49 min" in text
    assert "Elevation" not in text
    last = text.splitlines()[-1]
    assert last.startswith(
        "Give the user this mapy.com link to the route: https://mapy.com/fnc/v1/route"
    )


@respx.mock
async def test_routing_request_params(mcp_with_key: FastMCP) -> None:
    routing = respx.get(_ROUTE_URL).respond(
        200, json=_route_body(legs=[(1000, 600), (2000, 1200)])
    )
    await _call(
        mcp_with_key, points=_THREE_POINTS, route_type="car_short", language="cs"
    )
    params = routing.calls.last.request.url.params
    assert params["routeType"] == "car_short"
    assert params["lang"] == "cs"
    assert params["waypoints"] == "14.42,50.08"


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
    result = await _call(mcp_with_key, points=_POINTS, route_type="car_fast")
    assert expected in _text(result)


@respx.mock
async def test_per_leg_lines_tie_marker_numbers_to_labels(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(
        200, json=_route_body(legs=[(1200, 900), (2600, 2040)])
    )
    text = _text(await _call(mcp_with_key, points=_THREE_POINTS, route_type="car_fast"))
    assert "Route (car_fast): 3.8 km, 49 min" in text
    assert "1. Castle → 2. Square: 1.2 km, 15 min" in text
    assert "2. Square → 3. Park: 2.6 km, 34 min" in text


@respx.mock
async def test_single_leg_route_still_lists_the_leg(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    text = _text(await _call(mcp_with_key, points=_POINTS, route_type="car_fast"))
    assert "1. Castle → 2. Square: 3.8 km, 49 min" in text


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
    text = _text(await _call(mcp_with_key, points=_THREE_POINTS, route_type="car_fast"))
    warnings = next(line for line in text.splitlines() if line.startswith("Warnings:"))
    assert "1. Castle" not in warnings
    assert "2. Square was moved 120 m to the nearest road or path." in warnings
    assert "2. Square lies in a restricted area (pedestrian zone)." in warnings
    assert "3. Park lies in a restricted area (closure)." in warnings
    assert text.count("Warnings:") == 1


@respx.mock
async def test_no_warnings_line_when_all_clear(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    text = _text(await _call(mcp_with_key, points=_POINTS, route_type="car_fast"))
    assert "Warnings" not in text


@respx.mock
async def test_without_ui_warnings_come_before_the_link(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(
        200, json=_route_body(route_points=[{"snapDistance": 90}, {"snapDistance": 0}])
    )
    lines = _text(
        await _call(mcp_with_key, points=_POINTS, route_type="car_fast")
    ).splitlines()
    assert lines[-2].startswith("Warnings:")
    assert lines[-1].startswith("Give the user this mapy.com link")


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [Response(500), httpx.ConnectTimeout("slow")],
    ids=["500", "timeout"],
)
async def test_without_ui_routing_failure_gives_text_with_link(
    mcp_with_key: FastMCP, failure: Response | Exception
) -> None:
    if isinstance(failure, Exception):
        respx.get(_ROUTE_URL).mock(side_effect=failure)
    else:
        respx.get(_ROUTE_URL).mock(return_value=failure)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert not result.is_error
    text = _text(result)
    assert text.startswith("Route planning failed (")
    assert "Give the user this mapy.com link to the route: https://mapy.com/" in text
    assert not result.meta


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_without_ui_rejected_key_on_routing_raises_rejected_message(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_ROUTE_URL).respond(status)
    with pytest.raises(ToolError, match=r"Mapy\.com rejected the API key"):
        await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")


# ---------------------------------------------------------------------------
# Client with the UI extension
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_foot_meta_has_map_numbers_profile_and_sparkline(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")

    meta = result.meta
    assert set(meta) == {
        "map_url",
        "language",
        "map_image_jpeg_base64",
        "route_length_m",
        "route_duration_s",
        "profile_image_jpeg_base64",
        "elevation_sparkline",
    }
    assert meta["route_length_m"] == 3800
    assert meta["route_duration_s"] == 2940
    assert meta["map_url"].startswith("https://mapy.com/fnc/v1/route")
    assert _jpeg_size(meta["map_image_jpeg_base64"]) == (1024, 640)
    assert _jpeg_size(meta["profile_image_jpeg_base64"]) == (1024, 280)
    assert all(isinstance(v, int) for v in meta["elevation_sparkline"])
    assert len(meta["elevation_sparkline"]) > 1
    assert elevation.call_count == 1
    params = static.calls.last.request.url.params
    assert (int(params["width"]), int(params["height"])) == (1024, 640)
    assert params["mapset"] == "outdoor"


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_text_is_plain_no_images_no_base64_no_structured_content(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert all(isinstance(c, TextContent) for c in result.content)
    assert result.structured_content is None
    text = _text(result)
    assert result.meta["map_image_jpeg_base64"] not in text
    assert result.meta["profile_image_jpeg_base64"] not in text
    assert "Route (foot_fast): 3.8 km, 49 min" in text
    assert "Elevation: min 300 m, max 326 m" in text
    assert "Grid" not in text
    assert "https://" not in text
    last = text.splitlines()[-1]
    assert last.startswith("The user now sees, in the chat, ")
    assert "the route on a map" in last
    assert "an elevation profile" in last


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_car_has_map_and_numbers_but_no_profile_or_elevation_calls(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="car_fast")
    assert not elevation.called
    assert static.calls.last.request.url.params["mapset"] == "basic"
    assert set(result.meta) == {
        "map_url",
        "language",
        "map_image_jpeg_base64",
        "route_length_m",
        "route_duration_s",
    }
    last = _text(result).splitlines()[-1]
    assert "elevation profile" not in last
    assert "its length and time" in last


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_language_cs_in_meta(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="car_fast", language="cs"
    )
    assert result.meta["language"] == "cs"


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_german_maps_to_en_in_meta(mcp_with_key: FastMCP) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    result = await _call(
        mcp_with_key, points=_POINTS, route_type="car_fast", language="de"
    )
    assert result.meta["language"] == "en"


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_long_route_uses_multiple_elevation_batches(
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
    assert "profile_image_jpeg_base64" in result.meta


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_no_data_elevations_are_dropped(mcp_with_key: FastMCP) -> None:
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
    assert "Elevation: min 400 m" in _text(result)
    assert -100000 not in result.meta["elevation_sparkline"]


# ---------------------------------------------------------------------------
# UI path failures: never raise (except a rejected key)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize(
    "failure",
    [Response(500), httpx.ConnectTimeout("slow")],
    ids=["500", "timeout"],
)
async def test_with_ui_routing_failure_gives_text_and_meta_with_only_url_and_language(
    mcp_with_key: FastMCP, failure: Response | Exception
) -> None:
    if isinstance(failure, Exception):
        respx.get(_ROUTE_URL).mock(side_effect=failure)
    else:
        respx.get(_ROUTE_URL).mock(return_value=failure)
    static = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert not result.is_error
    assert set(result.meta) == {"map_url", "language"}
    assert _text(result).startswith("Route planning failed (")
    assert not static.called


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_map_failure_drops_profile_from_meta_but_keeps_elevation_line(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).respond(503)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert not result.is_error
    assert elevation.called
    assert set(result.meta) == {
        "map_url",
        "language",
        "route_length_m",
        "route_duration_s",
    }
    assert result.meta["route_length_m"] == 3800
    text = _text(result)
    assert "The map image could not be drawn (" in text
    assert "Route (foot_fast): 3.8 km" in text
    assert "Elevation: min 300 m, max 326 m" in text
    last = text.splitlines()[-1]
    assert "the route on a map" not in last
    assert "elevation profile" not in last
    assert "its length and time" in last


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize("what", ["http", "no-data"])
async def test_with_ui_elevation_failure_is_a_note_and_meta_has_no_profile(
    mcp_with_key: FastMCP, what: str
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    if what == "http":
        respx.get(_ELEVATION_URL).respond(500)
    else:

        def no_data(request: httpx.Request) -> Response:
            count = len(request.url.params["positions"].split(";"))
            return Response(200, json={"items": [{"elevation": -100000}] * count})

        respx.get(_ELEVATION_URL).mock(side_effect=no_data)
    result = await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
    assert not result.is_error
    text = _text(result)
    assert "Elevation profile unavailable (" in text
    assert "Elevation:" not in text
    assert "profile_image_jpeg_base64" not in result.meta
    assert "elevation_sparkline" not in result.meta
    assert "map_image_jpeg_base64" in result.meta
    assert "elevation profile" not in text.splitlines()[-1]


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_zero_length_route_skips_profile_without_error(
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
    assert "profile_image_jpeg_base64" not in result.meta


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize("status", [401, 403])
async def test_with_ui_rejected_key_on_routing_raises_rejected_message(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_ROUTE_URL).respond(status)
    with pytest.raises(ToolError, match=r"Mapy\.com rejected the API key"):
        await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize("status", [401, 403])
async def test_with_ui_rejected_key_on_static_map_raises_rejected_message(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).respond(status)
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    with pytest.raises(ToolError, match=r"Mapy\.com rejected the API key"):
        await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_rejected_key_on_elevation_raises_rejected_message(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).respond(401)
    with pytest.raises(ToolError, match=r"Mapy\.com rejected the API key"):
        await _call(mcp_with_key, points=_POINTS, route_type="foot_fast")
