"""Encoder for the mapy.com `uc` query parameter (delta-encoded coordinate stream).

Used by the legacy `vlastni-body` URL pattern. Pure function; no I/O.
"""

from __future__ import annotations

_ALPHABET = "0ABCD2EFGH4IJKLMN6OPQRST8UVWXYZ-1abcd3efgh5ijklmn7opqrst9uvwxyz."


def encode_uc(points_lon_lat: list[tuple[float, float]]) -> str:
    """Encode a sequence of (lon, lat) pairs into mapy.com's `uc` parameter."""
    prev_x = 0
    prev_y = 0
    out: list[str] = []
    for lon, lat in points_lon_lat:
        x = round((lon + 180) * (1 << 28) / 360)
        y = round((lat + 90) * (1 << 28) / 180)
        out.append(_serialize_number(x - prev_x, x))
        out.append(_serialize_number(y - prev_y, y))
        prev_x = x
        prev_y = y
    return "".join(out)


def _serialize_number(delta: int, absolute: int) -> str:
    if -1024 <= delta < 1024:
        v = delta + 1024
        return _ALPHABET[(v >> 6) & 63] + _ALPHABET[v & 63]
    if -32768 <= delta < 32768:
        v = 131072 | (delta + 32768)
        return _ALPHABET[(v >> 12) & 63] + _ALPHABET[(v >> 6) & 63] + _ALPHABET[v & 63]
    v = 805306368 | (268435455 & absolute)
    return "".join(_ALPHABET[(v >> shift) & 63] for shift in (24, 18, 12, 6, 0))
