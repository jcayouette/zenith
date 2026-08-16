"""Celestrak TLE cache and SGP4 look angles."""

from __future__ import annotations

import math
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import numpy as np

from zenith.paths import DATA_DIR
from zenith.sky.coords import gmst_deg

USER_AGENT = "ZenithAllSky/0.2 (https://github.com/jcayouette/zenith)"
MAX_AGE = timedelta(hours=12)
TLE_GROUPS = {
    "stations": "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle",
    "visual": "https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle",
    "starlink": "https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=tle",
    "oneweb": "https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=tle",
    "kuiper": "https://celestrak.org/NORAD/elements/gp.php?GROUP=kuiper&FORMAT=tle",
    "qianfan": "https://celestrak.org/NORAD/elements/gp.php?GROUP=qianfan&FORMAT=tle",
    "hulianwang": "https://celestrak.org/NORAD/elements/gp.php?GROUP=hulianwang&FORMAT=tle",
    "military": "https://celestrak.org/NORAD/elements/gp.php?GROUP=military&FORMAT=tle",
    "weather": "https://celestrak.org/NORAD/elements/gp.php?GROUP=weather&FORMAT=tle",
    "science": "https://celestrak.org/NORAD/elements/gp.php?GROUP=science&FORMAT=tle",
    "gps-ops": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=tle",
    "glo-ops": "https://celestrak.org/NORAD/elements/gp.php?GROUP=glo-ops&FORMAT=tle",
    "galileo": "https://celestrak.org/NORAD/elements/gp.php?GROUP=galileo&FORMAT=tle",
    "beidou": "https://celestrak.org/NORAD/elements/gp.php?GROUP=beidou&FORMAT=tle",
    "gnss": "https://celestrak.org/NORAD/elements/gp.php?GROUP=gnss&FORMAT=tle",
    "iridium-NEXT": "https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle",
    "geo": "https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=tle",
    "intelsat": "https://celestrak.org/NORAD/elements/gp.php?GROUP=intelsat&FORMAT=tle",
    "ses": "https://celestrak.org/NORAD/elements/gp.php?GROUP=ses&FORMAT=tle",
    "planet": "https://celestrak.org/NORAD/elements/gp.php?GROUP=planet&FORMAT=tle",
    "spire": "https://celestrak.org/NORAD/elements/gp.php?GROUP=spire&FORMAT=tle",
    "amateur": "https://celestrak.org/NORAD/elements/gp.php?GROUP=amateur&FORMAT=tle",
    "cubesat": "https://celestrak.org/NORAD/elements/gp.php?GROUP=cubesat&FORMAT=tle",
    "globalstar": "https://celestrak.org/NORAD/elements/gp.php?GROUP=globalstar&FORMAT=tle",
    "orbcomm": "https://celestrak.org/NORAD/elements/gp.php?GROUP=orbcomm&FORMAT=tle",
    "other-comm": "https://celestrak.org/NORAD/elements/gp.php?GROUP=other-comm&FORMAT=tle",
    "last-30-days": "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle",
    "active": "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle",
}
GROUP_KIND = {
    "stations": "station",
    "starlink": "starlink",
    "oneweb": "oneweb",
    "kuiper": "kuiper",
    "qianfan": "other",
    "hulianwang": "other",
    "military": "military",
    "weather": "weather",
    "science": "science",
    "gps-ops": "gnss",
    "glo-ops": "gnss",
    "galileo": "gnss",
    "beidou": "gnss",
    "gnss": "gnss",
    "iridium-NEXT": "comms",
    "geo": "geo",
    "intelsat": "geo",
    "ses": "geo",
    "planet": "planet",
    "spire": "planet",
    "amateur": "other",
    "cubesat": "other",
    "globalstar": "comms",
    "orbcomm": "comms",
    "other-comm": "comms",
    "last-30-days": "other",
    "visual": "other",
    "active": "other",
}
KIND_RANK = {
    "station": 0,
    "starlink": 1,
    "oneweb": 2,
    "kuiper": 3,
    "military": 4,
    "weather": 5,
    "science": 6,
    "gnss": 7,
    "geo": 8,
    "planet": 9,
    "comms": 10,
    "other": 11,
}

