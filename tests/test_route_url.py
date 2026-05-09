"""Tests for tools/route_url.py — FastMCP wrapper for build_route_url."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

_PRAGUE_TO_BRNO = {
    "start_lon": 14.4378,
    "start_lat": 50.0755,
    "end_lon": 16.6068,
    "end_lat": 49.1951,
}


async def test_build_route_url_appears_in_tool_list(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "build_route_url" in names


async def test_build_route_url_has_non_empty_description(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_route_url")
    assert tool.description and tool.description.strip()


async def test_build_route_url_annotations(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_route_url")
    ann = tool.annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is False


async def test_build_route_url_title_annotation(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_route_url")
    assert tool.annotations is not None
    assert tool.annotations.title and tool.annotations.title.strip()


async def test_build_route_url_happy_path_returns_url_string(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("build_route_url", _PRAGUE_TO_BRNO)
    assert not result.is_error
    assert isinstance(result.data, str)
    assert result.data.startswith("https://mapy.com/")


async def test_build_route_url_docs_example_exact_url(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("build_route_url", _PRAGUE_TO_BRNO)
    expected = (
        "https://mapy.com/fnc/v1/route"
        "?start=14.4378,50.0755"
        "&end=16.6068,49.1951"
        "&routeType=car_fast"
        "&mapset=traffic"
        "&lang=en"
    )
    assert result.data == expected


async def test_build_route_url_no_waypoints_omits_waypoints_key(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("build_route_url", _PRAGUE_TO_BRNO)
    assert "waypoints" not in result.data


async def test_build_route_url_with_one_waypoint(mcp: FastMCP) -> None:
    payload = {**_PRAGUE_TO_BRNO, "waypoints": [[14.45, 50.08]]}
    async with Client(mcp) as client:
        result = await client.call_tool("build_route_url", payload)
    assert "waypoints=14.45,50.08" in result.data


async def test_build_route_url_15_waypoints_succeeds(mcp: FastMCP) -> None:
    wp = [[14.0 + i * 0.1, 50.0] for i in range(15)]
    payload = {**_PRAGUE_TO_BRNO, "waypoints": wp}
    async with Client(mcp) as client:
        result = await client.call_tool("build_route_url", payload)
    assert not result.is_error
    assert result.data.startswith("https://mapy.com/")


async def test_build_route_url_16_waypoints_raises_tool_error(mcp: FastMCP) -> None:
    """Pydantic max_length=15 on waypoints catches this before the function runs."""
    wp = [[14.0 + i * 0.1, 50.0] for i in range(16)]
    payload = {**_PRAGUE_TO_BRNO, "waypoints": wp}
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("build_route_url", payload)


async def test_build_route_url_schema_exposes_expected_fields(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_route_url")
    props = set(tool.inputSchema.get("properties", {}).keys())
    assert {
        "start_lon",
        "start_lat",
        "end_lon",
        "end_lat",
        "route_type",
        "language",
    } <= props
