"""Pydantic models for the mapy.com forward-geocoding API.

Used by both `mapy_client.MapyClient.geocode` and the `find_places` tool.
Field descriptions are written for LLM consumption — FastMCP surfaces them
in the tool schema.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    lon: float = Field(
        description="WGS84 longitude in decimal degrees.",
        ge=-180,
        le=180,
    )
    lat: float = Field(
        description="WGS84 latitude in decimal degrees.",
        ge=-90,
        le=90,
    )


class GeocodeQuery(BaseModel):
    query: str = Field(
        description=(
            "Place name, address, or point of interest to resolve to "
            "coordinates (e.g. 'Charles Bridge, Prague', 'Týnská 7 Praha', "
            "'Brno hlavní nádraží')."
        ),
        min_length=1,
    )
    near: Coordinate | None = Field(
        default=None,
        description=(
            "Optional proximity hint — prefer results near this point. "
            "Useful when disambiguating common names (e.g. searching "
            "'restaurant' near Charles Bridge to bias results to that "
            "neighborhood). Does not filter; only ranks."
        ),
    )


class GeocodeMatch(BaseModel):
    name: str = Field(
        description=(
            "Matched entity name as returned by mapy.com (e.g. 'Karlův most', "
            "'Týnská ulička 610/7'). Suitable as a marker label when feeding "
            "into build_points_url."
        ),
    )
    label: str = Field(
        description=(
            "Short entity-type label from mapy.com (e.g. 'Most', 'Adresa', "
            "'Město'). Mostly Czech; useful for distinguishing addresses "
            "from POIs from regions at a glance."
        ),
    )
    lon: float = Field(description="WGS84 longitude.", ge=-180, le=180)
    lat: float = Field(description="WGS84 latitude.", ge=-90, le=90)
    location: str = Field(
        description=(
            "Human-readable locality hierarchy (e.g. 'Praha 1 - Staré "
            "Město, Česko'). The primary disambiguator when several "
            "matches share a name."
        ),
    )
    type: str = Field(
        description=(
            "Entity type string from mapy.com (e.g. an address, a POI, a "
            "municipality, a region). See the mapy.com geocoding API "
            "docs for the full list of values."
        ),
    )
    zip: str | None = Field(
        default=None,
        description="Postal code, when mapy.com provides one (addresses only).",
    )


class GeocodeQueryResult(BaseModel):
    query: str = Field(
        description="Echo of the input query that produced these matches.",
    )
    matches: list[GeocodeMatch] = Field(
        description=(
            "Candidate matches in mapy.com's relevance order. Empty list "
            "means no matches were found (not an error). Up to 5 entries."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Set when this query failed (network error, mapy.com 5xx, etc.). "
            "Other queries in the same batch may still have succeeded; "
            "check each result independently. None on success."
        ),
    )
