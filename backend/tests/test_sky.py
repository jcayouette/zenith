from __future__ import annotations

import unittest
from datetime import datetime, timezone

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.imaging import orient
from zenith.sky.catalog import load_asterisms, load_constellations, load_stars, mag_at
from zenith.sky.tle import classify_sat, display_name, intl_designator, norad_id, parse_tles
from zenith.sky.coords import eq_to_altaz, lst_deg
from zenith.sky.layers import build_sky
from zenith.sky.project import altaz_to_xy, inverse_orient_xy, orient_xy
from zenith.sky.sun import sun_azimuth_deg


class CoordTests(unittest.TestCase):
    def test_polaris_altitude_near_latitude(self):
        lat, lon = 49.6314, 10.8772
        when = datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)
        alt, az = eq_to_altaz(37.954, 89.264, lat, lst_deg(lon, when))
        self.assertAlmostEqual(alt, lat, delta=1.2)
        self.assertTrue(az < 20 or az > 340)

    def test_berlin_summer_noon_sun_is_south(self):
        when = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
        az = sun_azimuth_deg(52.52, 13.4, when)
        self.assertGreater(az, 150)
        self.assertLess(az, 210)


class ProjectTests(unittest.TestCase):
    def test_zenith_is_centre(self):
        x, y, vis = altaz_to_xy(90.0, 0.0, 200, 200)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 100.0, delta=0.6)
        self.assertAlmostEqual(y, 100.0, delta=0.6)

    def test_north_horizon_is_up(self):
        x, y, vis = altaz_to_xy(0.0, 0.0, 200, 200)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 100.0, delta=2)
        self.assertLess(y, 20)

    def test_east_horizon_is_right(self):
        x, y, vis = altaz_to_xy(0.0, 90.0, 200, 200)
        self.assertTrue(vis)
        self.assertGreater(x, 180)
        self.assertAlmostEqual(y, 100.0, delta=2)

    def test_wide_frame_horizon_reaches_long_edge(self):
        x, y, vis = altaz_to_xy(0.0, 90.0, 400, 300)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 400.0, delta=2)
        self.assertAlmostEqual(y, 150.0, delta=2)

    def test_xy_to_altaz_roundtrip(self):
        from zenith.sky.project import xy_to_altaz

        for alt, az in ((90.0, 0.0), (45.0, 30.0), (12.0, 270.0), (8.0, 180.0)):
            x, y, vis = altaz_to_xy(alt, az, 200, 200, north_angle_deg=15)
            self.assertTrue(vis)
            a2, z2, ok = xy_to_altaz(x, y, 200, 200, north_angle_deg=15)
            self.assertTrue(ok)
            self.assertAlmostEqual(a2, alt, delta=0.4)
            if alt < 89:
                daz = abs((z2 - az + 180) % 360 - 180)
                self.assertLess(daz, 0.5)

    def test_rangeaz_roundtrip_and_north_is_up(self):
        from zenith.sky.project import rangeaz_to_xy, xy_to_rangeaz

        x, y, vis = rangeaz_to_xy(0.0, 0.0, 200, 200, max_range_km=420)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 100.0, delta=0.6)
        self.assertAlmostEqual(y, 100.0, delta=0.6)
        x, y, vis = rangeaz_to_xy(420.0, 0.0, 200, 200, max_range_km=420)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 100.0, delta=2)
        self.assertLess(y, 20)
        x, y, vis = rangeaz_to_xy(50.0, 0.0, 200, 200, max_range_km=420)
        self.assertTrue(vis)
        self.assertAlmostEqual(x, 100.0, delta=2)
        self.assertAlmostEqual(y, 100.0 - (50.0 / 420.0) * 100.0, delta=2)
        r2, az2, ok = xy_to_rangeaz(x, y, 200, 200, max_range_km=420)
        self.assertTrue(ok)
        self.assertAlmostEqual(r2, 50.0, delta=0.8)
        self.assertLess(min(az2, 360 - az2), 1.0)

    def test_orient_xy_matches_numpy(self):
        h, w = 5, 8
        y0, x0 = 1, 6
        img = np.zeros((h, w), dtype=np.uint8)
        img[y0, x0] = 1
        rgb = np.stack([img, img, img], axis=-1)
        for fh in (False, True):
            for fv in (False, True):
                for rot in (0, 90, 180, 270):
                    out = orient(rgb.copy(), fh, fv, rot)
                    ys, xs = np.where(out[:, :, 0] == 1)
                    px, py = orient_xy(x0, y0, w, h, fh, fv, rot)
                    self.assertEqual(int(xs[0]), int(round(px)), msg=(fh, fv, rot))
                    self.assertEqual(int(ys[0]), int(round(py)), msg=(fh, fv, rot))

    def test_inverse_orient_roundtrip(self):
        w, h = 200, 160
        x, y = 40.0, 90.0
        for rot in (0, 90, 180, 270):
            ow, oh = (h, w) if rot in (90, 270) else (w, h)
            xo, yo = orient_xy(x, y, w, h, True, True, rot)
            xi, yi = inverse_orient_xy(xo, yo, ow, oh, True, True, rot)
            self.assertAlmostEqual(xi, x, delta=1e-6)
            self.assertAlmostEqual(yi, y, delta=1e-6)


