"""MCP tool: find_places."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from ..links.urls import Language
from ..mapy_api.client import MapyClient
from ..mapy_api.geocoding import GeocodeQuery, GeocodeQueryResult

_PER_QUERY_LIMIT = 5


def register(mcp: FastMCP, *, client: MapyClient | None = None, **_: object) -> None:
    if client is None:
        return  # API-key gate — no MAPY_API_KEY, no tool.

    async def find_places(
        queries: Annotated[
            list[GeocodeQuery],
            Field(
                description=(
                    "One or more place queries to resolve to coordinates. "
                    "Each query is a free-form string (place name, address, "
                    "or POI) with an optional `near` coordinate for "
                    "disambiguation. All queries are fired in parallel; "
                    "results come back in input order."
                ),
                min_length=1,
            ),
        ],
        language: Annotated[
            Language,
            Field(
                description=(
                    "Preferred language for result labels and locality "
                    "strings. 'en' (default), 'cs' for Czech, 'sk' for "
                    "Slovak, 'de' for German, 'pl' for Polish. Affects "
                    "the response text, not which places match."
                ),
            ),
        ] = "en",
    ) -> list[GeocodeQueryResult]:
        """Find coordinates for places by name, address, or POI.

        Use this when you have a human-readable place reference (e.g.
        'Charles Bridge, Prague', a street address, a city name) but need
        WGS84 lat/lon to feed into build_points_url or build_route_url.

        Returns up to 5 candidate matches per query, in mapy.com's
        relevance order. When several matches exist for one query, use the
        `location` field to disambiguate or surface choices to the user —
        the top result is not guaranteed to be the intended one.

        For ambiguous names ('restaurant', 'hlavní nádraží'), set the
        `near` field on the query to a known coordinate to bias results
        toward that area.

        Each query in the batch is resolved independently; one failing
        query does not abort the others. Check each result's `error`
        field. If every query fails, the whole call raises an error
        (likely a bad API key or network problem).
        """
        results = await asyncio.gather(
            *(_resolve_one(client, q, language) for q in queries),
            return_exceptions=True,
        )
        out: list[GeocodeQueryResult] = []
        for query, result in zip(queries, results, strict=True):
            if isinstance(result, BaseException):
                out.append(
                    GeocodeQueryResult(
                        query=query.query,
                        matches=[],
                        error=_format_error(result),
                    )
                )
            else:
                out.append(result)
        if all(r.error is not None for r in out):
            raise ToolError(
                "All geocoding queries failed; see error fields on each "
                "result for details."
            )
        return out

    mcp.tool(
        find_places,
        annotations={
            "title": "Find coordinates for places by name or address",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )


async def _resolve_one(
    client: MapyClient,
    query: GeocodeQuery,
    language: str,
) -> GeocodeQueryResult:
    prefer_near = (query.near.lon, query.near.lat) if query.near is not None else None
    matches = await client.geocode(
        query.query,
        lang=language,
        limit=_PER_QUERY_LIMIT,
        prefer_near=prefer_near,
    )
    return GeocodeQueryResult(query=query.query, matches=matches)


def _format_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"
