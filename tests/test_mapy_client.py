"""Tests for mapy_client.py — MapyClient HTTP boundary.

All HTTP is mocked with respx; no real network calls are made.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from mapy_com_mcp.geocoding import GeocodeMatch
from mapy_com_mcp.mapy_client import MapyAPIError, MapyClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_API_KEY = "test-api-key-123"

# A minimal but realistic geocode response item (Charles Bridge).
_CHARLES_BRIDGE_ITEM = {
    "name": "Karlův most",
    "label": "Most",
    "position": {"lon": 14.4112, "lat": 50.0865},
    "type": "poi",
    "location": "Praha 1 - Staré Město, Česko",
    "bbox": [14.409, 50.085, 14.413, 50.088],
    "regionalStructure": [],
}

_GEOCODE_URL = "https://api.mapy.com/v1/geocode"


@pytest.fixture
async def client() -> MapyClient:  # type: ignore[return]  # yield makes this a generator
    """A MapyClient wired to the real base URL (intercepted by respx)."""
    c = MapyClient(_API_KEY)
    yield c  # type: ignore[misc]
    await c.aclose()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@respx.mock
async def test_geocode_happy_path_returns_matches(client: MapyClient) -> None:
    """geocode() parses a valid items list into GeocodeMatch objects."""
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(200, json={"items": [_CHARLES_BRIDGE_ITEM]})
    )

    matches = await client.geocode("Charles Bridge")

    assert len(matches) == 1
    match = matches[0]
    assert isinstance(match, GeocodeMatch)
    assert match.name == "Karlův most"
    assert match.label == "Most"
    assert match.lon == pytest.approx(14.4112)
    assert match.lat == pytest.approx(50.0865)
    assert match.type == "poi"
    assert match.location == "Praha 1 - Staré Město, Česko"
    assert match.zip is None


@respx.mock
async def test_geocode_empty_items_returns_empty_list(client: MapyClient) -> None:
    """geocode() on a zero-match response returns an empty list (not an error)."""
    respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))
    matches = await client.geocode("xyzzy-no-such-place")
    assert matches == []


@respx.mock
async def test_geocode_multiple_matches(client: MapyClient) -> None:
    """geocode() parses all items in the response list."""
    second_item = {
        **_CHARLES_BRIDGE_ITEM,
        "name": "Karlův most — alt",
        "position": {"lon": 14.4113, "lat": 50.0866},
    }
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(200, json={"items": [_CHARLES_BRIDGE_ITEM, second_item]})
    )

    matches = await client.geocode("Karlův most")
    assert len(matches) == 2
    assert matches[0].name == "Karlův most"
    assert matches[1].name == "Karlův most — alt"


@respx.mock
async def test_geocode_match_with_zip(client: MapyClient) -> None:
    """GeocodeMatch.zip is populated when the API returns a zip field."""
    item_with_zip = {**_CHARLES_BRIDGE_ITEM, "zip": "110 00"}
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(200, json={"items": [item_with_zip]})
    )

    matches = await client.geocode("Týnská 7")
    assert matches[0].zip == "110 00"


# ---------------------------------------------------------------------------
# Auth — apikey must be a query parameter, not a header
# ---------------------------------------------------------------------------


@respx.mock
async def test_geocode_sends_apikey_as_query_param(client: MapyClient) -> None:
    """The API key must be sent as ?apikey=... (not as a header)."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    await client.geocode("Prague")

    assert route.called
    request = route.calls.last.request
    assert request.url.params["apikey"] == _API_KEY
    # Must NOT leak as a header.
    assert "x-mapy-api-key" not in {k.lower() for k in request.headers}
    assert "authorization" not in {k.lower() for k in request.headers}


@respx.mock
async def test_geocode_passes_query_param(client: MapyClient) -> None:
    """The query string is forwarded verbatim as the `query` parameter."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    await client.geocode("Charles Bridge")

    request = route.calls.last.request
    assert request.url.params["query"] == "Charles Bridge"


@respx.mock
async def test_geocode_default_lang_and_limit(client: MapyClient) -> None:
    """Default lang='en' and limit=5 are forwarded."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    await client.geocode("Prague")

    params = route.calls.last.request.url.params
    assert params["lang"] == "en"
    assert params["limit"] == "5"


# ---------------------------------------------------------------------------
# preferNear formatting
# ---------------------------------------------------------------------------


@respx.mock
async def test_geocode_prefer_near_formats_as_lon_comma_lat(
    client: MapyClient,
) -> None:
    """prefer_near=(lon, lat) must produce preferNear='lon,lat' as a single string."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    await client.geocode("restaurant", prefer_near=(14.4378, 50.0755))

    params = route.calls.last.request.url.params
    assert params["preferNear"] == "14.4378,50.0755"


@respx.mock
async def test_geocode_without_prefer_near_omits_param(client: MapyClient) -> None:
    """preferNear must be absent when prefer_near is not provided."""
    route = respx.get(_GEOCODE_URL).mock(return_value=Response(200, json={"items": []}))

    await client.geocode("Prague")

    params = route.calls.last.request.url.params
    assert "preferNear" not in params


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@respx.mock
async def test_geocode_401_raises_map_api_error(client: MapyClient) -> None:
    """HTTP 401 maps to MapyAPIError with status 401 and 'unauthorized' message."""
    respx.get(_GEOCODE_URL).mock(return_value=Response(401, text="Unauthorized"))

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague")

    err = exc_info.value
    assert err.status == 401
    assert "unauthorized" in err.message.lower()


@respx.mock
async def test_geocode_403_raises_map_api_error(client: MapyClient) -> None:
    """HTTP 403 is treated the same as 401 — key invalid or unauthorized."""
    respx.get(_GEOCODE_URL).mock(return_value=Response(403, text="Forbidden"))

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague")

    err = exc_info.value
    assert err.status == 403
    assert "unauthorized" in err.message.lower()


@respx.mock
async def test_geocode_500_raises_map_api_error(client: MapyClient) -> None:
    """HTTP 500 maps to MapyAPIError with status 500 and 'service error' message."""
    respx.get(_GEOCODE_URL).mock(
        return_value=Response(500, text="Internal Server Error")
    )

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague")

    err = exc_info.value
    assert err.status == 500
    assert "service error" in err.message.lower()


@respx.mock
async def test_geocode_503_raises_map_api_error(client: MapyClient) -> None:
    """Any 5xx is a service error."""
    respx.get(_GEOCODE_URL).mock(return_value=Response(503, text="Service Unavailable"))

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague")

    err = exc_info.value
    assert err.status == 503


@respx.mock
async def test_geocode_422_raises_map_api_error_with_body(
    client: MapyClient,
) -> None:
    """Other 4xx errors include a (possibly truncated) body in the message."""
    body = "Invalid query parameter: limit must be between 1 and 15"
    respx.get(_GEOCODE_URL).mock(return_value=Response(422, text=body))

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague", limit=99)

    err = exc_info.value
    assert err.status == 422
    # body should appear, possibly truncated at 200 chars
    assert err.message in body or body[: len(err.message)] == err.message


@respx.mock
async def test_geocode_4xx_body_truncated_at_200(client: MapyClient) -> None:
    """Body longer than 200 chars is truncated in the error message."""
    long_body = "x" * 300
    respx.get(_GEOCODE_URL).mock(return_value=Response(400, text=long_body))

    with pytest.raises(MapyAPIError) as exc_info:
        await client.geocode("Prague")

    err = exc_info.value
    assert len(err.message) <= 200 + 50  # allow for "status: " prefix overhead
