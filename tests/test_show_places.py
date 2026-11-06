"""Tests for tools/show_places.py — link-only vs inline map view paths.

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
# Schema and validation
# ---------------------------------------------------------------------------


async def test_schema_has_no_output_or_zoom_and_is_open_world(
    mcp_with_key: FastMCP,
) -> None:
    tool = await _tool(mcp_with_key)
    assert set(tool.inputSchema["properties"]) == {"points", "mapset", "language"}
    assert tool.annotations.openWorldHint is True


async def test_tool_meta_points_at_the_map_view(mcp_with_key: FastMCP) -> None:
    tool = await _tool(mcp_with_key)
    assert tool.meta["ui"]["resourceUri"] == MAP_VIEW_URI


async def test_empty_points_raises_tool_error(mcp_with_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_with_key, points=[])


async def test_empty_label_raises_tool_error(mcp_with_key: FastMCP) -> None:
    with pytest.raises(ToolError):
        await _call(mcp_with_key, points=[{"lon": 14.0, "lat": 50.0, "label": ""}])


# ---------------------------------------------------------------------------
# Client without the UI extension: text + link, no static API
# ---------------------------------------------------------------------------


@respx.mock
async def test_without_ui_returns_link_text_only_and_no_http(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.route().mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS)
    assert len(result.content) == 1
    text = _text(result)
    assert text.startswith(
        "Give the user this mapy.com link to the places: "
        "https://mapy.com/en/turisticka?vlastni-body"
    )
    assert "1. Prague Castle\n2. Old Town Square" in text
    assert not route.called
    assert not result.meta
    assert result.structured_content is None


@respx.mock
async def test_without_ui_single_point_uses_showmap(mcp_with_key: FastMCP) -> None:
    text = _text(await _call(mcp_with_key, points=_ONE_POINT))
    assert "https://mapy.com/fnc/v1/showmap?" in text
    assert "center=14.4003,50.0907" in text
    assert "zoom=16" in text


async def test_without_ui_traffic_mapset_in_link(mcp_with_key: FastMCP) -> None:
    text = _text(await _call(mcp_with_key, points=_POINTS, mapset="traffic"))
    assert "/dopravni?" in text


async def test_pole_point_does_not_raise(mcp_with_key: FastMCP) -> None:
    points = [{"lon": 0.0, "lat": 90.0, "label": "North Pole"}]
    assert "https://mapy.com/" in _text(await _call(mcp_with_key, points=points))


@respx.mock
async def test_without_ui_works_with_key_that_would_be_rejected(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.route().mock(return_value=Response(401))
    result = await _call(mcp_with_key, points=_POINTS)
    assert not result.is_error
    assert not route.called


# ---------------------------------------------------------------------------
# Client with the UI extension: meta carries the map
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_returns_meta_with_jpeg_map_and_text_without_base64(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, language="cs")
    meta = result.meta
    assert meta["language"] == "cs"
    assert meta["map_url"].startswith("https://mapy.com/cs/turisticka?vlastni-body")
    jpeg = base64.b64decode(meta["map_image_jpeg_base64"])
    assert Image.open(io.BytesIO(jpeg)).format == "JPEG"
    assert not any(isinstance(c, ImageContent) for c in result.content)
    assert result.structured_content is None
    text = _text(result)
    assert text.startswith("The user now sees these places on a map")
    assert "1. Prague Castle\n2. Old Town Square" in text
    assert meta["map_image_jpeg_base64"] not in text
    assert "https://" not in text


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_map_is_landscape_1024x640_without_grid(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS)
    params = route.calls.last.request.url.params
    assert (int(params["width"]), int(params["height"])) == (1024, 640)
    jpeg = base64.b64decode(result.meta["map_image_jpeg_base64"])
    assert Image.open(io.BytesIO(jpeg)).size == (1024, 640)
    assert "Grid" not in _text(result)


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_landscape_even_for_tall_point_sets(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    tall = [
        {"lon": 14.40, "lat": 49.0, "label": "S"},
        {"lon": 14.41, "lat": 51.0, "label": "N"},
    ]
    await _call(mcp_with_key, points=tall)
    params = route.calls.last.request.url.params
    assert int(params["width"]) > int(params["height"])


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_static_api_params_and_link_share_viewport(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, language="cs")
    params = route.calls.last.request.url.params
    assert params["apikey"] == "fake-test-key"
    assert params["lang"] == "cs"
    assert params["format"] == "png"
    url = result.meta["map_url"]
    assert f"z={params['zoom']}" in url
    assert f"x={round(float(params['lon']), 6)}" in url
    assert f"y={round(float(params['lat']), 6)}" in url


@respx.mock
@pytest.mark.usefixtures("ui_client")
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
async def test_with_ui_static_mapset_mapping(
    mcp_with_key: FastMCP, mapset: str, expected: str
) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, mapset=mapset)
    assert route.calls.last.request.url.params["mapset"] == expected
    assert not result.is_error


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_traffic_mapset_still_used_in_link(
    mcp_with_key: FastMCP,
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, mapset="traffic")
    assert "/dopravni?" in result.meta["map_url"]


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_single_point_zoom_16(mcp_with_key: FastMCP) -> None:
    route = respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_ONE_POINT)
    assert route.calls.last.request.url.params["zoom"] == "16"
    assert "showmap" in result.meta["map_url"]


@respx.mock
@pytest.mark.usefixtures("ui_client")
async def test_with_ui_50_points_render(mcp_with_key: FastMCP) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    points = [
        {"lon": 14.0 + 0.01 * i, "lat": 50.0 + 0.005 * i, "label": f"P{i}"}
        for i in range(50)
    ]
    result = await _call(mcp_with_key, points=points)
    assert "map_image_jpeg_base64" in result.meta
    assert "50. P49" in _text(result)


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize("language", ["sk", "de", "pl"])
async def test_with_ui_other_languages_map_to_en_in_meta(
    mcp_with_key: FastMCP, language: str
) -> None:
    respx.get(_STATIC_URL).mock(side_effect=_static_png_response)
    result = await _call(mcp_with_key, points=_POINTS, language=language)
    assert result.meta["language"] == "en"


# ---------------------------------------------------------------------------
# UI path failures
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize(
    "failure",
    [Response(500, text="nope"), Response(422, text="bad"), httpx.ConnectTimeout("x")],
    ids=["500", "422", "timeout"],
)
async def test_with_ui_map_failure_degrades_to_note_and_meta_without_image(
    mcp_with_key: FastMCP, failure: Response | Exception
) -> None:
    if isinstance(failure, Exception):
        respx.get(_STATIC_URL).mock(side_effect=failure)
    else:
        respx.get(_STATIC_URL).mock(return_value=failure)
    result = await _call(mcp_with_key, points=_POINTS)
    assert not result.is_error
    assert set(result.meta) == {"map_url", "language"}
    text = _text(result)
    assert text.startswith("The map image could not be drawn (")
    assert "1. Prague Castle" in text


@respx.mock
@pytest.mark.usefixtures("ui_client")
@pytest.mark.parametrize("status", [401, 403])
async def test_with_ui_rejected_key_raises_rejected_message(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_STATIC_URL).mock(return_value=Response(status))
    with pytest.raises(ToolError, match=r"Mapy\.com rejected the API key"):
        await _call(mcp_with_key, points=_POINTS)
