from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.imaging import atomic_write, encode_jpeg, encode_png, rgb_thumbnail
from zenith.paths import (
    DATA_DIR,
    PRODUCT_PLACES,
    jpeg_dir,
    png_dir,
    product_find_path,
    raw_dir,
    session_root,
    thumbs_dir,
)

PRODUCT_LABELS = {
    "keogram": "Keogram",
    "keogram_realtime": "Realtime keogram",
    "startrails": "Startrails",
    "timelapse": "Timelapse",
    "mini": "Mini timelapse",
}

PRODUCT_FILES = (
    "keogram.jpg",
    "keogram_realtime.jpg",
    "startrails.jpg",
    "timelapse.mp4",
    "mini.mp4",
)


@dataclass(frozen=True)
class SavedFrame:
    kind: str
    date: date
    stem: str
    thumb_path: Path
    raw_path: Path | None
    png_path: Path | None
    jpeg_path: Path | None


def should_save(kind: str, settings: ZenithSettings) -> bool:
    """Night (and twilight-in-night-folder) frames always save; daytime honors save_day."""
    if kind == "night":
        return True
    return bool(settings.camera.save_day)


def save_frame(
    *,
    rgb_linear: np.ndarray,
    rgb_preview: np.ndarray,
    kind: str,
    session_date: date,
    when_local: datetime,
    settings: ZenithSettings,
    raw_path: Path | None = None,
) -> SavedFrame:
    stem = when_local.strftime("%Y%m%d_%H%M%S")
    thumb_path = thumbs_dir(kind, session_date) / f"{stem}.jpg"
    atomic_write(thumb_path, rgb_thumbnail(rgb_preview, settings.products.thumb_width))

    png_path = None
    if settings.camera.save_png:
        png_path = png_dir(kind, session_date) / f"{stem}.png"
        atomic_write(png_path, encode_png(rgb_linear))

    jpeg_path = None
    if settings.camera.save_jpeg:
        jpeg_path = jpeg_dir(kind, session_date) / f"{stem}.jpg"
        atomic_write(jpeg_path, encode_jpeg(rgb_preview, settings.camera.jpeg_quality))

    if raw_path is None and settings.camera.save_raw:
        raw_path = raw_dir(kind, session_date) / f"{stem}.png"
        atomic_write(raw_path, encode_png(rgb_linear))

    return SavedFrame(
        kind=kind,
        date=session_date,
        stem=stem,
        thumb_path=thumb_path,
        raw_path=raw_path if raw_path and raw_path.is_file() else None,
        png_path=png_path,
        jpeg_path=jpeg_path,
    )


def _product_map(session_date: date) -> dict[str, str]:
    iso = session_date.isoformat()
    out: dict[str, str] = {}
    for name in PRODUCT_FILES:
        path = product_find_path(session_date, name)
        if path is None:
            continue
        key = name.rsplit(".", 1)[0]
        category = PRODUCT_PLACES.get(name, "products")
        out[key] = f"/api/processed/media/{category}/{iso}/{name}"
    return out


