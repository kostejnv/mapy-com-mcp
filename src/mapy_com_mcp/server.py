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
from .mapy_client import MapyClient

_LOG = logging.getLogger(__name__)

_BASE_INSTRUCTIONS = (
    "First-class access to mapy.com, the Czech mapping service from "
    "Seznam.cz. URL-builder tools compose mapy.com links the user can "
    "click — show one or more points on a map, or plan a route between "
    "two locations. Use these whenever the user asks to see a place on a "
    "map or get directions, especially in the Czech Republic and "
    "surrounding region."
)
_HTTP_INSTRUCTIONS = (
    " When MAPY_API_KEY is configured, the server also exposes a "
    "find_places tool that resolves human-readable place names to "
    "coordinates via the mapy.com REST API — feed its output into the "
    "URL-builder tools."
)


def create_app() -> FastMCP:
    api_key = os.environ.get("MAPY_API_KEY")
    client = MapyClient(api_key) if api_key else None
    if client is None:
        _LOG.info("MAPY_API_KEY not set; HTTP-backed tools will not be registered.")

    mcp = FastMCP(
        "mapy-com-mcp",
        instructions=_build_instructions(http_enabled=client is not None),
        on_duplicate="error",
        lifespan=_make_lifespan(client),
    )
    for info in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"{tools.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError(
                f"{module.__name__} must expose register(mcp, *, client=None)"
            )
        register(mcp, client=client)
    return mcp


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    app = create_app()
    if args.transport == "stdio":
        app.run(transport="stdio")
    else:
        app.run(transport="streamable-http", host=args.host, port=args.port)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mapy-com-mcp", description="MCP server for mapy.com."
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="stdio for local MCP clients (default), streamable-http over HTTP.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="HTTP bind address (streamable-http only)."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="HTTP port (streamable-http only)."
    )
    return parser.parse_args(argv)


def _build_instructions(*, http_enabled: bool) -> str:
    return _BASE_INSTRUCTIONS + (_HTTP_INSTRUCTIONS if http_enabled else "")


def _make_lifespan(
    client: MapyClient | None,
) -> Callable[[FastMCP], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_app: FastMCP) -> AsyncGenerator[None, None]:
        try:
            yield
        finally:
            if client is not None:
                await client.aclose()

    return lifespan
