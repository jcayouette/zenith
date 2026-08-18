"""Live aircraft from OpenSky / ADS-B, plotted on a flat ground-range overlay."""

from __future__ import annotations

import json
import math
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.sky.layers import OVERLAY_BAKE_HORIZON, _norm, _proj_kw
from zenith.sky.project import rangeaz_to_xy
from zenith.sky.tle import USER_AGENT, WGS84_A, WGS84_E2

OPENSKY_URL = "https://opensky-network.org/api/states/all"
ADSBD_URL = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{nm}"
CACHE_S = 25.0
LOOKAHEAD_S = 8.0
MAP_RANGE_KM = 80.0
FETCH_KM = 420.0
CPA_KM = 50.0
MAX_TCA_S = 90 * 60.0
HEADING_KM = 10.0
M_PER_DEG = 111_320.0
KT_MS = 0.514444
FT_M = 0.3048
FPM_MS = 0.00508
ADSB_CAT = {
    "A0": 1,
    "A1": 1,
    "A2": 2,
    "A3": 3,
    "A4": 4,
    "A5": 5,
    "A6": 6,
    "A7": 7,
    "B0": 8,
    "B1": 9,
    "B2": 10,
    "B3": 11,
    "B4": 13,
    "B6": 14,
    "B7": 15,
    "C0": 16,
    "C1": 17,
    "C2": 18,
}

CATEGORY = {
    0: "Unknown",
    1: "Light",
    2: "Small",
    3: "Large",
    4: "High-vortex",
    5: "Heavy",
    6: "High performance",
    7: "Helicopter",
    8: "Glider",
    9: "Lighter than air",
    10: "Parachute",
    11: "Ultralight",
    13: "UAV",
    14: "Space",
    15: "Emergency",
    16: "Service",
    17: "Military",
    18: "Law enforcement",
}

_cache: dict = {
    "key": None,
    "at": 0.0,
    "states": [],
    "error": None,
    "source": "opensky",
    "backoff_until": 0.0,
}
_lock = threading.Lock()


def build_aircraft(
    settings: ZenithSettings,
    *,
    width: int,
    height: int,
    when: datetime | None = None,
) -> dict:
    utc = when or datetime.now(timezone.utc)
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    loc = settings.location
    now_s = utc.timestamp()
    states, fetch_err = _states(loc.latitude, loc.longitude, now_s)
    proj = dict(
        width=width,
        height=height,
        north_angle_deg=loc.keogram_angle_deg,
        horizon=OVERLAY_BAKE_HORIZON,
        flip_h=False,
        flip_v=False,
        rotation_deg=0,
    )
    planes = _project(states, loc.latitude, loc.longitude, loc.elevation_m, now_s, **proj)
    inbound = sum(1 for p in planes if p.get("inbound"))
    with _lock:
        source = _cache.get("source") or "opensky"
    return {
        "when": utc.isoformat(timespec="seconds"),
        "dt": LOOKAHEAD_S,
        "source": source,
        "cpa_km": CPA_KM,
        "map_km": MAP_RANGE_KM,
        "aircraft": planes,
        "count": len(planes),
        "inbound": inbound,
        "error": fetch_err,
    }