PREFERRED_NORAD = {
    "25544": "ISS",
    "48274": "CSS",
    "20580": "Hubble",
}

WGS84_A = 6378.137
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

_prop_cache: dict = {"sig": None, "catalog": [], "recs": None}


def tle_dir() -> Path:
    folder = DATA_DIR / "tle"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def tle_path(group: str = "stations") -> Path:
    return tle_dir() / f"{group}.txt"


def refresh_tles(*, force: bool = False) -> list[Path]:
    def fetch_one(group: str, url: str) -> Path | None:
        path = tle_path(group)
        if not force and path.is_file():
            age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
            if age < MAX_AGE.total_seconds():
                return path
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("ascii", errors="replace")
        except OSError:
            return path if path.is_file() else None
        if "1 " not in text or "2 " not in text:
            return path if path.is_file() else None
        path.write_text(text, encoding="ascii")
        return path

    paths: list[Path] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(fetch_one, group, url) for group, url in TLE_GROUPS.items()]
        for fut in futs:
            path = fut.result()
            if path is not None:
                paths.append(path)
    return paths


def parse_tles(text: str) -> list[tuple[str, str, str]]:
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out: list[tuple[str, str, str]] = []
    i = 0
    while i + 2 < len(lines):
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            out.append((name.strip(), l1, l2))
            i += 3
        else:
            i += 1
    return out


def norad_id(line1: str) -> str:
    return line1[2:7].strip()


def intl_designator(line1: str) -> str | None:
    raw = line1[9:17].strip()
    if len(raw) < 5 or not raw[:2].isdigit():
        return None
    yy = int(raw[:2])
    year = 1900 + yy if yy >= 57 else 2000 + yy
    return f"{year}-{raw[2:]}"


def classify_sat(name: str, group: str = "visual") -> str:
    kind = GROUP_KIND.get(group, "other")
    upper = name.upper()
    if "STARLINK" in upper:
        return "starlink"
    if "ONEWEB" in upper:
        return "oneweb"
    if "KUIPER" in upper:
        return "kuiper"
    if any(tag in upper for tag in ("FLOCK", "SKYSAT", "DOVE")):
        return "planet"
    if any(tag in upper for tag in ("USA ", "NROL", "NOSS", "INTRUDER", "LACROSSE", "ONYX", "KEYHOLE")):
        return "military"
    if any(tag in upper for tag in ("NAVSTAR", "GSAT", "BEIDOU", "GLONASS", "GALILEO", "GPS ")):
        return "gnss"
    if any(tag in upper for tag in ("NOAA", "GOES", "METEOR", "METOP", "HIMAWARI", "FENGYUN")):
        return "weather"
    if any(tag in upper for tag in ("HUBBLE", "HST", "JWST", "TESS", "CHANDRA", "XMM")):
        return "science"
    if "ISS" in upper or "TIANHE" in upper or upper.startswith("CSS"):
        return "station"
    return kind


def display_name(name: str, line1: str) -> str | None:
    nid = norad_id(line1)
    if nid in PREFERRED_NORAD:
        return PREFERRED_NORAD[nid]
    upper = f" {name.upper()} "
    if " DEB" in upper or " R/B" in upper:
        return None
    cleaned = name.split(" (")[0].strip()
    if cleaned.upper().startswith("STARLINK"):
        return cleaned.replace("STARLINK", "SL", 1)
    if cleaned.upper().startswith("ONEWEB"):
        return cleaned.replace("ONEWEB", "OW", 1)
    return cleaned or name.strip()


def load_stations() -> list[tuple[str, str, str]]:
    return [(name, l1, l2) for name, _norad, _kind, l1, l2 in overlay_catalog()]


