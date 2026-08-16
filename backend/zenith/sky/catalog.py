"""Bright-star catalog and IAU constellation stick figures."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data"

CONSTELLATION_NAMES = {
    "And": "Andromeda",
    "Ant": "Antlia",
    "Aps": "Apus",
    "Aql": "Aquila",
    "Aqr": "Aquarius",
    "Ara": "Ara",
    "Ari": "Aries",
    "Aur": "Auriga",
    "Boo": "Boötes",
    "Cae": "Caelum",
    "Cam": "Camelopardalis",
    "Cap": "Capricornus",
    "Car": "Carina",
    "Cas": "Cassiopeia",
    "Cen": "Centaurus",
    "Cep": "Cepheus",
    "Cet": "Cetus",
    "Cha": "Chamaeleon",
    "Cir": "Circinus",
    "CMa": "Canis Major",
    "CMi": "Canis Minor",
    "Cnc": "Cancer",
    "Col": "Columba",
    "Com": "Coma Berenices",
    "CrA": "Corona Australis",
    "CrB": "Corona Borealis",
    "Crt": "Crater",
    "Cru": "Crux",
    "Crv": "Corvus",
    "CVn": "Canes Venatici",
    "Cyg": "Cygnus",
    "Del": "Delphinus",
    "Dor": "Dorado",
    "Dra": "Draco",
    "Equ": "Equuleus",
    "Eri": "Eridanus",
    "For": "Fornax",
    "Gem": "Gemini",
    "Gru": "Grus",
    "Her": "Hercules",
    "Hor": "Horologium",
    "Hya": "Hydra",
    "Hyi": "Hydrus",
    "Ind": "Indus",
    "Lac": "Lacerta",
    "Leo": "Leo",
    "Lep": "Lepus",
    "Lib": "Libra",
    "LMi": "Leo Minor",
    "Lup": "Lupus",
    "Lyn": "Lynx",
    "Lyr": "Lyra",
    "Men": "Mensa",
    "Mic": "Microscopium",
    "Mon": "Monoceros",
    "Mus": "Musca",
    "Nor": "Norma",
    "Oct": "Octans",
    "Oph": "Ophiuchus",
    "Ori": "Orion",
    "Pav": "Pavo",
    "Peg": "Pegasus",
    "Per": "Perseus",
    "Phe": "Phoenix",
    "Pic": "Pictor",
    "PsA": "Piscis Austrinus",
    "Psc": "Pisces",
    "Pup": "Puppis",
    "Pyx": "Pyxis",
    "Ret": "Reticulum",
    "Scl": "Sculptor",
    "Sco": "Scorpius",
    "Sct": "Scutum",
    "Ser": "Serpens",
    "Sex": "Sextans",
    "Sge": "Sagitta",
    "Sgr": "Sagittarius",
    "Tau": "Taurus",
    "Tel": "Telescopium",
    "TrA": "Triangulum Australe",
    "Tri": "Triangulum",
    "Tuc": "Tucana",
    "UMa": "Ursa Major",
    "UMi": "Ursa Minor",
    "Vel": "Vela",
    "Vir": "Virgo",
    "Vol": "Volans",
    "Vul": "Vulpecula",
}

# J2000 names for overlay labels (matched to catalog stars).
NAMED = (
    ("Sirius", 101.287, -16.716),
    ("Canopus", 95.988, -52.696),
    ("Arcturus", 213.915, 19.182),
    ("Vega", 279.234, 38.784),
    ("Capella", 79.172, 45.998),
    ("Rigel", 78.634, -8.202),
    ("Procyon", 114.826, 5.225),
    ("Betelgeuse", 88.793, 7.407),
    ("Achernar", 24.429, -57.237),
    ("Hadar", 210.956, -60.373),
    ("Altair", 297.696, 8.868),
    ("Acrux", 186.650, -63.099),
    ("Aldebaran", 68.980, 16.509),
    ("Antares", 247.352, -26.432),
    ("Spica", 201.298, -11.161),
    ("Pollux", 116.329, 28.026),
    ("Fomalhaut", 344.413, -29.622),
    ("Mimosa", 191.930, -59.689),
    ("Deneb", 310.358, 45.280),
    ("Regulus", 152.093, 11.967),
    ("Adhara", 104.656, -28.972),
    ("Castor", 113.650, 31.888),
    ("Gacrux", 187.791, -57.113),
    ("Shaula", 263.402, -37.104),
    ("Bellatrix", 81.283, 6.350),
    ("Elnath", 81.573, 28.608),
    ("Miaplacidus", 138.300, -69.717),
    ("Alnilam", 84.053, -1.202),
    ("Alnair", 332.058, -46.961),
    ("Alnitak", 85.190, -1.943),
    ("Regor", 122.383, -47.337),
    ("Alioth", 193.507, 55.960),
    ("Mirfak", 51.081, 49.861),
    ("Kaus Australis", 276.043, -34.385),
    ("Dubhe", 165.932, 61.751),
    ("Wezen", 107.098, -26.393),
    ("Alkaid", 206.885, 49.313),
    ("Sargas", 264.330, -42.998),
    ("Avior", 125.628, -59.510),
    ("Menkalinan", 89.882, 44.947),
    ("Atria", 252.166, -69.028),
    ("Alhena", 99.428, 16.399),
    ("Peacock", 306.412, -56.735),
    ("Polaris", 37.954, 89.264),
    ("Mirzam", 95.675, -17.956),
    ("Alphard", 141.897, -8.659),
    ("Hamal", 31.793, 23.462),
    ("Algieba", 154.993, 19.842),
    ("Diphda", 10.897, -17.987),
    ("Nunki", 283.816, -26.297),
    ("Alpheratz", 2.097, 29.090),
    ("Mirach", 17.433, 35.621),
    ("Saiph", 86.939, -9.670),
    ("Rasalhague", 263.734, 12.560),
    ("Algol", 47.042, 40.956),
    ("Almach", 30.975, 42.330),
    ("Denebola", 177.265, 14.572),
    ("Caph", 2.294, 59.150),
    ("Schedar", 10.127, 56.537),
    ("Mizar", 200.981, 54.925),
    ("Sadr", 305.557, 40.257),
    ("Navi", 14.177, 60.717),
    ("Mintaka", 83.002, -0.299),
    ("Kochab", 222.676, 74.155),
    ("Ruchbah", 21.454, 60.235),
    ("Merak", 165.460, 56.382),
    ("Izar", 217.957, 30.371),
    ("Enif", 326.046, 9.875),
    ("Eltanin", 269.152, 51.489),
    ("Phecda", 178.458, 53.695),
    ("Scheat", 345.944, 28.083),
    ("Markab", 346.190, 15.205),
    ("Menkar", 45.570, 4.090),
    ("Sabik", 257.595, -15.725),
    ("Alphecca", 233.672, 26.715),
    ("Dschubba", 240.083, -22.622),
    ("Gienah Cyg", 311.553, 33.970),
    ("Algenib", 3.309, 15.184),
    ("Segin", 28.599, 63.670),
    ("Albireo", 292.680, 27.960),
    ("Megrez", 183.857, 57.033),
    ("Pherkad", 230.182, 71.834),
    ("Cor Caroli", 194.007, 38.318),
    ("Unukalhai", 236.067, 6.426),
    ("Zubeneschamali", 229.252, -9.383),
    ("Zubenelgenubi", 222.720, -16.042),
    ("Alcyone", 56.871, 24.105),
    ("Kaus Media", 275.249, -29.828),
    ("Kaus Borealis", 276.993, -25.422),
    ("Ascella", 281.414, -26.991),
    ("Alnasl", 271.452, -30.424),
    ("Adhafera", 154.173, 23.417),
    ("Rasalas", 148.191, 26.007),
    ("Chertan", 168.527, 20.524),
    ("Zosma", 168.560, 15.430),
    ("Suhail", 136.999, -43.433),
    ("Naos", 120.896, -40.003),
    ("Ankaa", 6.571, -42.306),
    ("Thuban", 211.097, 64.376),
    ("Nekkar", 225.486, 40.391),
    ("Seginus", 228.876, 33.315),
    ("Sadalmelik", 331.446, -0.320),
    ("Sadalsuud", 322.890, -5.571),
)


@lru_cache(maxsize=1)
def load_stars() -> np.ndarray:
    """Nx3 array: RA deg, Dec deg, V mag."""
    raw = json.loads((DATA / "stars.json").read_text(encoding="utf-8"))
    return np.asarray(raw, dtype=np.float64)


@lru_cache(maxsize=1)
def load_constellations() -> list[dict]:
    return _load_line_figures(DATA / "constellations.json", CONSTELLATION_NAMES)


@lru_cache(maxsize=1)
def load_asterisms() -> list[dict]:
    return _load_line_figures(DATA / "asterisms.json", {})


def mag_at(ra: float, dec: float) -> float:
    """V mag of the catalog star nearest to this RA/Dec, or 6.0 if none."""
    key = (round(float(ra), 4), round(float(dec), 4))
    table = _star_mag_index()
    if key in table:
        return table[key]
    stars = load_stars()
    dra = np.abs(stars[:, 0] - ra)
    dra = np.minimum(dra, 360.0 - dra)
    dist = dra * dra + (stars[:, 1] - dec) ** 2
    i = int(np.argmin(dist))
    return float(stars[i, 2]) if dist[i] < 0.05 else 6.0


@lru_cache(maxsize=1)
def _star_mag_index() -> dict[tuple[float, float], float]:
    stars = load_stars()
    return {(round(float(row[0]), 4), round(float(row[1]), 4)): float(row[2]) for row in stars}


def _load_line_figures(path: Path, names: dict[str, str]) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    by_id: dict[str, dict] = {}
    for row in raw:
        abbr = str(row["id"])
        item = by_id.setdefault(
            abbr,
            {"id": abbr, "name": row.get("name") or names.get(abbr, abbr), "lines": []},
        )
        if "name" in row and row["name"]:
            item["name"] = row["name"]
        item["lines"].extend(row["lines"])
    return list(by_id.values())
