from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from zenith.config.schema import OverlaySettings
from zenith.sky.project import altaz_to_xy


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
        for label, az in (("N", 0.0), ("E", 90.0), ("S", 180.0), ("W", 270.0)):
            px, py, vis = altaz_to_xy(
                0.0,
                az,
                w,
                h,
                north_angle_deg=cardinal_offset_deg,
            )
            if vis:
                draw.text((px - 6, py - 8), label, fill=(251, 191, 36), font=small)

    return np.array(img)
