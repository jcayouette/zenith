from __future__ import annotations

import asyncio
import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
from PIL import Image

from zenith.camera import create_backend
from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.config.schema import ExposureProfile, ZenithSettings
from zenith.config.store import load_settings
from zenith.overlay import apply_overlay
from zenith.paths import LATEST_JPEG, LATEST_META, ensure_data_dir
from zenith.sky.sun import sky_mode, sun_altitude_deg


@dataclass
class Telemetry:
    mode: str = "day"
    sun_alt: float = 0.0
    exposure_us: int = 0
    gain: float = 1.0
    adu: float = 0.0
    backend: str = "simulator"
    sensor: str = ""
    ts: str = ""
    error: str | None = None
    capturing: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "sun_alt": round(self.sun_alt, 2),
            "exposure_us": self.exposure_us,
            "gain": round(self.gain, 3),
            "adu": round(self.adu, 4),
            "backend": self.backend,
            "sensor": self.sensor,
            "ts": self.ts,
            "error": self.error,
            "capturing": self.capturing,
        }


class LiveHub:
    def __init__(self) -> None:
        self._clients: set[asyncio.Queue] = set()
        self.telemetry = Telemetry()
        self.jpeg: bytes = b""

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    async def publish(self, jpeg: bytes, telemetry: Telemetry) -> None:
        self.jpeg = jpeg
        self.telemetry = telemetry
        payload = {"jpeg": jpeg, "telemetry": telemetry.as_dict()}
        dead = []
        for q in self._clients:
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._clients.discard(q)


class CaptureService:
    def __init__(self, hub: LiveHub) -> None:
        self.hub = hub
        self._task: asyncio.Task | None = None
        self._backend: CameraBackend | None = None
        self._reload = asyncio.Event()
        self.exposure_us = 1_000_000
        self.gain = 1.0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="zenith-capture")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._close_backend()

    def request_reload(self) -> None:
        self._reload.set()

    def _close_backend(self) -> None:
        if self._backend is not None:
            try:
                self._backend.close()
            except Exception:
                pass
            self._backend = None

    async def _run(self) -> None:
        ensure_data_dir()
        while True:
            settings = load_settings()
            self._reload.clear()
            try:
                self._close_backend()
                self._backend = await asyncio.to_thread(create_backend, settings)
                await self._loop(settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                tel = Telemetry(
                    backend=settings.camera.backend,
                    error=str(exc),
                    capturing=False,
                    ts=_now(),
                )
                await self.hub.publish(_placeholder_jpeg(str(exc)), tel)
                try:
                    await asyncio.wait_for(self._reload.wait(), timeout=3.0)
                except TimeoutError:
                    continue

    async def _loop(self, settings: ZenithSettings) -> None:
        assert self._backend is not None
        backend = self._backend
        while not self._reload.is_set():
            settings = load_settings()
            sun_alt = sun_altitude_deg(settings.location.latitude, settings.location.longitude)
            mode = sky_mode(sun_alt, settings.location.night_sun_altitude_deg)
            night = mode == "night"
            profile = settings.night if night else settings.day
            should_capture = settings.camera.capture_night if night else settings.camera.capture_day
            if not should_capture:
                tel = Telemetry(
                    mode=mode,
                    sun_alt=sun_alt,
                    backend=backend.name,
                    capturing=False,
                    ts=_now(),
                )
                await self.hub.publish(self.hub.jpeg or _placeholder_jpeg("capture paused"), tel)
                await asyncio.sleep(2)
                continue

            if profile.auto_exposure:
                self._servo(profile)
            else:
                self.exposure_us = profile.exposure_us
                self.gain = profile.gain

            await asyncio.to_thread(
                backend.configure, settings, int(self.exposure_us), float(self.gain), night
            )
            try:
                frame: Frame = await asyncio.to_thread(backend.capture)
            except CameraError as exc:
                raise exc

            rgb = _orient(frame.rgb, settings.camera.flip_h, settings.camera.flip_v, settings.camera.rotation_deg)
            mean = float(rgb.mean() / 255.0)
            self._last_mean = mean
            overlaid = apply_overlay(
                rgb,
                overlay=settings.overlay,
                mode=mode,
                sun_alt=sun_alt,
                exposure_us=frame.exposure_us,
                gain=frame.gain,
                mean=mean,
                backend=backend.name,
            )
            jpeg = _encode_jpeg(overlaid, settings.camera.jpeg_quality)
            await asyncio.to_thread(_write_latest, jpeg, {
                "mode": mode,
                "sun_alt": sun_alt,
                "exposure_us": frame.exposure_us,
                "gain": frame.gain,
                "adu": mean,
                "backend": backend.name,
                "ts": _now(),
            })
            tel = Telemetry(
                mode=mode,
                sun_alt=sun_alt,
                exposure_us=frame.exposure_us,
                gain=frame.gain,
                adu=mean,
                backend=backend.name,
                sensor=frame.sensor,
                ts=_now(),
                capturing=True,
            )
            preview = _encode_jpeg(_downscale(overlaid, 960), min(settings.camera.jpeg_quality, 80))
            await self.hub.publish(preview, tel)
            delay = settings.camera.extra_delay_s
            if delay:
                await asyncio.sleep(delay)

    def _servo(self, profile: ExposureProfile) -> None:
        mean = getattr(self, "_last_mean", profile.target_mean)
        error = profile.target_mean - mean
        if abs(error) < 0.02:
            return
        factor = 1.0 + error * 1.4
        nxt = int(np.clip(self.exposure_us * factor, 200, profile.max_exposure_us))
        if nxt >= profile.max_exposure_us and error > 0:
            self.gain = float(np.clip(self.gain * factor, 1.0, profile.max_gain))
        else:
            self.gain = max(1.0, min(self.gain, profile.max_gain))
        self.exposure_us = nxt


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _orient(rgb: np.ndarray, flip_h: bool, flip_v: bool, rotation: int) -> np.ndarray:
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


def _encode_jpeg(rgb: np.ndarray, quality: int) -> bytes:
    img = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=int(quality), optimize=True)
    return buf.getvalue()


def _downscale(rgb: np.ndarray, max_side: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return rgb
    img = Image.fromarray(rgb)
    img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
    return np.array(img)


def _write_latest(jpeg: bytes, meta: dict) -> None:
    LATEST_JPEG.write_bytes(jpeg)
    LATEST_META.write_text(json.dumps(meta, indent=2))


def _placeholder_jpeg(message: str) -> bytes:
    img = Image.new("RGB", (960, 720), (8, 12, 22))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.text((40, 320), "ZENITH", fill=(125, 211, 252))
    draw.text((40, 360), message[:120], fill=(226, 232, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
