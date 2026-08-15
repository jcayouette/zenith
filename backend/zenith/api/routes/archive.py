from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from zenith.archive.store import delete_all, delete_kind, delete_session, list_frames, list_sessions
from zenith.config.store import load_settings
from zenith.paths import DATA_DIR, product_find_path
from zenith.products.encode_jobs import tracker

router = APIRouter(prefix="/archive", tags=["archive"])

_KINDS = {"night": "nights", "day": "days", "nights": "nights", "days": "days"}
_FOLDERS = {"jpeg", "thumbs", "raw", "png"}
_SAFE_NAME = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")


@router.get("")
def archive_index():
    return {"nights": list_sessions("night"), "days": list_sessions("day")}


@router.get("/media/{kind}/{session_date}/{name}")
def archive_product(kind: str, session_date: str, name: str):
    if kind != "products":
        raise HTTPException(404, "Not found")
    day = _date(session_date)
    path = product_find_path(day, name)
    if path is None:
        raise HTTPException(404, "File not found")
    return FileResponse(path, media_type=_media_type(path))


@router.get("/media/{kind}/{session_date}/{folder}/{name}")
def archive_frame(kind: str, session_date: str, folder: str, name: str):
    root_name = _KINDS.get(kind)
    if root_name is None or folder not in _FOLDERS:
        raise HTTPException(404, "Not found")
    path = _safe_file(DATA_DIR / root_name / _date(session_date).isoformat() / folder, name)
    return FileResponse(path, media_type=_media_type(path))


@router.delete("/all")
def archive_delete_all():
    try:
        return delete_all()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/nights")
def archive_delete_nights():
    try:
        return delete_kind("night")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/days")
def archive_delete_days():
    try:
        return delete_kind("day")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{kind}/{session_date}/timelapse")
async def archive_encode_timelapse(kind: str, session_date: str, request: Request):
    """Start DNG develop + H.264 encode in the background (can take minutes)."""
    import asyncio

    resolved = _kind(kind)
    day = _date(session_date)
    settings = load_settings()
    products = request.app.state.capture.products
    jobs: set[str] = request.app.state.__dict__.setdefault("tl_jobs", set())
    key = f"{resolved}:{day.isoformat()}"
    if key in jobs or tracker.active(key):
        return {"ok": True, "status": "already_running", "date": day.isoformat(), "kind": resolved}

    async def _job() -> None:
        jobs.add(key)
        try:
            await asyncio.to_thread(products.encode, day, settings, True, True, resolved)
        finally:
            jobs.discard(key)

    asyncio.create_task(_job())
    return {"ok": True, "status": "started", "date": day.isoformat(), "kind": resolved}


@router.get("/{kind}/{session_date}/timelapse")
def archive_timelapse_status(kind: str, session_date: str, request: Request):
    resolved = _kind(kind)
    day = _date(session_date)
    key = f"{resolved}:{day.isoformat()}"
    jobs: set[str] = request.app.state.__dict__.setdefault("tl_jobs", set())
    snap = tracker.snapshot(key)
    return {
        "encoding": tracker.active(key) or key in jobs,
        "encode": snap,
        "date": day.isoformat(),
        "kind": resolved,
    }


@router.delete("/{kind}/{session_date}")
def archive_delete_session(kind: str, session_date: str):
    try:
        return delete_session(_kind(kind), _date(session_date))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{kind}/{session_date}")
def archive_session(kind: str, session_date: str, request: Request, offset: int = 0, limit: int = 200):
    resolved = _kind(kind)
    day = _date(session_date)
    payload = list_frames(resolved, day, offset=offset, limit=limit)
    jobs: set[str] = request.app.state.__dict__.setdefault("tl_jobs", set())
    key = f"{resolved}:{day.isoformat()}"
    payload["encoding"] = tracker.active(key) or key in jobs
    payload["encode"] = tracker.snapshot(key)
    return payload


def _kind(kind: str) -> str:
    if kind in ("night", "nights"):
        return "night"
    if kind in ("day", "days"):
        return "day"
    raise HTTPException(404, "Unknown archive kind")


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, "Date must be YYYY-MM-DD") from exc


def _safe_file(folder: Path, name: str) -> Path:
    if not name or any(ch not in _SAFE_NAME for ch in name) or ".." in name:
        raise HTTPException(400, "Invalid filename")
    folder = folder.resolve()
    path = (folder / name).resolve()
    try:
        path.relative_to(folder)
    except ValueError as exc:
        raise HTTPException(400, "Invalid path") from exc
    if not path.is_file():
        raise HTTPException(404, "File not found")
    return path


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".dng":
        return "image/x-adobe-dng"
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"
