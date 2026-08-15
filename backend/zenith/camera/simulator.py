from __future__ import annotations

import math
import time

import numpy as np

from zenith.camera.base import CameraBackend, Frame
from zenith.config.schema import ZenithSettings


class SimulatorBackend(CameraBackend):
    """Synthetic fisheye sky so the UI works off the Pi."""

    name = "simulator"

    def __init__(self) -> None:
        self._exposure_us = 1_000_000
        self._gain = 1.0
        self._night = True
        self._focus = False
        self._size = 720
        rng = np.random.default_rng(42)
        n = 420
        self._stars_r = np.sqrt(rng.random(n)) * 0.92
        self._stars_theta = rng.random(n) * 2 * math.pi
        self._stars_mag = rng.uniform(0.35, 1.0, n)

    def open(self, settings: ZenithSettings) -> None:
        return None

    def close(self) -> None:
        return None

    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None:
        self._exposure_us = exposure_us
        self._gain = gain
        self._night = night
        self._focus = settings.camera.focus_mode

    def capture(self, raw_path=None) -> Frame:
        if not getattr(self, "_focus", False):
            time.sleep(min(0.08, self._exposure_us / 1_000_000 * 0.02))
        rgb = self._render()
        return Frame(rgb=rgb, exposure_us=self._exposure_us, gain=self._gain, sensor="simulator")

    def _render(self) -> np.ndarray:
        h = w = self._size
        yy, xx = np.mgrid[0:h, 0:w]
        cx = cy = (h - 1) / 2
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (h / 2)
        mask = r <= 1.0

        if self._night:
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
        if self._night:
            sidereal = time.time() / 86164.0 * 2 * math.pi
            brightness = np.clip(self._exposure_us / 8_000_000 * self._gain / 4, 0.2, 2.5)
            xs = cx + self._stars_r * math.cos(self._stars_theta + sidereal) * (h / 2)
            ys = cy + self._stars_r * math.sin(self._stars_theta + sidereal) * (h / 2)
            for x, y, mag in zip(xs, ys, self._stars_mag):
                xi, yi = int(x), int(y)
                if 1 <= xi < w - 1 and 1 <= yi < h - 1 and r[yi, xi] < 0.96:
                    val = 40 + mag * 210 * brightness
                    img[yi, xi] = np.clip(img[yi, xi] + val, 0, 255)
                    img[yi - 1, xi] = np.clip(img[yi - 1, xi] + val * 0.35, 0, 255)
                    img[yi + 1, xi] = np.clip(img[yi + 1, xi] + val * 0.35, 0, 255)
                    img[yi, xi - 1] = np.clip(img[yi, xi - 1] + val * 0.35, 0, 255)
                    img[yi, xi + 1] = np.clip(img[yi, xi + 1] + val * 0.35, 0, 255)

            # Fake ISS crossing
            t = (time.time() % 42) / 42
            iss_x = int(cx + math.cos(t * math.pi) * h * 0.38)
            iss_y = int(cy + (t - 0.5) * h * 0.7)
            if 2 <= iss_x < w - 2 and 2 <= iss_y < h - 2 and r[iss_y, iss_x] < 0.95:
                img[iss_y - 1 : iss_y + 2, iss_x - 1 : iss_x + 2] = 255

        img[~mask] = 6
        return np.clip(img, 0, 255).astype(np.uint8)
