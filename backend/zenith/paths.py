from __future__ import annotations

import os
from datetime import date
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("ZENITH_DATA", REPO_ROOT / "data")).expanduser().resolve()
CONFIG_PATH = Path(os.environ.get("ZENITH_CONFIG", DATA_DIR / "config.yaml")).expanduser().resolve()
LATEST_JPEG = DATA_DIR / "latest.jpg"
LATEST_META = DATA_DIR / "latest.json"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


PROCESSED_KINDS = ("keograms", "startrails", "timelapses", "developed", "detections")

PRODUCT_PLACES = {
    "keogram.jpg": "keograms",
    "keogram_realtime.jpg": "keograms",
    "startrails.jpg": "startrails",
    "startrails.json": "startrails",
    "startrails_stack.png": "startrails",
    "meteors.mp4": "detections",
    "timelapse.mp4": "timelapses",
    "mini.mp4": "timelapses",
}


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "nights").mkdir(exist_ok=True)
    (DATA_DIR / "days").mkdir(exist_ok=True)
    (DATA_DIR / "products").mkdir(exist_ok=True)
    (DATA_DIR / "processed").mkdir(exist_ok=True)
    for kind in PROCESSED_KINDS:
        (DATA_DIR / "processed" / kind).mkdir(exist_ok=True)
    (DATA_DIR / "darks").mkdir(exist_ok=True)
    (DATA_DIR / "tle").mkdir(exist_ok=True)
    (DATA_DIR / "logs").mkdir(exist_ok=True)
    return DATA_DIR


def session_root(kind: str, session_date: date) -> Path:
    folder = "nights" if kind == "night" else "days"
    return DATA_DIR / folder / session_date.isoformat()


def jpeg_dir(kind: str, session_date: date) -> Path:
    return session_root(kind, session_date) / "jpeg"


def png_dir(kind: str, session_date: date) -> Path:
    return session_root(kind, session_date) / "png"


def raw_dir(kind: str, session_date: date) -> Path:
    return session_root(kind, session_date) / "raw"


def thumbs_dir(kind: str, session_date: date) -> Path:
    return session_root(kind, session_date) / "thumbs"


def products_dir(session_date: date) -> Path:
    return DATA_DIR / "products" / session_date.isoformat()


def processed_kind_dir(kind: str, session_date: date) -> Path:
    return DATA_DIR / "processed" / kind / session_date.isoformat()


def product_write_path(session_date: date, name: str) -> Path:
    """Canonical write path: processed/{type}/{date}/{name}."""
    kind = PRODUCT_PLACES.get(name)
    if kind is None:
        folder = products_dir(session_date)
        folder.mkdir(parents=True, exist_ok=True)
        return folder / name
    folder = processed_kind_dir(kind, session_date)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / name


def product_find_path(session_date: date, name: str) -> Path | None:
    """New processed layout first, then legacy products/{date}/{name}."""
    kind = PRODUCT_PLACES.get(name)
    candidates: list[Path] = []
    if kind:
        candidates.append(processed_kind_dir(kind, session_date) / name)
    candidates.append(products_dir(session_date) / name)
    for path in candidates:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def developed_dir(session_date: date) -> Path:
    folder = processed_kind_dir("developed", session_date)
    folder.mkdir(parents=True, exist_ok=True)
    return folder
