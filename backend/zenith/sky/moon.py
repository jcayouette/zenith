"""Moon RA/Dec from a compact Meeus-style approximation."""

from __future__ import annotations

import math
from datetime import datetime

from zenith.sky.coords import eq_to_altaz, julian_date, lst_deg


def moon_ra_dec_deg(when: datetime | None = None) -> tuple[float, float]:
    d = julian_date(when) - 2451545.0
    l = math.radians((218.316 + 13.176396 * d) % 360.0)
    m = math.radians((134.963 + 13.064993 * d) % 360.0)
    f = math.radians((93.272 + 13.229350 * d) % 360.0)
    lon = l + math.radians(6.289) * math.sin(m)
    lat = math.radians(5.128) * math.sin(f)
    eps = math.radians(23.439 - 0.0000004 * d)
    y = math.cos(lat) * math.sin(lon)
    x = math.cos(lat) * math.cos(lon)
    ra = math.atan2(y * math.cos(eps) - math.sin(lat) * math.sin(eps), x)
    dec = math.asin(
        math.sin(lat) * math.cos(eps) + math.cos(lat) * math.sin(eps) * math.sin(lon)
    )
    return math.degrees(ra) % 360.0, math.degrees(dec)


def moon_altaz(lat: float, lon: float, when: datetime | None = None) -> tuple[float, float]:
    ra, dec = moon_ra_dec_deg(when)
    return eq_to_altaz(ra, dec, lat, lst_deg(lon, when))