def look_azel_geodetic(
    lat_deg: np.ndarray | float,
    lon_deg: np.ndarray | float,
    alt_m: np.ndarray | float,
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Observer-relative azimuth, altitude (deg) and range (km) for geodetic points."""
    lat = np.asarray(lat_deg, dtype=np.float64)
    lon = np.asarray(lon_deg, dtype=np.float64)
    alt_km = np.asarray(alt_m, dtype=np.float64) / 1000.0
    tgt = _geodetic_to_ecef(lat, lon, alt_km)
    obs = _geodetic_to_ecef(np.asarray(obs_lat), np.asarray(obs_lon), np.asarray(obs_alt_m / 1000.0))
    if tgt.ndim == 1:
        rho_x, rho_y, rho_z = tgt - obs
    else:
        rho_x = tgt[0] - obs[0]
        rho_y = tgt[1] - obs[1]
        rho_z = tgt[2] - obs[2]
    lat_r, lon_r = math.radians(obs_lat), math.radians(obs_lon)
    sl, cl, s0, c0 = math.sin(lat_r), math.cos(lat_r), math.sin(lon_r), math.cos(lon_r)
    south = sl * c0 * rho_x + sl * s0 * rho_y - cl * rho_z
    east = -s0 * rho_x + c0 * rho_y
    up = cl * c0 * rho_x + cl * s0 * rho_y + sl * rho_z
    horiz = np.hypot(south, east)
    az = np.degrees(np.arctan2(east, -south)) % 360.0
    el = np.degrees(np.arctan2(up, horiz))
    rng = np.hypot(horiz, up)
    if np.ndim(lat_deg) == 0:
        return float(az), float(el), float(rng)
    return az, el, rng


def llh_along_look(
    az_deg: np.ndarray | float,
    el_deg: np.ndarray | float,
    height_m: float,
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lat/lon of the point at ``height_m`` along a look ray (inverse of look_azel_geodetic)."""
    az = np.deg2rad(np.asarray(az_deg, dtype=np.float64))
    el = np.deg2rad(np.asarray(el_deg, dtype=np.float64))
    obs = _geodetic_to_ecef(np.asarray(obs_lat), np.asarray(obs_lon), np.asarray(obs_alt_m / 1000.0))
    lat_r, lon_r = math.radians(obs_lat), math.radians(obs_lon)
    sl, cl, s0, c0 = math.sin(lat_r), math.cos(lat_r), math.sin(lon_r), math.cos(lon_r)
    east = np.cos(el) * np.sin(az)
    north = np.cos(el) * np.cos(az)
    up = np.sin(el)
    dx = -s0 * east - sl * c0 * north + cl * c0 * up
    dy = c0 * east - sl * s0 * north + cl * s0 * up
    dz = cl * north + sl * up
    sine = np.clip(np.sin(el), 1e-3, None)
    s = np.clip((height_m - obs_alt_m) / 1000.0 / sine, 0.0, 500.0)
    for _ in range(4):
        lat, lon, alt_m = _ecef_to_geodetic(obs[0] + dx * s, obs[1] + dy * s, obs[2] + dz * s)
        s = np.clip(s + (height_m - alt_m) / 1000.0 / sine, 0.0, 500.0)
    lat, lon, alt_m = _ecef_to_geodetic(obs[0] + dx * s, obs[1] + dy * s, obs[2] + dz * s)
    if np.ndim(az_deg) == 0:
        return float(lat), float(lon), float(alt_m)
    return lat, lon, alt_m


def _ecef_to_geodetic(x, y, z) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    for _ in range(5):
        sinlat = np.sin(lat)
        n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sinlat**2)
        lat = np.arctan2(z + n * WGS84_E2 * sinlat, p)
    sinlat = np.sin(lat)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * sinlat**2)
    alt_km = p / np.clip(np.cos(lat), 1e-6, None) - n
    return np.degrees(lat), np.degrees(lon), alt_km * 1000.0


