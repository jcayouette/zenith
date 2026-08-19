from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from zenith.archive.store import list_processed
from zenith.paths import PROCESSED_KINDS, processed_kind_dir, product_find_path

router = APIRouter(prefix="/processed", tags=["processed"])

_SAFE_NAME = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


@router.get("")
def processed_index(category: str | None = None):
    if category is not None and category not in {"keograms", "startrails", "timelapses"}:
        raise HTTPException(400, "category must be keograms, startrails, or timelapses")
    return list_processed(category)


@router.post("/startrails/{session_date}")
async def rebuild_startrails(session_date: str, request: Request):
    """Rebuild startrails.jpg from archived night PNG/JPEG into processed/startrails/."""
    import asyncio

    from zenith.config.store import load_settings

    day = _date(session_date)
    settings = load_settings()
    products = request.app.state.capture.products
    return await asyncio.to_thread(products.rebuild_startrails, day, settings)


@router.get("/media/{category}/{session_date}/{name}")
def processed_media(category: str, session_date: str, name: str):
    if category not in PROCESSED_KINDS:
        raise HTTPException(404, "Unknown processed category")
    if not name or any(ch not in _SAFE_NAME for ch in name) or ".." in name:
        raise HTTPException(400, "Invalid filename")
    day = _date(session_date)
    path = product_find_path(day, name)
    if path is None:
        candidate = processed_kind_dir(category, day) / name
        if candidate.is_file():
            path = candidate
    if path is None or not path.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=_media_type(path))


def _date(value: str):
    try:
        return date_cls.fromisoformat(value)
    except ValueError as extra:
        raise HTTPException(400, "Date must be YYYY-MM-DD") from extra


def _media_type(path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"
