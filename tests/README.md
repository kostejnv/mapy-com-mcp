# tests/

Living inventory of what's tested in `mapy-com-mcp` and what isn't. Read this
before assuming a behavior is covered.

## Conventions

- **Framework:** `pytest`. Run with `uv run pytest`.
- **HTTP mocking:** `respx`. No real network calls in tests, ever — CI
  doesn't have outbound network anyway.
- **Async tests:** `pytest-asyncio` with `asyncio_mode = "auto"` (set in
  `pyproject.toml`). All async tests run automatically without decorators.
- **In-process MCP client:** `fastmcp.Client(mcp)` used as a context manager
  to drive tools without spawning a subprocess.
- **Layout:** one test file per source module (`src/mapy_com_mcp/foo.py` →
  `tests/test_foo.py`).
- **Naming:** test functions read like sentences:
  `test_ping_returns_pong`.
- **Fixtures:** shared fixtures in `tests/conftest.py`. Keep narrow — prefer
  per-file fixtures unless something is truly cross-cutting.
- **No skips, no xfails without an inline reason** that links to an issue
  or a decision in `.context/decisions.md`.

## Coverage map

| Module | Tested? | Notes |
| --- | --- | --- |
| `server.py` | Yes | `create_app()` discovery, `main()` wiring via mocks, `TypeError` guard for modules missing `register` |
| `tools/ping.py` | Yes | Happy path: list shows `ping`, call returns `"pong"`, not an error |
| `tools/__init__.py` | Yes (indirect) | Imported via `create_app()`; 100% coverage |
| `mapy_client.py` | — | Does not exist yet |

## Known gaps

- `mapy_client.py` doesn't exist yet; once it does, its tests are the most
  important to maintain (it's the only HTTP boundary, so its correctness
  underpins everything else). `respx` is already installed as a dev
  dependency for that future work.
