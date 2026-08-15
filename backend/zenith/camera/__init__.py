from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.camera.indi import IndiBackend
from zenith.camera.mqtt import MqttLibcameraBackend
from zenith.camera.picamera import Picamera2Backend
from zenith.camera.simulator import SimulatorBackend
from zenith.config.schema import ZenithSettings

_BACKENDS = {
    "simulator": SimulatorBackend,
    "picamera2": Picamera2Backend,
    "indi": IndiBackend,
    "mqtt_libcamera": MqttLibcameraBackend,
}


def create_backend(settings: ZenithSettings) -> CameraBackend:
    name = settings.camera.backend
    cls = _BACKENDS.get(name)
    if cls is None:
        raise CameraError(f"Unknown camera backend: {name}")
    backend = cls()
    backend.open(settings)
    return backend
