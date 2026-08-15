from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("ZENITH_DATA", REPO_ROOT / "data")).expanduser().resolve()
CONFIG_PATH = Path(os.environ.get("ZENITH_CONFIG", DATA_DIR / "config.yaml")).expanduser().resolve()
LATEST_JPEG = DATA_DIR / "latest.jpg"
LATEST_META = DATA_DIR / "latest.json"
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "nights").mkdir(exist_ok=True)
    (DATA_DIR / "days").mkdir(exist_ok=True)
    (DATA_DIR / "products").mkdir(exist_ok=True)
    (DATA_DIR / "darks").mkdir(exist_ok=True)
    (DATA_DIR / "logs").mkdir(exist_ok=True)
    return DATA_DIR
