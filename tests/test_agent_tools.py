"""Tests for tools/inspect_places.py and tools/plan_route.py.

Agent-only tools: images + text for the model, never a mapy.com link.
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

from mapy_com_mcp.api_key import MISSING_KEY_MESSAGE, REJECTED_KEY_MESSAGE
from mapy_com_mcp.server import create_app

_ROUTE_URL = "https://api.mapy.com/v1/routing/route"
_STATIC_URL = "https://api.mapy.com/v1/static/map"
_ELEVATION_URL = "https://api.mapy.com/v1/elevation"

_POINTS = [
    {"lon": 14.40, "lat": 50.09, "label": "Castle"},
    {"lon": 14.42, "lat": 50.08, "label": "Square"},
]


def _route_body(snap: float = 0) -> dict[str, Any]:
    return {
        "length": 3800,
        "duration": 2940,
        "parts": [{"length": 3800, "duration": 2940}],
        "geometry": {
            "geometry": {"coordinates": [[14.40, 50.09], [14.42, 50.08]]},
        },
        "routePoints": [{"snapDistance": snap}, {"snapDistance": 0}],
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
    return Response(
        200, json={"items": [{"elevation": 300 + i * 0.1} for i in range(count)]}
    )


def _no_data_elevation_response(request: httpx.Request) -> Response:
    count = len(request.url.params["positions"].split(";"))
    return Response(200, json={"items": [{"elevation": -100000}] * count})


@pytest.fixture
def mcp_with_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.setenv("MAPY_API_KEY", "fake-test-key")
    return create_app()


async def _call(mcp: FastMCP, tool: str, **args: Any) -> Any:
    async with Client(mcp) as client:
        return await client.call_tool(tool, args)


def _text(result: Any) -> str:
    return "\n".join(c.text for c in result.content if isinstance(c, TextContent))


def _images(result: Any) -> list[ImageContent]:
    return [c for c in result.content if isinstance(c, ImageContent)]


def _mock_plan_route_apis() -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "params", "required"),
    [
        ("inspect_places", {"points", "mapset", "language"}, {"points"}),
        ("plan_route", {"points", "route_type", "language"}, {"points", "route_type"}),
    ],
)
async def test_schema_has_no_output_param_and_is_read_only(
    mcp_with_key: FastMCP, tool: str, params: set[str], required: set[str]
) -> None:
    async with Client(mcp_with_key) as client:
        found = next(t for t in await client.list_tools() if t.name == tool)
    assert set(found.inputSchema["properties"]) == params
    assert set(found.inputSchema["required"]) == required
    assert found.annotations is not None
    assert found.annotations.readOnlyHint is True
    assert found.annotations.openWorldHint is True


async def test_plan_route_rejects_a_single_point(mcp_with_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(
            mcp_with_key, "plan_route", points=_POINTS[:1], route_type="foot_fast"
        )


async def test_inspect_places_rejects_empty_points(mcp_with_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_with_key, "inspect_places", points=[])


# ---------------------------------------------------------------------------
# inspect_places
# ---------------------------------------------------------------------------


@respx.mock
async def test_inspect_places_returns_image_and_legend_without_link(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    result = await _call(mcp_with_key, "inspect_places", points=_POINTS)
    assert len(result.content) == 2
    assert len(_images(result)) == 1
    assert _images(result)[0].mimeType == "image/jpeg"
    text = _text(result)
    assert text.startswith("1. Castle\n2. Square\nGrid: ")
    assert "mapy.com" not in text
    assert "link" not in text.lower()


@respx.mock
@pytest.mark.parametrize(
    ("mapset", "expected"), [("outdoor", "outdoor"), ("traffic", "basic")]
)
async def test_inspect_places_mapset_is_forwarded(
    mcp_with_key: FastMCP, mapset: str, expected: str
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_response)
    await _call(mcp_with_key, "inspect_places", points=_POINTS, mapset=mapset)
    assert route.calls.last.request.url.params["mapset"] == expected


@respx.mock
@pytest.mark.parametrize("status", [500, 422])
async def test_inspect_places_static_failure_raises_tool_error(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_STATIC_URL).respond(status, text="boom")
    with pytest.raises(ToolError, match="Map image unavailable"):
        await _call(mcp_with_key, "inspect_places", points=_POINTS)


@respx.mock
async def test_inspect_places_timeout_raises_tool_error(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="Map image unavailable"):
        await _call(mcp_with_key, "inspect_places", points=_POINTS)


# ---------------------------------------------------------------------------
# plan_route: happy paths
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize(
    "route_type", ["foot_fast", "foot_hiking", "bike_road", "bike_mountain"]
)
async def test_plan_route_foot_and_bike_return_map_profile_and_text(
    mcp_with_key: FastMCP, route_type: str
) -> None:
    _mock_plan_route_apis()
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type=route_type
    )
    assert len(_images(result)) == 2
    assert isinstance(result.content[-1], TextContent)
    text = _text(result)
    assert "Elevation: min 300 m" in text
    assert "Grid:" in text
    assert "mapy.com" not in text
    assert "link" not in text.lower()


@respx.mock
@pytest.mark.parametrize("route_type", ["car_fast", "car_short"])
async def test_plan_route_car_has_one_image_and_no_elevation_calls(
    mcp_with_key: FastMCP, route_type: str
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    elevation = respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type=route_type
    )
    assert len(_images(result)) == 1
    assert not elevation.called
    text = _text(result)
    assert "Elevation" not in text
    assert "Grid:" in text


@respx.mock
async def test_plan_route_text_contains_summary_and_warnings(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body(snap=500))
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast"
    )
    text = _text(result)
    assert "3.8 km" in text
    assert "Castle" in text
    assert "500 m" in text  # snap warning for the moved start point


# ---------------------------------------------------------------------------
# plan_route: failures
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("status", [500, 422])
async def test_plan_route_routing_failure_raises_tool_error(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_ROUTE_URL).respond(status, text="boom")
    with pytest.raises(ToolError, match="Route planning failed"):
        await _call(mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast")


@respx.mock
async def test_plan_route_routing_timeout_raises_tool_error(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ToolError, match="Route planning failed"):
        await _call(mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast")


@respx.mock
async def test_plan_route_static_failure_becomes_note_and_keeps_profile(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).respond(500, text="boom")
    respx.get(_ELEVATION_URL).mock(side_effect=_elevation_response)
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast"
    )
    assert len(_images(result)) == 1
    text = _text(result)
    assert "Map image unavailable (" in text
    assert "3.8 km" in text
    assert "Elevation: min" in text
    assert "Grid:" not in text


@respx.mock
async def test_plan_route_elevation_failure_becomes_note_and_keeps_map(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).respond(500, text="boom")
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast"
    )
    assert len(_images(result)) == 1
    text = _text(result)
    assert "Elevation profile unavailable (" in text
    assert "Elevation:" not in text
    assert "Grid:" in text


@respx.mock
async def test_plan_route_all_no_data_elevation_becomes_note(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_ROUTE_URL).respond(200, json=_route_body())
    respx.get(_STATIC_URL).mock(side_effect=_static_response)
    respx.get(_ELEVATION_URL).mock(side_effect=_no_data_elevation_response)
    result = await _call(
        mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast"
    )
    assert len(_images(result)) == 1
    assert "Elevation profile unavailable (" in _text(result)


# ---------------------------------------------------------------------------
# API key guard
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("failing", ["route", "static", "elevation"])
async def test_plan_route_rejected_key_gives_rejected_message(
    mcp_with_key: FastMCP, status: int, failing: str
) -> None:
    urls = {"route": _ROUTE_URL, "static": _STATIC_URL, "elevation": _ELEVATION_URL}
    _mock_plan_route_apis()
    respx.get(urls[failing]).respond(status)
    with pytest.raises(ToolError) as exc_info:
        await _call(mcp_with_key, "plan_route", points=_POINTS, route_type="foot_fast")
    assert str(exc_info.value) == REJECTED_KEY_MESSAGE


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_inspect_places_rejected_key_gives_rejected_message(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_STATIC_URL).respond(status)
    with pytest.raises(ToolError) as exc_info:
        await _call(mcp_with_key, "inspect_places", points=_POINTS)
    assert str(exc_info.value) == REJECTED_KEY_MESSAGE


@respx.mock
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("inspect_places", {"points": _POINTS}),
        ("plan_route", {"points": _POINTS, "route_type": "foot_fast"}),
    ],
)
async def test_missing_key_gives_missing_message_without_http(
    monkeypatch: pytest.MonkeyPatch, tool: str, args: dict[str, Any]
) -> None:
    monkeypatch.delenv("MAPY_API_KEY", raising=False)
    route = respx.route().mock(return_value=Response(200, json={}))
    with pytest.raises(ToolError) as exc_info:
        await _call(create_app(), tool, **args)
    assert str(exc_info.value) == MISSING_KEY_MESSAGE
    assert not route.called
