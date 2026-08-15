from __future__ import annotations

from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.config.schema import ZenithSettings


class Picamera2Backend(CameraBackend):
    name = "picamera2"

    def __init__(self) -> None:
        self._picam = None
        self._exposure_us = 1_000_000
        self._gain = 1.0

    def open(self, settings: ZenithSettings) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise CameraError(
                "picamera2 is not installed. On Raspberry Pi OS: sudo apt install python3-picamera2. "
                "Use the simulator backend off the Pi."
            ) from exc
        cam = Picamera2()
        still = cam.create_still_configuration(buffer_count=2)
        cam.configure(still)
        cam.start()
        self._picam = cam

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
        controls = {
            "ExposureTime": int(exposure_us),
            "AnalogueGain": float(gain),
            "AeEnable": False,
            "AwbEnable": bool(settings.picamera2.awb_enable_day and not night),
        }
        if not controls["AwbEnable"]:
            controls["ColourGains"] = (
                float(settings.picamera2.colour_gain_r),
                float(settings.picamera2.colour_gain_b),
            )
        self._picam.set_controls(controls)

    def capture(self) -> Frame:
        if self._picam is None:
            raise CameraError("Picamera2 is not open")
        arr = self._picam.capture_array()
        if arr.ndim == 2:
            rgb = __import__("numpy").stack([arr, arr, arr], axis=-1)
        else:
            rgb = arr[..., :3]
        return Frame(rgb=rgb, exposure_us=self._exposure_us, gain=self._gain, sensor="picamera2")
