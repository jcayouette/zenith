from __future__ import annotations

from fastapi import APIRouter, Request

from zenith import __version__
from zenith.paths import DATA_DIR

router = APIRouter(tags=["status"])


@router.get("/health")
def health():
    return {"ok": True, "name": "zenith", "version": __version__}


@router.get("/status")
def status(request: Request):
    hub = request.app.state.hub
    return {
        "version": __version__,
        "data_dir": str(DATA_DIR),
        "telemetry": hub.telemetry.as_dict(),
        "clients": len(hub._clients),
    }
