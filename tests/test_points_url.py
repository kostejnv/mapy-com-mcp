"""Tests for tools/points_url.py — FastMCP wrapper for build_points_url."""

from __future__ import annotations

import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError


async def test_build_points_url_appears_in_tool_list(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "build_points_url" in names


async def test_build_points_url_has_non_empty_description(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_points_url")
    assert tool.description and tool.description.strip()


async def test_build_points_url_annotations(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_points_url")
    ann = tool.annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is False


async def test_build_points_url_title_annotation(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_points_url")
    assert tool.annotations is not None
    assert tool.annotations.title and tool.annotations.title.strip()


async def test_build_points_url_schema_has_no_zoom_field(mcp: FastMCP) -> None:
    """Zoom is computed internally and must not be exposed to the LLM."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_points_url")
    schema_props = tool.inputSchema.get("properties", {})
    assert "zoom" not in schema_props


async def test_build_points_url_happy_path_returns_url_string(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "build_points_url",
            {"points": [{"lon": 14.4003, "lat": 50.0907, "label": "Prague Castle"}]},
        )
    assert not result.is_error
    assert isinstance(result.data, str)
    assert result.data.startswith("https://mapy.com/")


async def test_build_points_url_single_point_uses_showmap(mcp: FastMCP) -> None:
    """Single-point call dispatches to the showmap endpoint, not vlastni-body."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "build_points_url",
            {"points": [{"lon": 14.4003, "lat": 50.0907, "label": "Prague Castle"}]},
        )
    assert not result.is_error
    assert "/fnc/v1/showmap" in result.data
    assert "vlastni-body" not in result.data


async def test_build_points_url_multi_point_uses_vlastni_body(mcp: FastMCP) -> None:
    """Two-point call dispatches to the legacy vlastni-body endpoint."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "build_points_url",
            {
                "points": [
                    {"lon": 14.4003, "lat": 50.0907, "label": "Prague Castle"},
                    {"lon": 14.4178, "lat": 50.0880, "label": "Old Town Square"},
                ]
            },
        )
    assert not result.is_error
    assert "vlastni-body" in result.data
    assert "/fnc/v1/showmap" not in result.data


async def test_build_points_url_empty_points_raises_tool_error(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("build_points_url", {"points": []})


async def test_build_points_url_empty_label_raises_tool_error(mcp: FastMCP) -> None:
    """Empty label is rejected by Field(min_length=1) before the function runs."""
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "build_points_url",
                {"points": [{"lon": 14.0, "lat": 50.0, "label": ""}]},
            )


async def test_build_points_url_schema_has_points_mapset_language(mcp: FastMCP) -> None:
    """Input schema must expose points, mapset, and language — not more, not less."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "build_points_url")
    props = set(tool.inputSchema.get("properties", {}).keys())
    assert {"points", "mapset", "language"} <= props