class CatalogTests(unittest.TestCase):
    def test_catalog_has_sirius_and_cygnus(self):
        stars = load_stars()
        self.assertGreater(len(stars), 4000)
        self.assertLess(stars[0, 2], 0)  # Sirius
        ids = {row["id"] for row in load_constellations()}
        self.assertIn("Cyg", ids)
        self.assertIn("UMa", ids)

    def test_constellation_vertices_have_magnitudes(self):
        for item in load_constellations():
            for line in item["lines"]:
                for ra, dec in line:
                    self.assertLessEqual(mag_at(float(ra), float(dec)), 6.0)

    def test_asterisms_include_summer_triangle(self):
        ids = {row["id"] for row in load_asterisms()}
        self.assertIn("summer-triangle", ids)
        self.assertIn("big-dipper", ids)
        self.assertIn("teapot", ids)

    def test_summer_triangle_above_horizon(self):
        settings = ZenithSettings()
        settings.location.latitude = 49.6314
        settings.location.longitude = 10.8772
        when = datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)
        sky = build_sky(settings, width=720, height=720, when=when, include_passes=False)
        names = {row["name"] for row in sky["star_names"]}
        self.assertTrue({"Vega", "Deneb", "Altair"} <= names)
        cyg = next(row for row in sky["constellations"] if row["id"] == "Cyg")
        self.assertGreater(len(cyg["lines"]), 0)
        self.assertIn("label", cyg)
        self.assertTrue(all("mag" in pt for line in cyg["lines"] for pt in line))
        self.assertGreater(len(sky["stars"]), 200)
        bright = [s for s in sky["stars"] if s["mag"] <= 2.0]
        faint = [s for s in sky["stars"] if s["mag"] <= 5.0]
        self.assertGreater(len(faint), len(bright))
        ast = {row["id"] for row in sky["asterisms"]}
        self.assertIn("summer-triangle", ast)
        uma = next(row for row in sky["constellations"] if row["id"] == "UMa")
        mags = [pt["mag"] for line in uma["lines"] for pt in line]
        self.assertTrue(any(m <= 2.0 for m in mags))
        self.assertTrue(any(m > 3.0 for m in mags))

    def test_overlay_scale_does_not_rebake_coordinates(self):
        settings = ZenithSettings()
        settings.location.latitude = 49.6314
        settings.location.longitude = 10.8772
        when = datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc)
        settings.sky.horizon = 1.0
        wide = build_sky(settings, width=720, height=720, when=when, include_passes=False)
        settings.sky.horizon = 0.5
        tight = build_sky(settings, width=720, height=720, when=when, include_passes=False)
        self.assertEqual(wide["projected_horizon"], 1.0)
        self.assertEqual(tight["projected_horizon"], 1.0)
        self.assertAlmostEqual(wide["stars"][0]["x"], tight["stars"][0]["x"], places=4)
        self.assertAlmostEqual(wide["stars"][0]["y"], tight["stars"][0]["y"], places=4)


