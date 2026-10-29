"""Tests for tools/show_places.py — url / map / both output modes.

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

_STATIC_URL = "https://api.mapy.com/v1/static/map"
_POINTS = [
    {"lon": 14.4003, "lat": 50.0907, "label": "Prague Castle"},
    {"lon": 14.4178, "lat": 50.0880, "label": "Old Town Square"},
]
_ONE_POINT = _POINTS[:1]


def _png(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "#99bb99").save(buf, format="PNG")
    return buf.getvalue()


def _static_png_response(request: httpx.Request) -> Response:
    params = request.url.params
    return Response(200, content=_png(int(params["width"]), int(params["height"])))


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
        return await client.call_tool("show_places", args)


async def _tool(mcp: FastMCP) -> Any:
    async with Client(mcp) as client:
        return next(t for t in await client.list_tools() if t.name == "show_places")


def _text(result: Any) -> str:
    return "\n".join(c.text for c in result.content if isinstance(c, TextContent))


# ---------------------------------------------------------------------------
# Without an API key: URL only
# ---------------------------------------------------------------------------


async def test_without_key_schema_hides_output(mcp_no_key: FastMCP) -> None:
    tool = await _tool(mcp_no_key)
    props = set(tool.inputSchema["properties"])
    assert props == {"points", "mapset", "language"}


async def test_without_key_returns_url_only(mcp_no_key: FastMCP) -> None:
    result = await _call(mcp_no_key, points=_POINTS)
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextContent)
    assert _text(result).startswith("https://mapy.com/en/turisticka?vlastni-body")


async def test_without_key_annotations_are_closed_world(mcp_no_key: FastMCP) -> None:
    ann = (await _tool(mcp_no_key)).annotations
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is False
    assert ann.title and ann.title.strip()


async def test_without_key_single_point_uses_showmap(mcp_no_key: FastMCP) -> None:
    result = await _call(mcp_no_key, points=_ONE_POINT)
    url = _text(result)
    assert url.startswith("https://mapy.com/fnc/v1/showmap?")
    assert "center=14.4003,50.0907" in url
    assert "zoom=16" in url


async def test_without_key_empty_points_raises_tool_error(
    mcp_no_key: FastMCP,
) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_no_key, points=[])


async def test_empty_label_raises_tool_error(mcp_no_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_no_key, points=[{"lon": 14.0, "lat": 50.0, "label": ""}])


async def test_schema_has_no_zoom_field(mcp_with_key: FastMCP) -> None:
    props = (await _tool(mcp_with_key)).inputSchema["properties"]
    assert "zoom" not in props


# ---------------------------------------------------------------------------
# With an API key
# ---------------------------------------------------------------------------


async def test_with_key_schema_exposes_output_and_open_world(
    mcp_with_key: FastMCP,
) -> None:
    tool = await _tool(mcp_with_key)
    assert set(tool.inputSchema["properties"]) == {
        "points",
        "output",
        "mapset",
        "language",
    }
    assert tool.annotations.openWorldHint is True


@respx.mock
async def test_output_url_returns_link_without_calling_static_api(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, output="url")
    assert _text(result).startswith("https://mapy.com/")
    assert len(result.content) == 1
    assert not route.called


@respx.mock
async def test_output_map_returns_jpeg_image_and_legend(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, output="map")
    image, legend = result.content
    assert isinstance(image, ImageContent)
    assert image.mimeType == "image/jpeg"
    assert isinstance(legend, TextContent)
    assert legend.text.startswith("1. Prague Castle\n2. Old Town Square\nGrid: ")
    assert legend.text.endswith(" between lines.")
    assert "mapy.com" not in legend.text


@respx.mock
async def test_output_both_is_default_and_adds_link_to_legend(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS)
    image, legend = result.content
    assert isinstance(image, ImageContent)
    assert isinstance(legend, TextContent)
    assert "1. Prague Castle" in legend.text
    assert "\nMap link for the user: https://mapy.com/" in legend.text


@respx.mock
async def test_image_is_rendered_at_viewport_size(mcp_with_key: FastMCP) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, output="map")
    params = route.calls.last.request.url.params
    import base64

    img = Image.open(io.BytesIO(base64.b64decode(result.content[0].data)))  # type: ignore[union-attr]  # first content is ImageContent
    assert img.size == (int(params["width"]), int(params["height"]))


@respx.mock
async def test_static_api_receives_apikey_and_viewport(mcp_with_key: FastMCP) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    await _call(mcp_with_key, points=_POINTS, output="map", language="cs")
    params = route.calls.last.request.url.params
    assert params["apikey"] == "fake-test-key"
    assert params["mapset"] == "outdoor"
    assert params["lang"] == "cs"
    assert params["format"] == "png"


@respx.mock
@pytest.mark.parametrize(
    "mapset,expected",
    [
        ("traffic", "basic"),
        ("basic", "basic"),
        ("outdoor", "outdoor"),
        ("winter", "winter"),
        ("aerial", "aerial"),
    ],
)
async def test_static_mapset_mapping(
    mcp_with_key: FastMCP, mapset: str, expected: str
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, output="map", mapset=mapset)
    assert route.calls.last.request.url.params["mapset"] == expected
    assert not result.is_error


@respx.mock
async def test_traffic_mapset_still_used_in_link(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, mapset="traffic")
    assert "/dopravni?" in _text(result)


@respx.mock
async def test_image_and_link_share_the_same_viewport(mcp_with_key: FastMCP) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS)
    params = route.calls.last.request.url.params
    link = _text(result).split("Map link for the user: ")[1]
    assert f"z={params['zoom']}" in link
    assert f"x={round(float(params['lon']), 6)}" in link
    assert f"y={round(float(params['lat']), 6)}" in link


@respx.mock
async def test_single_point_map_works(mcp_with_key: FastMCP) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_ONE_POINT, output="both")
    assert route.calls.last.request.url.params["zoom"] == "16"
    assert "showmap" in _text(result)


@respx.mock
async def test_50_points_render(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    points = [
        {"lon": 14.0 + 0.01 * i, "lat": 50.0 + 0.005 * i, "label": f"P{i}"}
        for i in range(50)
    ]
    result = await _call(mcp_with_key, points=points, output="map")
    assert isinstance(result.content[0], ImageContent)
    assert "50. P49" in _text(result)


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.parametrize("status", [401, 500, 422])
async def test_both_falls_back_to_text_with_link_on_api_error(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_STATIC_URL).mock(return_value=Response(status, text="nope"))
    result = await _call(mcp_with_key, points=_POINTS, output="both")
    assert not result.is_error
    assert len(result.content) == 1
    text = _text(result)
    assert text.startswith("Map image unavailable (")
    assert "\nMap link for the user: https://mapy.com/" in text


@respx.mock
async def test_both_falls_back_on_network_error(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    result = await _call(mcp_with_key, points=_POINTS, output="both")
    assert _text(result).startswith("Map image unavailable (")
    assert "Map link for the user: https://mapy.com/" in _text(result)


@respx.mock
async def test_map_raises_tool_error_on_api_error(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(return_value=Response(500))
    with pytest.raises(ToolError, match="Map image unavailable"):
        await _call(mcp_with_key, points=_POINTS, output="map")


@respx.mock
async def test_map_raises_tool_error_on_network_error(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(ToolError, match="Map image unavailable"):
        await _call(mcp_with_key, points=_POINTS, output="map")


async def test_pole_point_does_not_raise(mcp_no_key: FastMCP) -> None:
    points = [{"lon": 0.0, "lat": 90.0, "label": "North Pole"}]
    result = await _call(mcp_no_key, points=points)
    assert _text(result).startswith("https://mapy.com/")
