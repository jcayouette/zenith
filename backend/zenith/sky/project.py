"""Equidistant fisheye: zenith at the centre, horizon on a ring."""

from __future__ import annotations

import numpy as np

# 1.0 = horizon sits on the long edge of the frame (fills a 4:3 HQ image).
HORIZON = 1.0


def altaz_to_xy(
    alt_deg: np.ndarray | float,
    az_deg: np.ndarray | float,
    width: int,
    height: int,
    *,
    north_angle_deg: float = 0.0,
    horizon: float = HORIZON,
    flip_h: bool = False,
    flip_v: bool = False,
    rotation_deg: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project altitude/azimuth into oriented-image pixel coordinates.

    Azimuth 0 is north, 90 is east. With ``north_angle_deg=0`` and no flips,
    north is up and east is right — the same convention as the cardinal overlay.
    Returns (x, y, visible) where visible is above the horizon and inside the frame.
    """
    alt = np.asarray(alt_deg, dtype=np.float64)
    az = np.asarray(az_deg, dtype=np.float64)
    native_w, native_h = _native_size(width, height, rotation_deg)
    radius = max(native_w, native_h) / 2.0 * float(horizon)
    zenith = np.clip(90.0 - alt, 0.0, 180.0)
    r = zenith / 90.0 * radius
    theta = np.deg2rad(az - 90.0 + north_angle_deg)
    cx = native_w / 2.0
    cy = native_h / 2.0
    x = cx + np.cos(theta) * r
    y = cy + np.sin(theta) * r
    x, y = orient_xy(x, y, native_w, native_h, flip_h, flip_v, rotation_deg)
    visible = (alt >= 0) & (x >= -1.0) & (x <= width) & (y >= -1.0) & (y <= height)
    if np.ndim(alt_deg) == 0:
        return float(x), float(y), bool(visible)
    return x, y, visible


def xy_to_altaz(
    x: np.ndarray | float,
    y: np.ndarray | float,
    width: int,
    height: int,
    *,
    north_angle_deg: float = 0.0,
    horizon: float = HORIZON,
    flip_h: bool = False,
    flip_v: bool = False,
    rotation_deg: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Inverse of ``altaz_to_xy``: overlay pixels back to altitude / azimuth."""
    native_w, native_h = _native_size(width, height, rotation_deg)
    xx, yy = inverse_orient_xy(x, y, width, height, flip_h, flip_v, rotation_deg)
    radius = max(native_w, native_h) / 2.0 * float(horizon)
    cx = native_w / 2.0
    cy = native_h / 2.0
    dx = np.asarray(xx, dtype=np.float64) - cx
    dy = np.asarray(yy, dtype=np.float64) - cy
    r = np.hypot(dx, dy)
    alt = 90.0 - r / max(radius, 1e-6) * 90.0
    az = (np.degrees(np.arctan2(dy, dx)) + 90.0 - north_angle_deg) % 360.0
    visible = (alt >= 0) & (r <= radius * 1.002)
    if np.ndim(x) == 0:
        return float(alt), float(az), bool(visible)
    return alt, az, visible


def rangeaz_to_xy(
    range_km: np.ndarray | float,
    az_deg: np.ndarray | float,
    width: int,
    height: int,
    *,
    max_range_km: float,
    north_angle_deg: float = 0.0,
    horizon: float = HORIZON,
    flip_h: bool = False,
    flip_v: bool = False,
    rotation_deg: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Azimuthal-equidistant radar plot: site at the centre, range to the rim.

    Same compass as ``altaz_to_xy`` (azimuth 0 = north). Radius is ground range,
    not zenith angle — a jet 50 km away sits halfway to a 100 km rim, not on it.
    """
    rng = np.asarray(range_km, dtype=np.float64)
    az = np.asarray(az_deg, dtype=np.float64)
    native_w, native_h = _native_size(width, height, rotation_deg)
    radius = max(native_w, native_h) / 2.0 * float(horizon)
    r = np.clip(rng / max(float(max_range_km), 1e-6), 0.0, 1.0) * radius
    theta = np.deg2rad(az - 90.0 + north_angle_deg)
    cx = native_w / 2.0
    cy = native_h / 2.0
    x = cx + np.cos(theta) * r
    y = cy + np.sin(theta) * r
    x, y = orient_xy(x, y, native_w, native_h, flip_h, flip_v, rotation_deg)
    visible = (rng >= 0.0) & (x >= -1.0) & (x <= width) & (y >= -1.0) & (y <= height)
    if np.ndim(range_km) == 0:
        return float(x), float(y), bool(visible)
    return x, y, visible


def xy_to_rangeaz(
    x: np.ndarray | float,
    y: np.ndarray | float,
    width: int,
    height: int,
    *,
    max_range_km: float,
    north_angle_deg: float = 0.0,
    horizon: float = HORIZON,
    flip_h: bool = False,
    flip_v: bool = False,
    rotation_deg: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Inverse of ``rangeaz_to_xy``: overlay pixels to ground range (km) and azimuth."""
    native_w, native_h = _native_size(width, height, rotation_deg)
    xx, yy = inverse_orient_xy(x, y, width, height, flip_h, flip_v, rotation_deg)
    radius = max(native_w, native_h) / 2.0 * float(horizon)
    cx = native_w / 2.0
    cy = native_h / 2.0
    dx = np.asarray(xx, dtype=np.float64) - cx
    dy = np.asarray(yy, dtype=np.float64) - cy
    r = np.hypot(dx, dy)
    range_km = r / max(radius, 1e-6) * float(max_range_km)
    az = (np.degrees(np.arctan2(dy, dx)) + 90.0 - north_angle_deg) % 360.0
    visible = r <= radius * 1.002
    if np.ndim(x) == 0:
        return float(range_km), float(az), bool(visible)
    return range_km, az, visible


def _native_size(width: int, height: int, rotation_deg: int) -> tuple[int, int]:
    if rotation_deg in (90, 270):
        return height, width
    return width, height


def orient_xy(
    x: np.ndarray | float,
    y: np.ndarray | float,
    width: int,
    height: int,
    flip_h: bool,
    flip_v: bool,
    rotation_deg: int,
) -> tuple[np.ndarray | float, np.ndarray | float]:
    """Map native-image coordinates through the same transform as ``imaging.orient``."""
    xx = np.asarray(x, dtype=np.float64).copy()
    yy = np.asarray(y, dtype=np.float64).copy()
    if flip_h:
        xx = (width - 1) - xx
    if flip_v:
        yy = (height - 1) - yy
    if rotation_deg == 90:
        xx, yy = yy, (width - 1) - xx
    elif rotation_deg == 180:
        xx, yy = (width - 1) - xx, (height - 1) - yy
    elif rotation_deg == 270:
        xx, yy = (height - 1) - yy, xx
    if np.ndim(x) == 0:
        return float(xx), float(yy)
    return xx, yy


def inverse_orient_xy(
    x: np.ndarray | float,
    y: np.ndarray | float,
    width: int,
    height: int,
    flip_h: bool,
    flip_v: bool,
    rotation_deg: int,
) -> tuple[np.ndarray | float, np.ndarray | float]:
    """Undo ``orient_xy`` so a simulator can paint into the pre-orient frame."""
    native_w, native_h = _native_size(width, height, rotation_deg)
    xx = np.asarray(x, dtype=np.float64).copy()
    yy = np.asarray(y, dtype=np.float64).copy()
    if rotation_deg == 90:
        xx, yy = (native_w - 1) - yy, xx
    elif rotation_deg == 180:
        xx, yy = (native_w - 1) - xx, (native_h - 1) - yy
    elif rotation_deg == 270:
        xx, yy = yy, (native_h - 1) - xx
    if flip_v:
        yy = (native_h - 1) - yy
    if flip_h:
        xx = (native_w - 1) - xx
    if np.ndim(x) == 0:
        return float(xx), float(yy)
    return xx, yy
