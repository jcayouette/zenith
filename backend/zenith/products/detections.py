"""Nightly streak detection index under processed/detections/{date}/."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from zenith.imaging import atomic_write, encode_jpeg
from zenith.paths import DATA_DIR, processed_kind_dir
from zenith.products.detect import Streak, annotate_crop
from zenith.products.timelapse import encode_image_list

INDEX_NAME = "index.json"
REEL_NAME = "meteors.mp4"


def detections_dir(session_date: date) -> Path:
    folder = processed_kind_dir("detections", session_date)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def index_path(session_date: date) -> Path:
    return detections_dir(session_date) / INDEX_NAME


def load_index(session_date: date) -> list[dict[str, Any]]:
    path = index_path(session_date)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("items") or []
    return list(data) if isinstance(data, list) else []


def save_index(session_date: date, items: list[dict[str, Any]]) -> None:
    payload = {"date": session_date.isoformat(), "count": len(items), "items": items}
    index_path(session_date).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_detection(
    session_date: date,
    rgb: np.ndarray,
    streak: Streak,
    *,
    stem: str,
    cls: str,
    match: str | None,
    distance: float | None,
    stars: int,
    adu: float,
) -> dict[str, Any]:
    folder = detections_dir(session_date)
    items = load_index(session_date)
    for item in items:
        if item.get("stem") == stem and abs(float(item.get("cx") or 0) - streak.cx) < 0.03 and abs(float(item.get("cy") or 0) - streak.cy) < 0.03:
            return item
    ident = uuid4().hex[:8]
    name = f"{stem}_{ident}"
    crop = annotate_crop(rgb, streak)
    jpeg_name = f"{name}.jpg"
    json_name = f"{name}.json"
    atomic_write(folder / jpeg_name, encode_jpeg(crop, 88))
    row: dict[str, Any] = {
        "id": name,
        "date": session_date.isoformat(),
        "stem": stem,
        "cls": cls,
        "match": match,
        "distance": None if distance is None else round(distance, 4),
        "cx": round(streak.cx, 4),
        "cy": round(streak.cy, 4),
        "length_px": round(streak.length_px, 1),
        "aspect": round(streak.aspect, 2),
        "brightness": round(streak.brightness, 1),
        "persist": streak.persist,
        "stars": stars,
        "adu": round(adu, 4),
        "image": jpeg_name,
        "archive_url": f"/archive/night/{session_date.isoformat()}",
    }
    (folder / json_name).write_text(json.dumps(row, indent=2), encoding="utf-8")
    items = [item for item in load_index(session_date) if item.get("id") != name]
    items.append(row)
    items.sort(key=lambda item: item.get("stem") or item.get("id") or "", reverse=True)
    save_index(session_date, items)
    return row


def list_detections(session_date: date | None = None, cls: str | None = None) -> dict[str, Any]:
    days: list[date] = []
    if session_date is not None:
        days = [session_date]
    else:
        root = DATA_DIR / "processed" / "detections"
        if root.is_dir():
            for child in sorted(root.iterdir(), reverse=True):
                try:
                    days.append(date.fromisoformat(child.name))
                except ValueError:
                    continue
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {"meteor": 0, "fireball": 0, "aircraft": 0, "satellite": 0, "unknown": 0}
    reels: list[dict[str, str]] = []
    for day in days:
        for row in load_index(day):
            kind = str(row.get("cls") or "unknown")
            counts[kind] = counts.get(kind, 0) + 1
            if cls and kind != cls:
                continue
            iso = day.isoformat()
            image = row.get("image") or f"{row.get('id')}.jpg"
            items.append(
                {
                    **row,
                    "date": iso,
                    "url": f"/api/processed/media/detections/{iso}/{image}",
                    "archive_url": row.get("archive_url") or f"/archive/night/{iso}",
                }
            )
        reel = detections_dir(day) / REEL_NAME
        if reel.is_file() and reel.stat().st_size > 0:
            iso = day.isoformat()
            reels.append(
                {
                    "date": iso,
                    "url": f"/api/processed/media/detections/{iso}/{REEL_NAME}",
                    "label": "Meteor highlight reel",
                }
            )
    return {
        "items": items,
        "counts": counts,
        "reels": reels,
        "total": sum(counts.values()),
    }


def write_highlight_reel(session_date: date) -> Path | None:
    items = [row for row in load_index(session_date) if row.get("cls") in {"meteor", "fireball"}]
    items.sort(key=lambda row: row.get("stem") or "")
    folder = detections_dir(session_date)
    frames = [folder / str(row["image"]) for row in items if row.get("image")]
    dest = folder / REEL_NAME
    if not encode_image_list(frames, dest, fps=3):
        return None
    return dest
