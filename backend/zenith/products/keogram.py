from __future__ import annotations

import numpy as np
from PIL import Image

from zenith.imaging import atomic_write, encode_jpeg


def meridian_column(rgb: np.ndarray, angle_deg: float, slice_px: int) -> np.ndarray:
    """Average a vertical strip through the frame centre after rotating the meridian upright."""
    img = Image.fromarray(rgb, mode="RGB")
    if abs(angle_deg) > 0.05:
        img = img.rotate(float(angle_deg), resample=Image.Resampling.BILINEAR, expand=False)
    arr = np.asarray(img)
    height, width = arr.shape[:2]
    half = max(0, slice_px // 2)
    cx = width // 2
    left = max(0, cx - half)
    right = min(width, cx + half + 1)
    col = arr[:, left:right].mean(axis=1)
    return np.clip(col, 0, 255).astype(np.uint8)


class Keogram:
    def __init__(self) -> None:
        self.image: np.ndarray | None = None

    def reset(self) -> None:
        self.image = None

    def load(self, path) -> None:
        if path.is_file():
            self.image = np.array(Image.open(path).convert("RGB"))
        else:
            self.image = None

    def append(self, rgb: np.ndarray, angle_deg: float, slice_px: int) -> None:
        col = meridian_column(rgb, angle_deg, slice_px)
        if self.image is None:
            self.image = col[:, None, :]
            return
        if col.shape[0] != self.image.shape[0]:
            col_img = Image.fromarray(col[:, None, :])
            col_img = col_img.resize((1, self.image.shape[0]), Image.Resampling.BILINEAR)
            col = np.array(col_img)[:, 0]
        if self.image.shape[1] >= 8000:
            return
        self.image = np.concatenate([self.image, col[:, None, :]], axis=1)

    def save(self, path) -> None:
        if self.image is None:
            return
        atomic_write(path, encode_jpeg(self.image, 90))
