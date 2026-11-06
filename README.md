<div align="center">

# mapy-com-mcp

MCP server that lets LLMs find places, look at them on a real map, and hand the user a [mapy.com](https://mapy.com) link to the same view.

[![PyPI version](https://img.shields.io/pypi/v/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/mapy-com-mcp?style=flat-square&include_prereleases)](https://pypi.org/project/mapy-com-mcp/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![MCP-compatible](https://img.shields.io/badge/MCP-compatible-blue?style=flat-square)](https://modelcontextprotocol.io)

</div>

> [!NOTE]
> **Unofficial.** Not affiliated with, endorsed by, or supported by Seznam.cz a.s., operators of mapy.com. Trademarks belong to their respective owners.

## Why

LLMs are good at recommending places and itineraries, but bad at anything requiring real spatial understanding — distances, walkability, what's near what. This server closes that gap from both sides:

- **The model checks its work.** `find_places` turns names into real coordinates, so suggestions are grounded in actual places. `inspect_places` and `plan_route` then return map images with numbered markers and a coordinate grid, so the model can *see* how the places relate before it answers — and a route comes with real distance, time and, on foot or by bike, an elevation profile.
- **The user gets a map, not just text.** `show_places` and `show_route` show the places or the route on a map right in the chat, with a button that opens the same view on mapy.com — in clients that support [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview), such as Claude and ChatGPT. Other clients get a mapy.com link to hand on.

Built on [mapy.com](https://mapy.com), the Czech mapping service from Seznam.cz — especially strong in the Czech Republic and the surrounding region.

## Available tools

| Tool | What it does |
|---|---|
| `show_places` | Shows the user one or more labeled points on a map: an inline map with numbered markers and an "Open on Mapy.com" button where the client supports it, otherwise a mapy.com link. Area and zoom are fitted to the points automatically. |
| `show_route` | Shows the user a route through 2–17 labeled points (start, up to 15 waypoints, destination) for car, foot or bike: an inline map with length, time and, on foot or by bike, an elevation profile that opens large on click — or a mapy.com link. The model gets total and per-leg distance and time and warnings about moved or restricted points. |
| `inspect_places` | Lets the model look at places for itself, without showing the user anything: a map image with numbered markers and a coordinate grid, to check how places relate before it answers. |
| `plan_route` | Lets the model plan a route for itself, without showing the user anything: total and per-leg distance and time, warnings, a map image of the route and, on foot or by bike, an elevation profile. |
| `find_places` | Resolves human-readable place references (names, addresses, POIs) to WGS84 coordinates via the mapy.com REST API. Accepts a batch of queries and an optional `near` hint for disambiguation. Feed the result into `show_places` / `show_route`. |

All tools call the mapy.com REST API, so the server needs a mapy.com API key — see [Configuration](#configuration).

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

## Self-hosting over HTTP

By default the server talks to a local MCP client over stdio. To run it on a server instead — for example to use it from ChatGPT or Claude on the web and on mobile — run it over Streamable HTTP, most easily with Docker:

```bash
docker build -t mapy-com-mcp .
docker run -d --name mapy-com-mcp --restart unless-stopped \
  -e MAPY_API_KEY=your-key-here -p 127.0.0.1:8000:8000 mapy-com-mcp
```

The MCP endpoint is then `http://127.0.0.1:8000/mcp`. Without Docker, `mapy-com-mcp --transport http` does the same; it binds to `127.0.0.1:8000` unless you pass `--host` and `--port`.

> [!IMPORTANT]
> The server has no authentication of its own, and every request spends the credits of your mapy.com API key. Before exposing it to the internet, put it behind an HTTPS reverse proxy that controls who can reach it.

## License

MIT — see [LICENSE](LICENSE).
