from __future__ import annotations

from pathlib import Path

import numpy as np

from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.camera.imx477 import size_for_binning
from zenith.config.schema import ZenithSettings


class Picamera2Backend(CameraBackend):
    name = "picamera2"

    def __init__(self) -> None:
        self._picam = None
        self._exposure_us = 1_000_000
        self._gain = 1.0
        self._isp_wb = False
        self._focus = False

    def open(self, settings: ZenithSettings) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CameraError(
                "picamera2 is not installed. On Raspberry Pi OS: sudo apt install python3-picamera2. "
                "Use the simulator backend off the Pi."
            ) from exc
        try:
            camera_num = int(settings.camera.device)
        except ValueError:
            camera_num = 0
        tuning = None
        tuning_file = settings.picamera2.tuning_file.strip()
        if tuning_file and Path(tuning_file).is_file():
            tuning = Picamera2.load_tuning_file(tuning_file)
        cam = Picamera2(camera_num=camera_num, tuning=tuning) if tuning is not None else Picamera2(
            camera_num=camera_num
        )
        self._focus = bool(settings.camera.focus_mode)
        self._configure_stream(cam, settings)
        cam.start()
        self._picam = cam
        self._lock_colour(settings, night=False)

    def _configure_stream(self, cam, settings: ZenithSettings) -> None:
        """Same RGB+raw still pipeline for focus and archive so ISP colour matches."""
        size = size_for_binning(settings.camera.binning)
        main = {"size": size, "format": "RGB888"}
        try:
            cam.configure(
                cam.create_still_configuration(main=main, raw={"size": size}, buffer_count=2)
            )
        except Exception:
            cam.configure(cam.create_still_configuration(main=main, buffer_count=2))

    def _lock_colour(self, settings: ZenithSettings, night: bool) -> None:
        if self._picam is None:
            return
        awb = bool(settings.picamera2.awb_enable_day and not night)
        try:
            self._picam.set_controls({"AwbEnable": awb, "AeEnable": False})
        except Exception:
            pass

    def close(self) -> None:
        if self._picam is not None:
            self._picam.stop()
            self._picam.close()
            self._picam = None

    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None:
        if self._picam is None:
            raise CameraError("Picamera2 is not open")
        self._exposure_us = exposure_us
        self._gain = gain
        p = settings.picamera2
        awb = bool(p.awb_enable_day and not night)
        controls = {
            "ExposureTime": int(exposure_us),
            "AnalogueGain": float(gain),
            "AeEnable": False,
            "AwbEnable": awb,
            "Sharpness": float(p.sharpness),
            "Contrast": float(p.contrast),
            "Saturation": float(p.saturation),
        }
        exp = max(1000, int(exposure_us))
        controls["FrameDurationLimits"] = (exp, exp + 10_000)
        self._isp_wb = awb
        try:
            self._picam.set_controls(controls)
        except Exception:
            controls.pop("FrameDurationLimits", None)
            try:
                self._picam.set_controls(controls)
            except Exception:
                self._picam.set_controls(
                    {
                        "ExposureTime": int(exposure_us),
                        "AnalogueGain": float(gain),
                        "AeEnable": False,
                        "AwbEnable": awb,
                    }
                )

    def capture(self, raw_path: Path | None = None) -> Frame:
        if self._picam is None:
            raise CameraError("Picamera2 is not open")
        request = self._picam.capture_request()
        try:
            arr = request.make_array("main")
            if arr.ndim == 2:
                rgb = np.stack([arr, arr, arr], axis=-1)
            else:
                rgb = arr[..., :3]
            extra: dict = {"isp_wb": self._isp_wb}
            if raw_path is not None:
                try:
                    raw_path.parent.mkdir(parents=True, exist_ok=True)
                    request.save_dng(str(raw_path))
                    extra["raw"] = str(raw_path)
                except Exception as exc:
                    extra["raw_error"] = str(exc)
            return Frame(
                rgb=np.ascontiguousarray(rgb),
                exposure_us=self._exposure_us,
                gain=self._gain,
                sensor="imx477",
                extra=extra,
            )
        finally:
            request.release()
