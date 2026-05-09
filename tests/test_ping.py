"""Tests for the ping tool (tools/ping.py)."""

from __future__ import annotations

from fastmcp import Client, FastMCP


async def test_ping_appears_in_tool_list(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "ping" in names


async def test_ping_has_non_empty_description(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    ping = next(t for t in tools if t.name == "ping")
    assert ping.description and ping.description.strip()


async def test_ping_returns_pong(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("ping", {})
    assert result.data == "pong"


async def test_ping_is_not_an_error(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("ping", {})
    assert not result.is_error
