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
    """Every module under mapy_com_mcp.tools must be registered."""
    expected = {info.name for info in pkgutil.iter_modules(tools.__path__)}
    mcp = create_app()
    async with Client(mcp) as client:
        registered = {t.name for t in await client.list_tools()}
    assert expected <= registered


async def test_create_app_includes_ping() -> None:
    """create_app() populates a FastMCP with at least 'ping'."""
    mcp = create_app()
    async with Client(mcp) as client:
        names = [t.name for t in await client.list_tools()]
    assert "ping" in names


def test_main_calls_create_app_and_run() -> None:
    """main() must call create_app() and invoke mcp.run() exactly once."""
    mock_mcp = MagicMock()
    with patch("mapy_com_mcp.server.create_app", return_value=mock_mcp) as mock_create:
        main()
        mock_create.assert_called_once_with()
        mock_mcp.run.assert_called_once_with()


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

    with pytest.raises(TypeError, match="must expose a callable register"):
        create_app()


def test_create_app_raises_type_error_when_register_not_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """create_app() raises TypeError when register exists but is not callable."""
    stub_module = types.ModuleType("mapy_com_mcp.tools.bad_tool")
    stub_module.register = "not-a-function"  # type: ignore[attr-defined]
    stub_module_name = f"{tools.__name__}.bad_tool"

    # None is valid at runtime for module_finder; stubs wrongly reject it.
    finder: Any = None
    fake_info = pkgutil.ModuleInfo(module_finder=finder, name="bad_tool", ispkg=False)
    monkeypatch.setattr(pkgutil, "iter_modules", _make_iter_modules_stub(fake_info))
    monkeypatch.setattr(
        "importlib.import_module",
        _make_import_module_stub(stub_module, stub_module_name),
    )

    with pytest.raises(TypeError, match="must expose a callable register"):
        create_app()
