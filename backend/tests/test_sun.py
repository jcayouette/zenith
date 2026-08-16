from __future__ import annotations

import unittest
from datetime import datetime, timezone

from zenith.sky.sun import sky_mode, sky_session, sun_altitude_deg


class SunTests(unittest.TestCase):
    def test_sky_mode_thresholds(self):
        self.assertEqual(sky_mode(5.0, -18), "day")
        self.assertEqual(sky_mode(-6.0, -18), "twilight")
        self.assertEqual(sky_mode(-19.0, -18), "night")

    def test_berlin_summer_noon_is_day(self):
        when = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)  # 12:00 CEST
        session = sky_session(52.52, 13.4, "Europe/Berlin", -18.0, when)
        self.assertEqual(session.kind, "day")
        self.assertEqual(session.mode, "day")
        self.assertEqual(session.date.isoformat(), "2026-08-15")
        self.assertGreater(session.sun_alt, 0)

    def test_berlin_evening_night_uses_sunset_date(self):
        when = datetime(2026, 8, 15, 21, 0, tzinfo=timezone.utc)  # 23:00 CEST
        session = sky_session(52.52, 13.4, "Europe/Berlin", -18.0, when)
        self.assertEqual(session.kind, "night")
        self.assertEqual(session.date.isoformat(), "2026-08-15")
        self.assertLess(session.sun_alt, 0)

    def test_berlin_morning_keeps_previous_night_date(self):
        when = datetime(2026, 8, 16, 0, 30, tzinfo=timezone.utc)  # 02:30 CEST
        session = sky_session(52.52, 13.4, "Europe/Berlin", -18.0, when)
        self.assertEqual(session.kind, "night")
        self.assertEqual(session.date.isoformat(), "2026-08-15")
        self.assertLess(sun_altitude_deg(52.52, 13.4, when), 0)

    def test_next_events_after_noon_include_sunset(self):
        from zenith.sky.sun import next_sun_events

        when = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
        names = [row["name"] for row in next_sun_events(52.52, 13.4, "Europe/Berlin", -18.0, when)]
        self.assertIn("sunset", names)
        self.assertIn("night", names)

    def test_dst_active_in_berlin_summer(self):
        from zenith.sky.clock import dst_active

        summer = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        winter = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(dst_active("Europe/Berlin", summer))
        self.assertFalse(dst_active("Europe/Berlin", winter))


if __name__ == "__main__":
    unittest.main()