def overlay_catalog() -> list[tuple[str, str, str, str, str]]:
    """(display name, norad, kind, l1, l2), deduped by NORAD. Uses cached TLE files."""
    sig = _catalog_sig()
    if _prop_cache["sig"] == sig and _prop_cache["catalog"]:
        return _prop_cache["catalog"]
    by_id: dict[str, tuple[str, str, str, str, str]] = {}
    ranks: dict[str, int] = {}
    for group in TLE_GROUPS:
        path = tle_path(group)
        if not path.is_file():
            continue
        for raw_name, l1, l2 in parse_tles(path.read_text(encoding="ascii", errors="replace")):
            nid = norad_id(l1)
            label = display_name(raw_name, l1)
            if not label:
                continue
            kind = classify_sat(raw_name, group)
            rank = KIND_RANK.get(kind, 9)
            prev = ranks.get(nid)
            if prev is None or rank < prev:
                by_id[nid] = (label, nid, kind, l1, l2)
                ranks[nid] = rank
    catalog = list(by_id.values())
    _prop_cache["sig"] = sig
    _prop_cache["catalog"] = catalog
    _prop_cache["recs"] = None
    return catalog


def _catalog_sig() -> tuple:
    rows = []
    for group in TLE_GROUPS:
        path = tle_path(group)
        rows.append((group, path.stat().st_mtime if path.is_file() else 0))
    return tuple(rows)


def _propagation_set():
    sig = _catalog_sig()
    if _prop_cache["sig"] == sig and _prop_cache["recs"] is not None:
        return _prop_cache["catalog"], _prop_cache["recs"]
    from sgp4.api import Satrec

    catalog = overlay_catalog()
    recs = [Satrec.twoline2rv(l1, l2) for _n, _id, _k, l1, l2 in catalog]
    _prop_cache["sig"] = sig
    _prop_cache["catalog"] = catalog
    _prop_cache["recs"] = recs
    return catalog, recs


