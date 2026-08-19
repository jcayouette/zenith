from __future__ import annotations

from datetime import date
from threading import Lock
from time import time

import numpy as np
from PIL import Image

from zenith.config.schema import ZenithSettings
from zenith.imaging import encode_jpeg, encode_png, atomic_write
from zenith.paths import developed_dir, jpeg_dir, png_dir, product_find_path, product_write_path, products_dir, raw_dir
from zenith.products.detect import StreakDetector, classify_streak
from zenith.products.detections import write_detection, write_highlight_reel
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
        self.detector = StreakDetector()
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
        stem: str | None = None,
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
                self._write_trails(session_date, force=False)
            hits = []
            if prod.detections_enabled:
                hits = self.detector.feed(
                    rgb_linear,
                    min_length=prod.detections_min_length_px,
                    min_aspect=prod.detections_min_aspect,
                    now_s=time(),
                )
            self.frames_this_session += 1
            if prod.mini_timelapse_enabled and self.frames_this_session % 12 == 0:
                self.pending_mini = True
                self.pending_date = session_date
            if prod.timelapse_enabled and self.frames_this_session % 48 == 0:
                self.pending_full = True
                self.pending_date = session_date
            trails_frames = self.trails.frames_used
            keogram_width = 0 if self.keogram.image is None else int(self.keogram.image.shape[1])
        detections = 0
        if hits:
            detections = self._record_hits(rgb_linear, adu, stars, session_date, settings, stem, hits)
        return {
            "stars": stars,
            "trails_frames": trails_frames,
            "keogram_width": keogram_width,
            "detections": detections,
        }

    def finalize(self, session_date: date, settings: ZenithSettings) -> None:
        with self._lock:
            if settings.products.keogram_enabled:
                self.keogram.save(product_write_path(session_date, "keogram_realtime.jpg"))
                self.keogram.save(product_write_path(session_date, "keogram.jpg"))
            if settings.products.startrails_enabled:
                self._write_trails(session_date, force=True)
            if settings.products.detections_enabled:
                write_highlight_reel(session_date)
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

    def rebuild_startrails(self, session_date: date, settings: ZenithSettings) -> dict:
        """Rebuild the night's max-stack from archived PNG/JPEG. Does not touch live capture mid-frame."""
        trails = Startrails()
        frames = _night_still_frames(session_date)
        prod = settings.products
        for path in frames:
            rgb = np.array(Image.open(path).convert("RGB"))
            adu = float(rgb.mean() / 255.0)
            stars = count_stars(rgb)
            trails.maybe_add(
                rgb,
                adu,
                stars,
                min_stars=prod.startrails_min_stars,
                adu_min=prod.startrails_adu_min,
                adu_max=prod.startrails_adu_max,
            )
        self._persist_trails(trails, session_date, force=True)
        with self._lock:
            if self.session_date == session_date:
                self.trails = trails
        return {
            "ok": True,
            "date": session_date.isoformat(),
            "frames_seen": trails.frames_seen,
            "frames_used": trails.frames_used,
            "wrote": trails.stack is not None,
        }

    def scan_detections(self, session_date: date, settings: ZenithSettings) -> dict:
        """Replay a night's stills through the streak finder (offline)."""
        detector = StreakDetector()
        frames = _night_still_frames(session_date)
        prod = settings.products
        found = 0
        sats, planes = _sky_objects(settings)
        now_s = time()
        for i, path in enumerate(frames):
            rgb = np.array(Image.open(path).convert("RGB"))
            adu = float(rgb.mean() / 255.0)
            stars = count_stars(rgb)
            hits = detector.feed(
                rgb,
                min_length=prod.detections_min_length_px,
                min_aspect=prod.detections_min_aspect,
                now_s=now_s + i,
            )
            stem = path.stem
            for streak in hits:
                cls, match, dist = classify_streak(streak, sats, planes)
                write_detection(
                    session_date,
                    rgb,
                    streak,
                    stem=stem,
                    cls=cls,
                    match=match,
                    distance=dist,
                    stars=stars,
                    adu=adu,
                )
                found += 1
        reel = write_highlight_reel(session_date)
        return {
            "ok": True,
            "date": session_date.isoformat(),
            "frames": len(frames),
            "detections": found,
            "reel": reel is not None,
        }

    def _record_hits(
        self,
        rgb: np.ndarray,
        adu: float,
        stars: int,
        session_date: date,
        settings: ZenithSettings,
        stem: str | None,
        hits,
    ) -> int:
        sats, planes = _sky_objects(settings)
        n = 0
        for streak in hits:
            cls, match, dist = classify_streak(streak, sats, planes)
            write_detection(
                session_date,
                rgb,
                streak,
                stem=stem or "frame",
                cls=cls,
                match=match,
                distance=dist,
                stars=stars,
                adu=adu,
            )
            n += 1
        return n

    def _write_trails(self, session_date: date, *, force: bool = False) -> None:
        self._persist_trails(self.trails, session_date, force=force)

    def _persist_trails(self, trails: Startrails, session_date: date, *, force: bool) -> None:
        used = trails.frames_used
        if trails.stack is not None and (force or used % 8 == 0):
            atomic_write(product_write_path(session_date, "startrails.jpg"), encode_jpeg(trails.stack, 90))
        if trails.stack is not None and (force or used % 16 == 0):
            atomic_write(product_write_path(session_date, "startrails_stack.png"), encode_png(trails.stack))
        trails.save(
            product_write_path(session_date, "startrails.jpg"),
            product_write_path(session_date, "startrails.json"),
        )

    def _load_session(self, session_date: date) -> None:
        self.session_date = session_date
        rt = product_find_path(session_date, "keogram_realtime.jpg")
        self.keogram.load(rt if rt is not None else product_write_path(session_date, "keogram_realtime.jpg"))
        self.trails.reset()
        self.detector.reset()
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


def _night_still_frames(session_date: date) -> list:
    png = png_dir("night", session_date)
    frames = sorted(p for p in png.glob("*.png") if p.is_file()) if png.is_dir() else []
    if len(frames) >= 2:
        return frames
    jpeg = jpeg_dir("night", session_date)
    if jpeg.is_dir():
        frames = sorted(p for p in jpeg.glob("*.jpg") if p.is_file())
    return frames


def _sky_objects(settings: ZenithSettings) -> tuple[list, list]:
    sats: list = []
    planes: list = []
    try:
        from zenith.sky.layers import build_sats

        sats = (build_sats(settings, width=1000, height=1000).get("satellites") or [])
    except Exception:
        sats = []
    try:
        from zenith.sky.aircraft import build_aircraft

        planes = (build_aircraft(settings, width=1000, height=1000).get("aircraft") or [])
    except Exception:
        planes = []
    return sats, planes
