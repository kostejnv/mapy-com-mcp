"""Shared fixtures for the mapy-com-mcp test suite."""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from mapy_com_mcp.server import create_app


@pytest.fixture
def mcp() -> FastMCP:
    """A fresh FastMCP instance with all tools registered."""
    return create_app()
