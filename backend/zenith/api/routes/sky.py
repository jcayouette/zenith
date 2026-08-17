from __future__ import annotations

import io
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, Response
from PIL import Image

from zenith.config.store import load_settings
from zenith.sky.acmeta import lookup_aircraft, lookup_route
from zenith.sky.aircraft import build_aircraft
from zenith.sky.groundmap import map_png, tile_png
from zenith.sky.layers import build_sats, build_sky
from zenith.sky.places import nearby_places
from zenith.sky.satcat import describe_sat, lookup_satcat
from zenith.sky.tle import refresh_tles

router = APIRouter(tags=["sky"])

_pass_cache: dict = {"key": None, "passes": [], "error": None}
_tle_started = False


def ensure_tle_thread() -> None:
    global _tle_started
    if _tle_started:
        return
    _tle_started = True
    threading.Thread(target=refresh_tles, name="zenith-tle", daemon=True).start()


@router.get("/sky")
def sky(
    request: Request,
    at: str | None = Query(default=None, description="UTC ISO timestamp; default now"),
):
    ensure_tle_thread()
    settings = load_settings()
    when = _parse_at(at)
    width, height = _frame_size(request)
    key = (
        when.replace(second=0, microsecond=0).isoformat(),
        round(settings.location.latitude, 4),
        round(settings.location.longitude, 4),
        settings.sky.min_sat_alt_deg,
    )
    include_passes = _pass_cache["key"] != key
    payload = build_sky(
        settings,
        width=width,
        height=height,
        when=when,
        include_passes=include_passes,
    )
    if include_passes:
        _pass_cache["key"] = key
        _pass_cache["passes"] = payload.get("passes") or []
        _pass_cache["error"] = payload.get("error")
    else:
        payload["passes"] = _pass_cache["passes"]
        if not payload.get("error"):
            payload["error"] = _pass_cache["error"]
    payload["needs_location"] = settings.location.latitude == 0 and settings.location.longitude == 0
    return payload


@router.get("/sky/sats")
def sky_sats(
    request: Request,
    horizon: float | None = Query(default=None),
):
    """Lightweight SGP4 positions for the live overlay (~1 Hz)."""
    ensure_tle_thread()
    settings = load_settings()
    width, height = _frame_size(request)
    return build_sats(settings, width=width, height=height, horizon=horizon)


@router.get("/sky/aircraft")
def sky_aircraft(request: Request):
    """OpenSky ADS-B positions above the site horizon (~10 s cache)."""
    settings = load_settings()
    if not settings.sky.aircraft:
        return {"aircraft": [], "dt": 8.0, "count": 0, "error": None}
    if settings.location.latitude == 0 and settings.location.longitude == 0:
        return {"aircraft": [], "dt": 8.0, "count": 0, "error": "Set latitude and longitude in Settings."}
    width, height = _frame_size(request)
    return build_aircraft(settings, width=width, height=height)


@router.get("/sky/map")
def sky_map(
    request: Request,
    w: int | None = Query(default=None),
    h: int | None = Query(default=None),
):
    """Flat ground map of the camera's aircraft coverage, same overlay as the radar layer."""
    settings = load_settings()
    if settings.location.latitude == 0 and settings.location.longitude == 0:
        return Response(status_code=400)
    width, height = _frame_size(request)
    if w and h and w > 8 and h > 8:
        width, height = w, h
    return Response(content=map_png(settings, width, height), media_type="image/png")


@router.get("/sky/maptile/{z}/{x}/{y}")
def sky_maptile(z: int, x: int, y: int):
    """OSM/CARTO tile proxy so the Sky map can stay sharp at the current view zoom."""
    if z < 0 or z > 20:
        return Response(status_code=400)
    n = 2**z
    if y < 0 or y >= n:
        return Response(status_code=400)
    png = tile_png(z, x % n, y)
    if not png:
        return Response(status_code=404)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/sky/places")
def sky_places():
    """Nearby towns and cities for map labels, cached around the site."""
    settings = load_settings()
    if settings.location.latitude == 0 and settings.location.longitude == 0:
        return {"places": []}
    return {"places": nearby_places(settings)}


@router.get("/sky/aircraft/{icao24}")
def sky_aircraft_meta(icao24: str, callsign: str | None = Query(default=None)):
    """Type, registration, operator, and filed route for one ICAO24 (adsbdb / hexdb)."""
    row = lookup_aircraft(icao24) or {"icao24": icao24, "error": "No aircraft type record"}
    route = lookup_route(callsign) if callsign else None
    if route:
        if not row.get("operator") and route.get("airline"):
            row["operator"] = route["airline"]
        row.update({k: v for k, v in route.items() if k != "callsign" and v is not None})
    return row


@router.get("/sky/satcat/{norad}")
def sky_satcat(
    norad: str,
    kind: str | None = Query(default=None),
    name: str | None = Query(default=None),
):
    """Launch site, date, catalog fields, and a short purpose line for one NORAD id."""
    row = lookup_satcat(norad)
    if not row:
        row = {"norad": norad, "error": "No SATCAT record"}
    row = {
        **row,
        "summary": describe_sat(
            norad=norad,
            name=name or row.get("name"),
            kind=kind,
            object_type=row.get("object_type"),
        ),
    }
    return row


def _parse_at(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    text = raw.replace("Z", "+00:00")
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


def _frame_size(request: Request) -> tuple[int, int]:
    jpeg = getattr(request.app.state, "hub", None)
    data = jpeg.jpeg if jpeg is not None else None
    if data:
        try:
            img = Image.open(io.BytesIO(data))
            return img.size
        except Exception:
            pass
    return 720, 720
