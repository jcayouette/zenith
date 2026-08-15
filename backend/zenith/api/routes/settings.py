from __future__ import annotations

from fastapi import APIRouter, Request

from zenith.config.schema import ZenithSettings
from zenith.config.store import load_settings, replace_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings():
    return load_settings().model_dump(mode="json")


@router.get("/schema")
def get_schema():
    return ZenithSettings.model_json_schema()


@router.put("")
def put_settings(payload: dict, request: Request):
    settings = replace_settings(payload)
    request.app.state.capture.request_reload()
    return settings.model_dump(mode="json")
