from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from zenith.camera.base import CameraBackend, Frame
from zenith.config.schema import ZenithSettings
from zenith.sky.layers import catalog_stars_xy
from zenith.sky.project import inverse_orient_xy


class SimulatorBackend(CameraBackend):
    """Catalog fisheye sky at the configured site and time."""

    name = "simulator"

    def __init__(self) -> None:
        self._exposure_us = 1_000_000
        self._gain = 1.0
        self._night = True
        self._focus = False
        self._size = 720
        self._settings: ZenithSettings | None = None

    def open(self, settings: ZenithSettings) -> None:
        self._settings = settings

    def close(self) -> None:
        return None

    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None:
        self._settings = settings
        self._exposure_us = exposure_us
        self._gain = gain
        self._night = night
        self._focus = settings.camera.focus_mode

    def capture(self, raw_path=None) -> Frame:
        if not getattr(self, "_focus", False):
            import time

            time.sleep(min(0.08, self._exposure_us / 1_000_000 * 0.02))
        rgb = self._render()
        return Frame(rgb=rgb, exposure_us=self._exposure_us, gain=self._gain, sensor="simulator")

    def _render(self) -> np.ndarray:
        h = w = self._size
        yy, xx = np.mgrid[0:h, 0:w]
        cx = cy = (h - 1) / 2
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (h / 2)
        mask = r <= 1.0
        settings = self._settings
        catalog = bool(settings and settings.sky.simulator_catalog)
        night = self._night or catalog

        if night:
            sky = np.zeros((h, w, 3), dtype=np.float32)
            sky[..., 2] = 8 + (1 - r) * 18
            sky[..., 1] = 4 + (1 - r) * 8
            glow = np.clip(1.15 - r, 0, 1) ** 2 * min(self._gain, 8) * 4
            sky[..., 0] += glow * 0.4
            sky[..., 2] += glow
        else:
            sky = np.zeros((h, w, 3), dtype=np.float32)
            sky[..., 0] = 110 + (1 - r) * 80
            sky[..., 1] = 150 + (1 - r) * 50
            sky[..., 2] = 210

        img = sky
        if night and settings is not None:
            xs, ys, mags = catalog_stars_xy(settings, width=w, height=h, when=datetime.now(timezone.utc))
            xs, ys = inverse_orient_xy(
                xs,
                ys,
                w,
                h,
                settings.camera.flip_h,
                settings.camera.flip_v,
                int(settings.camera.rotation_deg),
            )
            brightness = np.clip(self._exposure_us / 8_000_000 * self._gain / 4, 0.25, 2.8)
            for x, y, mag in zip(xs, ys, mags):
                xi, yi = int(round(float(x))), int(round(float(y)))
                if not (1 <= xi < w - 1 and 1 <= yi < h - 1):
                    continue
                if r[yi, xi] >= 0.98:
                    continue
                val = (40 + (5.2 - float(mag)) / 6.6 * 215) * brightness
                img[yi, xi] = np.clip(img[yi, xi] + val, 0, 255)
                img[yi - 1, xi] = np.clip(img[yi - 1, xi] + val * 0.32, 0, 255)
                img[yi + 1, xi] = np.clip(img[yi + 1, xi] + val * 0.32, 0, 255)
                img[yi, xi - 1] = np.clip(img[yi, xi - 1] + val * 0.32, 0, 255)
                img[yi, xi + 1] = np.clip(img[yi, xi + 1] + val * 0.32, 0, 255)

        img[~mask] = 6
        return np.clip(img, 0, 255).astype(np.uint8)
