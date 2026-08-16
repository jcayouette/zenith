"""Sky overlay geometry in 0–1 image coordinates for the SVG HUD."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.sky.catalog import NAMED, load_asterisms, load_constellations, load_stars, mag_at
from zenith.sky.coords import eq_to_altaz, lst_deg
from zenith.sky.moon import moon_altaz
from zenith.sky.project import altaz_to_xy
from zenith.sky.sun import sun_altitude_deg, sun_azimuth_deg
from zenith.sky.tle import PREFERRED_NORAD, look_azel_batch, overlay_catalog, upcoming_passes, _propagation_set

# Overlay geometry is always projected at this fill; the Sky page scales it to the
# user's overlay-radius slider so stars, grid, and satellites stay locked together.
OVERLAY_BAKE_HORIZON = 1.0

# Short lookahead so the overlay can extrapolate smoothly between ~1 Hz SGP4 samples.
SAT_LOOKAHEAD_S = 1.0


def build_sky(
    settings: ZenithSettings,
    *,
    width: int,
    height: int,
    when: datetime | None = None,
    include_passes: bool = True,
) -> dict:
    utc = when or datetime.now(timezone.utc)
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    loc = settings.location
    sky = settings.sky
    lst = lst_deg(loc.longitude, utc)
    proj = dict(
        width=width,
        height=height,
        north_angle_deg=loc.keogram_angle_deg,
        horizon=OVERLAY_BAKE_HORIZON,
        flip_h=False,
        flip_v=False,
        rotation_deg=0,
    )
    sun_alt = sun_altitude_deg(loc.latitude, loc.longitude, utc)
    sun_az = sun_azimuth_deg(loc.latitude, loc.longitude, utc)
    moon_alt, moon_az = moon_altaz(loc.latitude, loc.longitude, utc)

    payload: dict = {
        "when": utc.isoformat(timespec="seconds"),
        "lst_deg": round(lst, 3),
        "width": width,
        "height": height,
        "layers": {
            "constellations": sky.constellations,
            "constellation_names": sky.constellation_names,
            "asterisms": sky.asterisms,
            "star_names": sky.star_names,
            "grid": sky.grid,
            "planets": sky.planets,
            "satellites": sky.satellites,
        },
        "horizon": float(sky.horizon),
        "projected_horizon": OVERLAY_BAKE_HORIZON,
        "line_width": sky.constellation_line_px,
        "sun": _body("Sun", sun_alt, sun_az, **proj),
        "moon": _body("Moon", moon_alt, moon_az, **proj),
        "stars": [],
        "constellations": [],
        "asterisms": [],
        "star_names": [],
        "grid": [],
        "satellites": [],
        "passes": [],
        "error": None,
    }
    payload["stars"] = _catalog_overlay(loc.latitude, lst, **proj)
    payload["constellations"] = _line_figures(load_constellations(), loc.latitude, lst, **proj)
    payload["asterisms"] = _line_figures(load_asterisms(), loc.latitude, lst, **proj)
    payload["star_names"] = _star_names(loc.latitude, lst, **proj)
    payload["grid"] = _grid(**proj)
    try:
        sats, passes = _satellites(settings, utc, include_passes=include_passes, **proj)
        payload["satellites"] = sats
        payload["passes"] = passes
    except Exception as exc:
        payload["error"] = f"TLE: {exc}"
    payload["tle_count"] = len(overlay_catalog()) if not payload.get("error") else 0
    return payload


def build_sats(
    settings: ZenithSettings,
    *,
    width: int,
    height: int,
    when: datetime | None = None,
    horizon: float | None = None,
) -> dict:
    utc = when or datetime.now(timezone.utc)
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    _ = horizon
    loc = settings.location
    proj = dict(
        width=width,
        height=height,
        north_angle_deg=loc.keogram_angle_deg,
        horizon=OVERLAY_BAKE_HORIZON,
        flip_h=False,
        flip_v=False,
        rotation_deg=0,
    )
    catalog = overlay_catalog()
    payload = {
        "when": utc.isoformat(timespec="seconds"),
        "horizon": float(settings.sky.horizon),
        "projected_horizon": OVERLAY_BAKE_HORIZON,
        "tle_count": len(catalog),
        "dt": SAT_LOOKAHEAD_S,
        "satellites": [],
        "error": None if catalog else "No TLEs yet — Celestrak cache is empty.",
    }
    try:
        payload["satellites"] = _project_sats(settings, utc, catalog, **proj)
    except Exception as exc:
        payload["error"] = f"TLE: {exc}"
    return payload


def catalog_stars_xy(
    settings: ZenithSettings,
    *,
    width: int,
    height: int,
    when: datetime | None = None,
    mag_limit: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pixel positions of catalog stars in the *oriented* frame."""
    utc = when or datetime.now(timezone.utc)
    loc = settings.location
    stars = load_stars()
    limit = settings.sky.mag_limit if mag_limit is None else mag_limit
    pick = stars[stars[:, 2] <= limit]
    alt, az = eq_to_altaz(pick[:, 0], pick[:, 1], loc.latitude, lst_deg(loc.longitude, utc))
    xs, ys, vis = altaz_to_xy(
        alt,
        az,
        width,
        height,
        north_angle_deg=loc.keogram_angle_deg,
        horizon=settings.sky.horizon,
    )
    return xs[vis], ys[vis], pick[vis, 2]


