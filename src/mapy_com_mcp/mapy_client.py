"""HTTP boundary for the mapy.com REST API.

This is the only module that talks to api.mapy.com over HTTP. Tools never
call httpx directly — auth, timeouts, error mapping live here.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any

import httpx

from .geocoding import GeocodeMatch

_DEFAULT_BASE_URL = "https://api.mapy.com"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _get_user_agent() -> str:
    try:
        return f"mapy-com-mcp/{version('mapy-com-mcp')}"
    except PackageNotFoundError:
        return "mapy-com-mcp/0.0.0"


class MapyAPIError(Exception):
    """Raised when api.mapy.com returns an error response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"mapy.com API error {status}: {message}")
        self.status = status
        self.message = message


class MapyClient:
    """Thin async wrapper around the mapy.com REST API.

    One method per endpoint, no caching, no retries. Auth is via the
    `apikey` query parameter (mapy.com's documented method per
    getting-access.md).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": _get_user_agent()},
        )

    async def geocode(
        self,
        query: str,
        *,
        lang: str = "en",
        limit: int = 5,
        prefer_near: tuple[float, float] | None = None,
    ) -> list[GeocodeMatch]:
        """Resolve a place query to a list of candidate matches.

        Raises MapyAPIError on 4xx/5xx responses. httpx exceptions (timeout,
        connection error) propagate to the caller.
        """
        params: dict[str, Any] = {
            "apikey": self._api_key,
            "query": query,
            "lang": lang,
            "limit": limit,
        }
        if prefer_near is not None:
            lon, lat = prefer_near
            params["preferNear"] = f"{lon},{lat}"

        resp = await self._client.get("/v1/geocode", params=params)

        if resp.status_code in (401, 403):
            raise MapyAPIError(resp.status_code, "API key invalid or unauthorized")
        if resp.status_code >= 500:
            raise MapyAPIError(resp.status_code, "mapy.com geocoding service error")
        if resp.status_code >= 400:
            raise MapyAPIError(resp.status_code, resp.text[:200])

        return [_parse_match(item) for item in resp.json().get("items", [])]

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse_match(item: dict[str, Any]) -> GeocodeMatch:
    position: dict[str, float] = item["position"]
    return GeocodeMatch(
        name=item["name"],
        label=item["label"],
        lon=position["lon"],
        lat=position["lat"],
        location=item.get("location", ""),
        type=item["type"],
        zip=item.get("zip"),
    )
