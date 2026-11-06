"""Tests for the map_view package: served view, URI, and the _meta contract."""

from __future__ import annotations

import base64
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from mcp.types import TextResourceContents

import mapy_com_mcp.map_view as map_view
from mapy_com_mcp.map_view import MAP_VIEW_URI, map_view_meta

_VIEW_DIR = Path(map_view.__file__).parent
_JPEG = b"\xff\xd8fake-jpeg"
_FULL_KWARGS: dict[str, Any] = {
    "map_jpeg": _JPEG,
    "route_length_m": 3800,
    "route_duration_s": 2940,
    "profile_jpeg": _JPEG,
    "elevation_sparkline": [1, 2, 3],
}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


# ---------------------------------------------------------------------------
# Contract between map_view_meta and map_view.html
# ---------------------------------------------------------------------------


def test_html_reads_exactly_the_meta_keys_python_can_write() -> None:
    html = (_VIEW_DIR / "map_view.html").read_text(encoding="utf-8")
    read_by_view = set(re.findall(r"\bmeta\.([A-Za-z_]\w*)", html))
    written_by_python = set(map_view_meta("https://mapy.com/x", "en", **_FULL_KWARGS))
    assert read_by_view == written_by_python


# ---------------------------------------------------------------------------
# map_view_meta
# ---------------------------------------------------------------------------


def test_meta_minimal_has_only_url_and_language() -> None:
    assert map_view_meta("https://mapy.com/x", "en") == {
        "map_url": "https://mapy.com/x",
        "language": "en",
    }


@pytest.mark.parametrize(
    "language,expected",
    [("cs", "cs"), ("en", "en"), ("sk", "en"), ("de", "en"), ("pl", "en"), ("", "en")],
)
def test_meta_language_is_cs_or_en(language: str, expected: str) -> None:
    assert map_view_meta("u", language)["language"] == expected


def test_meta_map_image_is_base64_of_the_jpeg() -> None:
    meta = map_view_meta("u", "en", map_jpeg=_JPEG)
    assert meta["map_image_jpeg_base64"] == _b64(_JPEG)
    assert set(meta) == {"map_url", "language", "map_image_jpeg_base64"}


def test_meta_full_route_has_every_key() -> None:
    meta = map_view_meta("u", "cs", **_FULL_KWARGS)
    assert meta == {
        "map_url": "u",
        "language": "cs",
        "map_image_jpeg_base64": _b64(_JPEG),
        "route_length_m": 3800,
        "route_duration_s": 2940,
        "profile_image_jpeg_base64": _b64(_JPEG),
        "elevation_sparkline": [1, 2, 3],
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"route_length_m": 100},
        {"route_duration_s": 100},
    ],
)
def test_meta_route_numbers_are_both_or_neither(kwargs: dict[str, Any]) -> None:
    meta = map_view_meta("u", "en", **kwargs)
    assert "route_length_m" not in meta and "route_duration_s" not in meta


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profile_jpeg": _JPEG},
        {"elevation_sparkline": [1, 2]},
    ],
)
def test_meta_profile_and_sparkline_are_both_or_neither(
    kwargs: dict[str, Any],
) -> None:
    meta = map_view_meta("u", "en", **kwargs)
    assert "profile_image_jpeg_base64" not in meta
    assert "elevation_sparkline" not in meta


def test_meta_zero_route_numbers_are_kept() -> None:
    meta = map_view_meta("u", "en", route_length_m=0, route_duration_s=0)
    assert meta["route_length_m"] == 0 and meta["route_duration_s"] == 0


# ---------------------------------------------------------------------------
# URI and served resource
# ---------------------------------------------------------------------------


def test_uri_is_derived_from_the_inlined_html_hash() -> None:
    html = map_view._HTML  # pyright: ignore[reportPrivateUsage]
    digest = sha256(html.encode()).hexdigest()[:12]
    assert MAP_VIEW_URI == f"ui://mapy-com-mcp/map-view-{digest}.html"


def test_uri_changes_when_html_changes() -> None:
    html = map_view._HTML  # pyright: ignore[reportPrivateUsage]
    other = sha256((html + " ").encode()).hexdigest()[:12]
    assert other not in MAP_VIEW_URI


async def test_view_is_served_as_mcp_app_html_with_logo_inlined(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        contents = await client.read_resource(MAP_VIEW_URI)
    assert len(contents) == 1
    content = contents[0]
    assert isinstance(content, TextResourceContents)
    assert content.mimeType == "text/html;profile=mcp-app"
    assert "<svg" in content.text
    assert "<!-- mapy-logo -->" not in content.text


async def test_view_is_listed_among_resources(mcp: FastMCP) -> None:
    async with Client(mcp) as client:
        uris = {str(r.uri) for r in await client.list_resources()}
    assert MAP_VIEW_URI in uris


def test_html_source_still_has_the_logo_placeholder() -> None:
    html = (_VIEW_DIR / "map_view.html").read_text(encoding="utf-8")
    assert html.count("<!-- mapy-logo -->") == 1
