from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Request

from zenith.products.detections import list_detections

router = APIRouter(prefix="/detections", tags=["detections"])


@router.get("")
def detections_index(date: str | None = None, cls: str | None = None):
    day = _date(date) if date else None
    if cls and cls not in {"meteor", "fireball", "aircraft", "satellite", "unknown"}:
        raise HTTPException(400, "cls must be meteor, fireball, aircraft, satellite, or unknown")
    return list_detections(day, cls)


@router.post("/scan/{session_date}")
async def detections_scan(session_date: str, request: Request):
    """Replay a night's stills through the streak finder."""
    import asyncio

    from zenith.config.store import load_settings

    day = _date(session_date)
    settings = load_settings()
    products = request.app.state.capture.products
    return await asyncio.to_thread(products.scan_detections, day, settings)


def _date(value: str):
    try:
        return date_cls.fromisoformat(value)
    except ValueError as extra:
        raise HTTPException(400, "Date must be YYYY-MM-DD") from extra
