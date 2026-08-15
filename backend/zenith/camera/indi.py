from zenith.camera.base import CameraBackend, CameraError, Frame
from zenith.config.schema import ZenithSettings


class IndiBackend(CameraBackend):
    name = "indi"

    def open(self, settings: ZenithSettings) -> None:
        raise CameraError(
            "INDI backend is stubbed in Phase 1. Phase 5 connects to indiserver for ZWO, QHY, "
            "Svbony, Player One, ToupTek, and other CCDs."
        )

    def close(self) -> None:
        return None

    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None:
        raise CameraError("INDI backend is not implemented yet")

    def capture(self, raw_path=None) -> Frame:
        raise CameraError("INDI backend is not implemented yet")
