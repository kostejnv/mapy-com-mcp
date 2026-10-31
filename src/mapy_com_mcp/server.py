from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastmcp import FastMCP

from . import tools
from .mapy_api.client import MapyClient

_LOG = logging.getLogger(__name__)

_BASE_INSTRUCTIONS = (
    "First-class access to mapy.com, the Czech mapping service from "
    "Seznam.cz. show_places puts one or more points on a map and "
    "show_route plans a route through several points; both give the user "
    "a mapy.com link to click. Use these whenever the user asks to see a "
    "place on a map or get directions, especially in the Czech Republic "
    "and surrounding region."
)
_HTTP_INSTRUCTIONS = (
    " When MAPY_API_KEY is configured, both tools also return map images "
    "with numbered markers and a coordinate grid so you can see where "
    "places are; show_route adds distance, time and, on foot or by bike, "
    "an elevation profile. A find_places tool resolves human-readable "
    "place names to coordinates — feed its output into the map tools."
)


def create_app() -> FastMCP:
    api_key = os.environ.get("MAPY_API_KEY")
    client = MapyClient(api_key) if api_key else None
    if client is None:
        _LOG.info("MAPY_API_KEY not set; map images and find_places are unavailable.")

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


def main() -> None:
    create_app().run()


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
