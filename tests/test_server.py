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


async def test_create_app_registers_all_five_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All tools are registered regardless of whether a key is configured."""
    for key in (None, "fake-test-key"):
        if key is None:
            monkeypatch.delenv("MAPY_API_KEY", raising=False)
        else:
            monkeypatch.setenv("MAPY_API_KEY", key)
        async with Client(create_app()) as client:
            names = {t.name for t in await client.list_tools()}
        assert names == {
            "find_places",
            "show_places",
            "show_route",
            "inspect_places",
            "plan_route",
        }


def test_create_app_instructions_mention_all_tools() -> None:
    """One instructions string, naming every tool, with or without a key."""
    mcp = create_app()
    assert mcp.instructions
    for name in (
        "find_places",
        "show_places",
        "show_route",
        "inspect_places",
        "plan_route",
    ):
        assert name in mcp.instructions


@pytest.mark.parametrize(
    ("argv", "expected_run_kwargs"),
    [
        ([], {"transport": "stdio"}),
        (["--transport", "stdio"], {"transport": "stdio"}),
        (
            ["--transport", "http"],
            {"transport": "http", "host": "127.0.0.1", "port": 8000},
        ),
        (
            ["--transport", "http", "--host", "0.0.0.0", "--port", "9000"],
            {"transport": "http", "host": "0.0.0.0", "port": 9000},
        ),
        # host/port are ignored for stdio
        (["--port", "9000"], {"transport": "stdio"}),
    ],
)
def test_main_runs_app_with_selected_transport(
    argv: list[str], expected_run_kwargs: dict[str, Any]
) -> None:
    mock_mcp = MagicMock()
    with patch("mapy_com_mcp.server.create_app", return_value=mock_mcp) as mock_create:
        main(argv)
        mock_create.assert_called_once_with()
        mock_mcp.run.assert_called_once_with(**expected_run_kwargs)


@pytest.mark.parametrize(
    "argv",
    [["--transport", "sse"], ["--transport", "http", "--port", "abc"]],
)
def test_main_rejects_invalid_arguments_before_creating_app(argv: list[str]) -> None:
    with patch("mapy_com_mcp.server.create_app") as mock_create:
        with pytest.raises(SystemExit):
            main(argv)
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
