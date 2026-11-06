"""Shared fixtures for the mapy-com-mcp test suite."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP
from fastmcp.apps import UI_EXTENSION_ID
from fastmcp.server.low_level import MiddlewareServerSession

from mapy_com_mcp.server import create_app


@pytest.fixture
def mcp() -> FastMCP:
    """A fresh FastMCP instance with all tools registered."""
    return create_app()


@pytest.fixture
def ui_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the in-process client look like one that advertises MCP Apps.

    The fastmcp Client cannot advertise extensions, so the session-level check
    is patched; client_shows_map_view still runs through get_context().
    """

    def supports(_self: MiddlewareServerSession, extension_id: str) -> bool:
        return extension_id == UI_EXTENSION_ID

    monkeypatch.setattr(MiddlewareServerSession, "client_supports_extension", supports)
