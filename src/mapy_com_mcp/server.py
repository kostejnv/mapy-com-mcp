from __future__ import annotations

import argparse
import importlib
import logging
import os
import pkgutil
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastmcp import FastMCP

from . import tools
from .api_key import APIKeyGuard
from .map_view import register_map_view
from .mapy_api.client import MapyClient

_LOG = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "First-class access to mapy.com, the Czech mapping service from "
    "Seznam.cz, especially strong in the Czech Republic and surrounding "
    "region. When the user should see or open a map — places, or a route "
    "with directions — use show_places or show_route: the user gets the map "
    "right in the chat where the client supports it, or a mapy.com link to "
    "pass on; show_route also gives you distance and time. When you need to "
    "look at places or a route yourself before answering, use "
    "inspect_places or plan_route: map images with numbered markers and a "
    "coordinate grid, plus route numbers and, on foot or by bike, an "
    "elevation profile — the user sees nothing. find_places resolves "
    "human-readable place names to coordinates — feed its output into the "
    "map tools."
)


def create_app() -> FastMCP:
    api_key = os.environ.get("MAPY_API_KEY", "").strip()
    if not api_key:
        _LOG.warning("MAPY_API_KEY is not set; every tool call will fail.")
    # Without a key the guard stops every tool call before the client is used.
    client = MapyClient(api_key)

    mcp = FastMCP(
        "mapy-com-mcp",
        instructions=_INSTRUCTIONS,
        on_duplicate="error",
        lifespan=_make_lifespan(client),
        middleware=[APIKeyGuard(key_configured=bool(api_key))],
    )
    register_map_view(mcp)
    for info in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"{tools.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError(f"{module.__name__} must expose register(mcp, *, client)")
        register(mcp, client=client)
    return mcp


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app()
    if args.transport == "stdio":
        app.run(transport="stdio")
    else:
        app.run(transport="http", host=args.host, port=args.port)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mapy-com-mcp", description="MCP server for mapy.com."
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for a local MCP client (default), or Streamable HTTP.",
    )
    # Loopback by default: the server has no authentication of its own.
    parser.add_argument(
        "--host", default="127.0.0.1", help="HTTP bind address (http only)."
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (http only).")
    return parser.parse_args(argv)


def _make_lifespan(
    client: MapyClient,
) -> Callable[[FastMCP], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            await client.aclose()

    return lifespan
