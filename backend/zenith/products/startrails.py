from __future__ import annotations

import json

import numpy as np
from PIL import Image


def count_stars(rgb: np.ndarray, threshold: float = 40.0) -> int:
    """Count isolated bright peaks on a downsampled luma plane (no OpenCV)."""
    gray = rgb.mean(axis=2).astype(np.float32)
    gray = gray[::4, ::4]
    if gray.shape[0] < 4 or gray.shape[1] < 4:
        return 0
    mu = float(gray.mean())
    sd = float(gray.std())
    floor = max(threshold, mu + 2.8 * max(sd, 1.0))
    center = gray[1:-1, 1:-1]
    neigh = np.maximum.reduce(
        [
            gray[:-2, :-2],
            gray[:-2, 1:-1],
            gray[:-2, 2:],
            gray[1:-1, :-2],
            gray[1:-1, 2:],
            gray[2:, :-2],
            gray[2:, 1:-1],
            gray[2:, 2:],
        ]
    )
    peaks = (center > neigh) & (center >= floor)
    return int(peaks.sum())


class Startrails:
    def __init__(self) -> None:
        self.stack: np.ndarray | None = None
        self.frames_used = 0
        self.frames_seen = 0
        self.star_sum = 0
        self.adu_sum = 0.0

    def reset(self) -> None:
        self.stack = None
        self.frames_used = 0
        self.frames_seen = 0
        self.star_sum = 0
        self.adu_sum = 0.0

    def load(self, path) -> None:
        if path.is_file():
            self.stack = np.array(Image.open(path).convert("RGB"))
        else:
            self.stack = None

    def maybe_add(
        self,
        rgb: np.ndarray,
        adu: float,
        stars: int,
        *,
        min_stars: int,
        adu_min: float,
        adu_max: float,
    ) -> bool:
        self.frames_seen += 1
        if stars < min_stars or adu < adu_min or adu > adu_max:
            return False
        arr = np.ascontiguousarray(rgb, dtype=np.uint8)
        if self.stack is None:
            self.stack = arr.copy()
        elif self.stack.shape != arr.shape:
            return False
        else:
            np.maximum(self.stack, arr, out=self.stack)
        self.frames_used += 1
        self.star_sum += stars
        self.adu_sum += adu
        return True

    def save(self, image_path, meta_path) -> None:
        meta = {
            "frames_used": self.frames_used,
            "frames_seen": self.frames_seen,
            "mean_stars": round(self.star_sum / self.frames_used, 2) if self.frames_used else 0,
            "mean_adu": round(self.adu_sum / self.frames_used, 4) if self.frames_used else 0,
        }
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2))