def look_azel_batch(
    recs: list,
    lat: float,
    lon: float,
    elevation_m: float,
    times: list[datetime],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return az, alt, ok, range_km with shape (n_sats, n_times)."""
    from sgp4.api import SatrecArray, jday

    if not recs or not times:
        z = np.zeros((len(recs), max(len(times), 1)))
        return z, z, np.zeros_like(z, dtype=bool), z
    jd = np.empty(len(times), dtype=np.float64)
    fr = np.empty(len(times), dtype=np.float64)
    for i, when in enumerate(times):
        utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
        jd[i], fr[i] = jday(
            utc.year,
            utc.month,
            utc.day,
            utc.hour,
            utc.minute,
            utc.second + utc.microsecond * 1e-6,
        )
    arr = SatrecArray(recs)
    err, r_teme, _v = arr.sgp4(jd, fr)
    ok = err == 0
    gmst = np.array(
        [
            math.radians(
                gmst_deg(t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc))
            )
            for t in times
        ],
        dtype=np.float64,
    )
    c, s = np.cos(gmst), np.sin(gmst)
    x = r_teme[:, :, 0]
    y = r_teme[:, :, 1]
    z = r_teme[:, :, 2]
    ecef_x = c * x + s * y
    ecef_y = -s * x + c * y
    ecef_z = z
    obs = _geodetic_to_ecef(lat, lon, elevation_m / 1000.0)
    rho_x = ecef_x - obs[0]
    rho_y = ecef_y - obs[1]
    rho_z = ecef_z - obs[2]
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    sl, cl, s0, c0 = math.sin(lat_r), math.cos(lat_r), math.sin(lon_r), math.cos(lon_r)
    south = sl * c0 * rho_x + sl * s0 * rho_y - cl * rho_z
    east = -s0 * rho_x + c0 * rho_y
    up = cl * c0 * rho_x + cl * s0 * rho_y + sl * rho_z
    horiz = np.hypot(south, east)
    az = np.degrees(np.arctan2(east, -south)) % 360.0
    el = np.degrees(np.arctan2(up, horiz))
    rng = np.hypot(horiz, up)
    return az, el, ok, rng


@lru_cache(maxsize=4096)
def _satrec(l1: str, l2: str):
    from sgp4.api import Satrec

    return Satrec.twoline2rv(l1, l2)


def sat_azel(
    l1: str,
    l2: str,
    lat: float,
    lon: float,
    elevation_m: float,
    when: datetime,
) -> tuple[float, float] | None:
    try:
        from sgp4.api import jday
    except ImportError:
        return None
    sat = _satrec(l1, l2)
    utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    jd, fr = jday(
        utc.year,
        utc.month,
        utc.day,
        utc.hour,
        utc.minute,
        utc.second + utc.microsecond * 1e-6,
    )
    err, r_teme, _v = sat.sgp4(jd, fr)
    if err != 0:
        return None
    gmst = math.radians(gmst_deg(utc))
    r_ecef = _teme_to_ecef(np.asarray(r_teme, dtype=np.float64), gmst)
    return _look_azel(r_ecef, lat, lon, elevation_m / 1000.0)


def upcoming_passes(
    name: str,
    l1: str,
    l2: str,
    lat: float,
    lon: float,
    elevation_m: float,
    when: datetime,
    *,
    hours: float = 24,
    min_alt: float = 10.0,
    step_s: int = 30,
) -> list[dict]:
    start = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    end = start + timedelta(hours=hours)
    step = timedelta(seconds=step_s)
    samples: list[tuple[datetime, float, float]] = []
    t = start
    while t <= end:
        look = sat_azel(l1, l2, lat, lon, elevation_m, t)
        if look is not None:
            samples.append((t, look[0], look[1]))
        t += step
    passes: list[dict] = []
    current: list[tuple[datetime, float, float]] = []
    for row in samples:
        if row[2] >= min_alt:
            current.append(row)
        elif current:
            _commit_pass(passes, name, current)
            current = []
    if current:
        _commit_pass(passes, name, current)
    return passes


def _commit_pass(passes: list[dict], name: str, rows: list[tuple[datetime, float, float]]) -> None:
    peak = max(rows, key=lambda r: r[2])
    passes.append(
        {
            "name": name,
            "start": rows[0][0].isoformat(timespec="minutes"),
            "peak": peak[0].isoformat(timespec="minutes"),
            "end": rows[-1][0].isoformat(timespec="minutes"),
            "max_alt": round(peak[2], 1),
            "az_peak": round(peak[1], 1),
        }
    )


def _teme_to_ecef(r_teme: np.ndarray, gmst_rad: float) -> np.ndarray:
    c, s = math.cos(gmst_rad), math.sin(gmst_rad)
    x, y, z = r_teme
    return np.array([c * x + s * y, -s * x + c * y, z], dtype=np.float64)


def _geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_km: float) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + alt_km) * math.cos(lat) * math.cos(lon),
            (n + alt_km) * math.cos(lat) * math.sin(lon),
            (n * (1.0 - WGS84_E2) + alt_km) * math.sin(lat),
        ],
        dtype=np.float64,
    )


def _look_azel(r_ecef: np.ndarray, lat_deg: float, lon_deg: float, alt_km: float) -> tuple[float, float]:
    obs = _geodetic_to_ecef(lat_deg, lon_deg, alt_km)
    rho = r_ecef - obs
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sl, cl, s0, c0 = math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon)
    south = sl * c0 * rho[0] + sl * s0 * rho[1] - cl * rho[2]
    east = -s0 * rho[0] + c0 * rho[1]
    up = cl * c0 * rho[0] + cl * s0 * rho[1] + sl * rho[2]
    az = math.degrees(math.atan2(east, -south)) % 360.0
    el = math.degrees(math.atan2(up, math.hypot(south, east)))
    return az, el
