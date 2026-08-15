from __future__ import annotations

from fastapi import APIRouter, Request

from zenith.config.schema import ZenithSettings
from zenith.config.store import discard_cache, load_settings, merge_settings, persist_cache, replace_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    return load_settings().model_dump(mode="json")


@router.get("/schema")
def get_schema():
    return ZenithSettings.model_json_schema()


@router.put("")
def put_settings(payload: dict, request: Request):
    before = load_settings()
    settings = replace_settings(payload)
    if _pipeline_changed(before, settings):
        request.app.state.capture.request_reload()
    return settings.model_dump(mode="json")


@router.patch("/live")
def patch_live(payload: dict, request: Request):
    """Apply a partial settings patch in memory. Does not write yaml until /commit."""
    before = load_settings()
    settings = merge_settings(payload)
    if _pipeline_changed(before, settings):
        request.app.state.capture.request_reload()
    return settings.model_dump(mode="json")


@router.post("/commit")
def commit_settings():
    return persist_cache().model_dump(mode="json")


@router.post("/revert")
def revert_settings(request: Request):
    settings = discard_cache()
    request.app.state.capture.request_reload()
    return settings.model_dump(mode="json")


def _pipeline_changed(before: ZenithSettings, after: ZenithSettings) -> bool:
    return (
        before.camera.focus_mode != after.camera.focus_mode
        or before.camera.backend != after.camera.backend
        or before.camera.binning != after.camera.binning
        or before.camera.device != after.camera.device
        or before.picamera2.tuning_file != after.picamera2.tuning_file
    )
