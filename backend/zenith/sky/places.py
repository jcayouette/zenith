"""Nearby settlement labels for the Sky OpenStreetMap overlay."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from zenith.config.schema import ZenithSettings
from zenith.paths import DATA_DIR
from zenith.sky.aircraft import MAP_RANGE_KM, M_PER_DEG
from zenith.sky.tle import USER_AGENT

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
CACHE_S = 7 * 24 * 3600
MAX_PLACES = 36


def nearby_places(settings: ZenithSettings) -> list[dict]:
    loc = settings.location
    lat, lon = loc.latitude, loc.longitude
    cache = DATA_DIR / "places"
    cache.mkdir(parents=True, exist_ok=True)
    key = f"{lat:.4f}_{lon:.4f}_{int(MAP_RANGE_KM)}"
    path = cache / f"{key}.json"
    rows: list[dict] = []
    if path.is_file() and path.stat().st_size > 8 and time.time() - path.stat().st_mtime < CACHE_S:
        try:
            rows = json.loads(path.read_text())
        except json.JSONDecodeError:
            rows = []
    if not rows:
        rows = _overpass(lat, lon) or []
        if rows:
            path.write_text(json.dumps(rows))
    city = (loc.city or "").strip()
    if city and not any(p["name"].casefold() == city.casefold() for p in rows):
        found = _nominatim_city(city, lat, lon)
        if found:
            rows.append(found)
    rows = _dedupe(rows)
    return rows[:MAX_PLACES]


def _overpass(lat: float, lon: float) -> list[dict]:
    radius_m = int(MAP_RANGE_KM * 1000)
    query = (
        f"[out:json][timeout:20];"
        f'(node["place"~"city|town|village"](around:{radius_m},{lat:.5f},{lon:.5f}););'
        f"out tags center;"
    )
    req = urllib.request.Request(
        OVERPASS_URL,
        data=query.encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "text/plain"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=22) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError):
        return []
    out: list[dict] = []
    for el in payload.get("elements") or []:
        if not isinstance(el, dict):
            continue
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        kind = (tags.get("place") or "").strip()
        plat = el.get("lat")
        plon = el.get("lon")
        if plat is None and isinstance(el.get("center"), dict):
            plat = el["center"].get("lat")
            plon = el["center"].get("lon")
        if not name or plat is None or plon is None:
            continue
        dist = _dist_km(lat, lon, float(plat), float(plon))
        if kind == "village" and dist > 22:
            continue
        out.append(
            {
                "name": name,
                "lat": round(float(plat), 5),
                "lon": round(float(plon), 5),
                "kind": kind or "town",
                "km": round(dist, 1),
            }
        )
    return out


def _nominatim_city(city: str, lat: float, lon: float) -> dict | None:
    qs = urllib.parse.urlencode(
        {
            "format": "json",
            "q": city,
            "limit": 1,
            "countrycodes": "de",
            "viewbox": f"{lon - 1.2},{lat + 0.8},{lon + 1.2},{lat - 0.8}",
            "bounded": 1,
        }
    )
    req = urllib.request.Request(
        f"{NOMINATIM_URL}?{qs}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            rows = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    if not isinstance(rows, list) or not rows:
        return None
    hit = rows[0]
    try:
        plat, plon = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "name": (hit.get("name") or city).strip() or city,
        "lat": round(plat, 5),
        "lon": round(plon, 5),
        "kind": "city",
        "km": round(_dist_km(lat, lon, plat, plon), 1),
    }


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    deast = (lon2 - lon1) * M_PER_DEG * math.cos(math.radians(lat1)) / 1000.0
    dnorth = (lat2 - lat1) * M_PER_DEG / 1000.0
    return math.hypot(deast, dnorth)


def _dedupe(rows: list[dict]) -> list[dict]:
    rank = {"city": 0, "town": 1, "village": 2}
    best: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("name") or "").casefold()
        if not key:
            continue
        prev = best.get(key)
        if prev is None or rank.get(row.get("kind"), 9) < rank.get(prev.get("kind"), 9):
            best[key] = row
    ordered = sorted(
        best.values(),
        key=lambda r: (rank.get(r.get("kind"), 9), float(r.get("km") or 99)),
    )
    return ordered
