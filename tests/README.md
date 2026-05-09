# tests/

Living inventory of what's tested in `mapy-com-mcp` and what isn't. Read this
before assuming a behavior is covered.

## Conventions

- **Framework:** `pytest`. Run with `uv run pytest`.
- **HTTP mocking:** `respx`. No real network calls in tests, ever — CI
  doesn't have outbound network anyway.
- **Layout:** one test file per source module (`src/mapy_com_mcp/foo.py` →
  `tests/test_foo.py`).
- **Naming:** test functions read like sentences:
  `test_geocode_returns_lat_lon_for_known_address`.
- **Fixtures:** shared fixtures in `tests/conftest.py`. Keep narrow — prefer
  per-file fixtures unless something is truly cross-cutting.
- **No skips, no xfails without an inline reason** that links to an issue
  or a decision in `.context/decisions.md`.

## Coverage map

| Module | Tested? | Notes |
| --- | --- | --- |
| _(none yet)_ | — | Module-level tests will be added as tools land. |

## Known gaps

- No tests yet — repo is at scaffolding stage. First tests land alongside
  the trivial `ping` tool in step 4 of `.context/setup-plan.md`.
- `mapy_client.py` doesn't exist yet; once it does, its tests are the most
  important to maintain (it's the only HTTP boundary, so its correctness
  underpins everything else).