def _norm(x: float, y: float, width: int, height: int) -> dict[str, float]:
    return {"x": round(x / (width or 1), 5), "y": round(y / (height or 1), 5)}


def _project_point(alt: float, az: float, **proj) -> dict | None:
    x, y, vis = altaz_to_xy(alt, az, proj["width"], proj["height"], **_proj_kw(proj))
    if not vis:
        return None
    pt = _norm(x, y, proj["width"], proj["height"])
    pt["alt"] = round(float(alt), 2)
    pt["az"] = round(float(az), 1)
    return pt


def _proj_kw(proj: dict) -> dict:
    return {
        "north_angle_deg": proj["north_angle_deg"],
        "horizon": proj.get("horizon", 1.0),
        "flip_h": proj["flip_h"],
        "flip_v": proj["flip_v"],
        "rotation_deg": proj["rotation_deg"],
    }


def _body(name: str, alt: float, az: float, **proj) -> dict:
    pt = _project_point(alt, az, **proj)
    row = {"name": name, "alt": round(alt, 2), "az": round(az, 1), "visible": pt is not None}
    if pt:
        row.update(pt)
    return row


def _catalog_overlay(lat: float, lst: float, **proj) -> list[dict]:
    stars = load_stars()
    alt, az = eq_to_altaz(stars[:, 0], stars[:, 1], lat, lst)
    xs, ys, vis = altaz_to_xy(alt, az, proj["width"], proj["height"], **_proj_kw(proj))
    out: list[dict] = []
    for x, y, mag, ok in zip(xs, ys, stars[:, 2], vis):
        if not ok:
            continue
        pt = _norm(float(x), float(y), proj["width"], proj["height"])
        pt["mag"] = round(float(mag), 2)
        out.append(pt)
    return out


def _line_figures(figures: list[dict], lat: float, lst: float, **proj) -> list[dict]:
    out: list[dict] = []
    for item in figures:
        lines_xy: list[list[dict]] = []
        label_pts: list[tuple[float, float]] = []
        for line in item["lines"]:
            arr = np.asarray(line, dtype=np.float64)
            mags = [mag_at(float(ra), float(dec)) for ra, dec in arr]
            alt, az = eq_to_altaz(arr[:, 0], arr[:, 1], lat, lst)
            xs, ys, vis = altaz_to_xy(alt, az, proj["width"], proj["height"], **_proj_kw(proj))
            run: list[dict] = []
            for x, y, mag, ok in zip(xs, ys, mags, vis):
                if ok:
                    pt = _norm(float(x), float(y), proj["width"], proj["height"])
                    pt["mag"] = round(float(mag), 2)
                    run.append(pt)
                    label_pts.append((float(x), float(y)))
                elif run:
                    if len(run) >= 2:
                        lines_xy.append(run)
                    run = []
            if len(run) >= 2:
                lines_xy.append(run)
        if not lines_xy:
            continue
        row: dict = {"id": item["id"], "name": item["name"], "lines": lines_xy}
        if label_pts:
            mx = sum(p[0] for p in label_pts) / len(label_pts)
            my = sum(p[1] for p in label_pts) / len(label_pts)
            row["label"] = _norm(mx, my, proj["width"], proj["height"])
        out.append(row)
    return out


def _star_names(lat: float, lst: float, **proj) -> list[dict]:
    stars = load_stars()
    out: list[dict] = []
    for name, ra, dec in NAMED:
        dra = np.abs(stars[:, 0] - ra)
        dra = np.minimum(dra, 360.0 - dra)
        dist = dra * dra + (stars[:, 1] - dec) ** 2
        i = int(np.argmin(dist))
        if dist[i] > 1.0:
            mag = mag_at(ra, dec)
            ra_use, dec_use = ra, dec
        else:
            ra_use, dec_use, mag = float(stars[i, 0]), float(stars[i, 1]), float(stars[i, 2])
        alt, az = eq_to_altaz(ra_use, dec_use, lat, lst)
        pt = _project_point(float(alt), float(az), **proj)
        if pt:
            pt["name"] = name
            pt["mag"] = round(float(mag), 2)
            out.append(pt)
    return out


