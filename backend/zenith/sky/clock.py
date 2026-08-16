from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import subprocess

from zenith.sky.sun import local_time, next_sun_events, sky_session


def system_timezone() -> str:
    tz = _timedatectl("Timezone")
    if tz:
        return tz
    from pathlib import Path

    path = Path("/etc/timezone")
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return "UTC"


def dst_active(tz_name: str, when: datetime | None = None) -> bool:
    local = local_time(tz_name, when)
    offset = local.dst()
    return offset is not None and offset != timedelta(0)


def ntp_status() -> dict[str, Any]:
    synced = _timedatectl("NTPSynchronized")
    ntp = _timedatectl("NTP")
    return {
        "synchronized": synced == "yes",
        "ntp_enabled": ntp == "yes",
        "service": "systemd-timesyncd" if ntp is not None or synced is not None else None,
    }


def clock_snapshot(
    *,
    lat: float,
    lon: float,
    tz_name: str,
    night_threshold: float,
    timezone_auto: bool,
) -> dict[str, Any]:
    session = sky_session(lat, lon, tz_name, night_threshold)
    local = local_time(tz_name)
    ntp = ntp_status()
    offset = local.utcoffset() or timedelta(0)
    hours = offset.total_seconds() / 3600
    offset_label = f"UTC{hours:+.0f}" if hours == int(hours) else f"UTC{hours:+.1f}"
    return {
        "timezone": tz_name,
        "timezone_auto": timezone_auto,
        "timezone_source": "system" if timezone_auto else "config",
        "dst_active": dst_active(tz_name, local),
        "utc_offset": offset_label,
        "local_time": local.strftime("%Y-%m-%d %H:%M:%S"),
        "sun_alt": round(session.sun_alt, 2),
        "mode": session.mode,
        "kind": session.kind,
        "session_date": session.date.isoformat(),
        "ntp": ntp,
        "next": next_sun_events(lat, lon, tz_name, night_threshold),
        "cycle": "sun",
    }


def _timedatectl(key: str) -> str | None:
    try:
        proc = subprocess.run(
            ["timedatectl", "show", f"-p{key}", "--value"],
            capture_output=True,
            text=True,
            timeout=0.6,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    text = (proc.stdout or "").strip()
    return text or None
