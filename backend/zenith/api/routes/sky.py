from __future__ import annotations

import io
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from PIL import Image

from zenith.config.store import load_settings
from zenith.sky.layers import build_sats, build_sky
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
