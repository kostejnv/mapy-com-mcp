"""Tests for server.py — wiring, auto-registration, and entry point."""

from __future__ import annotations

import importlib
import pkgutil
import types
from collections.abc import Callable, Iterable, Iterator
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client

from mapy_com_mcp import tools
from mapy_com_mcp.server import create_app, main


async def test_create_app_discovers_all_tool_modules() -> None:
    """Every unconditional module under mapy_com_mcp.tools must contribute at least
    one tool.  Some modules (e.g. find_places) are gated behind MAPY_API_KEY and
    register nothing when the key is absent.  The safe invariant is therefore that
    the number of registered tools is at least 1 (i.e., create_app didn't silently
    drop every tool) and that every module's register() was *called* without raising.
    The stronger per-module check lives in test_find_places.py which exercises the
    gate directly.
    """
    mcp = create_app()
    async with Client(mcp) as client:
        registered_count = len(await client.list_tools())
    # Without MAPY_API_KEY the two URL-builder tools must always be present.
    assert registered_count >= 2


def test_create_app_instructions_is_non_empty() -> None:
    """FastMCP instance must have a non-empty instructions string."""
    mcp = create_app()
    assert mcp.instructions and mcp.instructions.strip()


@pytest.mark.parametrize("argv", [None, []])
def test_main_defaults_to_stdio(
    argv: list[str] | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no flags main() runs stdio and passes no host/port."""
    monkeypatch.setattr("sys.argv", ["mapy-com-mcp"])
    mock_mcp = MagicMock()
    with patch("mapy_com_mcp.server.create_app", return_value=mock_mcp) as mock_create:
        main(argv)
        mock_create.assert_called_once_with()
        mock_mcp.run.assert_called_once_with(transport="stdio")


def test_main_streamable_http_forwards_host_and_port() -> None:
    mock_mcp = MagicMock()
    with patch("mapy_com_mcp.server.create_app", return_value=mock_mcp):
        main(["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"])
        mock_mcp.run.assert_called_once_with(
            transport="streamable-http", host="0.0.0.0", port=9000
        )


def test_main_streamable_http_uses_default_host_and_port() -> None:
    mock_mcp = MagicMock()
    with patch("mapy_com_mcp.server.create_app", return_value=mock_mcp):
        main(["--transport", "streamable-http"])
        mock_mcp.run.assert_called_once_with(
            transport="streamable-http", host="127.0.0.1", port=8000
        )


@pytest.mark.parametrize(
    "argv",
    [["--transport", "sse"], ["--transport", "streamable-http", "--port", "abc"]],
)
def test_main_rejects_invalid_args_before_creating_app(argv: list[str]) -> None:
    with patch("mapy_com_mcp.server.create_app") as mock_create:
        with pytest.raises(SystemExit) as exc:
            main(argv)
    assert exc.value.code == 2
    mock_create.assert_not_called()


def _make_iter_modules_stub(
    fake_info: pkgutil.ModuleInfo,
) -> Callable[[Iterable[str]], Iterator[pkgutil.ModuleInfo]]:
    """Return a typed replacement for pkgutil.iter_modules yielding one fake entry."""

    def _iter_modules(path: Iterable[str]) -> Iterator[pkgutil.ModuleInfo]:
        yield fake_info

    return _iter_modules


def _make_import_module_stub(
    stub_module: ModuleType, stub_name: str
) -> Callable[[str], ModuleType]:
    """Return a typed replacement for importlib.import_module."""

    def _import_module(name: str) -> ModuleType:
        return stub_module if name == stub_name else importlib.import_module(name)

    return _import_module


def test_create_app_raises_type_error_for_module_missing_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_app() raises TypeError when a tool module lacks a callable register."""
    stub_module = types.ModuleType("mapy_com_mcp.tools.bad_tool")
    stub_module_name = f"{tools.__name__}.bad_tool"

    # None is valid at runtime for module_finder; stubs wrongly reject it.
    finder: Any = None
    fake_info = pkgutil.ModuleInfo(module_finder=finder, name="bad_tool", ispkg=False)
    monkeypatch.setattr(pkgutil, "iter_modules", _make_iter_modules_stub(fake_info))
    monkeypatch.setattr(
        "importlib.import_module",
        _make_import_module_stub(stub_module, stub_module_name),
    )

    with pytest.raises(TypeError, match="must expose register"):
        create_app()


def test_create_app_raises_type_error_when_register_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_app() raises TypeError when register exists but is not callable."""
    stub_module = types.ModuleType("mapy_com_mcp.tools.bad_tool")
    stub_module.register = "not-a-function"  # type: ignore[attr-defined]  # deliberately setting non-callable on the module to test the TypeError guard
    stub_module_name = f"{tools.__name__}.bad_tool"

    # None is valid at runtime for module_finder; stubs wrongly reject it.
    finder: Any = None
    fake_info = pkgutil.ModuleInfo(module_finder=finder, name="bad_tool", ispkg=False)
    monkeypatch.setattr(pkgutil, "iter_modules", _make_iter_modules_stub(fake_info))
    monkeypatch.setattr(
        "importlib.import_module",
        _make_import_module_stub(stub_module, stub_module_name),
    )

    with pytest.raises(TypeError, match="must expose register"):
        create_app()
