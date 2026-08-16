"""Equatorial ↔ horizontal coordinates. No ephemeris file required."""

from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np


def _utc(when: datetime | None) -> datetime:
    when = when or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def julian_date(when: datetime | None = None) -> float:
    utc = _utc(when)
    y, m = utc.year, utc.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    day = utc.day + (utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9) / 24
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5


def gmst_deg(when: datetime | None = None) -> float:
    """Greenwich mean sidereal time in degrees (Meeus)."""
    jd = julian_date(when)
    t = (jd - 2451545.0) / 36525.0
    gmst = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t * t
        - t * t * t / 38710000.0
    )
    return gmst % 360.0


def lst_deg(longitude_deg: float, when: datetime | None = None) -> float:
    return (gmst_deg(when) + longitude_deg) % 360.0


def eq_to_altaz(
    ra_deg: np.ndarray | float,
    dec_deg: np.ndarray | float,
    lat_deg: float,
    lst_deg_value: float,
) -> tuple[np.ndarray, np.ndarray]:
    """J2000 RA/Dec → altitude and azimuth (0=north, 90=east) in degrees."""
    ra = np.deg2rad(np.asarray(ra_deg, dtype=np.float64))
    dec = np.deg2rad(np.asarray(dec_deg, dtype=np.float64))
    lat = math.radians(lat_deg)
    ha = np.deg2rad(lst_deg_value) - ra
    sin_alt = np.sin(dec) * math.sin(lat) + np.cos(dec) * math.cos(lat) * np.cos(ha)
    sin_alt = np.clip(sin_alt, -1.0, 1.0)
    alt = np.arcsin(sin_alt)
    y = -np.sin(ha) * np.cos(dec)
    x = np.tan(dec) * math.cos(lat) - math.sin(lat) * np.cos(ha)
    az = np.arctan2(y, x)
    alt_deg = np.rad2deg(alt)
    az_deg = np.rad2deg(az) % 360.0
    if np.ndim(ra_deg) == 0:
        return float(alt_deg), float(az_deg)
    return alt_deg, az_deg