def _grid(**proj) -> list[dict]:
    rings = []
    label_az = 22.5
    for alt in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0):
        az = np.linspace(0, 360, 73)
        alts = np.full_like(az, alt)
        xs, ys, vis = altaz_to_xy(alts, az, proj["width"], proj["height"], **_proj_kw(proj))
        pts = [
            _norm(float(x), float(y), proj["width"], proj["height"])
            for x, y, ok in zip(xs, ys, vis)
            if ok
        ]
        if len(pts) < 8:
            continue
        row: dict = {"kind": "alt", "alt": alt, "points": pts}
        lab = _project_point(alt, label_az, **proj)
        if lab:
            row["label"] = {"x": lab["x"], "y": lab["y"]}
        rings.append(row)
    zenith = _project_point(90.0, 0.0, **proj)
    if zenith:
        rings.append(
            {
                "kind": "zenith",
                "alt": 90.0,
                "points": [],
                "label": {"x": zenith["x"], "y": zenith["y"]},
            }
        )
    spokes = []
    for az in range(0, 360, 45):
        alts = np.linspace(0, 90, 19)
        azs = np.full_like(alts, float(az))
        xs, ys, vis = altaz_to_xy(alts, azs, proj["width"], proj["height"], **_proj_kw(proj))
        pts = [
            _norm(float(x), float(y), proj["width"], proj["height"])
            for x, y, ok in zip(xs, ys, vis)
            if ok
        ]
        if len(pts) >= 2:
            spokes.append({"kind": "az", "az": az, "points": pts})
    return rings + spokes


def _satellites(settings: ZenithSettings, when: datetime, include_passes: bool, **proj) -> tuple[list, list]:
    catalog = overlay_catalog()
    visible: list[dict] = []
    passes: list[dict] = []
    if include_passes:
        loc = settings.location
        for name, norad, _kind, l1, l2 in catalog:
            if norad not in PREFERRED_NORAD:
                continue
            passes.extend(
                upcoming_passes(
                    name,
                    l1,
                    l2,
                    loc.latitude,
                    loc.longitude,
                    loc.elevation_m,
                    when,
                    hours=24,
                    min_alt=settings.sky.min_sat_alt_deg,
                )
            )
        passes.sort(key=lambda row: row["start"])
    return visible, passes[:12]


def _project_sats(
    settings: ZenithSettings,
    when: datetime,
    catalog: list[tuple[str, str, str, str, str]],
    **proj,
) -> list[dict]:
    if not catalog:
        return []
    loc = settings.location
    utc = when.astimezone(timezone.utc) if when.tzinfo else when.replace(tzinfo=timezone.utc)
    ahead = utc + timedelta(seconds=SAT_LOOKAHEAD_S)
    catalog, recs = _propagation_set()
    if recs is None or not recs or not catalog:
        return []
    az, alt, ok, rng = look_azel_batch(recs, loc.latitude, loc.longitude, loc.elevation_m, [utc, ahead])
    now_az, now_alt, now_ok = az[:, 0], alt[:, 0], ok[:, 0]
    nxt_az, nxt_alt, nxt_ok = az[:, 1], alt[:, 1], ok[:, 1]
    pick = now_ok & (now_alt >= settings.sky.min_sat_alt_deg)
    if not np.any(pick):
        return []
    xs, ys, vis = altaz_to_xy(now_alt, now_az, proj["width"], proj["height"], **_proj_kw(proj))
    nxs, nys, nvis = altaz_to_xy(nxt_alt, nxt_az, proj["width"], proj["height"], **_proj_kw(proj))
    visible: list[dict] = []
    for i, (name, norad, kind, _l1, _l2) in enumerate(catalog):
        if not pick[i] or not vis[i]:
            continue
        pt = _norm(float(xs[i]), float(ys[i]), proj["width"], proj["height"])
        pt["alt"] = round(float(now_alt[i]), 2)
        pt["az"] = round(float(now_az[i]), 1)
        pt["range_km"] = round(float(rng[i, 0]), 1)
        pt["name"] = name
        pt["norad"] = norad
        pt["kind"] = kind
        if nxt_ok[i] and nvis[i]:
            pt["x2"] = round(float(nxs[i]) / (proj["width"] or 1), 5)
            pt["y2"] = round(float(nys[i]) / (proj["height"] or 1), 5)
        visible.append(pt)
    visible.sort(key=lambda row: row.get("alt", 0), reverse=True)
    return visible