class TleTests(unittest.TestCase):
    def test_display_name_prefers_iss(self):
        l1 = "1 25544U 98067A   26228.18012382  .00004999  00000+0  97292-4 0  9998"
        self.assertEqual(norad_id(l1), "25544")
        self.assertEqual(display_name("ISS (ZARYA)", l1), "ISS")
        self.assertEqual(intl_designator(l1), "1998-067A")
        self.assertIsNone(display_name("FREGAT DEB", "1 49271U 11037PF  26228.29031530  .00012011  00000+0  18802-1 0  9992"))

    def test_parse_three_line_tles(self):
        text = (
            "ISS (ZARYA)\n"
            "1 25544U 98067A   26228.18012382  .00004999  00000+0  97292-4 0  9998\n"
            "2 25544  51.6332   3.1747 0007602  51.3505 308.8163 15.49457398581051\n"
        )
        rows = parse_tles(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "ISS (ZARYA)")

    def test_look_azel_batch_empty(self):
        from zenith.sky.tle import look_azel_batch

        az, el, ok, rng = look_azel_batch([], 49.6314, 10.8772, 296, [])
        self.assertEqual(az.shape[0], 0)
        self.assertEqual(el.shape, az.shape)
        self.assertEqual(ok.shape, az.shape)
        self.assertEqual(rng.shape, az.shape)

    def test_classify_starlink_and_military(self):
        self.assertEqual(classify_sat("STARLINK-1234", "visual"), "starlink")
        self.assertEqual(classify_sat("USA 234", "military"), "military")
        self.assertEqual(classify_sat("NAVSTAR 81", "gps-ops"), "gnss")
        self.assertEqual(classify_sat("KUIPER-1", "kuiper"), "kuiper")
        self.assertEqual(classify_sat("FLOCK 4Y-1", "planet"), "planet")


class SatcatTests(unittest.TestCase):
    def test_rejects_empty_norad(self):
        from zenith.sky.satcat import lookup_satcat

        self.assertIsNone(lookup_satcat(""))
        self.assertIsNone(lookup_satcat("abc"))

    def test_launch_site_names(self):
        from zenith.sky.satcat import SITE_NAME

        self.assertEqual(SITE_NAME["AFETR"], "Cape Canaveral")
        self.assertEqual(SITE_NAME["TTMTR"], "Baikonur")
        self.assertEqual(SITE_NAME["TYMSC"], "Baikonur")
        self.assertEqual(SITE_NAME["FRGUI"], "Guiana Space Centre")

    def test_describe_known_and_kinds(self):
        from zenith.sky.satcat import describe_sat

        self.assertIn("International Space Station", describe_sat(norad="25544", kind="station"))
        self.assertIn("Starlink", describe_sat(name="STARLINK-1234", kind="starlink"))
        self.assertIn("debris", describe_sat(name="FENGYUN 1C DEB", object_type="DEB").lower())
        self.assertIn("rocket", describe_sat(name="SL-4 R/B", object_type="R/B").lower())
        self.assertIn("Navigation", describe_sat(kind="gnss"))


