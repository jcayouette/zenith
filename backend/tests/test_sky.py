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

    def test_project_keeps_inbound_and_drops_parallel(self):
        from zenith.sky.aircraft import _project

        now = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc).timestamp()
        lat_n = 49.6314 + 80 / 111.32
        inbound = [
            "inb001",
            "INB01",
            "Germany",
            now,
            now,
            10.8772,
            lat_n,
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
        parallel = list(inbound)
        parallel[0] = "par001"
        parallel[1] = "PAR01"
        parallel[10] = 90
        planes = _project(
            [inbound, parallel],
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
        self.assertNotIn("PAR01", names)
        row = next(p for p in planes if p["name"] == "INB01")
        self.assertTrue(row["inbound"])
        self.assertIn("from_x", row)
        self.assertGreater(len(row.get("path") or []), 2)


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


if __name__ == "__main__":
    unittest.main()
