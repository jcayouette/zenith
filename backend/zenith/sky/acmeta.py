"""Aircraft type / registration lookups (adsbdb, hexdb fallback)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zenith.paths import DATA_DIR
from zenith.sky.tle import USER_AGENT

MAX_AGE = timedelta(days=30)
ADSBD_URL = "https://api.adsbdb.com/v0/aircraft/{icao}"
HEXDB_URL = "https://hexdb.io/api/v1/aircraft/{icao}"
ICAO_RE = re.compile(r"^[0-9a-f]{6}$")


def aircraft_dir() -> Path:
    folder = DATA_DIR / "aircraft"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def lookup_aircraft(icao24: str) -> dict | None:
    icao = "".join(ch for ch in icao24.lower() if ch in "0123456789abcdef")
    if not ICAO_RE.match(icao):
        return None
    path = aircraft_dir() / f"{icao}.json"
    if path.is_file():
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        if age < MAX_AGE.total_seconds():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    row = _fetch_adsbdb(icao) or _fetch_hexdb(icao)
    if row is None:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    path.write_text(json.dumps(row), encoding="utf-8")
    return row


def parse_adsbdb(payload: dict, icao: str) -> dict | None:
    aircraft = (payload.get("response") or {}).get("aircraft") if isinstance(payload, dict) else None
    if not isinstance(aircraft, dict) or aircraft.get("error"):
        return None
    return _row(
        icao,
        typecode=aircraft.get("icao_type"),
        model=aircraft.get("type"),
        manufacturer=aircraft.get("manufacturer"),
        registration=aircraft.get("registration"),
        operator=aircraft.get("registered_owner"),
    )


def parse_hexdb(payload: dict, icao: str) -> dict | None:
    if not isinstance(payload, dict) or not (payload.get("Type") or payload.get("ICAOTypeCode")):
        return None
    return _row(
        icao,
        typecode=payload.get("ICAOTypeCode"),
        model=payload.get("Type"),
        manufacturer=payload.get("Manufacturer"),
        registration=payload.get("Registration"),
        operator=payload.get("RegisteredOwners"),
    )


def _row(
    icao: str,
    *,
    typecode: str | None,
    model: str | None,
    manufacturer: str | None,
    registration: str | None,
    operator: str | None,
) -> dict:
    model_s = _clean(model)
    mfr = _clean(manufacturer)
    type_s = _clean(typecode)
    label = " ".join(p for p in (mfr, model_s) if p) or type_s
    return {
        "icao24": icao,
        "typecode": type_s,
        "model": model_s,
        "manufacturer": mfr,
        "registration": _clean(registration),
        "operator": _clean(operator),
        "label": label or None,
    }


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unknown", "none", "n/a", "-"}:
        return None
    return text


def _fetch_adsbdb(icao: str) -> dict | None:
    data = _get_json(ADSBD_URL.format(icao=icao))
    return parse_adsbdb(data, icao) if data else None


def _fetch_hexdb(icao: str) -> dict | None:
    data = _get_json(HEXDB_URL.format(icao=icao))
    return parse_hexdb(data, icao) if data else None


def _get_json(url: str) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except (OSError, urllib.error.HTTPError):
        return None
    text = text.strip()
    if not text or text[0] not in "{[":
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
