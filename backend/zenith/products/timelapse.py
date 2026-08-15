from __future__ import annotations

import subprocess
from pathlib import Path


def encode_timelapse(
    frame_dir: Path,
    dest: Path,
    fps: int,
    width: int | None = None,
    pattern: str = "*.png",
) -> bool:
    if not frame_dir.is_dir():
        return False
    frames = sorted(p for p in frame_dir.glob(pattern) if p.is_file())
    if len(frames) < 2:
        jpeg_fallback = sorted(p for p in frame_dir.glob("*.jpg") if p.is_file())
        if len(jpeg_fallback) >= 2:
            pattern = "*.jpg"
            frames = jpeg_fallback
        else:
            return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(int(fps)),
        "-pattern_type",
        "glob",
        "-i",
        str(frame_dir / pattern),
    ]
    if width:
        cmd += ["-vf", f"scale={int(width)}:-2"]
    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=900)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False
    return dest.is_file() and dest.stat().st_size > 0
