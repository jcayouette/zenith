"""USB dew pad: manual on/off and auto from Open-Meteo humidity / dew point."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from time import time
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from zenith.config.schema import DewSettings, ZenithSettings
from zenith.config.store import load_settings, merge_settings, persist_cache
from zenith.sky.sun import sun_altitude_deg

UHUBCTL = "/usr/sbin/uhubctl"
OPEN_METEO = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation"
    "&timezone=auto"
)


def want_heat(
    *,
    rh: float | None,
    spread_c: float | None,
    precip_mm: float | None,
    sun_alt: float,
    night_alt: float,
    dew: DewSettings,
) -> tuple[bool, str]:
    """Whether auto mode should power the pad. Night + wet air; not 24/7."""
    night = sun_alt < night_alt
    if not night:
        return False, "day"
    if precip_mm is not None and precip_mm >= 0.1:
        return True, "rain"
    if rh is not None and rh >= dew.rh_on:
        return True, "humidity"
    if spread_c is not None and spread_c <= dew.spread_c:
        return True, "dewpoint"
    return False, "dry"


def fetch_weather(lat: float, lon: float) -> dict[str, Any]:
    url = OPEN_METEO.format(lat=lat, lon=lon)
    with urlopen(url, timeout=12) as resp:
        payload = json.loads(resp.read().decode())
    cur = payload.get("current") or {}
    temp = cur.get("temperature_2m")
    rh = cur.get("relative_humidity_2m")
    dp = cur.get("dew_point_2m")
    spread = None
    if temp is not None and dp is not None:
        spread = round(float(temp) - float(dp), 1)
    return {
        "when": cur.get("time"),
        "temp_c": temp,
        "rh": rh,
        "dewpoint_c": dp,
        "spread_c": spread,
        "precip_mm": cur.get("precipitation"),
    }


def usb_set(on: bool) -> dict[str, Any]:
    action = "1" if on else "0"
    errors: list[str] = []
    ok = 0
    for loc in ("1", "2", "3", "4"):
        code, out = _uhubctl("-l", loc, "-a", action)
        if code == 0:
            ok += 1
        elif out:
            errors.append(out)
    if ok == 0:
        return {"ok": False, "on": None, "error": errors[-1] if errors else "uhubctl failed"}
    return {"ok": True, "on": on, "error": None}


def usb_is_on() -> bool | None:
    code, out = _uhubctl()
    if code != 0:
        return None
    ports = [line for line in out.splitlines() if "Port " in line]
    if not ports:
        return None
    return any(" power" in line for line in ports)


def _uhubctl(*args: str) -> tuple[int, str]:
    cmd = [UHUBCTL, *args]
    if os.geteuid() != 0:
        cmd = ["sudo", "-n", *cmd]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except FileNotFoundError:
        return 1, f"{UHUBCTL} not found"
    except subprocess.TimeoutExpired:
        return 1, "uhubctl timed out"
    text = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, text.strip()


class DewHeater:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self.last: dict[str, Any] = {
            "mode": "off",
            "usb_on": None,
            "wanted": False,
            "reason": "idle",
            "weather": None,
            "error": None,
            "checked_at": None,
        }

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="zenith-dew")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def snapshot(self) -> dict[str, Any]:
        settings = load_settings()
        dew = settings.dew
        usb = usb_is_on()
        return {
            **self.last,
            "mode": dew.mode,
            "interval_min": dew.interval_min,
            "rh_on": dew.rh_on,
            "spread_c": dew.spread_c,
            "usb_on": usb if usb is not None else self.last.get("usb_on"),
            "intervals": [1, 3, 5, 10, 15, 30],
        }

    async def apply(self, patch: dict[str, Any]) -> dict[str, Any]:
        allowed = {}
        if "mode" in patch and patch["mode"] in {"off", "on", "auto"}:
            allowed["mode"] = patch["mode"]
        if "interval_min" in patch:
            allowed["interval_min"] = int(patch["interval_min"])
        if "rh_on" in patch:
            allowed["rh_on"] = float(patch["rh_on"])
        if "spread_c" in patch:
            allowed["spread_c"] = float(patch["spread_c"])
        if allowed:
            merge_settings({"dew": allowed})
            persist_cache()
        await asyncio.to_thread(self.tick)
        self._wake.set()
        return self.snapshot()

    def tick(self) -> dict[str, Any]:
        settings = load_settings()
        dew = settings.dew
        loc = settings.location
        error = None
        weather = self.last.get("weather")
        reason = "idle"
        wanted = False
        try:
            if dew.mode == "on":
                wanted, reason = True, "manual"
            elif dew.mode == "off":
                wanted, reason = False, "manual"
            else:
                try:
                    weather = fetch_weather(loc.latitude, loc.longitude)
                except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                    error = str(exc)
                    weather = self.last.get("weather")
                sun_alt = sun_altitude_deg(loc.latitude, loc.longitude)
                wanted, reason = want_heat(
                    rh=weather.get("rh") if weather else None,
                    spread_c=weather.get("spread_c") if weather else None,
                    precip_mm=weather.get("precip_mm") if weather else None,
                    sun_alt=sun_alt,
                    night_alt=loc.night_sun_altitude_deg,
                    dew=dew,
                )
            usb = usb_set(wanted)
            if not usb["ok"]:
                error = usb.get("error") or "USB switch failed"
            self.last = {
                "mode": dew.mode,
                "usb_on": usb.get("on"),
                "wanted": wanted,
                "reason": reason,
                "weather": weather,
                "error": error,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        except Exception as exc:
            self.last["error"] = str(exc)
        return self.last

    async def _run(self) -> None:
        await asyncio.to_thread(self.tick)
        while True:
            settings = load_settings()
            timeout = max(60, int(settings.dew.interval_min) * 60)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=timeout)
            except TimeoutError:
                pass
            await asyncio.to_thread(self.tick)
