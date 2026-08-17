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
ROUTE_AGE = timedelta(hours=1)
MISS_AGE = timedelta(minutes=15)
ADSBD_URL = "https://api.adsbdb.com/v0/aircraft/{icao}"
ADSBD_CALLSIGN_URL = "https://api.adsbdb.com/v0/callsign/{callsign}"
HEXDB_URL = "https://hexdb.io/api/v1/aircraft/{icao}"
HEXDB_ROUTE_URL = "https://hexdb.io/callsign-route-api?callsign={callsign}"
ICAO_RE = re.compile(r"^[0-9a-f]{6}$")
CALLSIGN_RE = re.compile(r"^[A-Z0-9]{3,8}$")


def aircraft_dir() -> Path:
    folder = DATA_DIR / "aircraft"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def routes_dir() -> Path:
    folder = DATA_DIR / "routes"
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


def lookup_route(callsign: str) -> dict | None:
    """Origin / destination for a flight callsign (adsbdb, hexdb fallback)."""
    cs = _norm_callsign(callsign)
    if not cs:
        return None
    path = routes_dir() / f"{cs}.json"
    cached = _read_cache(path)
    if cached is not False:
        return cached or None
    row = _fetch_adsbdb_route(cs) or _fetch_hexdb_route(cs)
    path.write_text(json.dumps(row or {}), encoding="utf-8")
    return row


def parse_adsbdb_route(payload: dict, callsign: str) -> dict | None:
    route = (payload.get("response") or {}).get("flightroute") if isinstance(payload, dict) else None
    if not isinstance(route, dict) or route.get("error"):
        return None
    origin = _airport(route.get("origin"))
    dest = _airport(route.get("destination"))
    if not origin and not dest:
        return None
    airline = route.get("airline") if isinstance(route.get("airline"), dict) else {}
    codes = [p["code"] for p in (origin, dest) if p and p.get("code")]
    return {
        "callsign": callsign,
        "airline": _clean(airline.get("name")) if airline else None,
        "origin": origin,
        "destination": dest,
        "route": " → ".join(codes) if len(codes) == 2 else None,
    }


def parse_hexdb_route(payload: dict, callsign: str) -> dict | None:
    if not isinstance(payload, dict):
        return None
    origin = _airport_code(payload.get("origin") or payload.get("Origin"))
    dest = _airport_code(payload.get("destination") or payload.get("Destination"))
    if not origin and not dest:
        return None
    codes = [p["code"] for p in (origin, dest) if p]
    return {
        "callsign": callsign,
        "airline": None,
        "origin": origin,
        "destination": dest,
        "route": " → ".join(codes) if len(codes) == 2 else None,
    }


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


def _fetch_adsbdb_route(callsign: str) -> dict | None:
    data = _get_json(ADSBD_CALLSIGN_URL.format(callsign=callsign))
    return parse_adsbdb_route(data, callsign) if data else None


def _fetch_hexdb_route(callsign: str) -> dict | None:
    data = _get_json(HEXDB_ROUTE_URL.format(callsign=callsign))
    return parse_hexdb_route(data, callsign) if data else None


def _norm_callsign(value: str) -> str | None:
    cs = "".join(ch for ch in str(value or "").upper() if ch.isalnum())
    if not CALLSIGN_RE.match(cs):
        return None
    if ICAO_RE.match(cs.lower()):
        return None
    return cs


def _airport(raw) -> dict | None:
    if isinstance(raw, str):
        return _airport_code(raw)
    if not isinstance(raw, dict):
        return None
    iata = _clean(raw.get("iata_code") or raw.get("iata"))
    icao = _clean(raw.get("icao_code") or raw.get("icao"))
    city = _clean(raw.get("municipality") or raw.get("city"))
    name = _clean(raw.get("name"))
    code = iata or icao
    if not code and not city and not name:
        return None
    place = city or name
    label = " · ".join(p for p in (code, place) if p)
    return {
        "code": code,
        "iata": iata,
        "icao": icao,
        "city": city,
        "name": name,
        "label": label or None,
    }


def _airport_code(value) -> dict | None:
    code = _clean(value)
    if not code:
        return None
    code = code.upper()
    return {"code": code, "iata": None, "icao": code if len(code) == 4 else None, "city": None, "name": None, "label": code}


def _read_cache(path: Path) -> dict | bool:
    """Cached JSON object, empty dict for a remembered miss, or False if stale."""
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
    limit = ROUTE_AGE.total_seconds() if data else MISS_AGE.total_seconds()
    if age >= limit:
        return False
    return data


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
