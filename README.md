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
> **Early preview.** URL-builder tools and the first REST-API tool (`find_places`) have shipped (see below); more REST tools and hosted deployment land in later milestones. Expect the public surface to grow.

> [!NOTE]
> **Unofficial.** Not affiliated with, endorsed by, or supported by Seznam.cz a.s., operators of mapy.com. Trademarks belong to their respective owners.

## Why

LLMs are good at recommending places and itineraries, but bad at anything requiring real spatial understanding — distances, walkability, what's near what. This MCP closes that gap by letting LLMs surface a clickable mapy.com link the user can open to *see* the recommendation on a real map.

## Available tools

| Tool | What it does | Needs API key |
|---|---|---|
| `build_points_url` | Builds a mapy.com URL that opens the map showing one or more labeled points. The general-purpose "show me on the map" tool — single place or many, the operation is the same. Auto-fits the zoom to the points. | No |
| `build_route_url` | Builds a mapy.com URL that opens a planned route between two points (with optional waypoints). Map style is auto-derived from the chosen transport mode (car / foot / bike). | No |
| `find_places` | Resolves human-readable place references (names, addresses, POIs) to WGS84 coordinates via the mapy.com REST API. Accepts a batch of queries and an optional `near` hint for disambiguation. Feed the result into `build_points_url` / `build_route_url`. | Yes |

URL-builder tools are pure — no HTTP calls, no key. `find_places` calls the mapy.com REST API and is only registered when `MAPY_API_KEY` is set in the environment.

## Configuration

Set `MAPY_API_KEY` in the environment when you want the REST tools. Get a free key from the [mapy.com developer portal](https://developer.mapy.com/account/). With the key unset, the server runs with only the URL-builder tools.

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

### Transports

The server speaks stdio by default, which is what local MCP clients expect. To serve it over [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports#streamable-http) instead:

```bash
uvx mapy-com-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

The MCP endpoint is then `http://127.0.0.1:8000/mcp`. The server has no authentication, so binding `--host` to anything other than loopback exposes your `MAPY_API_KEY` quota to whoever can reach it.

## License

MIT — see [LICENSE](LICENSE).
