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
  `test_build_route_url_docs_example_exact_match`.
- **Fixtures:** shared fixtures in `tests/conftest.py`. Keep narrow — prefer
  per-file fixtures unless something is truly cross-cutting.
- **No skips, no xfails without an inline reason** that links to an issue
  or a decision in `.context/decisions.md`.

## Coverage map

| Module | Tested? | Notes |
| --- | --- | --- |
| `server.py` | Yes | `create_app()` discovery, `main()` wiring via mocks, `TypeError` guard for modules missing `register`, `instructions` non-empty; registration gate (no key → show_places + show_route, key set → plus find_places) |
| `tools/__init__.py` | Yes (indirect) | Imported via `create_app()`; 100% coverage |
| `tools/show_places.py` | Yes | No-key: schema hides `output`, returns URL, closed-world annotations, single-point showmap / multi-point vlastni-body, empty-points and empty-label errors. With key: schema exposes `output`, openWorldHint; `url` skips the static API; `map` → [jpeg Image, legend]; `both` (default) → legend + "Map link for the user"; image size = viewport; static API params (apikey, lang, format); mapset mapping (traffic → basic, link keeps traffic); image and link share viewport; 50 points; failures: `both` falls back to text + link (API error, timeout), `map` raises `ToolError` |
| `static_map/viewport.py` | Yes | `world_px`/`lon_lat` and `Viewport` round-trips, center → image center, `meters_per_px`, shape selection (landscape/portrait/square), single point → zoom 16 centered, all points inside margins, largest fitting zoom, clamps at 1 and 19, 64 px bottom margin floor, poles clamped (no math domain error), order independence |
| `static_map/render.py` | Yes | `format_distance`, `grid_step_m` (3-7 lines on the longer side over zooms 1-19 x 3 latitudes x 3 sizes, 1/2/3/5 series), `render` returns JPEG of base size for 1/2/15 points and odd base sizes, red marker at the point, footer left free of grid; optional `route` line: red pixels along it, none without it, valid JPEG for a 40-point line. Pixel-exact label/legend layout is not asserted |
| `static_map/profile.py` | Yes | `sample_positions`: 256/512/1024 samples for short/20 km/200 km (cap of 4 batches), first distance 0, last = total, strictly increasing, even spacing across unequal segments, samples lie on a bent line; `climb_stats` dead band (+-1 m noise adds nothing, 10 m climb counts, ascent/descent separate, slow drift accumulates); `render_profile` returns 1024x280 JPEG for rising/flat/up-down data. Pixel layout not asserted |
| `tools/show_route.py` | Yes | No key: schema hides `output`, `route_type` required, URL only, closed-world, <2 points rejected, `build_route_url` tool gone. With key: schema/openWorld; url mode = 1 routing call, no static/elevation, no Elevation line; routing params; distance/duration formats; per-leg lines (always, also for a single leg); warnings (snap > 50 m threshold, restriction kind); both/foot = [map, profile, text] with Elevation + Grid + link, outdoor mapset; car = 1 image, basic mapset, no elevation calls; map mode has no link; 512 samples → 2 elevation batches of 256; -100000 dropped; all-no-data and zero-length route → note, no profile; fallbacks: routing failure (url/both → text + link, map raises, timeout), static failure (both keeps summary + profile, map raises), elevation failure (note, not fatal) |
| `tools/find_places.py` | Yes | Registration gate (absent without key, present with key), schema/annotations, single-query happy path, batch ordering, `near` → `preferNear` forwarding, partial failure (no raise), all-failure → `ToolError`, `language` forwarded as `lang` |
| `mapy_api/geocoding.py` | Yes (indirect) | All four Pydantic models exercised through `mapy_api/client` and `find_places` tests; 100% coverage |
| `mapy_api/client.py` | Yes | `route`: params (apikey in query, start/end/routeType/lang/format=geojson, waypoints only for >2 points), parsing of length/duration/legs/geometry/routePoints, 401/403/500/503 and 4xx-with-body mapping; `elevation`: positions format (6 dp), -100000 passed through, error mapping; `static_map`: bytes returned, all query params (apikey in query not header, format=png), 401/403/500/503 and 4xx-with-body error mapping; `geocode`: Happy path (1 and N matches), empty result, zip field, apikey as query param (not header), query/lang/limit defaults, `preferNear` format (`lon,lat`), preferNear absent when not passed, 401/403/500/503 error mapping, 422 with body, 4xx body truncation at 200 chars |
| `links/uc_encoder.py` | Yes | Empty input, known Prague fixture, all three branches (small/medium/absolute) of `_serialize_number`, alphabet membership, 50-point stress case |
| `links/urls.py` | Yes | `build_route_url(points, route_type, language)`: exact 2-point URL, all six route types, mapset per type, all five languages, middle points → ordered `waypoints=`, 17 points OK, 0/1/18 → `ToolError`. `build_points_url` with an explicit `Viewport`: all five mapsets (English in showmap, Czech path in vlastni-body), all five languages, single point centers on the point with viewport zoom, multi-point x/y (6 dp)/z from viewport, numbered `ut=` titles, label/description encoding, `ut=`/`ud=` ordering, 50-point stress case, `ToolError` on empty points, 16-waypoint `ToolError`, single-point/multi-point dispatch boundary |

## Known gaps

- `mapy_api/client._get_user_agent()` lines 23-24 (the `PackageNotFoundError` fallback)
  are not covered because the package is always installed in the test environment.
  The fallback returns "mapy-com-mcp/0.0.0" — not worth mocking `importlib.metadata`
  for a version string.
- `mapy_api/client.py` `static_map` takes `lang` as a required keyword (no default);
  tests pass it explicitly.
- Each `create_app()` closes its HTTP client when a `fastmcp.Client` context exits, so a test can make only one tool call per `mcp` fixture.
- `static_map/render.py` line 105 (latitude outside +-85 skip in the horizontal grid)
  is not hit by any realistic viewport.
