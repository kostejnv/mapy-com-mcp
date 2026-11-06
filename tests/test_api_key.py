"""Tests for api_key.py — the missing / rejected API key guard.

All HTTP is mocked with respx; no real network calls are made.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from httpx import Response

from mapy_com_mcp.api_key import MISSING_KEY_MESSAGE, REJECTED_KEY_MESSAGE
from mapy_com_mcp.server import create_app

_GEOCODE_URL = "https://api.mapy.com/v1/geocode"
_ROUTE_URL = "https://api.mapy.com/v1/routing/route"
_STATIC_URL = "https://api.mapy.com/v1/static/map"

_POINTS = [
    {"lon": 14.40, "lat": 50.09, "label": "Castle"},
    {"lon": 14.42, "lat": 50.08, "label": "Square"},
]
_CALLS: dict[str, dict[str, Any]] = {
    "find_places": {"queries": [{"query": "Praha"}]},
    "show_places": {"points": _POINTS, "output": "url"},
    "show_route": {"points": _POINTS, "route_type": "foot_fast", "output": "url"},
    "inspect_places": {"points": _POINTS},
    "plan_route": {"points": _POINTS, "route_type": "foot_fast"},
}


@pytest.fixture
def mcp_no_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.delenv("MAPY_API_KEY", raising=False)
    return create_app()


@pytest.fixture
def mcp_empty_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.setenv("MAPY_API_KEY", "")
    return create_app()


@pytest.fixture
def mcp_with_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    monkeypatch.setenv("MAPY_API_KEY", "fake-test-key")
    return create_app()


def test_messages_tell_how_to_fix_it() -> None:
    for message in (MISSING_KEY_MESSAGE, REJECTED_KEY_MESSAGE):
        assert "https://developer.mapy.com/account/" in message
        assert "MAPY_API_KEY" in message
    assert MISSING_KEY_MESSAGE.startswith("Mapy.com needs an API key")
    assert REJECTED_KEY_MESSAGE.startswith("Mapy.com rejected the API key")


@respx.mock
@pytest.mark.parametrize("tool", list(_CALLS))
async def test_missing_key_every_tool_returns_missing_message_without_http(
    mcp_no_key: FastMCP, tool: str
) -> None:
    route = respx.route().mock(return_value=Response(200, json={}))
    async with Client(mcp_no_key) as client:
        with pytest.raises(ToolError, match=r"Mapy\.com needs an API key"):
            await client.call_tool(tool, _CALLS[tool])
    assert not route.called


@respx.mock
async def test_empty_key_counts_as_missing(mcp_empty_key: FastMCP) -> None:
    async with Client(mcp_empty_key) as client:
        with pytest.raises(ToolError, match=r"Mapy\.com needs an API key"):
            await client.call_tool("show_places", _CALLS["show_places"])


@respx.mock
async def test_whitespace_only_key_counts_as_missing_without_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAPY_API_KEY", "   \n")
    route = respx.route().mock(return_value=Response(200, json={}))
    async with Client(create_app()) as client:
        with pytest.raises(ToolError, match=r"Mapy\.com needs an API key"):
            await client.call_tool("find_places", _CALLS["find_places"])
    assert not route.called


@respx.mock
async def test_missing_key_still_lists_tools(mcp_no_key: FastMCP) -> None:
    async with Client(mcp_no_key) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == set(_CALLS)


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_message_replaces_generic_tool_error(
    mcp_with_key: FastMCP, status: int
) -> None:
    respx.get(_GEOCODE_URL).mock(return_value=Response(status))
    async with Client(mcp_with_key) as client:
        with pytest.raises(ToolError) as exc_info:
            await client.call_tool("find_places", _CALLS["find_places"])
    assert str(exc_info.value) == REJECTED_KEY_MESSAGE


@respx.mock
async def test_url_output_works_with_key_that_would_be_rejected(
    mcp_with_key: FastMCP,
) -> None:
    route = respx.route().mock(return_value=Response(401))
    async with Client(mcp_with_key) as client:
        result = await client.call_tool("show_places", _CALLS["show_places"])
    assert not result.is_error
    assert not route.called


@respx.mock
@pytest.mark.parametrize(
    "failure",
    [Response(500, text="boom"), httpx.ConnectTimeout("slow")],
    ids=["500", "timeout"],
)
async def test_non_key_errors_do_not_show_rejected_message(
    mcp_with_key: FastMCP, failure: Response | Exception
) -> None:
    for url in (_ROUTE_URL, _STATIC_URL):
        if isinstance(failure, Exception):
            respx.get(url).mock(side_effect=failure)
        else:
            respx.get(url).mock(return_value=failure)
    async with Client(mcp_with_key) as client:
        result = await client.call_tool(
            "show_route",
            {"points": _POINTS, "route_type": "foot_fast", "output": "both"},
        )
    assert not result.is_error
    assert "rejected the API key" not in str(result.content)
    assert "Route planning failed" in str(result.content)