def offset_llh(
    lat: np.ndarray,
    lon: np.ndarray,
    alt_m: np.ndarray,
    track_deg: np.ndarray,
    speed_ms: np.ndarray,
    vrate_ms: np.ndarray,
    dt_s: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dead-reckon lat/lon/alt by ground track, speed, and vertical rate."""
    dist = np.asarray(speed_ms, dtype=np.float64) * np.asarray(dt_s, dtype=np.float64)
    rad = np.deg2rad(np.asarray(track_deg, dtype=np.float64))
    dnorth = dist * np.cos(rad)
    deast = dist * np.sin(rad)
    dlat = dnorth / 111_320.0
    coslat = np.cos(np.deg2rad(lat))
    coslat = np.where(np.abs(coslat) < 1e-6, 1e-6, coslat)
    dlon = deast / (111_320.0 * coslat)
    alt2 = np.asarray(alt_m, dtype=np.float64) + np.asarray(vrate_ms, dtype=np.float64) * np.asarray(
        dt_s, dtype=np.float64
    )
    return lat + dlat, lon + dlon, np.maximum(alt2, 0.0)


def closest_approach(
    lat: np.ndarray | float,
    lon: np.ndarray | float,
    track_deg: np.ndarray | float,
    speed_ms: np.ndarray | float,
    obs_lat: float,
    obs_lon: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Horizontal CPA (km), time to CPA (s), and current ground range (km)."""
    lat_a = np.asarray(lat, dtype=np.float64)
    lon_a = np.asarray(lon, dtype=np.float64)
    track = np.deg2rad(np.asarray(track_deg, dtype=np.float64))
    speed = np.asarray(speed_ms, dtype=np.float64)
    deast, dnorth = _enu_km(lat_a, lon_a, obs_lat, obs_lon)
    ve = speed * np.sin(track) / 1000.0
    vn = speed * np.cos(track) / 1000.0
    horiz = np.hypot(deast, dnorth)
    v2 = ve * ve + vn * vn
    tca = np.where(v2 > 1e-12, -(deast * ve + dnorth * vn) / v2, 0.0)
    cpa = np.hypot(deast + ve * tca, dnorth + vn * tca)
    if np.ndim(lat) == 0 and np.ndim(lon) == 0:
        return float(cpa), float(tca), float(horiz)
    return cpa, tca, horiz


def _enu_km(
    lat: np.ndarray | float,
    lon: np.ndarray | float,
    obs_lat: float,
    obs_lon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """East/north kilometres from the site on a local tangent plane."""
    lat_a = np.asarray(lat, dtype=np.float64)
    lon_a = np.asarray(lon, dtype=np.float64)
    deast = (lon_a - obs_lon) * M_PER_DEG * math.cos(math.radians(obs_lat)) / 1000.0
    dnorth = (lat_a - obs_lat) * M_PER_DEG / 1000.0
    return deast, dnorth


def enu_az_range(
    lat: np.ndarray | float,
    lon: np.ndarray | float,
    obs_lat: float,
    obs_lon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """True-north azimuth (deg) and ground range (km) on the same plane as the map."""
    deast, dnorth = _enu_km(lat, lon, obs_lat, obs_lon)
    horiz = np.hypot(deast, dnorth)
    az = np.degrees(np.arctan2(deast, dnorth)) % 360.0
    if np.ndim(lat) == 0 and np.ndim(lon) == 0:
        return float(az), float(horiz)
    return az, horiz


def llh_at_range_az(
    az_deg: np.ndarray | float,
    range_km: np.ndarray | float,
    obs_lat: float,
    obs_lon: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of ``enu_az_range``: lat/lon at a ground range and azimuth from the site."""
    az = np.deg2rad(np.asarray(az_deg, dtype=np.float64))
    rng = np.asarray(range_km, dtype=np.float64)
    dnorth = rng * np.cos(az)
    deast = rng * np.sin(az)
    dlat = dnorth * 1000.0 / M_PER_DEG
    coslat = max(1e-6, abs(math.cos(math.radians(obs_lat))))
    dlon = deast * 1000.0 / (M_PER_DEG * coslat)
    lat = obs_lat + dlat
    lon = obs_lon + dlon
    if np.ndim(az_deg) == 0 and np.ndim(range_km) == 0:
        return float(lat), float(lon)
    return lat, lon


def bbox_for_site(lat: float, lon: float, radius_km: float = FETCH_KM) -> tuple[float, float, float, float]:
    dlat = radius_km / 111.32
    coslat = max(0.2, abs(math.cos(math.radians(lat))))
    dlon = radius_km / (111.32 * coslat)
    return (lat - dlat, lon - dlon, lat + dlat, lon + dlon)


def _geodetic_to_ecef(lat_deg: np.ndarray, lon_deg: np.ndarray, alt_km: np.ndarray) -> np.ndarray:
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    n = WGS84_A / np.sqrt(1.0 - WGS84_E2 * np.sin(lat) ** 2)
    x = (n + alt_km) * np.cos(lat) * np.cos(lon)
    y = (n + alt_km) * np.cos(lat) * np.sin(lon)
    z = (n * (1.0 - WGS84_E2) + alt_km) * np.sin(lat)
    return np.stack([x, y, z], axis=0)


def _states(lat: float, lon: float, now_s: float) -> tuple[list, str | None]:
    key = (round(lat, 2), round(lon, 2))
    with _lock:
        fresh = _cache["key"] == key and now_s - _cache["at"] < CACHE_S
        if fresh and (_cache["states"] or _cache["error"]):
            return _cache["states"], _cache["error"]
    rows, err, source = _fetch(lat, lon, now_s)
    with _lock:
        if rows:
            _cache.update(key=key, at=now_s, states=rows, error=None, source=source)
            return rows, None
        if _cache["states"]:
            age = now_s - _cache["at"]
            stale = f"{err}; using {age:.0f}s-old cache" if err else _cache["error"]
            _cache["error"] = stale
            return _cache["states"], stale
        _cache.update(key=key, at=now_s, states=[], error=err, source=source)
        return [], err


def parse_adsb_ac(payload: dict, now_s: float) -> list:
    """Convert an adsb.lol / readsb-style JSON dump into OpenSky state rows."""
    rows = payload.get("ac") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    stamp = payload.get("now")
    if isinstance(stamp, (int, float)):
        now_s = float(stamp) / 1000.0 if stamp > 1e12 else float(stamp)
    out: list = []
    for ac in rows:
        if not isinstance(ac, dict):
            continue
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        if ac.get("alt_baro") == "ground":
            continue
        alt = _feet_m(ac.get("alt_geom")) or _feet_m(ac.get("alt_baro"))
        if alt is None:
            continue
        gs = ac.get("gs")
        vel = float(gs) * KT_MS if gs is not None else 0.0
        rate = ac.get("baro_rate")
        if rate is None:
            rate = ac.get("geom_rate") or 0
        seen = ac.get("seen_pos")
        if seen is None:
            seen = ac.get("seen") or 0
        tpos = now_s - float(seen)
        hexid = str(ac.get("hex") or "").lower().lstrip("~")
        flight = (ac.get("flight") or "").strip()
        typecode = str(ac.get("t") or ac.get("type") or "").strip().upper() or None
        out.append(
            [
                hexid,
                flight,
                "",
                int(tpos),
                int(now_s),
                float(lon),
                float(lat),
                alt,
                False,
                vel,
                float(ac.get("track") or 0),
                float(rate) * FPM_MS,
                None,
                alt,
                str(ac.get("squawk") or "") or None,
                False,
                0,
                ADSB_CAT.get(str(ac.get("category") or ""), 0),
                typecode,
            ]
        )
    return out


def _feet_m(value) -> float | None:
    if value is None or value == "ground":
        return None
    try:
        return float(value) * FT_M
    except (TypeError, ValueError):
        return None


def _fetch(lat: float, lon: float, now_s: float) -> tuple[list, str | None, str]:
    skip_opensky = False
    with _lock:
        skip_opensky = now_s < float(_cache.get("backoff_until") or 0)
    if not skip_opensky:
        rows, err, retry_s = _fetch_opensky(lat, lon)
        if rows:
            with _lock:
                _cache["backoff_until"] = 0.0
            return rows, None, "opensky"
        if retry_s:
            with _lock:
                _cache["backoff_until"] = now_s + retry_s
        elif not err:
            return [], None, "opensky"
        adsb, adsb_err = _fetch_adsblol(lat, lon, now_s)
        if adsb:
            return adsb, None, "adsb.lol"
        return [], err or adsb_err, "opensky"
    adsb, adsb_err = _fetch_adsblol(lat, lon, now_s)
    if adsb:
        return adsb, None, "adsb.lol"
    return [], adsb_err, "adsb.lol"


def _fetch_opensky(lat: float, lon: float) -> tuple[list, str | None, float]:
    lamin, lomin, lamax, lomax = bbox_for_site(lat, lon)
    url = (
        f"{OPENSKY_URL}?lamin={lamin:.3f}&lomin={lomin:.3f}"
        f"&lamax={lamax:.3f}&lomax={lomax:.3f}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        retry = 120.0
        if exc.headers:
            raw = exc.headers.get("X-Rate-Limit-Retry-After-Seconds")
            if raw:
                try:
                    retry = max(30.0, float(raw))
                except ValueError:
                    pass
        return [], f"OpenSky HTTP {exc.code}", retry if exc.code == 429 else 0.0
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"OpenSky: {exc}", 0.0
    states = payload.get("states") if isinstance(payload, dict) else None
    if not states:
        return [], None, 0.0
    return states, None, 0.0


def _fetch_adsblol(lat: float, lon: float, now_s: float) -> tuple[list, str | None]:
    nm = max(40, int(round(FETCH_KM / 1.852)))
    url = ADSBD_URL.format(lat=f"{lat:.4f}", lon=f"{lon:.4f}", nm=nm)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return [], f"ADS-B HTTP {exc.code}"
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"ADS-B: {exc}"
    rows = parse_adsb_ac(payload, now_s) if isinstance(payload, dict) else []
    return rows, None if rows else "ADS-B: no aircraft in range"


def _project(states: list, obs_lat: float, obs_lon: float, obs_alt_m: float, now_s: float, **proj) -> list[dict]:
    if not states:
        return []
    icao, names, countries, lats, lons, alts = [], [], [], [], [], []
    tracks, speeds, vrates, squawks, cats, ages, types = [], [], [], [], [], [], []
    for row in states:
        if not isinstance(row, (list, tuple)) or len(row) < 8:
            continue
        if row[8]:
            continue
        lat, lon = row[6], row[5]
        alt = row[13] if len(row) > 13 and row[13] is not None else row[7]
        if lat is None or lon is None or alt is None:
            continue
        tpos = row[3] if row[3] is not None else row[4]
        age = max(0.0, now_s - float(tpos)) if tpos is not None else 0.0
        icao.append(str(row[0] or ""))
        names.append((row[1] or "").strip() or str(row[0] or "aircraft").upper())
        countries.append(row[2] or "")
        lats.append(float(lat))
        lons.append(float(lon))
        alts.append(float(alt))
        tracks.append(float(row[10]) if row[10] is not None else 0.0)
        speeds.append(float(row[9]) if row[9] is not None else 0.0)
        vrates.append(float(row[11]) if len(row) > 11 and row[11] is not None else 0.0)
        squawks.append(str(row[14]) if len(row) > 14 and row[14] else "")
        cat = int(row[17]) if len(row) > 17 and row[17] is not None else 0
        cats.append(cat)
        ages.append(age)
        typecode = str(row[18]).strip().upper() if len(row) > 18 and row[18] else ""
        types.append(typecode)
    if not lats:
        return []
    lat_a = np.array(lats)
    lon_a = np.array(lons)
    alt_a = np.array(alts)
    track_a = np.array(tracks)
    spd_a = np.array(speeds)
    vr_a = np.array(vrates)
    age_a = np.array(ages)
    lat1, lon1, alt1 = offset_llh(lat_a, lon_a, alt_a, track_a, spd_a, vr_a, age_a)
    lat2, lon2, alt2 = offset_llh(lat1, lon1, alt1, track_a, spd_a, vr_a, LOOKAHEAD_S)
    az, el, rng = look_azel_geodetic(lat1, lon1, alt1, obs_lat, obs_lon, obs_alt_m)
    cpa, tca, horiz = closest_approach(lat1, lon1, track_a, spd_a, obs_lat, obs_lon)
    map_az, _h = enu_az_range(lat1, lon1, obs_lat, obs_lon)
    map_az2, horiz2 = enu_az_range(lat2, lon2, obs_lat, obs_lon)
    inbound = (tca > 30.0) & (tca <= MAX_TCA_S) & (cpa <= CPA_KM)
    inside = (el >= 0) & (horiz <= MAP_RANGE_KM)
    pick = inside | inbound
    if not np.any(pick):
        return []
    kw = {**_proj_kw(proj), "max_range_km": MAP_RANGE_KM}
    xs, ys, vis = rangeaz_to_xy(horiz, map_az, proj["width"], proj["height"], **kw)
    nxs, nys, nvis = rangeaz_to_xy(horiz2, map_az2, proj["width"], proj["height"], **kw)
    oxs, oys, ovis = rangeaz_to_xy(
        np.full_like(map_az, MAP_RANGE_KM), map_az, proj["width"], proj["height"], **kw
    )
    out: list[dict] = []
    for i, show in enumerate(pick):
        if not show:
            continue
        coming = bool(inbound[i])
        on_disk = bool(inside[i] and vis[i])
        rim = coming and not on_disk
        if rim and not ovis[i]:
            continue
        if not rim and not vis[i]:
            continue
        if rim:
            pt = _norm(float(oxs[i]), float(oys[i]), proj["width"], proj["height"])
        else:
            pt = _norm(float(xs[i]), float(ys[i]), proj["width"], proj["height"])
        pt.update(
            {
                "id": icao[i],
                "name": names[i],
                "icao24": icao[i],
                "country": countries[i] or None,
                "alt": round(float(el[i]), 2),
                "az": round(float(az[i]), 1),
                "alt_m": round(float(alt1[i]), 0),
                "range_km": round(float(rng[i]), 1),
                "ground_km": round(float(horiz[i]), 1),
                "gs_kmh": round(float(spd_a[i]) * 3.6, 0) if spd_a[i] else None,
                "heading": round(float(track_a[i]), 0) if spd_a[i] or track_a[i] else None,
                "vrate_ms": round(float(vr_a[i]), 1) if vr_a[i] else 0.0,
                "squawk": squawks[i] or None,
                "category": CATEGORY.get(cats[i], "Aircraft"),
                "typecode": types[i] or None,
                "cpa_km": round(float(cpa[i]), 1),
                "tca_s": round(float(tca[i]), 0),
                "inbound": coming,
                "rim": rim,
            }
        )
        if on_disk and nvis[i]:
            pt["x2"] = round(float(nxs[i]) / (proj["width"] or 1), 5)
            pt["y2"] = round(float(nys[i]) / (proj["height"] or 1), 5)
        if coming and ovis[i]:
            origin = _norm(float(oxs[i]), float(oys[i]), proj["width"], proj["height"])
            pt["from_x"] = origin["x"]
            pt["from_y"] = origin["y"]
        path: list[dict] = []
        if on_disk:
            path = _heading_path(
                float(lat1[i]),
                float(lon1[i]),
                float(alt1[i]),
                float(track_a[i]),
                float(spd_a[i]),
                float(vr_a[i]),
                obs_lat,
                obs_lon,
                proj["width"],
                proj["height"],
                kw,
            )
        pt["path"] = path
        out.append(pt)
    out.sort(key=lambda row: (not row.get("inbound"), row.get("cpa_km", 99), -(row.get("alt") or 0)))
    return out


def _heading_path(
    lat: float,
    lon: float,
    alt_m: float,
    track: float,
    speed_ms: float,
    vrate: float,
    obs_lat: float,
    obs_lon: float,
    width: int,
    height: int,
    kw: dict,
) -> list[dict]:
    """Fixed-length ground track so every aircraft gets the same heading tick."""
    if speed_ms < 8:
        return []
    end_s = HEADING_KM * 1000.0 / speed_ms
    times = np.linspace(0.0, end_s, 6)
    n = times.size
    lat_t, lon_t, alt_t = offset_llh(
        np.full(n, lat),
        np.full(n, lon),
        np.full(n, alt_m),
        np.full(n, track),
        np.full(n, speed_ms),
        np.full(n, vrate),
        times,
    )
    map_az, horiz = enu_az_range(lat_t, lon_t, obs_lat, obs_lon)
    xs, ys, vis = rangeaz_to_xy(horiz, map_az, width, height, **kw)
    path = []
    for i, ok in enumerate(vis):
        if not ok or horiz[i] > MAP_RANGE_KM * 1.02:
            continue
        pt = _norm(float(xs[i]), float(ys[i]), width, height)
        pt["ground_km"] = round(float(horiz[i]), 1)
        path.append(pt)
    return path
