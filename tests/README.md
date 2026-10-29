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
  `test_build_points_url_happy_path`.
- **Fixtures:** shared fixtures in `tests/conftest.py`. Keep narrow — prefer
  per-file fixtures unless something is truly cross-cutting.
- **No skips, no xfails without an inline reason** that links to an issue
  or a decision in `.context/decisions.md`.

## Coverage map

| Module | Tested? | Notes |
| --- | --- | --- |
| `server.py` | Yes | `create_app()` discovery, `main()` CLI parsing and wiring via mocks (default stdio, streamable-http with/without host/port, invalid transport/port → exit 2 before `create_app`), `TypeError` guard for modules missing `register`, `instructions` non-empty; registration gate (no key → 2 tools, key set → 3 tools) |
| `tools/__init__.py` | Yes (indirect) | Imported via `create_app()`; 100% coverage |
| `tools/points_url.py` | Yes | Tool list, description, annotations, schema (no zoom field), happy path, empty-points error, empty-label error |
| `tools/route_url.py` | Yes | Tool list, description, annotations, docs-example exact URL, waypoints (0/1/15/16), 16-waypoint error |
| `tools/find_places.py` | Yes | Registration gate (absent without key, present with key), schema/annotations, single-query happy path, batch ordering, `near` → `preferNear` forwarding, partial failure (no raise), all-failure → `ToolError`, `language` forwarded as `lang` |
| `geocoding.py` | Yes (indirect) | All four Pydantic models exercised through `mapy_client` and `find_places` tests; 100% coverage |
| `mapy_client.py` | Yes | Happy path (1 and N matches), empty result, zip field, apikey as query param (not header), query/lang/limit defaults, `preferNear` format (`lon,lat`), preferNear absent when not passed, 401/403/500/503 error mapping, 422 with body, 4xx body truncation at 200 chars |
| `_uc_encoder.py` | Yes | Empty input, known Prague fixture, all three branches (small/medium/absolute) of `_serialize_number`, alphabet membership, 50-point stress case |
| `urls.py` | Yes | All five mapsets (English in showmap, Czech path in vlastni-body), all five languages (query param in showmap, path prefix in vlastni-body), all seven zoom buckets, label/description encoding (multi-point path), `ut=`/`ud=` ordering, center calculation, 50-point stress case, `ToolError` on empty points, 16-waypoint `ToolError`, all six route types, mapset auto-derivation, single-point/multi-point dispatch boundary |

## Known gaps

- `mapy_client._get_user_agent()` lines 23-24 (the `PackageNotFoundError` fallback)
  are not covered because the package is always installed in the test environment.
  The fallback returns "mapy-com-mcp/0.0.0" — not worth mocking `importlib.metadata`
  for a version string.
