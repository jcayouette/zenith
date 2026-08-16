from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from threading import Lock
from typing import Any

from zenith.paths import DATA_DIR
from zenith.sky.clock import ntp_status

_CPU_LOCK = Lock()
_CPU_SAMPLE: tuple[int, int] | None = None

_THROTTLE_BITS = (
    (0, "under_voltage", "Under-voltage now"),
    (1, "arm_freq_capped", "ARM frequency capped"),
    (2, "currently_throttled", "Throttling now"),
    (3, "soft_temp_limit", "Soft temperature limit"),
    (16, "under_voltage_occurred", "Under-voltage since boot"),
    (17, "arm_freq_capped_occurred", "ARM cap since boot"),
    (18, "throttled_occurred", "Throttling since boot"),
    (19, "soft_temp_limit_occurred", "Soft temp limit since boot"),
)


def collect() -> dict[str, Any]:
    memory = _memory()
    disks = _disks()
    temps = _temps()
    cpu = _cpu()
    power = _power()
    ntp = ntp_status()
    payload = {
        "hostname": socket.gethostname(),
        "uptime_s": _uptime(),
        "cpu": cpu,
        "memory": memory,
        "disks": disks,
        "temps": temps,
        "power": power,
        "ntp": ntp,
        "process": _process(),
        "alerts": [],
    }
    payload["alerts"] = _alerts(payload)
    return payload


def parse_throttled(value: int) -> dict[str, Any]:
    flags = {name: bool(value & (1 << bit)) for bit, name, _ in _THROTTLE_BITS}
    active = [name for name, on in flags.items() if on]
    return {
        "hex": f"0x{value:x}",
        "value": value,
        "throttled": bool(value & 0xF),
        "flags": flags,
        "active": active,
    }


def cpu_percent_from_samples(prev: tuple[int, int], curr: tuple[int, int]) -> float | None:
    d_total = curr[0] - prev[0]
    d_idle = curr[1] - prev[1]
    if d_total <= 0:
        return None
    used = 1.0 - (d_idle / d_total)
    return round(max(0.0, min(100.0, used * 100.0)), 1)


def _cpu() -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    cores = os.cpu_count() or 1
    sample = _read_cpu_times()
    percent = None
    global _CPU_SAMPLE
    with _CPU_LOCK:
        prev = _CPU_SAMPLE
        _CPU_SAMPLE = sample
        if prev is not None and sample is not None:
            percent = cpu_percent_from_samples(prev, sample)
    freq = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    freq_max = _read_int("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
    governor = _read_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    return {
        "percent": percent,
        "load_1": round(load1, 2),
        "load_5": round(load5, 2),
        "load_15": round(load15, 2),
        "load_percent": round(min(100.0, (load1 / cores) * 100.0), 1),
        "cores": cores,
        "freq_mhz": round(freq / 1000) if freq else None,
        "freq_max_mhz": round(freq_max / 1000) if freq_max else None,
        "governor": governor,
    }


def _read_cpu_times() -> tuple[int, int] | None:
    try:
        line = Path("/proc/stat").read_text().splitlines()[0]
    except OSError:
        return None
    parts = line.split()
    if not parts or parts[0] != "cpu":
        return None
    nums = [int(x) for x in parts[1:]]
    if len(nums) < 4:
        return None
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return sum(nums), idle


def _memory() -> dict[str, Any]:
    info = _meminfo()
    total = info.get("MemTotal", 0) * 1024
    available = info.get("MemAvailable", info.get("MemFree", 0)) * 1024
    used = max(0, total - available)
    swap_total = info.get("SwapTotal", 0) * 1024
    swap_free = info.get("SwapFree", 0) * 1024
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "percent": _pct(used, total),
        "swap_total_bytes": swap_total,
        "swap_used_bytes": max(0, swap_total - swap_free),
        "swap_percent": _pct(max(0, swap_total - swap_free), swap_total) if swap_total else 0.0,
    }


def _meminfo() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        text = Path("/proc/meminfo").read_text()
    except OSError:
        return out
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        num = rest.strip().split()[0]
        try:
            out[key] = int(num)
        except ValueError:
            continue
    return out


