"""Flat azimuthal-equidistant ground map of the camera's aircraft coverage."""

from __future__ import annotations

import io
import math
import threading
import urllib.error
import urllib.request

import numpy as np
from PIL import Image

from zenith.config.schema import ZenithSettings
from zenith.paths import DATA_DIR
from zenith.sky.aircraft import MAP_RANGE_KM, llh_at_range_az
from zenith.sky.layers import OVERLAY_BAKE_HORIZON
from zenith.sky.project import xy_to_rangeaz
from zenith.sky.tle import USER_AGENT

TILE_STYLE = "voyager"
TILE_URL = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"
TILE_ZOOM = 10
LONG_EDGE = 1600
MAX_TILES = 160

_lock = threading.Lock()


def map_png(settings: ZenithSettings, width: int, height: int) -> bytes:
    loc = settings.location
    scale = min(1.0, LONG_EDGE / max(width, height, 1))
    w = max(8, int(round(width * scale)))
    h = max(8, int(round(height * scale)))
    key = (
        f"eqd_{loc.latitude:.4f}_{loc.longitude:.4f}_{loc.keogram_angle_deg:.2f}_"
        f"{w}x{h}_{int(MAP_RANGE_KM)}"
    )
    cache = DATA_DIR / "mapcache"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{key}.png"
    if path.is_file() and path.stat().st_size > 64:
        return path.read_bytes()
    with _lock:
        if path.is_file() and path.stat().st_size > 64:
            return path.read_bytes()
        png = _render(settings, w, h)
        path.write_bytes(png)
        return png


def _render(settings: ZenithSettings, width: int, height: int) -> bytes:
    loc = settings.location
    yy, xx = np.indices((height, width), dtype=np.float64)
    range_km, az, vis = xy_to_rangeaz(
        xx,
        yy,
        width,
        height,
        max_range_km=MAP_RANGE_KM,
        north_angle_deg=loc.keogram_angle_deg,
        horizon=OVERLAY_BAKE_HORIZON,
        flip_h=False,
        flip_v=False,
        rotation_deg=0,
    )
    lat = np.full(range_km.shape, np.nan)
    lon = np.full(range_km.shape, np.nan)
    if np.any(vis):
        plat, plon = llh_at_range_az(az[vis], range_km[vis], loc.latitude, loc.longitude)
        lat[vis] = plat
        lon[vis] = plon
    rgba = _sample_tiles(lat, lon, vis)
    rgba[~vis] = 0
    rgba[..., 3] = np.where(vis, 255, 0).astype(np.uint8)
    cx, cy = width / 2.0, height / 2.0
    rr = max(3, int(round(min(width, height) * 0.012)))
    _dot(rgba, cx, cy, rr, (125, 211, 199, 220))
    img = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _dot(rgba: np.ndarray, cx: float, cy: float, r: int, color: tuple[int, int, int, int]) -> None:
    h, w = rgba.shape[:2]
    y0, y1 = max(0, int(cy) - r), min(h, int(cy) + r + 1)
    x0, x1 = max(0, int(cx) - r), min(w, int(cx) + r + 1)
    yy, xx = np.ogrid[y0:y1, x0:x1]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= r * r
    rgba[y0:y1, x0:x1][mask] = color


def _sample_tiles(lat: np.ndarray, lon: np.ndarray, vis: np.ndarray) -> np.ndarray:
    out = np.zeros(lat.shape + (4,), dtype=np.uint8)
    if not np.any(vis):
        return out
    valid = vis & np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) < 85.0)
    if not np.any(valid):
        return out
    z = TILE_ZOOM
    n = 2**z
    xs = (lon + 180.0) / 360.0 * n
    lat_r = np.deg2rad(np.clip(lat, -85.0, 85.0))
    ys = (1.0 - np.log(np.tan(lat_r) + 1.0 / np.cos(lat_r)) / math.pi) / 2.0 * n
    tx0 = int(np.floor(np.nanmin(xs[valid])))
    tx1 = int(np.floor(np.nanmax(xs[valid])))
    ty0 = int(np.floor(np.nanmin(ys[valid])))
    ty1 = int(np.floor(np.nanmax(ys[valid])))
    mosaic, origin_x, origin_y = _mosaic(z, tx0, tx1, ty0, ty1)
    if mosaic is None:
        return out
    mh, mw = mosaic.shape[:2]
    px = np.nan_to_num((xs - origin_x) * 256.0, nan=-1.0)
    py = np.nan_to_num((ys - origin_y) * 256.0, nan=-1.0)
    ix = np.clip(np.floor(px).astype(np.int32), 0, mw - 1)
    iy = np.clip(np.floor(py).astype(np.int32), 0, mh - 1)
    inside = valid & (px >= 0) & (py >= 0) & (px < mw) & (py < mh)
    out[inside] = mosaic[iy[inside], ix[inside]]
    return out


def _mosaic(z: int, tx0: int, tx1: int, ty0: int, ty1: int):
    n = 2**z
    tx0 = int(np.clip(tx0, 0, n - 1))
    tx1 = int(np.clip(tx1, 0, n - 1))
    ty0 = int(np.clip(ty0, 0, n - 1))
    ty1 = int(np.clip(ty1, 0, n - 1))
    if tx1 < tx0 or ty1 < ty0:
        return None, 0, 0
    cols = tx1 - tx0 + 1
    rows = ty1 - ty0 + 1
    if cols * rows > MAX_TILES:
        return None, 0, 0
    mosaic = np.zeros((rows * 256, cols * 256, 4), dtype=np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = _tile(z, tx % n, ty)
            if tile is None:
                continue
            y = (ty - ty0) * 256
            x = (tx - tx0) * 256
            mosaic[y : y + 256, x : x + 256] = tile
    return mosaic, tx0, ty0


def _tile(z: int, x: int, y: int) -> np.ndarray | None:
    folder = DATA_DIR / "maptiles"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{TILE_STYLE}_{z}_{x}_{y}.png"
    if not path.is_file():
        sub = "abcd"[(x + y) % 4]
        url = TILE_URL.format(s=sub, z=z, x=x, y=y)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                path.write_bytes(resp.read())
        except (OSError, urllib.error.HTTPError):
            return None
    try:
        img = Image.open(path).convert("RGBA")
        if img.size != (256, 256):
            img = img.resize((256, 256))
    except OSError:
        return None
    return np.array(img)


def tile_png(z: int, x: int, y: int) -> bytes | None:
    arr = _tile(int(z), int(x), int(y))
    if arr is None:
        return None
    buf = io.BytesIO()
    Image.fromarray(arr, "RGBA").save(buf, format="PNG")
    return buf.getvalue()
