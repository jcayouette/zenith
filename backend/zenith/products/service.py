from __future__ import annotations

from datetime import date
from threading import Lock

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.imaging import encode_jpeg, encode_png, atomic_write
from zenith.paths import developed_dir, png_dir, product_find_path, product_write_path, products_dir, raw_dir
from zenith.products.encode_jobs import tracker
from zenith.products.keogram import Keogram
from zenith.products.raw_develop import develop_dng_folder
from zenith.products.startrails import Startrails, count_stars
from zenith.products.timelapse import encode_timelapse


class ProductService:
    def __init__(self) -> None:
        self.session_date: date | None = None
        self.keogram = Keogram()
        self.trails = Startrails()
        self.frames_this_session = 0
        self.pending_mini = False
        self.pending_full = False
        self.pending_date: date | None = None
        self._lock = Lock()
        self._encode_lock = Lock()

    def on_saved_frame(
        self,
        rgb_linear: np.ndarray,
        adu: float,
        session_date: date,
        settings: ZenithSettings,
    ) -> dict:
        with self._lock:
            if self.session_date != session_date:
                self._load_session(session_date)
            stars = count_stars(rgb_linear)
            prod = settings.products
            dest_date = session_date
            if prod.keogram_enabled:
                self.keogram.append(rgb_linear, settings.location.keogram_angle_deg, prod.keogram_slice_px)
                self.keogram.save(product_write_path(dest_date, "keogram_realtime.jpg"))
            if prod.startrails_enabled:
                self.trails.maybe_add(
                    rgb_linear,
                    adu,
                    stars,
                    min_stars=prod.startrails_min_stars,
                    adu_min=prod.startrails_adu_min,
                    adu_max=prod.startrails_adu_max,
                )
                self._write_trails(session_date, settings)
            self.frames_this_session += 1
            if prod.mini_timelapse_enabled and self.frames_this_session % 12 == 0:
                self.pending_mini = True
                self.pending_date = session_date
            if prod.timelapse_enabled and self.frames_this_session % 48 == 0:
                self.pending_full = True
                self.pending_date = session_date
            return {
                "stars": stars,
                "trails_frames": self.trails.frames_used,
                "keogram_width": 0 if self.keogram.image is None else int(self.keogram.image.shape[1]),
            }

    def finalize(self, session_date: date, settings: ZenithSettings) -> None:
        with self._lock:
            if settings.products.keogram_enabled:
                self.keogram.save(product_write_path(session_date, "keogram_realtime.jpg"))
                self.keogram.save(product_write_path(session_date, "keogram.jpg"))
            if settings.products.startrails_enabled:
                self._write_trails(session_date, settings)
            self.pending_mini = bool(settings.products.mini_timelapse_enabled)
            self.pending_full = bool(settings.products.timelapse_enabled)
            self.pending_date = session_date

    def take_encode_job(self) -> tuple[date | None, bool, bool]:
        with self._lock:
            mini, full = self.pending_mini, self.pending_full
            target = self.pending_date or self.session_date
            self.pending_mini = False
            self.pending_full = False
            return target, mini, full

    def encode(
        self,
        session_date: date,
        settings: ZenithSettings,
        mini: bool,
        full: bool,
        kind: str = "night",
    ) -> None:
        key = f"{kind}:{session_date.isoformat()}"
        if not self._encode_lock.acquire(blocking=False):
            return
        tracker.start(key, kind=kind, date=session_date.isoformat())
        try:
            frames, pattern = self._timelapse_frames(kind, session_date, settings, key)
            if frames is None:
                tracker.finish(key)
                return
            if mini and settings.products.mini_timelapse_enabled:
                tracker.phase(key, "encoding", label="Encoding mini timelapse")
                encode_timelapse(
                    frames,
                    product_write_path(session_date, "mini.mp4"),
                    settings.products.mini_timelapse_fps,
                    settings.products.mini_timelapse_width,
                    pattern=pattern,
                )
            if full and settings.products.timelapse_enabled:
                tracker.phase(key, "encoding", label="Encoding full timelapse")
                encode_timelapse(
                    frames,
                    product_write_path(session_date, "timelapse.mp4"),
                    settings.products.timelapse_fps,
                    None,
                    pattern=pattern,
                )
            tracker.finish(key)
        except Exception as exc:
            tracker.fail(key, str(exc) or type(exc).__name__)
            raise
        finally:
            self._encode_lock.release()

    def _timelapse_frames(
        self,
        kind: str,
        session_date: date,
        settings: ZenithSettings,
        progress_key: str | None = None,
    ) -> tuple:
        raw = raw_dir(kind, session_date)
        dngs = list(raw.glob("*.dng")) if raw.is_dir() else []
        if settings.products.timelapse_from_raw and len(dngs) >= 2:
            developed = developed_dir(session_date)
            n = develop_dng_folder(
                raw,
                developed,
                bright=settings.products.timelapse_bright,
                colour=(
                    settings.picamera2.colour_gain_r,
                    settings.picamera2.colour_gain_g,
                    settings.picamera2.colour_gain_b,
                ),
                max_side=1920,
                skip_dirs=[products_dir(session_date) / "developed"],
                on_progress=(
                    None
                    if progress_key is None
                    else lambda info: tracker.tick(progress_key, **info)
                ),
            )
            if n >= 2:
                return developed, "*.jpg"
        png = png_dir(kind, session_date)
        return png, "*.png"

    def _write_trails(self, session_date: date, settings: ZenithSettings) -> None:
        if self.trails.stack is not None:
            atomic_write(product_write_path(session_date, "startrails_stack.png"), encode_png(self.trails.stack))
            atomic_write(product_write_path(session_date, "startrails.jpg"), encode_jpeg(self.trails.stack, 90))
        self.trails.save(
            product_write_path(session_date, "startrails.jpg"),
            product_write_path(session_date, "startrails.json"),
        )

    def _load_session(self, session_date: date) -> None:
        self.session_date = session_date
        rt = product_find_path(session_date, "keogram_realtime.jpg")
        self.keogram.load(rt if rt is not None else product_write_path(session_date, "keogram_realtime.jpg"))
        self.trails.reset()
        stack = product_find_path(session_date, "startrails_stack.png")
        trails = product_find_path(session_date, "startrails.jpg")
        load = stack or trails
        if load is not None:
            self.trails.load(load)
        self.frames_this_session = 0
        for folder in (png_dir("night", session_date), raw_dir("night", session_date)):
            if folder.is_dir():
                self.frames_this_session = max(
                    self.frames_this_session,
                    len([p for p in folder.iterdir() if p.is_file()]),
                )
