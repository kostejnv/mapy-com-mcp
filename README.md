<div align="center">

# mapy-com-mcp

MCP server that lets LLMs find places, look at them on a real map, and hand the user a [mapy.com](https://mapy.com) link to the same view.

[![PyPI version](https://img.shields.io/pypi/v/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![MCP-compatible](https://img.shields.io/badge/MCP-compatible-blue?style=flat-square)](https://modelcontextprotocol.io)

</div>

> [!WARNING]
> **Preview.** Place search, places on a map and route planning work today (see below). Tool names and parameters may still change.

> [!NOTE]
> **Unofficial.** Not affiliated with, endorsed by, or supported by Seznam.cz a.s., operators of mapy.com. Trademarks belong to their respective owners.

## Why

LLMs are good at recommending places and itineraries, but bad at anything requiring real spatial understanding — distances, walkability, what's near what. This server closes that gap from both sides:

- **The model checks its work.** `find_places` turns names into real coordinates, so suggestions are grounded in actual places. `show_places` and `show_route` then return map images with numbered markers and a coordinate grid, so the model can *see* how the places relate before it answers — and a route comes with real distance, time and, on foot or by bike, an elevation profile.
- **The user gets a map, not just text.** Both tools hand the user a mapy.com link to the same places or route.

Built on [mapy.com](https://mapy.com), the Czech mapping service from Seznam.cz — especially strong in the Czech Republic and the surrounding region.

## Available tools

| Tool | What it does |
|---|---|
| `show_places` | Shows one or more labeled points on a map. Returns a mapy.com link for the user and a map image the model can look at: numbered markers and a coordinate grid for reading positions and distances. `output` picks `url`, `map` or `both`. Area and zoom are fitted to the points automatically. |
| `show_route` | Plans a route through 2–17 labeled points (start, up to 15 waypoints, destination) for car, foot or bike. Returns a mapy.com link, total and per-leg distance and time, warnings about moved or restricted points, a map image of the route with numbered points, and on foot or by bike an elevation profile with min/max and total ascent/descent. `output` picks `url`, `map` or `both`. |
| `find_places` | Resolves human-readable place references (names, addresses, POIs) to WGS84 coordinates via the mapy.com REST API. Accepts a batch of queries and an optional `near` hint for disambiguation. Feed the result into `show_places` / `show_route`. |

All three tools call the mapy.com REST API, so the server needs a mapy.com API key — see [Configuration](#configuration).

## Configuration

Every tool needs a mapy.com API key in the `MAPY_API_KEY` environment variable. To get one, sign in with a Seznam account at the [mapy.com developer portal](https://developer.mapy.com/account/) and create a project — its first key is created automatically, and the free monthly credits cover normal use. Without a key the server still starts, and every tool call explains how to set one up.

```jsonc
// Example: Claude Desktop / Claude Code MCP config
{
  "mcpServers": {
    "mapy-com": {
      "command": "uvx",
      "args": ["mapy-com-mcp"],
      "env": { "MAPY_API_KEY": "your-key-here" }
    }
  }
}
```

## License

MIT — see [LICENSE](LICENSE).
