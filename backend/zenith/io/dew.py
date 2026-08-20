"""GPIO dew pad. USB-A VBUS is never cut — the Pi 5 fan is on that rail."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from zenith.config.schema import DewSettings
from zenith.config.store import load_settings, merge_settings, persist_cache
from zenith.sky.sun import sun_altitude_deg

UHUBCTL = "/usr/sbin/uhubctl"
PINCTRL = "/usr/bin/pinctrl"
OPEN_METEO = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,relative_humidity_2m,dew_point_2m,precipitation"
    "&timezone=auto"
)
# BCM GPIO 17 = header pin 11. Avoid 2/3 (I2C / PoE HAT).


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


def ensure_usb_on() -> dict[str, Any]:
    """Force USB-A VBUS on so the Active Cooler 5 V stays up. Never turns it off."""
    errors: list[str] = []
    ok = 0
    for loc in ("1", "2", "3", "4"):
        code, out = _uhubctl("-l", loc, "-a", "1")
        if code == 0:
            ok += 1
        elif out:
            errors.append(out)
    if ok == 0:
        return {"ok": False, "error": errors[-1] if errors else "uhubctl failed"}
    return {"ok": True, "error": None}


def pad_set(pin: int, on: bool) -> dict[str, Any]:
    """Drive the relay Signal pin. Low = heater on (active-low module). Does not touch USB."""
    if not 2 <= int(pin) <= 27 or int(pin) in {2, 3}:
        return {"ok": False, "on": None, "error": f"refusing GPIO {pin} (use 17, not I2C 2/3)"}
    cmd = [PINCTRL, "set", str(int(pin)), "op", "dl" if on else "dh"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
    except FileNotFoundError:
        return {"ok": False, "on": None, "error": f"{PINCTRL} not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "on": None, "error": "pinctrl timed out"}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "pinctrl failed").strip()
        return {"ok": False, "on": None, "error": err}
    return {"ok": True, "on": on, "error": None}


def pad_is_on(pin: int) -> bool | None:
    try:
        proc = subprocess.run(
            [PINCTRL, "get", str(int(pin))], capture_output=True, text=True, timeout=4
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout
    if " op " not in text and ": op" not in text:
        return False
    # Active-low: heater is on when the pin is driven low.
    return " dl " in text or "| lo" in text


def _uhubctl(*args: str) -> tuple[int, str]:
    if "-a" in args:
        idx = args.index("-a")
        if idx + 1 < len(args) and str(args[idx + 1]) in {"0", "off", "Off"}:
            return 1, "refusing USB off (Pi 5 fan shares VBUS)"
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
            "pad_on": None,
            "usb_on": True,
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
        pin = int(dew.gpio_pin)
        pad = pad_is_on(pin)
        return {
            **self.last,
            "mode": dew.mode,
            "interval_min": dew.interval_min,
            "rh_on": dew.rh_on,
            "spread_c": dew.spread_c,
            "gpio_pin": pin,
            "pad_on": pad if pad is not None else self.last.get("pad_on"),
            "usb_on": True,
            "usb_switching": False,
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
        if "gpio_pin" in patch:
            allowed["gpio_pin"] = int(patch["gpio_pin"])
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
        pin = int(dew.gpio_pin)
        error = None
        weather = self.last.get("weather")
        reason = "idle"
        wanted = False
        try:
            usb = ensure_usb_on()
            if not usb["ok"]:
                error = usb.get("error") or "USB force-on failed"
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
            pad = pad_set(pin, wanted)
            if not pad["ok"]:
                error = pad.get("error") or "GPIO switch failed"
            self.last = {
                "mode": dew.mode,
                "pad_on": pad.get("on"),
                "usb_on": True,
                "wanted": wanted,
                "reason": reason,
                "weather": weather,
                "error": error,
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "gpio_pin": pin,
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
