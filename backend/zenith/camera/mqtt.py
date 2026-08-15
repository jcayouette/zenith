from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.config.schema import ZenithSettings


class MqttLibcameraBackend(CameraBackend):
    name = "mqtt_libcamera"

    def open(self, settings: ZenithSettings) -> None:
        raise CameraError(
            "MQTT libcamera backend is stubbed in Phase 1. A remote Pi will own Picamera2 and "
            "publish frames to the broker."
        )

    def close(self) -> None:
        return None

    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None:
        raise CameraError("MQTT libcamera backend is not implemented yet")

    def capture(self, raw_path=None) -> Frame:
        raise CameraError("MQTT libcamera backend is not implemented yet")
