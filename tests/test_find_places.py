"""Tests for tools/find_places.py — the geocoding MCP tool.

Tests cover:
  - Registration gate (tool absent without API key, present with one)
  - Happy path via fastmcp.Client
  - Per-query near coordinate forwarded as preferNear
  - Partial failure (one query 500s, other succeeds — tool does NOT raise)
  - All-failure (every query 500s — tool raises ToolError)
  - Batch ordering preserved

All HTTP is mocked with respx; no real network calls are made.
"""

from __future__ import annotations

from typing import Any

import pytest
import respx
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError
from httpx import Response

from mapy_com_mcp.server import create_app

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_API_KEY = "fake-test-key"
_GEOCODE_URL = "https://api.mapy.com/v1/geocode"


def _make_item(
    name: str, lon: float, lat: float, entity_type: str = "poi"
) -> dict[str, Any]:
    return {
        "name": name,
        "label": "Místo",
        "position": {"lon": lon, "lat": lat},
        "type": entity_type,
        "location": "Praha, Česko",
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mcp_no_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    """FastMCP instance created without MAPY_API_KEY in the environment."""
    monkeypatch.delenv("MAPY_API_KEY", raising=False)
    return create_app()


@pytest.fixture
def mcp_with_key(monkeypatch: pytest.MonkeyPatch) -> FastMCP:
    """FastMCP instance created with MAPY_API_KEY set."""
    monkeypatch.setenv("MAPY_API_KEY", _API_KEY)
    return create_app()


# ---------------------------------------------------------------------------
# Registration gate
# ---------------------------------------------------------------------------


async def test_find_places_absent_without_api_key(mcp_no_key: FastMCP) -> None:
    """find_places must NOT appear in the tool list when MAPY_API_KEY is unset."""
    async with Client(mcp_no_key) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "find_places" not in names


async def test_url_tools_present_without_api_key(mcp_no_key: FastMCP) -> None:
    """URL-builder tools must always be registered regardless of API key."""
    async with Client(mcp_no_key) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "show_places" in names
    assert "build_route_url" in names


async def test_find_places_present_with_api_key(mcp_with_key: FastMCP) -> None:
    """find_places must appear in the tool list when MAPY_API_KEY is set."""
    async with Client(mcp_with_key) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "find_places" in names


async def test_all_three_tools_present_with_api_key(mcp_with_key: FastMCP) -> None:
    """All three tools are registered together when the API key is configured."""
    async with Client(mcp_with_key) as client:
        tools = await client.list_tools()
    names = [t.name for t in tools]
    assert "show_places" in names
    assert "build_route_url" in names
    assert "find_places" in names


# ---------------------------------------------------------------------------
# find_places tool schema
# ---------------------------------------------------------------------------


async def test_find_places_has_non_empty_description(mcp_with_key: FastMCP) -> None:
    async with Client(mcp_with_key) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "find_places")
    assert tool.description and tool.description.strip()


async def test_find_places_annotations(mcp_with_key: FastMCP) -> None:
    async with Client(mcp_with_key) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "find_places")
    ann = tool.annotations
    assert ann is not None
    assert ann.readOnlyHint is True
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.openWorldHint is True


# ---------------------------------------------------------------------------
# Happy path — single query
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_single_query_happy_path(
    mcp_with_key: FastMCP,
) -> None:
    """A single geocoding query returns one GeocodeQueryResult with matches.

    FastMCP returns Pydantic model instances (exposed as Root objects) when
    the tool returns Pydantic models; we access fields via attribute lookup.
    """
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(
            200,
            json={"items": [_make_item("Karlův most", 14.4112, 50.0865)]},
        )
    )

    async with Client(mcp_with_key) as client:
        result = await client.call_tool(
            "find_places",
            {"queries": [{"query": "Charles Bridge"}]},
        )

    assert not result.is_error
    data: list[Any] = result.data  # type: narrowed from fastmcp's untyped Client.data
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item.query == "Charles Bridge"  # type: ignore[union-attr]
    assert item.error is None  # type: ignore[union-attr]
    assert len(item.matches) == 1  # type: ignore[union-attr]
    assert item.matches[0].name == "Karlův most"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Happy path — batch of 2 queries, results in input order
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_batch_preserves_order(
    mcp_with_key: FastMCP,
) -> None:
    """Batch results are returned in input order, not response-arrival order."""
    call_count = 0

    def side_effect(request: Any) -> Response:
        nonlocal call_count
        call_count += 1
        query = request.url.params.get("query", "")
        if "Bridge" in query:
            return Response(
                200, json={"items": [_make_item("Karlův most", 14.4112, 50.0865)]}
            )
        return Response(
            200, json={"items": [_make_item("Praha hlavní nádraží", 14.4350, 50.0828)]}
        )

    respx.get(_GEOCODE_URL).mock(side_effect=side_effect)

    async with Client(mcp_with_key) as client:
        result = await client.call_tool(
            "find_places",
            {
                "queries": [
                    {"query": "Charles Bridge"},
                    {"query": "Praha hlavní nádraží"},
                ]
            },
        )

    data = result.data
    assert not result.is_error
    assert len(data) == 2
    assert data[0].query == "Charles Bridge"  # type: ignore[union-attr]
    assert data[1].query == "Praha hlavní nádraží"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# near coordinate forwarded as preferNear
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_near_forwarded_as_prefer_near(
    mcp_with_key: FastMCP,
) -> None:
    """GeocodeQuery.near.lon/lat must arrive as preferNear=lon,lat on the request."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    async with Client(mcp_with_key) as client:
        await client.call_tool(
            "find_places",
            {
                "queries": [
                    {
                        "query": "restaurant",
                        "near": {"lon": 14.4378, "lat": 50.0755},
                    }
                ]
            },
        )

    request = route.calls.last.request
    assert request.url.params["preferNear"] == "14.4378,50.0755"


@respx.mock
async def test_find_places_no_near_omits_prefer_near(
    mcp_with_key: FastMCP,
) -> None:
    """When near is absent, preferNear must not appear in the request."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    async with Client(mcp_with_key) as client:
        await client.call_tool(
            "find_places",
            {"queries": [{"query": "Prague Castle"}]},
        )

    params = route.calls.last.request.url.params
    assert "preferNear" not in params


