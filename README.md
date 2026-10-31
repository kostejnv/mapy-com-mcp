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

- **The model checks its work.** With a mapy.com API key, `find_places` turns names into real coordinates, so suggestions are grounded in actual places. `show_places` and `show_route` then return map images with numbered markers and a coordinate grid, so the model can *see* how the places relate before it answers — and a route comes with real distance, time and, on foot or by bike, an elevation profile.
- **The user gets a map, not just text.** Both tools hand the user a mapy.com link to the same places or route.

Built on [mapy.com](https://mapy.com), the Czech mapping service from Seznam.cz — especially strong in the Czech Republic and the surrounding region.

## Available tools

| Tool | What it does | Needs API key |
|---|---|---|
| `show_places` | Shows one or more labeled points on a map. Returns a mapy.com link for the user and — with an API key — a map image the model can look at: numbered markers and a coordinate grid for reading positions and distances. `output` picks `url`, `map` or `both`. Area and zoom are fitted to the points automatically. | Image only |
| `show_route` | Plans a route through 2–17 labeled points (start, up to 15 waypoints, destination) for car, foot or bike. Returns a mapy.com link and — with an API key — total and per-leg distance and time, warnings about moved or restricted points, a map image of the route with numbered points, and on foot or by bike an elevation profile with min/max and total ascent/descent. `output` picks `url`, `map` or `both`. | Route data & images |
| `find_places` | Resolves human-readable place references (names, addresses, POIs) to WGS84 coordinates via the mapy.com REST API. Accepts a batch of queries and an optional `near` hint for disambiguation. Feed the result into `show_places` / `show_route`. | Yes |

Links need no key. Map images, route planning and `find_places` call the mapy.com REST API, so they are only available when `MAPY_API_KEY` is set in the environment; without it, `show_places` and `show_route` return just the link.

## Configuration

Set `MAPY_API_KEY` in the environment when you want map images, route planning and `find_places`. Get a free key from the [mapy.com developer portal](https://developer.mapy.com/account/). With the key unset, the server still runs and returns mapy.com links.

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
