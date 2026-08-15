from __future__ import annotations

import io

import numpy as np
from PIL import Image


def orient(rgb: np.ndarray, flip_h: bool, flip_v: bool, rotation: int) -> np.ndarray:
    if flip_h:
        rgb = np.fliplr(rgb)
    if flip_v:
        rgb = np.flipud(rgb)
    if rotation == 90:
        rgb = np.rot90(rgb, 1)
    elif rotation == 180:
        rgb = np.rot90(rgb, 2)
    elif rotation == 270:
        rgb = np.rot90(rgb, 3)
    return np.ascontiguousarray(rgb)


def encode_jpeg(rgb: np.ndarray, quality: int, *, optimize: bool = True) -> bytes:
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=int(quality), optimize=optimize)
    return buf.getvalue()


def encode_png(rgb: np.ndarray) -> bytes:
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    return buf.getvalue()


def rgb_thumbnail(rgb: np.ndarray, max_side: int, quality: int = 75) -> bytes:
    return encode_jpeg(downscale(rgb, max_side), quality)


def apply_colour_gains(
    rgb: np.ndarray,
    red_gain: float = 1.0,
    green_gain: float = 1.0,
    blue_gain: float = 1.0,
) -> np.ndarray:
    """Manual R/G/B multiply. 1.0 / 1.0 / 1.0 returns the camera RGB unchanged."""
    r = max(0.0, float(red_gain))
    g = max(0.0, float(green_gain))
    b = max(0.0, float(blue_gain))
    if r == 1.0 and g == 1.0 and b == 1.0:
        return rgb
    out = np.asarray(rgb, dtype=np.float32).copy()
    out[..., 0] *= r
    out[..., 1] *= g
    out[..., 2] *= b
    return np.clip(out, 0, 255).astype(np.uint8)


def downscale(rgb: np.ndarray, max_side: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return rgb
    img = Image.fromarray(rgb)
    img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
    return np.array(img)


def jpeg_thumbnail(jpeg: bytes, max_side: int, quality: int = 75) -> bytes:
    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    w, h = img.size
    scale = max_side / max(w, h)
    if scale < 1:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=int(quality), optimize=True)
    return buf.getvalue()


def atomic_write(path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
