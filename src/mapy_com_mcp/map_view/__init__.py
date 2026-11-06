"""The inline map the user sees in clients that support MCP Apps.

One HTML view serves show_places and show_route. Everything it shows travels
in the tool result's `_meta`, never in `structuredContent`: Claude Code gives
the model structuredContent instead of the text content, which would hide the
tool's text from the model and paste base64 images into its context.
`map_view_meta` is the only place in Python that knows the keys;
`map_view.html` reads the same ones.
"""

from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import UI_EXTENSION_ID, UI_MIME_TYPE
from fastmcp.resources import TextResource
from fastmcp.server.dependencies import get_context
from pydantic import AnyUrl

_HERE = Path(__file__).parent
_HTML = (
    (_HERE / "map_view.html")
    .read_text(encoding="utf-8")
    .replace(
        "<!-- mapy-logo -->", (_HERE / "mapy_logo.svg").read_text(encoding="utf-8")
    )
)
# Clients cache the view by URI; a URI derived from the content changes with it.
MAP_VIEW_URI = (
    f"ui://mapy-com-mcp/map-view-{sha256(_HTML.encode()).hexdigest()[:12]}.html"
)
MAP_VIEW_TOOL_META: dict[str, Any] = {"ui": {"resourceUri": MAP_VIEW_URI}}


def register_map_view(mcp: FastMCP) -> None:
    mcp.add_resource(
        TextResource(
            uri=AnyUrl(MAP_VIEW_URI),
            name="map_view",
            text=_HTML,
            mime_type=UI_MIME_TYPE,
        )
    )


def client_shows_map_view() -> bool:
    """Whether the client of the current tool call renders the inline map."""
    return get_context().client_supports_extension(UI_EXTENSION_ID)


def map_view_meta(
    map_url: str,
    language: str,
    *,
    map_jpeg: bytes | None = None,
    route_length_m: int | None = None,
    route_duration_s: int | None = None,
    profile_jpeg: bytes | None = None,
    elevation_sparkline: list[int] | None = None,
) -> dict[str, Any]:
    """The tool result `_meta` the view renders; absent parts are left out."""
    meta: dict[str, Any] = {
        "map_url": map_url,
        "language": "cs" if language == "cs" else "en",
    }
    if map_jpeg is not None:
        meta["map_image_jpeg_base64"] = b64encode(map_jpeg).decode()
    if route_length_m is not None and route_duration_s is not None:
        meta["route_length_m"] = route_length_m
        meta["route_duration_s"] = route_duration_s
    if profile_jpeg is not None and elevation_sparkline is not None:
        meta["profile_image_jpeg_base64"] = b64encode(profile_jpeg).decode()
        meta["elevation_sparkline"] = elevation_sparkline
    return meta