def _disks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = _disk_row(DATA_DIR, "Archive")
    root = _disk_row(Path("/"), "System")
    if data and root and _same_volume(data, root):
        data["label"] = "Disk"
        data["path"] = str(DATA_DIR)
        rows = [data]
    else:
        if data:
            rows.append(data)
        if root:
            rows.append(root)
    for row in rows:
        row.pop("_blocks", None)
        row.pop("_bsize", None)
    return rows


def _disk_row(path: Path, label: str) -> dict[str, Any] | None:
    try:
        usage = shutil.disk_usage(path)
        st = os.statvfs(path)
    except OSError:
        return None
    return {
        "path": str(path),
        "label": label,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "percent": _pct(usage.used, usage.total),
        "_blocks": int(st.f_blocks),
        "_bsize": int(st.f_frsize or st.f_bsize),
    }


def _same_volume(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a["_blocks"] == b["_blocks"] and a["_bsize"] == b["_bsize"] and a["total_bytes"] == b["total_bytes"]


def _temps() -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        kind = _read_text(zone / "type") or zone.name
        milli = _read_int(zone / "temp")
        if milli is None:
            continue
        label, key = _temp_label(kind)
        found[key] = {"id": key, "label": label, "celsius": round(milli / 1000.0, 1), "source": kind}
    for hw in sorted(Path("/sys/class/hwmon").glob("hwmon*")):
        chip = _read_text(hw / "name") or hw.name
        for inp in sorted(hw.glob("temp*_input")):
            milli = _read_int(inp)
            if milli is None:
                continue
            tag = _read_text(inp.with_name(inp.name.replace("_input", "_label"))) or chip
            label, key = _temp_label(chip, tag)
            if key in found and abs(found[key]["celsius"] - milli / 1000.0) < 1.5:
                continue
            found[key] = {
                "id": key,
                "label": label,
                "celsius": round(milli / 1000.0, 1),
                "source": f"{chip}:{tag}",
            }
    soc = _vcgencmd_temp("")
    pmic = _vcgencmd_temp("pmic")
    if soc is not None and "cpu" not in found:
        found["cpu"] = {"id": "cpu", "label": "CPU", "celsius": soc, "source": "vcgencmd"}
    if pmic is not None:
        found["pmic"] = {"id": "pmic", "label": "PMIC", "celsius": pmic, "source": "vcgencmd"}
    order = ["cpu", "pmic", "rp1", "nvme"]
    rest = [k for k in found if k not in order]
    return [found[k] for k in order + rest if k in found]


def _temp_label(kind: str, tag: str = "") -> tuple[str, str]:
    blob = f"{kind} {tag}".lower()
    if "nvme" in blob:
        if "composite" in blob or tag.lower() in {"", "composite"}:
            return "NVMe", "nvme"
        return f"NVMe {tag}", f"nvme-{_slug(tag)}"
    if "rp1" in blob:
        return "RP1", "rp1"
    if "pmic" in blob:
        return "PMIC", "pmic"
    if "cpu" in blob or "soc" in blob:
        return "CPU", "cpu"
    if "gpu" in blob:
        return "GPU", "gpu"
    label = tag or kind
    return label, _slug(label)


def _power() -> dict[str, Any]:
    raw = _vcgencmd("get_throttled")
    value = 0
    if raw:
        match = re.search(r"0x[0-9a-fA-F]+", raw)
        if match:
            value = int(match.group(0), 16)
    parsed = parse_throttled(value)
    parsed["core_volts"] = _vcgencmd_volts()
    parsed["under_voltage_alarm"] = _undervolt_alarm()
    return parsed


def _undervolt_alarm() -> bool | None:
    root = Path("/sys/class/hwmon")
    if not root.is_dir():
        return None
    for alarm in root.glob("hwmon*/in0_lcrit_alarm"):
        val = _read_int(alarm)
        if val is not None:
            return bool(val)
    return None


def _process() -> dict[str, Any]:
    status = _proc_status()
    rss_kb = status.get("VmRSS", 0)
    return {
        "pid": os.getpid(),
        "rss_bytes": rss_kb * 1024,
        "threads": status.get("Threads", 0),
    }


def _proc_status() -> dict[str, int]:
    out: dict[str, int] = {}
    try:
        text = Path("/proc/self/status").read_text()
    except OSError:
        return out
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, rest = line.split(":", 1)
        num = rest.strip().split()[0]
        try:
            out[key] = int(num)
        except ValueError:
            continue
    return out


def _alerts(payload: dict[str, Any]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    cpu_temp = next((t["celsius"] for t in payload["temps"] if t["id"] == "cpu"), None)
    if cpu_temp is not None:
        if cpu_temp >= 80:
            alerts.append({"level": "crit", "code": "temp", "message": f"CPU {cpu_temp:.0f}°C — throttling likely"})
        elif cpu_temp >= 70:
            alerts.append({"level": "warn", "code": "temp", "message": f"CPU {cpu_temp:.0f}°C — getting warm"})
    nvme = next((t["celsius"] for t in payload["temps"] if t["id"] == "nvme"), None)
    if nvme is not None and nvme >= 70:
        alerts.append({"level": "warn", "code": "temp", "message": f"NVMe {nvme:.0f}°C"})
    mem = payload["memory"]
    if mem["total_bytes"] and mem["percent"] >= 92:
        alerts.append({"level": "crit", "code": "ram", "message": "RAM almost full"})
    elif mem["total_bytes"] and mem["percent"] >= 85:
        alerts.append({"level": "warn", "code": "ram", "message": "RAM is high"})
    for disk in payload["disks"]:
        free_gb = disk["free_bytes"] / (1024**3)
        if disk["percent"] >= 95 or free_gb < 5:
            alerts.append(
                {
                    "level": "crit",
                    "code": "disk",
                    "message": f"{disk['label']} has {free_gb:.1f} GB free",
                }
            )
        elif disk["percent"] >= 85 or free_gb < 15:
            alerts.append(
                {
                    "level": "warn",
                    "code": "disk",
                    "message": f"{disk['label']} has {free_gb:.1f} GB free",
                }
            )
    power = payload["power"]
    if power.get("flags", {}).get("under_voltage") or power.get("under_voltage_alarm"):
        alerts.append({"level": "crit", "code": "power", "message": "Under-voltage detected"})
    elif power.get("throttled"):
        alerts.append({"level": "warn", "code": "power", "message": "CPU is throttling"})
    elif power.get("flags", {}).get("under_voltage_occurred"):
        alerts.append({"level": "warn", "code": "power", "message": "Under-voltage occurred since boot"})
    cpu = payload["cpu"]
    busy = cpu.get("percent")
    if busy is not None and busy >= 95:
        alerts.append({"level": "warn", "code": "cpu", "message": f"CPU {busy:.0f}%"})
    ntp = payload.get("ntp") or {}
    if ntp.get("ntp_enabled") is False:
        alerts.append({"level": "warn", "code": "ntp", "message": "NTP is off — day/night times can drift"})
    elif ntp.get("synchronized") is False:
        alerts.append({"level": "warn", "code": "ntp", "message": "Clock is not NTP-synced"})
    if not alerts:
        alerts.append({"level": "ok", "code": "ok", "message": "Pi looks healthy"})
    return alerts


def _uptime() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _vcgencmd(arg: str) -> str | None:
    try:
        proc = subprocess.run(
            ["vcgencmd", arg] if arg.count(" ") == 0 else ["vcgencmd", *arg.split()],
            capture_output=True,
            text=True,
            timeout=0.6,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    text = (proc.stdout or "").strip()
    return text or None


def _vcgencmd_temp(which: str) -> float | None:
    raw = _vcgencmd("measure_temp pmic" if which == "pmic" else "measure_temp")
    if not raw:
        return None
    match = re.search(r"temp=([0-9.]+)", raw)
    return round(float(match.group(1)), 1) if match else None


def _vcgencmd_volts() -> float | None:
    raw = _vcgencmd("measure_volts")
    if not raw:
        return None
    match = re.search(r"volt=([0-9.]+)", raw)
    return round(float(match.group(1)), 4) if match else None


def _read_text(path: str | Path) -> str | None:
    try:
        return Path(path).read_text().strip() or None
    except OSError:
        return None


def _read_int(path: str | Path) -> int | None:
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text.split()[0])
    except ValueError:
        return None


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100.0, 1)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "sensor"
