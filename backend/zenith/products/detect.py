"""Frame-to-frame streak finder (meteors / aircraft / satellites). NumPy only."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from zenith.imaging import downscale

DETECT_SIDE = 320


@dataclass
class Streak:
    cx: float
    cy: float
    x0: float
    y0: float
    x1: float
    y1: float
    length_px: float
    aspect: float
    brightness: float
    n_px: int
    persist: int
    bbox: tuple[int, int, int, int]


class StreakDetector:
    def __init__(self) -> None:
        self.prev: np.ndarray | None = None
        self.prev_blobs: list[tuple[float, float, float]] = []
        self._cool: list[tuple[float, float, float]] = []

    def reset(self) -> None:
        self.prev = None
        self.prev_blobs = []
        self._cool = []

    def feed(
        self,
        rgb: np.ndarray,
        *,
        min_length: int,
        min_aspect: float,
        now_s: float,
    ) -> list[Streak]:
        gray = _luma320(rgb)
        prev = self.prev
        self.prev = gray
        if prev is None or prev.shape != gray.shape:
            self.prev_blobs = []
            return []
        diff = np.abs(gray.astype(np.float32) - prev.astype(np.float32))
        mu = float(diff.mean())
        sd = float(diff.std())
        floor = max(18.0, mu + 3.6 * max(sd, 1.0))
        mask = diff >= floor
        if int(mask.sum()) > 0.035 * mask.size:
            self.prev_blobs = []
            return []
        blobs = _components(mask, limit=24)
        streaks: list[Streak] = []
        now_blobs: list[tuple[float, float, float]] = []
        h, w = gray.shape
        self._cool = [(x, y, t) for x, y, t in self._cool if now_s - t < 28]
        for ys, xs in blobs:
            fitted = _fit_streak(ys, xs, h, w, rgb.shape[0], rgb.shape[1], float(gray[ys, xs].mean()))
            if fitted is None:
                continue
            if fitted.length_px < min_length or fitted.aspect < min_aspect:
                continue
            if _disk_radius(fitted.cx, fitted.cy) > 0.49:
                continue
            if _cooled(fitted.cx, fitted.cy, self._cool):
                continue
            persist = 1
            angle = _angle(fitted.x0, fitted.y0, fitted.x1, fitted.y1)
            for px, py, pa in self.prev_blobs:
                if hypot2(fitted.cx - px, fitted.cy - py) < 0.045**2 and _angle_close(angle, pa, 28):
                    persist = 2
                    break
            fitted.persist = persist
            streaks.append(fitted)
            now_blobs.append((fitted.cx, fitted.cy, angle))
            self._cool.append((fitted.cx, fitted.cy, now_s))
        self.prev_blobs = now_blobs
        return streaks


def annotate_crop(rgb: np.ndarray, streak: Streak, side: int = 420) -> np.ndarray:
    """Zoomed crop around the streak with a marker line."""
    h, w = rgb.shape[:2]
    x0 = int(streak.x0 * w)
    y0 = int(streak.y0 * h)
    x1 = int(streak.x1 * w)
    y1 = int(streak.y1 * h)
    pad = max(40, int(0.08 * max(h, w)))
    left = max(0, min(x0, x1) - pad)
    top = max(0, min(y0, y1) - pad)
    right = min(w, max(x0, x1) + pad)
    bottom = min(h, max(y0, y1) + pad)
    crop = rgb[top:bottom, left:right].copy()
    img = Image.fromarray(crop)
    draw = ImageDraw.Draw(img)
    draw.line((x0 - left, y0 - top, x1 - left, y1 - top), fill=(255, 214, 102), width=3)
    if max(img.size) > side:
        img.thumbnail((side, side), Image.Resampling.BILINEAR)
    return np.array(img.convert("RGB"))


def classify_streak(
    streak: Streak,
    sats: list[dict],
    planes: list[dict],
) -> tuple[str, str | None, float | None]:
    """Return (class, matched_name, distance 0-1)."""
    best_sat = _nearest(streak.cx, streak.cy, sats)
    best_ac = _nearest(streak.cx, streak.cy, planes)
    if best_ac and best_ac[1] < 0.035:
        return "aircraft", best_ac[0], best_ac[1]
    if best_sat and best_sat[1] < 0.04:
        return "satellite", best_sat[0], best_sat[1]
    if streak.persist >= 2 and streak.length_px < 40:
        return "satellite", best_sat[0] if best_sat else None, best_sat[1] if best_sat else None
    if streak.length_px >= 22 and streak.aspect >= 3.2:
        kind = "fireball" if streak.brightness > 90 and streak.length_px > 48 else "meteor"
        return kind, None, None
    return "unknown", None, None


def hypot2(dx: float, dy: float) -> float:
    return dx * dx + dy * dy


def _luma320(rgb: np.ndarray) -> np.ndarray:
    small = downscale(rgb, DETECT_SIDE)
    return small.mean(axis=2).astype(np.float32)


def _disk_radius(x: float, y: float) -> float:
    return float(((x - 0.5) ** 2 + (y - 0.5) ** 2) ** 0.5)


def _cooled(x: float, y: float, cool: list[tuple[float, float, float]]) -> bool:
    return any(hypot2(x - cx, y - cy) < 0.055**2 for cx, cy, _t in cool)


def _angle(x0: float, y0: float, x1: float, y1: float) -> float:
    return float(np.degrees(np.arctan2(y1 - y0, x1 - x0)))


def _angle_close(a: float, b: float, tol: float) -> bool:
    d = abs((a - b + 180) % 360 - 180)
    return d <= tol or abs(d - 180) <= tol


def _nearest(x: float, y: float, rows: list[dict]) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for row in rows:
        rx, ry = row.get("x"), row.get("y")
        if rx is None or ry is None:
            continue
        d = float(((x - float(rx)) ** 2 + (y - float(ry)) ** 2) ** 0.5)
        name = str(row.get("name") or row.get("id") or "")
        if best is None or d < best[1]:
            best = (name, d)
    return best


def _components(mask: np.ndarray, limit: int = 24) -> list[tuple[np.ndarray, np.ndarray]]:
    h, w = mask.shape
    seen = np.zeros(mask.shape, dtype=bool)
    out: list[tuple[np.ndarray, np.ndarray]] = []
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = True
        py: list[int] = []
        px: list[int] = []
        while stack:
            cy, cx = stack.pop()
            py.append(cy)
            px.append(cx)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(px) >= 8:
            out.append((np.asarray(py), np.asarray(px)))
        if len(out) >= limit:
            break
    return out


def _fit_streak(
    ys: np.ndarray,
    xs: np.ndarray,
    h: int,
    w: int,
    full_h: int,
    full_w: int,
    brightness: float,
) -> Streak | None:
    pts = np.column_stack((xs.astype(np.float64), ys.astype(np.float64)))
    mean = pts.mean(axis=0)
    centered = pts - mean
    if pts.shape[0] < 8:
        return None
    cov = np.cov(centered, rowvar=False)
    if cov.shape != (2, 2):
        return None
    evals, evecs = np.linalg.eigh(cov)
    order = np.argsort(evals)[::-1]
    major = evecs[:, order[0]]
    proj = centered @ major
    length = float(proj.max() - proj.min())
    width = float(max(np.sqrt(max(float(evals[order[1]]), 1e-6)) * 2.4, 0.8))
    aspect = length / width
    i0 = int(np.argmin(proj))
    i1 = int(np.argmax(proj))
    scale = max(full_w, full_h) / max(w, h)
    x0, y0 = float(pts[i0, 0]) / w, float(pts[i0, 1]) / h
    x1, y1 = float(pts[i1, 0]) / w, float(pts[i1, 1]) / h
    x_min, x_max = int(xs.min()), int(xs.max())
    y_min, y_max = int(ys.min()), int(ys.max())
    return Streak(
        cx=float(mean[0]) / w,
        cy=float(mean[1]) / h,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        length_px=length * scale,
        aspect=aspect,
        brightness=brightness,
        n_px=int(pts.shape[0]),
        persist=1,
        bbox=(x_min, y_min, x_max, y_max),
    )