class AircraftTests(unittest.TestCase):
    def test_overhead_is_near_zenith(self):
        from zenith.sky.aircraft import look_azel_geodetic

        az, el, rng = look_azel_geodetic(49.6314, 10.8772, 11000, 49.6314, 10.8772, 296)
        self.assertGreater(el, 85)
        self.assertLess(rng, 12)

    def test_due_north_azimuth(self):
        from zenith.sky.aircraft import look_azel_geodetic

        az, el, _rng = look_azel_geodetic(49.9, 10.8772, 11000, 49.6314, 10.8772, 296)
        self.assertLess(min(az, 360 - az), 8)
        self.assertGreater(el, 15)

    def test_bbox_covers_horizon(self):
        from zenith.sky.aircraft import bbox_for_site

        lamin, lomin, lamax, lomax = bbox_for_site(49.6314, 10.8772)
        self.assertLess(lamin, 49.6314)
        self.assertGreater(lamax, 49.6314)
        self.assertGreater(lamax - lamin, 6)

    def test_inbound_southbound_has_small_cpa(self):
        from zenith.sky.aircraft import closest_approach

        lat = 49.6314 + 100 / 111.32
        cpa, tca, horiz = closest_approach(lat, 10.8772, 180, 250, 49.6314, 10.8772)
        self.assertAlmostEqual(horiz, 100, delta=2)
        self.assertLess(cpa, 4)
        self.assertGreater(tca, 350)
        self.assertLess(tca, 450)

    def test_eastbound_parallel_has_large_cpa(self):
        from zenith.sky.aircraft import closest_approach

        lat = 49.6314 + 100 / 111.32
        cpa, _tca, _horiz = closest_approach(lat, 10.8772, 90, 250, 49.6314, 10.8772)
        self.assertGreater(cpa, 90)

    def test_look_inverse_matches_forward(self):
        from zenith.sky.aircraft import llh_along_look, look_azel_geodetic

        obs_lat, obs_lon, obs_h = 49.6314, 10.8772, 296.0
        tgt_lat = obs_lat + 50 / 111.32
        tgt_lon = obs_lon
        tgt_h = 11000.0
        az, el, _rng = look_azel_geodetic(tgt_lat, tgt_lon, tgt_h, obs_lat, obs_lon, obs_h)
        lat2, lon2, h2 = llh_along_look(az, el, tgt_h, obs_lat, obs_lon, obs_h)
        self.assertAlmostEqual(lat2, tgt_lat, delta=0.02)
        self.assertAlmostEqual(lon2, tgt_lon, delta=0.02)
        self.assertAlmostEqual(h2, tgt_h, delta=80)

    def test_project_skips_grounded(self):
        from zenith.sky.aircraft import _project

        now = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc).timestamp()
        states = [
            [
                "abc123",
                "DLH123  ",
                "Germany",
                now,
                now,
                10.8772,
                49.6314,
                11000,
                False,
                220,
                90,
                0,
                None,
                11000,
                "1000",
                False,
                0,
                3,
            ],
            [
                "gnd001",
                "TAXI",
                "Germany",
                now,
                now,
                10.88,
                49.63,
                0,
                True,
                5,
                0,
                0,
                None,
                0,
                None,
                False,
                0,
                1,
            ],
        ]
        planes = _project(states, 49.6314, 10.8772, 296, now, width=720, height=720, north_angle_deg=0, horizon=1.0, flip_h=False, flip_v=False, rotation_deg=0)
        self.assertEqual(len(planes), 1)
        self.assertEqual(planes[0]["name"], "DLH123")
        self.assertGreater(planes[0]["alt"], 80)

    def test_project_keeps_local_and_drops_far(self):
        from zenith.sky.aircraft import _project

        now = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc).timestamp()
        lat_local = 49.6314 + 40 / 111.32
        lat_far = 49.6314 + 200 / 111.32
        local = [
            "inb001",
            "INB01",
            "Germany",
            now,
            now,
            10.8772,
            lat_local,
            11000,
            False,
            250,
            180,
            0,
            None,
            11000,
            None,
            False,
            0,
            3,
        ]
        far = list(local)
        far[0] = "far001"
        far[1] = "FAR01"
        far[6] = lat_far
        planes = _project(
            [local, far],
            49.6314,
            10.8772,
            296,
            now,
            width=720,
            height=720,
            north_angle_deg=0,
            horizon=1.0,
            flip_h=False,
            flip_v=False,
            rotation_deg=0,
        )
        names = {p["name"] for p in planes}
        self.assertIn("INB01", names)
        self.assertIn("FAR01", names)
        row = next(p for p in planes if p["name"] == "INB01")
        self.assertTrue(row["inbound"])
        self.assertFalse(row.get("rim"))
        self.assertIn("from_x", row)
        self.assertAlmostEqual(row["from_x"], 0.5, delta=0.04)
        self.assertLess(row["from_y"], 0.08)
        self.assertAlmostEqual(row["x"], 0.5, delta=0.04)
        self.assertAlmostEqual(row["y"], 0.25, delta=0.06)
        self.assertAlmostEqual(row["ground_km"], 40, delta=3)
        self.assertGreater(len(row.get("path") or []), 2)
        self.assertLess(len(row.get("path") or []), 8)
        self.assertTrue(any((pt.get("ground_km") or 0) > 0 for pt in row["path"]))
        far = next(p for p in planes if p["name"] == "FAR01")
        self.assertTrue(far["inbound"])
        self.assertTrue(far.get("rim"))
        self.assertIn("from_x", far)
        self.assertAlmostEqual(far["from_x"], 0.5, delta=0.04)
        self.assertLess(far["from_y"], 0.08)
        self.assertEqual(far.get("path") or [], [])

    def test_enu_range_inverts_on_the_map_plane(self):
        from zenith.sky.aircraft import enu_az_range, llh_at_range_az

        obs_lat, obs_lon = 49.6314, 10.8772
        lat, lon = llh_at_range_az(0.0, 50.0, obs_lat, obs_lon)
        az, rng = enu_az_range(lat, lon, obs_lat, obs_lon)
        self.assertAlmostEqual(rng, 50.0, delta=0.05)
        self.assertLess(min(az, 360 - az), 0.5)

    def test_parse_adsb_lol_row(self):
        from zenith.sky.aircraft import parse_adsb_ac

        now = 1_700_000_000.0
        rows = parse_adsb_ac(
            {
                "now": now,
                "ac": [
                    {
                        "hex": "406d7b",
                        "flight": "BAW130  ",
                        "lat": 49.588531,
                        "lon": 7.944199,
                        "alt_baro": 40000,
                        "alt_geom": 41225,
                        "gs": 454.4,
                        "track": 302.78,
                        "baro_rate": -96,
                        "squawk": "7541",
                        "category": "A5",
                        "t": "B738",
                    },
                    {"hex": "gnd001", "lat": 49.63, "lon": 10.88, "alt_baro": "ground"},
                ],
            },
            now,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "406d7b")
        self.assertEqual(rows[0][1], "BAW130")
        self.assertGreater(rows[0][7], 12000)
        self.assertFalse(rows[0][8])
        self.assertEqual(rows[0][18], "B738")


