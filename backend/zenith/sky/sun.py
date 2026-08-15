"""NOAA-style solar altitude. No ephemeris file required."""

from __future__ import annotations

import math
from datetime import datetime, timezone


def sun_altitude_deg(lat: float, lon: float, when: datetime | None = None) -> float:
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    utc = when.astimezone(timezone.utc)
    lat_r = math.radians(lat)

    n = utc.timetuple().tm_yday
    frac = (utc.hour + utc.minute / 60 + utc.second / 3600) / 24
    gamma = 2 * math.pi / 365 * (n - 1 + (frac - 0.5))
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    time_offset = eqtime + 4 * lon
    true_solar = utc.hour * 60 + utc.minute + utc.second / 60 + time_offset
    hour_angle = math.radians(true_solar / 4 - 180)
    cos_zenith = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(hour_angle)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return 90 - math.degrees(math.acos(cos_zenith))


def sky_mode(sun_alt: float, night_threshold: float) -> str:
    if sun_alt >= 0:
        return "day"
    if sun_alt > night_threshold:
        return "twilight"
    return "night"
