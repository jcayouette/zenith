from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from zenith.config.schema import ZenithSettings


@dataclass
class Frame:
    rgb: np.ndarray
    exposure_us: int
    gain: float
    sensor: str = "unknown"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def mean(self) -> float:
        return float(self.rgb.mean() / 255.0)


class CameraBackend(ABC):
    name: str

    @abstractmethod
    def open(self, settings: ZenithSettings) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def configure(self, settings: ZenithSettings, exposure_us: int, gain: float, night: bool) -> None: ...

    @abstractmethod
    def capture(self, raw_path: Path | None = None) -> Frame: ...

    def describe(self) -> dict[str, Any]:
        return {"backend": self.name}


class CameraError(RuntimeError):
    pass
