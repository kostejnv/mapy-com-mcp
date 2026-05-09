<div align="center">

# mapy-com-mcp

MCP server that gives LLM clients first-class access to [mapy.com](https://mapy.com) — a Czech mapping service with strong route planning and static map rendering.

[![PyPI version](https://img.shields.io/pypi/v/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![MCP-compatible](https://img.shields.io/badge/MCP-compatible-blue?style=flat-square)](https://modelcontextprotocol.io)

</div>

> [!WARNING]
> **Early preview.** The first URL-builder tools have shipped (see below); REST-API tools and hosted deployment land in later milestones. Expect the public surface to grow.

> [!NOTE]
> **Unofficial.** Not affiliated with, endorsed by, or supported by Seznam.cz a.s., operators of mapy.com. Trademarks belong to their respective owners.

## Why

LLMs are good at recommending places and itineraries, but bad at anything requiring real spatial understanding — distances, walkability, what's near what. This MCP closes that gap by letting LLMs surface a clickable mapy.com link the user can open to *see* the recommendation on a real map.

## Available tools

| Tool | What it does |
|---|---|
| `build_points_url` | Builds a mapy.com URL that opens the map showing one or more labeled points. The general-purpose "show me on the map" tool — single place or many, the operation is the same. Auto-fits the zoom to the points. |
| `build_route_url` | Builds a mapy.com URL that opens a planned route between two points (with optional waypoints). Map style is auto-derived from the chosen transport mode (car / foot / bike). |

Both tools are pure URL builders — no API key, no HTTP calls. The user clicks the returned URL and mapy.com renders the result.

## License

MIT — see [LICENSE](LICENSE).
