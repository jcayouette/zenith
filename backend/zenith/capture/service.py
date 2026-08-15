from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
from PIL import Image

from zenith.archive.store import save_frame, should_save
from zenith.camera import create_backend
from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.config.schema import ExposureProfile, ZenithSettings
from zenith.config.store import load_settings
from zenith.imaging import apply_colour_gains, downscale, encode_jpeg, orient
from zenith.overlay import apply_overlay
from zenith.paths import LATEST_JPEG, LATEST_META, ensure_data_dir, raw_dir
from zenith.products.service import ProductService
from zenith.sky.sun import SkySession, local_time, sky_session


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
    session: str = ""
    stars: int = 0
    saved: bool = False
    focus: bool = False
    camera: bool = False

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
            "session": self.session,
            "stars": self.stars,
            "saved": self.saved,
            "focus": self.focus,
            "camera": self.camera,
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
        self.products = ProductService()
        self._last_kind: str | None = None
        self._last_date: date | None = None
        self._encode_task: asyncio.Task | None = None
        self._ctrl_key: tuple | None = None
        self._held = False

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
        settings = load_settings()
        if self.products.session_date is not None:
            await asyncio.to_thread(self.products.finalize, self.products.session_date, settings)
        self._close_backend()

    def request_reload(self) -> None:
        self._reload.set()

    def disconnect(self) -> None:
        """Release the CSI camera so it can be unplugged or used by another process."""
        self._held = True
        self.request_reload()

    def connect(self) -> None:
        self._held = False
        self.request_reload()

    def camera_state(self) -> dict[str, bool]:
        return {
            "connected": self._backend is not None and not self._held,
            "released": self._held,
        }

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
            if self._held:
                self._close_backend()
                settings = load_settings()
                tel = Telemetry(
                    backend=settings.camera.backend,
                    capturing=False,
                    camera=False,
                    ts=_now(),
                )
                await self.hub.publish(_placeholder_jpeg("Camera disconnected"), tel)
                self._reload.clear()
                try:
                    await asyncio.wait_for(self._reload.wait(), timeout=2.0)
                except TimeoutError:
                    pass
                continue
            settings = load_settings()
            self._reload.clear()
            try:
                self._close_backend()
                self._ctrl_key = None
                self._backend = await asyncio.to_thread(create_backend, settings)
                await self._loop(settings)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                tel = Telemetry(
                    backend=settings.camera.backend,
                    error=str(exc),
                    capturing=False,
                    camera=False,
                    ts=_now(),
                )
                await self.hub.publish(_placeholder_jpeg(str(exc)), tel)
                if self._held:
                    continue
                try:
                    await asyncio.wait_for(self._reload.wait(), timeout=3.0)
                except TimeoutError:
                    continue

    async def _loop(self, settings: ZenithSettings) -> None:
        assert self._backend is not None
        backend = self._backend
        while not self._reload.is_set():
            if self._held:
                break
            settings = load_settings()
            session = sky_session(
                settings.location.latitude,
                settings.location.longitude,
                settings.location.timezone,
                settings.location.night_sun_altitude_deg,
            )
            await self._maybe_finalize(session, settings)
            self._kick_encode(settings)
            night = session.mode == "night"
            focus = bool(settings.camera.focus_mode)
            opened_focus = bool(getattr(backend, "_focus", False))
            if focus != opened_focus:
                self.request_reload()
                break
            profile = settings.night if night else settings.day
            should_capture = settings.camera.capture_night if night else settings.camera.capture_day
            if not should_capture:
                tel = Telemetry(
                    mode=session.mode,
                    sun_alt=session.sun_alt,
                    backend=backend.name,
                    capturing=False,
                    camera=True,
                    ts=_now(),
                    session=f"{session.kind}:{session.date.isoformat()}",
                    focus=focus,
                )
                await self.hub.publish(self.hub.jpeg or _placeholder_jpeg("capture paused"), tel)
                await asyncio.sleep(2)
                continue

            max_exp = profile.max_exposure_us
            if profile.auto_exposure:
                self._servo(profile, max_exposure_us=max_exp)
            else:
                self.exposure_us = int(profile.exposure_us)
                self.gain = float(profile.gain)
            self.exposure_us = int(np.clip(self.exposure_us, 100, max_exp))

            p = settings.picamera2
            ctrl_key = (
                int(self.exposure_us),
                round(float(self.gain), 3),
                night,
                round(float(p.contrast), 3),
                round(float(p.saturation), 3),
                round(float(p.sharpness), 3),
                bool(p.awb_enable_day),
            )
            if ctrl_key != self._ctrl_key:
                await asyncio.to_thread(
                    backend.configure, settings, int(self.exposure_us), float(self.gain), night
                )
                self._ctrl_key = ctrl_key
            will_save = False
            raw_dest = None
            when_local = local_time(settings.location.timezone)
            try:
                will_save = (not focus) and should_save(session.kind, settings)
                if will_save and settings.camera.save_raw and backend.name == "picamera2":
                    stem = when_local.strftime("%Y%m%d_%H%M%S")
                    raw_dest = raw_dir(session.kind, session.date) / f"{stem}.dng"
                frame: Frame = await asyncio.to_thread(backend.capture, raw_dest)
            except CameraError as exc:
                raise exc

            rgb_linear = orient(frame.rgb, settings.camera.flip_h, settings.camera.flip_v, settings.camera.rotation_deg)
            mean = float(rgb_linear.mean() / 255.0)
            self._last_mean = mean
            red_gain = settings.picamera2.colour_gain_r
            green_gain = settings.picamera2.colour_gain_g
            blue_gain = settings.picamera2.colour_gain_b
            rgb_preview = apply_colour_gains(
                rgb_linear,
                red_gain=red_gain,
                green_gain=green_gain,
                blue_gain=blue_gain,
            )
            jpeg = encode_jpeg(
                downscale(rgb_preview, 1920),
                min(settings.camera.jpeg_quality, 85),
                optimize=False,
            )
            overlaid = rgb_preview
            if not focus:
                overlaid = apply_overlay(
                    rgb_preview,
                    overlay=settings.overlay,
                    mode=session.mode,
                    sun_alt=session.sun_alt,
                    exposure_us=frame.exposure_us,
                    gain=frame.gain,
                    mean=mean,
                    backend=backend.name,
                    cardinal_offset_deg=settings.location.keogram_angle_deg,
                )
            saved = False
            stars = 0
            if will_save:
                await asyncio.to_thread(
                    save_frame,
                    rgb_linear=rgb_linear,
                    rgb_preview=overlaid,
                    kind=session.kind,
                    session_date=session.date,
                    when_local=when_local,
                    settings=settings,
                    raw_path=raw_dest if raw_dest is not None and raw_dest.is_file() else None,
                )
                saved = True
                if session.kind == "night":
                    info = await asyncio.to_thread(
                        self.products.on_saved_frame,
                        rgb_linear,
                        mean,
                        session.date,
                        settings,
                    )
                    stars = int(info["stars"])
            if not focus:
                await asyncio.to_thread(
                    _write_latest,
                    encode_jpeg(overlaid, settings.camera.jpeg_quality),
                    {
                        "mode": session.mode,
                        "sun_alt": session.sun_alt,
                        "exposure_us": frame.exposure_us,
                        "gain": frame.gain,
                        "adu": mean,
                        "backend": backend.name,
                        "ts": _now(),
                        "session": f"{session.kind}:{session.date.isoformat()}",
                        "saved": saved,
                        "stars": stars,
                        "focus": focus,
                    },
                )
            tel = Telemetry(
                mode=session.mode,
                sun_alt=session.sun_alt,
                exposure_us=frame.exposure_us,
                gain=frame.gain,
                adu=mean,
                backend=backend.name,
                sensor=frame.sensor,
                ts=_now(),
                capturing=True,
                camera=True,
                session=f"{session.kind}:{session.date.isoformat()}",
                stars=stars,
                saved=saved,
                focus=focus,
            )
            await self.hub.publish(jpeg, tel)
            if not focus:
                delay = settings.camera.extra_delay_s
                if delay:
                    await asyncio.sleep(delay)

    async def _maybe_finalize(self, session: SkySession, settings: ZenithSettings) -> None:
        prev_kind, prev_date = self._last_kind, self._last_date
        self._last_kind = session.kind
        self._last_date = session.date
        if prev_kind == "night" and prev_date is not None:
            ended = session.kind == "day" or session.date != prev_date
            if ended:
                await asyncio.to_thread(self.products.finalize, prev_date, settings)
                self._kick_encode(settings)

    def _kick_encode(self, settings: ZenithSettings) -> None:
        if self._encode_task and not self._encode_task.done():
            return
        target, mini, full = self.products.take_encode_job()
        if target is None or (not mini and not full):
            return

        async def _run() -> None:
            await asyncio.to_thread(self.products.encode, target, settings, mini, full)

        self._encode_task = asyncio.create_task(_run(), name="zenith-timelapse")

    def _servo(self, profile: ExposureProfile, max_exposure_us: int | None = None) -> None:
        mean = getattr(self, "_last_mean", profile.target_mean)
        error = profile.target_mean - mean
        if abs(error) < 0.02:
            return
        factor = 1.0 + error * 1.4
        cap = int(max_exposure_us if max_exposure_us is not None else profile.max_exposure_us)
        nxt = int(np.clip(self.exposure_us * factor, 200, cap))
        if nxt >= cap and error > 0:
            self.gain = float(np.clip(self.gain * factor, 1.0, profile.max_gain))
        else:
            self.gain = max(1.0, min(self.gain, profile.max_gain))
        self.exposure_us = nxt


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_latest(jpeg: bytes, meta: dict) -> None:
    LATEST_JPEG.write_bytes(jpeg)
    LATEST_META.write_text(json.dumps(meta, indent=2))


def _placeholder_jpeg(message: str) -> bytes:
    img = Image.new("RGB", (960, 720), (8, 12, 22))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.text((40, 320), "ZENITH", fill=(125, 211, 252))
    draw.text((40, 360), message[:120], fill=(226, 232, 240))
    buf = __import__("io").BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()
