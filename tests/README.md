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
| `server.py` | Yes | `create_app()` discovery, `main()` wiring via mocks, `TypeError` guard for modules missing `register`, `instructions` name all five tools; all five tools registered with and without a key; `register_map_view` runs in `create_app` |
| `api_key.py` | Yes | Messages contain the account URL and `MAPY_API_KEY`; no/empty/whitespace-only key -> every tool (incl. `inspect_places`, `plan_route`) raises the missing-key message with zero HTTP calls, tools still listed; 401/403 -> exactly `REJECTED_KEY_MESSAGE` (not the generic FastMCP error); `show_places` link-only reply works with a key that would be rejected (no HTTP); 500 and timeout degrade as before, never the rejected message |
| `tools/__init__.py` | Yes (indirect) | Imported via `create_app()`; 100% coverage |
| `tools/show_places.py` | Yes | `output` param gone, `_meta.ui.resourceUri` on the tool, openWorldHint; empty points/label rejected. Without the UI extension: one text content starting "Give the user this mapy.com link to the places", labels listed, no `_meta`, no `structuredContent`, zero HTTP (also with a bad key), showmap vs vlastni-body, traffic link. With UI (`ui_client` fixture): `_meta` has map_url/language/JPEG base64 (1024x640, landscape even for tall sets, no grid), static API params, viewport shared with link, mapset mapping, single point zoom 16, 50 points, non-cs languages → "en"; no image content, base64 or URL in the text; static 500/422/timeout → note + meta with only map_url/language; 401/403 → rejected-key message (not swallowed) |
| `static_map/viewport.py` | Yes | `world_px`/`lon_lat` and `Viewport` round-trips, center → image center, `meters_per_px`, shape selection (landscape/portrait/square), single point → zoom 16 centered, all points inside margins, largest fitting zoom, clamps at 1 and 19, 64 px bottom margin floor, poles clamped (no math domain error), order independence |
| `static_map/render.py` | Yes | `format_distance`, `grid_step_m` (3-7 lines on the longer side over zooms 1-19 x 3 latitudes x 3 sizes, 1/2/3/5 series), `render` returns JPEG of base size for 1/2/15 points and odd base sizes, red marker at the point, footer left free of grid; optional `route` line: red pixels along it, none without it, valid JPEG for a 40-point line. Pixel-exact label/legend layout is not asserted |
| `static_map/profile.py` | Yes | `sample_positions`: 256/512/1024 samples for short/20 km/200 km (cap of 4 batches), first distance 0, last = total, strictly increasing, even spacing across unequal segments, samples lie on a bent line; `climb_stats` dead band (+-1 m noise adds nothing, 10 m climb counts, ascent/descent separate, slow drift accumulates); `render_profile` returns 1024x280 JPEG for rising/flat/up-down data. Pixel layout not asserted |
| `tools/show_route.py` | Yes | <2 points rejected, schema (no `output`, resourceUri meta, openWorld), `build_route_url` tool gone. Without UI: 1 routing call, no static/elevation, no `_meta`, text = summary + per-leg + warnings + "Give the user this mapy.com link to the route" last; routing params; distance/duration formats; warnings (snap > 50 m threshold, restriction kind); routing 500/timeout → text with link; 401/403 → rejected message. With UI (`ui_client`): foot meta has all 7 keys (route numbers, 1024x640 map, 1024x280 profile, int sparkline), text-only content with Elevation line and "The user now sees" sentence; car → no profile keys, no elevation calls, basic mapset; cs/en language; 512 samples → 2 elevation batches; -100000 dropped; routing failure → meta with only map_url/language, no static call; map failure with elevation ok → note, meta has only url/language/numbers (no profile keys), Elevation line kept in text, sentence omits map/profile; elevation failure/all-no-data/zero-length → note, no profile keys; 401/403 on routing, static, elevation → rejected message |
| `map_view/` | Yes | In `test_map_view.py`. Contract: `meta.<key>` names read by `map_view.html` equal the keys `map_view_meta` can write; `map_view_meta` minimal/full output, cs-or-en language mapping, both-or-neither pairs (route numbers, profile + sparkline), zero numbers kept; URI = `ui://mapy-com-mcp/map-view-<sha256[:12] of inlined html>.html`; view served with mime `text/html;profile=mcp-app`, inlined `<svg`, placeholder gone, listed as a resource. `client_shows_map_view` is covered through the tools via the `ui_client` fixture in `conftest.py` (patches `MiddlewareServerSession.client_supports_extension`; the fastmcp Client cannot advertise extensions) |
| `tools/inspect_places.py` | Yes | In `test_agent_tools.py`. Schema has no `output` param, readOnly/openWorld; empty points rejected; reply = [jpeg Image, legend] with no link; mapset forwarded (traffic -> basic); static 500/422/timeout -> `ToolError("Map image unavailable")`; 401/403 -> rejected-key message; missing key -> missing-key message, no HTTP |
| `tools/plan_route.py` | Yes | In `test_agent_tools.py`. Schema has no `output` param, readOnly/openWorld; single point rejected; foot/bike -> [map, profile, text] with summary, Elevation and Grid lines, no link; car -> 1 image, no elevation calls; snap warning in text; routing 500/422/timeout -> `ToolError("Route planning failed")`; static failure and elevation failure (HTTP or all-no-data) -> note in text, other image kept; 401/403 on routing/static/elevation -> rejected-key message; missing key -> missing-key message, no HTTP |
| `reports/places.py`, `reports/route.py` | Yes (via tools) | Shared by show_* and the agent tools; 100% covered through tool-level tests of all four; no direct unit tests |
| `tools/find_places.py` | Yes | Always registered, schema/annotations, single-query happy path, batch ordering, `near` → `preferNear` forwarding, partial failure (no raise), all-failure → `ToolError`, `language` forwarded as `lang`; 401/403 (single query, or one among several) → rejected-key message instead of a per-query error |
| `mapy_api/geocoding.py` | Yes (indirect) | All four Pydantic models exercised through `mapy_api/client` and `find_places` tests; 100% coverage |
| `mapy_api/client.py` | Yes | `route`: params (apikey in query, start/end/routeType/lang/format=geojson, waypoints only for >2 points), parsing of length/duration/legs/geometry/routePoints, 401/403 -> `APIKeyRejectedError` (not a `MapyAPIError`), 500/503 and 4xx-with-body mapping; `elevation`: positions format (6 dp), -100000 passed through, error mapping (401/403 -> `APIKeyRejectedError`); `static_map`: bytes returned, all query params (apikey in query not header, format=png), 401/403 -> `APIKeyRejectedError`, 500/503 and 4xx-with-body error mapping; `geocode`: Happy path (1 and N matches), empty result, zip field, apikey as query param (not header), query/lang/limit defaults, `preferNear` format (`lon,lat`), preferNear absent when not passed, 401/403 -> `APIKeyRejectedError`, 500/503 error mapping, 422 with body, 4xx body truncation at 200 chars |
| `links/uc_encoder.py` | Yes | Empty input, known Prague fixture, all three branches (small/medium/absolute) of `_serialize_number`, alphabet membership, 50-point stress case |
| `links/urls.py` | Yes | `build_route_url(points, route_type, language)`: exact 2-point URL, all six route types, mapset per type, all five languages, middle points → ordered `waypoints=`, 17 points OK, 0/1/18 → `ToolError`. `build_points_url` with an explicit `Viewport`: all five mapsets (English in showmap, Czech path in vlastni-body), all five languages, single point centers on the point with viewport zoom, multi-point x/y (6 dp)/z from viewport, numbered `ut=` titles, label/description encoding, `ut=`/`ud=` ordering, 50-point stress case, `ToolError` on empty points, 16-waypoint `ToolError`, single-point/multi-point dispatch boundary |

## Known gaps

- `mapy_api/client._get_user_agent()` lines 23-24 (the `PackageNotFoundError` fallback)
  are not covered because the package is always installed in the test environment.
  The fallback returns "mapy-com-mcp/0.0.0" — not worth mocking `importlib.metadata`
  for a version string.
- `mapy_api/client.py` `static_map` takes `lang` as a required keyword (no default);
  tests pass it explicitly.
- The HTML view's JS behavior is not tested; only its `meta.*` key names against `map_view_meta`. `route_viewport` / `landscape_only` are covered only through tool tests.
- `tests/test_agent_tools.py` ~lines 301-305 have pre-existing pyright strict errors (untyped lambda / `request.url.params`); not touched.
- Each `create_app()` closes its HTTP client when a `fastmcp.Client` context exits, so a test can make only one tool call per `mcp` fixture.
- `static_map/render.py` line 105 (latitude outside +-85 skip in the horizontal grid)
  is not hit by any realistic viewport.
