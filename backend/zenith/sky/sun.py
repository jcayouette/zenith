"""NOAA-style solar altitude. No ephemeris file required."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _utc(when: datetime | None) -> datetime:
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def local_time(tz_name: str, when: datetime | None = None) -> datetime:
    utc = _utc(when)
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        tz = timezone.utc
    return utc.astimezone(tz)


def _solar_geometry(lat: float, lon: float, utc: datetime) -> tuple[float, float]:
    """Return (altitude_deg, hour_angle_deg). Hour angle is negative in the morning."""
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
    hour_angle_deg = true_solar / 4 - 180
    hour_angle = math.radians(hour_angle_deg)
    cos_zenith = math.sin(lat_r) * math.sin(decl) + math.cos(lat_r) * math.cos(decl) * math.cos(
        hour_angle
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    altitude = 90 - math.degrees(math.acos(cos_zenith))
    return altitude, hour_angle_deg


def sun_altitude_deg(lat: float, lon: float, when: datetime | None = None) -> float:
    return _solar_geometry(lat, lon, _utc(when))[0]


def solar_hour_angle_deg(lat: float, lon: float, when: datetime | None = None) -> float:
    return _solar_geometry(lat, lon, _utc(when))[1]


def sky_mode(sun_alt: float, night_threshold: float) -> str:
    if sun_alt >= 0:
        return "day"
    if sun_alt > night_threshold:
        return "twilight"
    return "night"


@dataclass(frozen=True)
class SkySession:
    """Archive session for the current instant.

    Night dating: sunset on calendar date D through sunrise D+1 is stored as
    ``nights/YYYY-MM-DD`` using D. Daytime uses ``days/YYYY-MM-DD`` for the
    local calendar date. Twilight (sun below the horizon but above the night
    threshold) belongs to the night folder so keograms span sunset to sunrise.
    """

    mode: str
    kind: str
    date: date
    sun_alt: float
    hour_angle_deg: float


def sky_session(
    lat: float,
    lon: float,
    tz_name: str,
    night_threshold: float,
    when: datetime | None = None,
) -> SkySession:
    utc = _utc(when)
    sun_alt, hour_angle = _solar_geometry(lat, lon, utc)
    mode = sky_mode(sun_alt, night_threshold)
    local = local_time(tz_name, utc)
    if sun_alt >= 0:
        kind = "day"
        session_date = local.date()
    else:
        kind = "night"
        session_date = local.date() if hour_angle >= 0 else local.date() - timedelta(days=1)
    return SkySession(
        mode=mode,
        kind=kind,
        date=session_date,
        sun_alt=sun_alt,
        hour_angle_deg=hour_angle,
    )
