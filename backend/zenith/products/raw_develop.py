from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import numpy as np

from zenith.imaging import apply_colour_gains, atomic_write, downscale, encode_jpeg

ProgressFn = Callable[[dict[str, int]], None]


def develop_dng(
    path: Path,
    *,
    bright: float = 2.5,
    colour: tuple[float, float, float] = (1.0, 1.0, 1.0),
    max_side: int = 1920,
) -> np.ndarray:
    """Demosaic a Picamera2 HQ DNG to 8-bit RGB for video. No per-frame auto-bright."""
    import rawpy

    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=8,
            bright=float(bright),
        )
    rgb = apply_colour_gains(rgb, colour[0], colour[1], colour[2])
    if max_side:
        rgb = downscale(rgb, max_side)
    return rgb


def develop_dng_folder(
    src: Path,
    dest: Path,
    *,
    bright: float,
    colour: tuple[float, float, float],
    max_side: int,
    quality: int = 90,
    skip_dirs: list[Path] | None = None,
    on_progress: ProgressFn | None = None,
) -> int:
    """Write one JPEG per DNG. Skip files that are already newer than the DNG."""
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    dngs = sorted(src.glob("*.dng"))
    total = len(dngs)
    written = 0
    developed = 0
    skipped = 0
    extras = [folder for folder in (skip_dirs or []) if folder.is_dir()]
    for index, dng in enumerate(dngs, start=1):
        jpeg = dest / f"{dng.stem}.jpg"
        reused = _reuse_jpeg(dng, jpeg, extras)
        if reused:
            skipped += 1
            written += 1
        else:
            try:
                rgb = develop_dng(dng, bright=bright, colour=colour, max_side=max_side)
            except Exception:
                if on_progress:
                    on_progress(
                        {
                            "done": index,
                            "total": total,
                            "developed": developed,
                            "skipped": skipped,
                        }
                    )
                continue
            atomic_write(jpeg, encode_jpeg(rgb, quality, optimize=False))
            developed += 1
            written += 1
        if on_progress:
            on_progress(
                {
                    "done": index,
                    "total": total,
                    "developed": developed,
                    "skipped": skipped,
                }
            )
    return written


def _reuse_jpeg(dng: Path, dest: Path, extras: list[Path]) -> bool:
    src_mtime = dng.stat().st_mtime
    if dest.is_file() and dest.stat().st_mtime >= src_mtime:
        return True
    for folder in extras:
        alt = folder / dest.name
        if alt.is_file() and alt.stat().st_mtime >= src_mtime:
            if alt.resolve() != dest.resolve():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(alt, dest)
            return True
    return False
