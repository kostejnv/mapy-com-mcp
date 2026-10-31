"""HTTP boundary for the mapy.com REST API.

This is the only module that talks to api.mapy.com over HTTP. Tools never
call httpx directly — auth, timeouts, error mapping live here.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

import httpx

from .geocoding import GeocodeMatch
from .routing import Route, RouteLeg, RoutePointInfo, RouteType

_DEFAULT_BASE_URL = "https://api.mapy.com"
_DEFAULT_TIMEOUT_SECONDS = 10.0

StaticMapset = Literal["basic", "outdoor", "winter", "aerial"]


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
        _raise_for_error(resp, "geocoding")
        return [_parse_match(item) for item in resp.json().get("items", [])]

    async def static_map(
        self,
        *,
        lon: float,
        lat: float,
        zoom: int,
        width: int,
        height: int,
        mapset: StaticMapset,
        lang: str,
    ) -> bytes:
        """Fetch a PNG map image centered on (lon, lat) at the given zoom.

        Raises MapyAPIError on 4xx/5xx responses. httpx exceptions (timeout,
        connection error) propagate to the caller.
        """
        params: dict[str, Any] = {
            "apikey": self._api_key,
            "lon": lon,
            "lat": lat,
            "zoom": zoom,
            "width": width,
            "height": height,
            "mapset": mapset,
            "lang": lang,
            "format": "png",
        }

        resp = await self._client.get("/v1/static/map", params=params)
        _raise_for_error(resp, "static map")
        return resp.content

    async def route(
        self,
        points: list[tuple[float, float]],
        *,
        route_type: RouteType,
        lang: str,
    ) -> Route:
        """Plan a route through (lon, lat) points: first = start, last = end.

        Raises MapyAPIError on 4xx/5xx responses. httpx exceptions (timeout,
        connection error) propagate to the caller.
        """
        (start_lon, start_lat), *waypoints, (end_lon, end_lat) = points
        params: dict[str, Any] = {
            "apikey": self._api_key,
            "start": f"{start_lon},{start_lat}",
            "end": f"{end_lon},{end_lat}",
            "routeType": route_type,
            "lang": lang,
            "format": "geojson",
        }
        if waypoints:
            params["waypoints"] = ";".join(f"{lon},{lat}" for lon, lat in waypoints)

        resp = await self._client.get("/v1/routing/route", params=params)
        _raise_for_error(resp, "routing")
        return _parse_route(resp.json())

    async def elevation(self, positions: list[tuple[float, float]]) -> list[float]:
        """Elevations in meters for up to 256 (lon, lat) positions, same order.

        Raises MapyAPIError on 4xx/5xx responses. httpx exceptions (timeout,
        connection error) propagate to the caller.
        """
        params: dict[str, Any] = {
            "apikey": self._api_key,
            "positions": ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in positions),
        }
        resp = await self._client.get("/v1/elevation", params=params)
        _raise_for_error(resp, "elevation")
        return [item["elevation"] for item in resp.json()["items"]]

    async def aclose(self) -> None:
        await self._client.aclose()


def _raise_for_error(resp: httpx.Response, service: str) -> None:
    if resp.status_code in (401, 403):
        raise MapyAPIError(resp.status_code, "API key invalid or unauthorized")
    if resp.status_code >= 500:
        raise MapyAPIError(resp.status_code, f"mapy.com {service} service error")
    if resp.status_code >= 400:
        raise MapyAPIError(resp.status_code, resp.text[:200])


def _parse_route(data: dict[str, Any]) -> Route:
    return Route(
        length_m=data["length"],
        duration_s=data["duration"],
        legs=[RouteLeg(part["length"], part["duration"]) for part in data["parts"]],
        geometry=[
            (lon, lat) for lon, lat in data["geometry"]["geometry"]["coordinates"]
        ],
        points=[
            RoutePointInfo(point["snapDistance"], point.get("restrictionType"))
            for point in data["routePoints"]
        ],
    )


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
