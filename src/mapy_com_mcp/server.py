from __future__ import annotations

import importlib
import pkgutil

from fastmcp import FastMCP

from . import tools


def create_app() -> FastMCP:
    mcp = FastMCP(
        "mapy-com-mcp",
        instructions=(
            "First-class access to mapy.com, the Czech mapping service from "
            "Seznam.cz. V1 ships URL-builder tools that compose mapy.com "
            "links the user can click — show one or more points on a map, or "
            "plan a route between two locations. Tools are local-only: no "
            "API key, no HTTP calls. Use these whenever the user asks to see "
            "a place on a map or get directions, especially in the Czech "
            "Republic and surrounding region."
        ),
        on_duplicate="error",
    )
    for info in pkgutil.iter_modules(tools.__path__):
        module = importlib.import_module(f"{tools.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if not callable(register):
            raise TypeError(f"{module.__name__} must expose a callable register(mcp)")
        register(mcp)
    return mcp


def main() -> None:
    create_app().run()
