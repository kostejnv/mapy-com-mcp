"""Models for the mapy.com routing API response.

Used by `mapy_api.client.MapyClient.route` and the `show_route` tool.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RouteType = Literal[
    "car_fast",
    "car_short",
    "foot_fast",
    "foot_hiking",
    "bike_road",
    "bike_mountain",
]


@dataclass(frozen=True)
class RouteLeg:
    """One part of the route between two consecutive route points."""

    length_m: int
    duration_s: int


@dataclass(frozen=True)
class RoutePointInfo:
    """How the routing engine treated one input point."""

    snap_distance_m: int  # how far it was moved onto the road/path network
    restriction: str | None  # e.g. "CLOSURE", "PEDESTRIAN_ZONE"; None if allowed


@dataclass(frozen=True)
class Route:
    length_m: int
    duration_s: int
    legs: list[RouteLeg]
    geometry: list[tuple[float, float]]  # (lon, lat) along the route
    points: list[RoutePointInfo]  # one per input point, same order
