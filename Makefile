# Requires Node.js / npx (provides @modelcontextprotocol/inspector via npx).

.PHONY: inspect inspect-remote

inspect:
	npx @modelcontextprotocol/inspector uv run mapy-com-mcp

inspect-remote:
	npx @modelcontextprotocol/inspector uvx mapy-com-mcp
