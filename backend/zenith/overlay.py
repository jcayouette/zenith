from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from zenith.config.schema import OverlaySettings


def apply_overlay(
    rgb: np.ndarray,
    *,
    overlay: OverlaySettings,
    mode: str,
    sun_alt: float,
    exposure_us: float,
    gain: float,
    mean: float,
    backend: str,
    cardinal_offset_deg: float = 0.0,
) -> np.ndarray:
    if not overlay.enabled:
        return rgb
    img = Image.fromarray(rgb, mode="RGB")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 16)
        small = ImageFont.truetype("DejaVuSans.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
        small = font

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [f"ZENITH  {ts}", f"mode {mode}   sun {sun_alt:+.1f}°"]
    if overlay.show_exposure:
        if exposure_us >= 1_000_000:
            exp = f"{exposure_us / 1_000_000:.2f}s"
        else:
            exp = f"{exposure_us / 1000:.0f}ms"
        lines.append(f"exp {exp}   gain {gain:.2f}" if overlay.show_gain else f"exp {exp}")
    lines.append(f"mean {mean:.3f}   {backend}")

    x, y = 16, 14
    for line in lines:
        draw.text((x + 1, y + 1), line, fill=(0, 0, 0), font=font)
        draw.text((x, y), line, fill=(220, 235, 255), font=font)
        y += 20

    if overlay.cardinals:
        w, h = img.size
        cx, cy = w / 2, h / 2
        radius = min(w, h) * 0.46
        for label, ang in (("N", -90), ("E", 0), ("S", 90), ("W", 180)):
            rad = np.deg2rad(ang + cardinal_offset_deg)
            px = cx + np.cos(rad) * radius
            py = cy + np.sin(rad) * radius
            draw.text((px - 6, py - 8), label, fill=(251, 191, 36), font=small)

    return np.array(img)
