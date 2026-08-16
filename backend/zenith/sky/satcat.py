"""Celestrak SATCAT lookups for the Sky inspector (launch date, site, owner)."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from zenith.paths import DATA_DIR
from zenith.sky.tle import USER_AGENT

MAX_AGE = timedelta(days=30)
SATCAT_URL = "https://celestrak.org/satcat/records.php?CATNR={norad}&FORMAT=JSON"

SITE_NAME = {
    "AFETR": "Cape Canaveral",
    "AFWTR": "Vandenberg",
    "KSCUS": "Kennedy Space Center",
    "WLPIS": "Wallops",
    "KODAK": "Kodiak",
    "TTMTR": "Baikonur",
    "TYMSC": "Baikonur",
    "PKMTR": "Plesetsk",
    "VOSTO": "Vostochny",
    "JSC": "Jiuquan",
    "TSC": "Taiyuan",
    "WSC": "Xichang",
    "WSS": "Wenchang",
    "TNSTA": "Tanegashima",
    "KWAJ": "Kwajalein",
    "FRGUI": "Guiana Space Centre",
    "SRI": "Satish Dhawan",
    "SEAL": "Sea Launch",
    "RLLC": "Rocket Lab LC-1",
    "NSC": "Naro",
}

OPS_STATUS = {
    "+": "Operational",
    "-": "Non-operational",
    "P": "Partially operational",
    "B": "Standby",
    "S": "Spare",
    "X": "Extended mission",
    "D": "Decayed",
    "?": "Unknown",
}

OBJECT_TYPE = {
    "PAY": "Payload",
    "PAYLOAD": "Payload",
    "R/B": "Rocket body",
    "RB": "Rocket body",
    "ROCKET BODY": "Rocket body",
    "DEB": "Debris",
    "DEBRIS": "Debris",
    "UNK": "Unknown",
    "UNKNOWN": "Unknown",
}

OWNER_NAME = {
    "US": "United States",
    "CIS": "Russia / CIS",
    "PRC": "China",
    "ESA": "ESA",
    "ISS": "ISS partnership",
    "JPN": "Japan",
    "IND": "India",
    "FR": "France",
    "GER": "Germany",
    "UK": "United Kingdom",
    "CA": "Canada",
    "IT": "Italy",
    "AUS": "Australia",
    "SKOR": "South Korea",
    "TWN": "Taiwan",
    "UAE": "UAE",
    "SAFR": "South Africa",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "NOR": "Norway",
    "SWE": "Sweden",
    "NTO": "NATO",
    "EUTE": "Eutelsat",
    "SES": "SES",
    "ITSO": "Intelsat",
    "GLOB": "Globalstar",
    "IRID": "Iridium",
    "ORB": "ORBCOMM",
    "SPACEX": "SpaceX",
}

# Public catalogs do not publish a unique essay per NORAD id. These few are well-known.
KNOWN_SUMMARY = {
    "25544": "International Space Station — crewed laboratory in low Earth orbit, run by NASA, Roscosmos, ESA, JAXA, and CSA.",
    "48274": "Tianhe, the core module of China’s Tiangong space station (CSS).",
    "20580": "Hubble Space Telescope — NASA/ESA optical observatory in low Earth orbit.",
}

KIND_SUMMARY = {
    "station": "Crewed space station in low Earth orbit.",
    "starlink": "SpaceX Starlink satellite for consumer broadband internet, flying in a large low-Earth constellation.",
    "oneweb": "Eutelsat OneWeb broadband satellite in a low-Earth constellation.",
    "kuiper": "Amazon Kuiper broadband satellite in a low-Earth constellation.",
    "gnss": "Navigation satellite broadcasting GNSS timing and positioning signals (GPS, Galileo, GLONASS, or BeiDou).",
    "weather": "Weather satellite for Earth imaging and atmospheric measurements.",
    "science": "Scientific spacecraft — astronomy, Earth science, or space physics.",
    "planet": "Planet Labs Earth-imaging cubesat for optical remote sensing.",
    "military": "Military or national-security satellite. Public catalogs list owner and orbit, not a detailed mission.",
    "geo": "Geostationary satellite, typically communications, broadcast, or weather.",
    "comms": "Communications satellite for voice, TV, or data services.",
    "other": "Catalogued Earth-orbiting payload. Public SATCAT records cover identity and orbit, not a narrative mission description.",
}


def satcat_dir() -> Path:
    folder = DATA_DIR / "satcat"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def lookup_satcat(norad: str) -> dict | None:
    nid = "".join(ch for ch in norad if ch.isdigit())
    if not nid:
        return None
    path = satcat_dir() / f"{nid}.json"
    if path.is_file():
        age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        if age < MAX_AGE.total_seconds():
            try:
                return _enrich(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass
    row = _fetch(nid)
    if row is None:
        cached = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        return _enrich(cached)
    path.write_text(json.dumps(row), encoding="utf-8")
    return row


def _enrich(row: dict | None) -> dict | None:
    if not row:
        return row
    site = str(row.get("launch_site") or "").strip()
    if site:
        row = {**row, "launch_site_name": SITE_NAME.get(site) or row.get("launch_site_name")}
    otype = str(row.get("object_type") or "").strip()
    if otype:
        row = {**row, "object_type": OBJECT_TYPE.get(otype.upper(), otype)}
    owner = str(row.get("owner") or "").strip()
    if owner:
        row = {**row, "owner": OWNER_NAME.get(owner, owner)}
    return row


def describe_sat(
    *,
    norad: str | None = None,
    name: str | None = None,
    kind: str | None = None,
    object_type: str | None = None,
) -> str:
    """Short public-catalog purpose. There is no per-object encyclopedia for the full TLE set."""
    nid = "".join(ch for ch in (norad or "") if ch.isdigit())
    if nid in KNOWN_SUMMARY:
        return KNOWN_SUMMARY[nid]
    label = (object_type or "").strip().lower()
    raw_name = (name or "").upper()
    if "DEB" in label or "debris" in label or " DEB" in f" {raw_name} ":
        return "Orbital debris (a fragment or discarded part), not an active spacecraft."
    if "rocket" in label or "r/b" in label or " R/B" in f" {raw_name} ":
        return "Spent rocket stage left in orbit after delivering a payload."
    if "QIANFAN" in raw_name:
        return "Qianfan (Thousand Sails) broadband satellite in a Chinese low-Earth constellation."
    if "HULIANWANG" in raw_name or raw_name.startswith("GW-"):
        return "Guowang / Hulianwang broadband satellite in a Chinese low-Earth constellation."
    if kind and kind in KIND_SUMMARY:
        return KIND_SUMMARY[kind]
    return KIND_SUMMARY["other"]


def _fetch(norad: str) -> dict | None:
    url = SATCAT_URL.format(norad=norad)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    text = text.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return None
    site = str(data.get("LAUNCH_SITE") or "").strip()
    status = str(data.get("OPS_STATUS_CODE") or "").strip()
    otype = str(data.get("OBJECT_TYPE") or "").strip()
    owner = str(data.get("OWNER") or "").strip()
    return {
        "norad": str(data.get("NORAD_CAT_ID") or norad),
        "name": data.get("OBJECT_NAME") or None,
        "object_id": data.get("OBJECT_ID") or None,
        "object_type": OBJECT_TYPE.get(otype.upper(), otype or None),
        "owner": OWNER_NAME.get(owner, owner or None),
        "launch_date": data.get("LAUNCH_DATE") or None,
        "launch_site": site or None,
        "launch_site_name": SITE_NAME.get(site),
        "status": OPS_STATUS.get(status, status or None),
        "period_min": _num(data.get("PERIOD")),
        "inclination_deg": _num(data.get("INCLINATION")),
        "apogee_km": _num(data.get("APOGEE")),
        "perigee_km": _num(data.get("PERIGEE")),
    }


def _num(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