class PlacesTests(unittest.TestCase):
    def test_dedupe_prefers_city(self):
        from zenith.sky.places import _dedupe

        rows = _dedupe(
            [
                {"name": "Erlangen", "kind": "village", "km": 2},
                {"name": "Erlangen", "kind": "city", "km": 14},
                {"name": "Bamberg", "kind": "town", "km": 40},
            ]
        )
        names = [r["name"] for r in rows]
        self.assertEqual(names[0], "Erlangen")
        self.assertEqual(rows[0]["kind"], "city")
        self.assertIn("Bamberg", names)

    def test_address_query_joins_street_and_city(self):
        from zenith.sky.places import address_query

        self.assertEqual(address_query("Ringstrasse 12a", "91091", "Grossenseebach"), "Ringstrasse 12a, 91091 Grossenseebach")

    def test_parse_nominatim_prefers_house(self):
        from zenith.sky.places import parse_nominatim_hit

        row = parse_nominatim_hit(
            [
                {"lat": "49.63", "lon": "10.87", "type": "village", "display_name": "town"},
                {
                    "lat": "49.6278487",
                    "lon": "10.8792215",
                    "addresstype": "place",
                    "type": "house",
                    "display_name": "12a, Ringstraße, Großenseebach",
                },
            ]
        )
        self.assertAlmostEqual(row["lat"], 49.6278487)
        self.assertAlmostEqual(row["lon"], 10.8792215)
    def test_geocode_without_street_uses_coordinates(self):
        from zenith.config.schema import ZenithSettings
        from zenith.sky.places import geocode_site

        settings = ZenithSettings()
        settings.location.latitude = 49.6314
        settings.location.longitude = 10.8772
        settings.location.address = ""
        row = geocode_site(settings)
        self.assertEqual(row["source"], "coordinates")
        self.assertAlmostEqual(row["lat"], 49.6314)

    def test_settings_put_without_address_keeps_coordinates(self):
        from zenith.api.routes.settings import _apply_geocoded_site

        payload = {
            "location": {"latitude": 49.6314, "longitude": 10.8772, "address": ""},
        }
        out = _apply_geocoded_site(payload)
        self.assertEqual(out["location"]["latitude"], 49.6314)
        self.assertEqual(out["location"]["longitude"], 10.8772)


