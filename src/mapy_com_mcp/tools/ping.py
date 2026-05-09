from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    def ping() -> str:
        """Liveness check. Returns 'pong'."""
        return "pong"

    mcp.tool(ping)
