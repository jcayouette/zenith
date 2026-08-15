"""Raspberry Pi HQ camera (Sony IMX477) capture limits.

Electronic rolling shutter: shutter speed and exposure time are the same control.
Modes we use match libcamera's full and 2×2-binned streams.
"""

from __future__ import annotations

EXPOSURE_US_MIN = 100
EXPOSURE_US_MAX = 120_000_000  # 120 s — IMX477 can go longer; libcamera is happiest here
GAIN_MIN = 1.0
GAIN_MAX = 22.0

BINNING = (
    {"value": 1, "width": 4056, "height": 3040, "label": "1× · 4056×3040"},
    {"value": 2, "width": 2028, "height": 1520, "label": "2× · 2028×1520"},
)

# ASI Studio-style ranges: pick a decade, then the slider has room to move.
SHUTTER_RANGES = (
    {"id": "0.1-1ms", "label": "0.1 – 1 ms", "min": 100, "max": 1_000},
    {"id": "1-10ms", "label": "1 – 10 ms", "min": 1_000, "max": 10_000},
    {"id": "10-100ms", "label": "10 – 100 ms", "min": 10_000, "max": 100_000},
    {"id": "0.1-1s", "label": "0.1 – 1 s", "min": 100_000, "max": 1_000_000},
    {"id": "1-10s", "label": "1 – 10 s", "min": 1_000_000, "max": 10_000_000},
    {"id": "10-60s", "label": "10 – 60 s", "min": 10_000_000, "max": 60_000_000},
    {"id": "60-120s", "label": "60 – 120 s", "min": 60_000_000, "max": 120_000_000},
)

SIZE_FULL = (4056, 3040)
SIZE_BINNED = (2028, 1520)


def size_for_binning(binning: int) -> tuple[int, int]:
    return SIZE_BINNED if int(binning) == 2 else SIZE_FULL


def caps() -> dict:
    return {
        "sensor": "imx477",
        "name": "Raspberry Pi HQ",
        "exposure_us": {"min": EXPOSURE_US_MIN, "max": EXPOSURE_US_MAX},
        "analogue_gain": {"min": GAIN_MIN, "max": GAIN_MAX},
        "binning": list(BINNING),
        "shutter_ranges": list(SHUTTER_RANGES),
    }