class AcmetaTests(unittest.TestCase):
    def test_rejects_bad_icao(self):
        from zenith.sky.acmeta import lookup_aircraft

        self.assertIsNone(lookup_aircraft(""))
        self.assertIsNone(lookup_aircraft("xyz"))

    def test_parse_adsbdb_boeing(self):
        from zenith.sky.acmeta import parse_adsbdb

        payload = {
            "response": {
                "aircraft": {
                    "type": "737MAX 8 200",
                    "icao_type": "B38M",
                    "manufacturer": "Boeing",
                    "registration": "EI-HGV",
                    "registered_owner": "Ryanair",
                }
            }
        }
        row = parse_adsbdb(payload, "4cad54")
        self.assertEqual(row["typecode"], "B38M")
        self.assertEqual(row["registration"], "EI-HGV")
        self.assertEqual(row["operator"], "Ryanair")
        self.assertIn("Boeing", row["label"])

    def test_parse_hexdb(self):
        from zenith.sky.acmeta import parse_hexdb

        row = parse_hexdb(
            {
                "ModeS": "4CAD54",
                "Registration": "EI-HGV",
                "Manufacturer": "Boeing",
                "ICAOTypeCode": "B38M",
                "Type": "737MAX 8 200",
                "RegisteredOwners": "Ryanair",
            },
            "4cad54",
        )
        self.assertEqual(row["typecode"], "B38M")
        self.assertEqual(row["model"], "737MAX 8 200")

    def test_parse_adsbdb_route(self):
        from zenith.sky.acmeta import parse_adsbdb_route

        row = parse_adsbdb_route(
            {
                "response": {
                    "flightroute": {
                        "airline": {"name": "British Airways"},
                        "origin": {
                            "iata_code": "LHR",
                            "icao_code": "EGLL",
                            "municipality": "London",
                            "name": "London Heathrow Airport",
                        },
                        "destination": {
                            "iata_code": "FRA",
                            "icao_code": "EDDF",
                            "municipality": "Frankfurt am Main",
                            "name": "Frankfurt Airport",
                        },
                    }
                }
            },
            "BAW123",
        )
        self.assertEqual(row["route"], "LHR → FRA")
        self.assertEqual(row["origin"]["code"], "LHR")
        self.assertIn("London", row["origin"]["label"])
        self.assertEqual(row["destination"]["code"], "FRA")
        self.assertEqual(row["airline"], "British Airways")

    def test_parse_hexdb_route(self):
        from zenith.sky.acmeta import parse_hexdb_route

        row = parse_hexdb_route({"origin": "EGLL", "destination": "EDDF"}, "BAW123")
        self.assertEqual(row["route"], "EGLL → EDDF")
        self.assertEqual(row["origin"]["label"], "EGLL")

    def test_rejects_hex_as_callsign(self):
        from zenith.sky.acmeta import lookup_route

        self.assertIsNone(lookup_route("4cad54"))
        self.assertIsNone(lookup_route(""))


if __name__ == "__main__":
    unittest.main()