def list_processed(category: str | None = None) -> dict[str, Any]:
    """All finished products, newest date first. category = keograms|startrails|timelapses."""
    wanted = {"keograms", "startrails", "timelapses"}
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for cat in wanted:
        root = DATA_DIR / "processed" / cat
        if root.is_dir():
            for day_dir in root.iterdir():
                if not _is_session_dir(day_dir):
                    continue
                for path in day_dir.iterdir():
                    if not path.is_file() or path.stat().st_size <= 0:
                        continue
                    if path.name.endswith(".json") or path.suffix.lower() == ".json":
                        continue
                    if path.name == "startrails_stack.png":
                        continue
                    key = (day_dir.name, path.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(_processed_item(cat, day_dir.name, path))
    legacy = DATA_DIR / "products"
    if legacy.is_dir():
        for day_dir in legacy.iterdir():
            if not _is_session_dir(day_dir):
                continue
            for name in PRODUCT_FILES:
                cat = PRODUCT_PLACES.get(name)
                if cat not in wanted:
                    continue
                key = (day_dir.name, name)
                if key in seen:
                    continue
                path = day_dir / name
                if path.is_file() and path.stat().st_size > 0:
                    seen.add(key)
                    items.append(_processed_item(cat, day_dir.name, path))
    items.sort(key=lambda row: (row["date"], row["name"]), reverse=True)
    counts = {"keograms": 0, "startrails": 0, "timelapses": 0}
    for row in items:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    if category in {"keograms", "startrails", "timelapses"}:
        items = [row for row in items if row["category"] == category]
    return {"items": items, "counts": counts}


def _processed_item(category: str, iso: str, path: Path) -> dict[str, Any]:
    key = path.name.rsplit(".", 1)[0]
    suffix = path.suffix.lower()
    return {
        "date": iso,
        "category": category,
        "key": key,
        "name": path.name,
        "label": PRODUCT_LABELS.get(key, key.replace("_", " ")),
        "url": f"/api/processed/media/{category}/{iso}/{path.name}",
        "bytes": path.stat().st_size,
        "mtime": int(path.stat().st_mtime),
        "media": "video" if suffix == ".mp4" else "image",
        "archive_url": f"/archive/night/{iso}",
    }


def list_sessions(kind: str) -> list[dict]:
    folder = "nights" if kind == "night" else "days"
    root = DATA_DIR / folder
    if not root.is_dir():
        return []
    sessions: list[dict] = []
    for day_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        try:
            session_date = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        stems = _frame_stems(kind, session_date)
        latest = stems[-1] if stems else None
        sessions.append(
            {
                "date": day_dir.name,
                "kind": kind,
                "frames": len(stems),
                "latest": latest,
                "thumb_url": (
                    f"/api/archive/media/{folder}/{day_dir.name}/thumbs/{latest}.jpg" if latest else None
                ),
                "products": _product_map(session_date) if kind == "night" else {},
            }
        )
    return sessions


def list_frames(kind: str, session_date: date, *, offset: int = 0, limit: int = 200) -> dict:
    folder = "nights" if kind == "night" else "days"
    stems = _frame_stems(kind, session_date)
    total = len(stems)
    offset = max(0, offset)
    limit = max(1, min(limit, 500))
    newest_first = list(reversed(stems))
    page = newest_first[offset : offset + limit]
    iso = session_date.isoformat()
    frames = [_frame_urls(kind, folder, iso, stem) for stem in page]
    return {
        "date": iso,
        "kind": kind,
        "frames": frames,
        "total": total,
        "offset": offset,
        "limit": limit,
        "products": _product_map(session_date) if kind == "night" else {},
    }


def _frame_urls(kind: str, folder: str, iso: str, stem: str) -> dict:
    base = f"/api/archive/media/{folder}/{iso}"
    raw = _existing_raw(kind, date.fromisoformat(iso), stem)
    png = png_dir(kind, date.fromisoformat(iso)) / f"{stem}.png"
    jpeg = jpeg_dir(kind, date.fromisoformat(iso)) / f"{stem}.jpg"
    preview = f"{base}/png/{stem}.png" if png.is_file() else f"{base}/thumbs/{stem}.jpg"
    if jpeg.is_file() and not png.is_file():
        preview = f"{base}/jpeg/{stem}.jpg"
    return {
        "name": stem,
        "thumb_url": f"{base}/thumbs/{stem}.jpg",
        "preview_url": preview,
        "raw_url": f"{base}/raw/{raw.name}" if raw else None,
        "png_url": f"{base}/png/{stem}.png" if png.is_file() else None,
        "jpeg_url": f"{base}/jpeg/{stem}.jpg" if jpeg.is_file() else None,
    }


def _existing_raw(kind: str, session_date: date, stem: str) -> Path | None:
    folder = raw_dir(kind, session_date)
    for suffix in (".dng", ".png", ".fits"):
        path = folder / f"{stem}{suffix}"
        if path.is_file():
            return path
    return None


def delete_session(kind: str, session_date: date) -> dict[str, Any]:
    """Remove one night or day folder of capture frames. Processed outputs stay."""
    files = 0
    root = session_root(kind, session_date)
    if root.is_dir():
        files += _rmtree_inside_data(root)
    return {"ok": True, "kind": kind, "date": session_date.isoformat(), "files": files}


def delete_kind(kind: str) -> dict[str, Any]:
    """Remove every dated session of this kind. Processed outputs stay."""
    folder = "nights" if kind == "night" else "days"
    sessions = 0
    files = 0
    root = DATA_DIR / folder
    if root.is_dir():
        for child in list(root.iterdir()):
            if not _is_session_dir(child):
                continue
            sessions += 1
            files += _rmtree_inside_data(child)
    return {"ok": True, "kind": kind, "sessions": sessions, "files": files}


def delete_all() -> dict[str, Any]:
    """Remove all archived nights and days. Leaves processed outputs, config, darks, logs."""
    nights = delete_kind("night")
    days = delete_kind("day")
    return {
        "ok": True,
        "nights": nights["sessions"],
        "days": days["sessions"],
        "files": nights["files"] + days["files"],
    }


def _is_session_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        date.fromisoformat(path.name)
    except ValueError:
        return False
    return True


def _rmtree_inside_data(path: Path) -> int:
    resolved = path.resolve()
    root = DATA_DIR.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("refusing to delete outside the data directory") from exc
    if resolved == root:
        raise ValueError("refusing to delete the data directory")
    if not resolved.is_dir():
        return 0
    files = sum(1 for item in resolved.rglob("*") if item.is_file())
    shutil.rmtree(resolved)
    return files


def _frame_stems(kind: str, session_date: date) -> list[str]:
    stems: set[str] = set()
    for folder in (
        raw_dir(kind, session_date),
        png_dir(kind, session_date),
        thumbs_dir(kind, session_date),
        jpeg_dir(kind, session_date),
    ):
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if ".tmp" in path.name:
                continue
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".dng", ".fits"}:
                stems.add(path.stem)
    return sorted(stems)
