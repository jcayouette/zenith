"""Live aircraft from OpenSky Network, projected onto the all-sky overlay."""

from __future__ import annotations

import json
import math
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.sky.layers import OVERLAY_BAKE_HORIZON, _norm, _proj_kw
from zenith.sky.project import altaz_to_xy
from zenith.sky.tle import USER_AGENT, WGS84_A, WGS84_E2

OPENSKY_URL = "https://opensky-network.org/api/states/all"
CACHE_S = 10.0
LOOKAHEAD_S = 8.0
HORIZON_KM = 420.0
CPA_KM = 50.0
MAX_TCA_S = 90 * 60.0
M_PER_DEG = 111_320.0

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

_cache: dict = {"key": None, "at": 0.0, "states": [], "error": None}
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
    return {
        "when": utc.isoformat(timespec="seconds"),
        "dt": LOOKAHEAD_S,
        "source": "opensky",
        "cpa_km": CPA_KM,
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
    deast = (lon_a - obs_lon) * M_PER_DEG * math.cos(math.radians(obs_lat)) / 1000.0
    dnorth = (lat_a - obs_lat) * M_PER_DEG / 1000.0
    ve = speed * np.sin(track) / 1000.0
    vn = speed * np.cos(track) / 1000.0
    horiz = np.hypot(deast, dnorth)
    v2 = ve * ve + vn * vn
    tca = np.where(v2 > 1e-12, -(deast * ve + dnorth * vn) / v2, 0.0)
    cpa = np.hypot(deast + ve * tca, dnorth + vn * tca)
    if np.ndim(lat) == 0 and np.ndim(lon) == 0:
        return float(cpa), float(tca), float(horiz)
    return cpa, tca, horiz


def bbox_for_site(lat: float, lon: float, radius_km: float = HORIZON_KM) -> tuple[float, float, float, float]:
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
        if _cache["key"] == key and now_s - _cache["at"] < CACHE_S and (_cache["states"] or _cache["error"]):
            return _cache["states"], _cache["error"]
    rows, err = _fetch(lat, lon)
    with _lock:
        if rows or not _cache["states"]:
            _cache["key"] = key
            _cache["at"] = now_s
            _cache["states"] = rows
            _cache["error"] = err
            return rows, err
        age = now_s - _cache["at"]
        stale = f"{err}; using {age:.0f}s-old cache" if err else _cache["error"]
        return _cache["states"], stale


def _fetch(lat: float, lon: float) -> tuple[list, str | None]:
    lamin, lomin, lamax, lomax = bbox_for_site(lat, lon)
    url = (
        f"{OPENSKY_URL}?lamin={lamin:.3f}&lomin={lomin:.3f}"
        f"&lamax={lamax:.3f}&lomax={lomax:.3f}"
    )
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    user = os.environ.get("OPENSKY_USERNAME", "").strip()
    password = os.environ.get("OPENSKY_PASSWORD", "").strip()
    req = urllib.request.Request(url, headers=headers)
    if user:
        import base64

        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return [], f"OpenSky HTTP {exc.code}"
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"OpenSky: {exc}"
    states = payload.get("states") if isinstance(payload, dict) else None
    if not states:
        return [], None
    return states, None


def _project(states: list, obs_lat: float, obs_lon: float, obs_alt_m: float, now_s: float, **proj) -> list[dict]:
    if not states:
        return []
    icao, names, countries, lats, lons, alts = [], [], [], [], [], []
    tracks, speeds, vrates, squawks, cats, ages = [], [], [], [], [], []
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
    az2, el2, _rng2 = look_azel_geodetic(lat2, lon2, alt2, obs_lat, obs_lon, obs_alt_m)
    cpa, tca, horiz = closest_approach(lat1, lon1, track_a, spd_a, obs_lat, obs_lon)
    nearby = horiz <= CPA_KM
    inbound = (tca > 30.0) & (tca <= MAX_TCA_S) & (cpa <= CPA_KM)
    pick = (el >= 0) & (nearby | inbound)
    if not np.any(pick):
        return []
    xs, ys, vis = altaz_to_xy(el, az, proj["width"], proj["height"], **_proj_kw(proj))
    nxs, nys, nvis = altaz_to_xy(el2, az2, proj["width"], proj["height"], **_proj_kw(proj))
    oxs, oys, ovis = altaz_to_xy(
        np.zeros_like(az), az, proj["width"], proj["height"], **_proj_kw(proj)
    )
    kw = _proj_kw(proj)
    out: list[dict] = []
    for i, show in enumerate(pick):
        if not show or not vis[i]:
            continue
        pt = _norm(float(xs[i]), float(ys[i]), proj["width"], proj["height"])
        coming = bool(inbound[i])
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
                "gs_kmh": round(float(spd_a[i]) * 3.6, 0) if spd_a[i] else None,
                "heading": round(float(track_a[i]), 0) if spd_a[i] or track_a[i] else None,
                "vrate_ms": round(float(vr_a[i]), 1) if vr_a[i] else 0.0,
                "squawk": squawks[i] or None,
                "category": CATEGORY.get(cats[i], "Aircraft"),
                "cpa_km": round(float(cpa[i]), 1),
                "tca_s": round(float(tca[i]), 0),
                "inbound": coming,
            }
        )
        if nvis[i]:
            pt["x2"] = round(float(nxs[i]) / (proj["width"] or 1), 5)
            pt["y2"] = round(float(nys[i]) / (proj["height"] or 1), 5)
        if coming and ovis[i]:
            origin = _norm(float(oxs[i]), float(oys[i]), proj["width"], proj["height"])
            pt["from_x"] = origin["x"]
            pt["from_y"] = origin["y"]
        path_end = min(max(float(tca[i]), 0.0) + 180.0, 45 * 60.0)
        pt["path"] = _predict_path(
            float(lat1[i]),
            float(lon1[i]),
            float(alt1[i]),
            float(track_a[i]),
            float(spd_a[i]),
            float(vr_a[i]),
            path_end,
            obs_lat,
            obs_lon,
            obs_alt_m,
            proj["width"],
            proj["height"],
            kw,
        )
        out.append(pt)
    out.sort(key=lambda row: (not row.get("inbound"), row.get("cpa_km", 99), -(row.get("alt") or 0)))
    return out


def _predict_path(
    lat: float,
    lon: float,
    alt_m: float,
    track: float,
    speed_ms: float,
    vrate: float,
    end_s: float,
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
    width: int,
    height: int,
    kw: dict,
) -> list[dict]:
    if end_s < 20 or speed_ms < 15:
        return []
    times = np.linspace(0.0, end_s, 12)
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
    paz, pel, _rng = look_azel_geodetic(lat_t, lon_t, alt_t, obs_lat, obs_lon, obs_alt_m)
    xs, ys, vis = altaz_to_xy(pel, paz, width, height, **kw)
    path = []
    for i, ok in enumerate(vis):
        if not ok or pel[i] < 0:
            continue
        path.append(_norm(float(xs[i]), float(ys[i]), width, height))
    return path
