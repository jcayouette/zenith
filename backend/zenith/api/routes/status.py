from __future__ import annotations

from fastapi import APIRouter, Request

from zenith import __version__
from zenith.camera.imx477 import caps as imx477_caps
from zenith.config.store import load_settings
from zenith.paths import DATA_DIR
from zenith.sky.clock import clock_snapshot
from zenith.system.health import collect

router = APIRouter(tags=["status"])


@router.get("/health")
def health():
    return {"ok": True, "name": "zenith", "version": __version__}


@router.get("/camera")
def camera_state(request: Request):
    return request.app.state.capture.camera_state()


@router.get("/camera/caps")
def camera_caps():
    return imx477_caps()


@router.post("/camera/disconnect")
def camera_disconnect(request: Request):
    cap = request.app.state.capture
    cap.disconnect()
    return cap.camera_state()


@router.post("/camera/connect")
def camera_connect(request: Request):
    cap = request.app.state.capture
    cap.connect()
    return cap.camera_state()


@router.get("/clock")
def clock():
    loc = load_settings().location
    return clock_snapshot(
        lat=loc.latitude,
        lon=loc.longitude,
        tz_name=loc.resolved_timezone(),
        night_threshold=loc.night_sun_altitude_deg,
        timezone_auto=loc.timezone_auto,
    )


@router.get("/status")
def status(request: Request):
    hub = request.app.state.hub
    settings = load_settings()
    loc = settings.location
    tz = loc.resolved_timezone()
    return {
        "version": __version__,
        "data_dir": str(DATA_DIR),
        "telemetry": hub.telemetry.as_dict(),
        "clients": len(hub._clients),
        "clock": clock_snapshot(
            lat=loc.latitude,
            lon=loc.longitude,
            tz_name=tz,
            night_threshold=loc.night_sun_altitude_deg,
            timezone_auto=loc.timezone_auto,
        ),
    }


@router.get("/system")
def system_health(request: Request):
    hub = request.app.state.hub
    payload = collect()
    payload["version"] = __version__
    payload["data_dir"] = str(DATA_DIR)
    payload["camera"] = request.app.state.capture.camera_state()
    payload["clients"] = len(hub._clients)
    tel = hub.telemetry.as_dict()
    payload["capture"] = {
        "capturing": tel.get("capturing"),
        "backend": tel.get("backend"),
        "session": tel.get("session"),
        "error": tel.get("error"),
    }
    return payload
