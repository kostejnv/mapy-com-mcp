"""Every tool needs a mapy.com API key: say clearly how to fix it when it fails.

The server starts without a key so the agent can explain the fix in the chat;
a server that refuses to start only shows a bare "failed to connect".
"""

from __future__ import annotations

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

from .mapy_api.client import APIKeyRejectedError

_HOW_TO_GET_A_KEY = """\
1. Sign in with a Seznam account at https://developer.mapy.com/account/ and
   create a project. Its first API key is created automatically, and the free
   monthly credits cover normal use.
2. Add the key to this server's entry in the MCP client config as the
   environment variable MAPY_API_KEY, e.g. "env": { "MAPY_API_KEY": "…" }.
3. Restart the MCP client.

Step-by-step guide: https://developer.mapy.com/rest-api-mapy-cz/how-to-start/
Do not ask the user to paste the key into this chat."""

MISSING_KEY_MESSAGE = f"""\
Mapy.com needs an API key, and MAPY_API_KEY is not set for this server, so no
map tool can run. Do not retry; tell the user how to fix it, in their language:

{_HOW_TO_GET_A_KEY}"""

REJECTED_KEY_MESSAGE = f"""\
Mapy.com rejected the API key set in MAPY_API_KEY, so no map tool can run. Do
not retry; tell the user how to fix it, in their language. The key may be
mistyped, incomplete or deleted; they can check it at
https://developer.mapy.com/account/. To use a new key:

{_HOW_TO_GET_A_KEY}"""


class APIKeyGuard(Middleware):
    """Turns a missing or rejected key into one clear error on every tool call."""

    def __init__(self, *, key_configured: bool) -> None:
        self._key_configured = key_configured

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        if not self._key_configured:
            raise ToolError(MISSING_KEY_MESSAGE)
        try:
            return await call_next(context)
        except ToolError as exc:
            # FastMCP wraps whatever a tool raises in a generic ToolError.
            if isinstance(exc.__cause__, APIKeyRejectedError):
                raise ToolError(REJECTED_KEY_MESSAGE) from exc.__cause__
            raise