# ---------------------------------------------------------------------------
# Partial failure — one query fails, the other succeeds
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_partial_failure_does_not_raise(
    mcp_with_key: FastMCP,
) -> None:
    """If one query fails and another succeeds, the tool must NOT raise — the
    failing result gets its `error` field set, the succeeding one is normal."""
    call_count = 0

    def side_effect(request: Any) -> Response:
        nonlocal call_count
        call_count += 1
        if "fail" in request.url.params.get("query", "").lower():
            return Response(500, text="Internal Server Error")
        return Response(
            200, json={"items": [_make_item("Prague Castle", 14.4003, 50.0907)]}
        )

    respx.get(_GEOCODE_URL).mock(side_effect=side_effect)

    async with Client(mcp_with_key) as client:
        result = await client.call_tool(
            "find_places",
            {
                "queries": [
                    {"query": "Prague Castle"},
                    {"query": "fail this one"},
                ]
            },
        )

    assert not result.is_error
    data = result.data
    assert len(data) == 2

    # First query succeeded.
    assert data[0].query == "Prague Castle"  # type: ignore[union-attr]
    assert data[0].error is None  # type: ignore[union-attr]
    assert len(data[0].matches) == 1  # type: ignore[union-attr]

    # Second query failed — error field set, empty matches.
    assert data[1].query == "fail this one"  # type: ignore[union-attr]
    assert data[1].error is not None  # type: ignore[union-attr]
    assert data[1].matches == []  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# All-failure — every query fails → ToolError
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_all_failures_raises_tool_error(
    mcp_with_key: FastMCP,
) -> None:
    """If every query in the batch fails, find_places must raise ToolError."""
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(500, text="Internal Server Error")
    )

    async with Client(mcp_with_key) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "find_places",
                {
                    "queries": [
                        {"query": "nowhere"},
                        {"query": "also nowhere"},
                    ]
                },
            )


# ---------------------------------------------------------------------------
# Language parameter forwarded
# ---------------------------------------------------------------------------


@respx.mock
async def test_find_places_language_forwarded(mcp_with_key: FastMCP) -> None:
    """The `language` parameter must reach the HTTP request as `lang`."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    async with Client(mcp_with_key) as client:
        await client.call_tool(
            "find_places",
            {"queries": [{"query": "Praha"}], "language": "cs"},
        )

    params = route.calls.last.request.url.params
    assert params["lang"] == "cs"


# ---------------------------------------------------------------------------
# Instructions string updated when key is present
# ---------------------------------------------------------------------------


def test_instructions_include_find_places_hint_when_key_set(
    mcp_with_key: FastMCP,
) -> None:
    """When MAPY_API_KEY is set, instructions must mention find_places."""
    assert mcp_with_key.instructions is not None
    assert "find_places" in mcp_with_key.instructions


def test_instructions_do_not_mention_find_places_without_key(
    mcp_no_key: FastMCP,
) -> None:
    """Without MAPY_API_KEY, the base instructions must NOT reference find_places
    (the hint is appended only when the tool is available)."""
    assert mcp_no_key.instructions is not None
    assert mcp_no_key.instructions.strip()
    assert "find_places" not in mcp_no_key.instructions
