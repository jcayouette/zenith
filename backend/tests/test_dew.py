from __future__ import annotations

import unittest

from zenith.config.schema import DewSettings
from zenith.io.dew import want_heat


class DewHeatTests(unittest.TestCase):
    def setUp(self):
        self.dew = DewSettings(rh_on=80, spread_c=4.0)

    def test_day_stays_off(self):
        on, reason = want_heat(
            rh=95, spread_c=1.0, precip_mm=2.0, sun_alt=20, night_alt=-0.8, dew=self.dew
        )
        self.assertFalse(on)
        self.assertEqual(reason, "day")

    def test_night_humidity(self):
        on, reason = want_heat(
            rh=88, spread_c=6.0, precip_mm=0, sun_alt=-12, night_alt=-0.8, dew=self.dew
        )
        self.assertTrue(on)
        self.assertEqual(reason, "humidity")

    def test_night_spread(self):
        on, reason = want_heat(
            rh=70, spread_c=3.0, precip_mm=0, sun_alt=-12, night_alt=-0.8, dew=self.dew
        )
        self.assertTrue(on)
        self.assertEqual(reason, "dewpoint")

    def test_night_dry(self):
        on, reason = want_heat(
            rh=60, spread_c=8.0, precip_mm=0, sun_alt=-12, night_alt=-0.8, dew=self.dew
        )
        self.assertFalse(on)
        self.assertEqual(reason, "dry")

    def test_night_rain(self):
        on, reason = want_heat(
            rh=60, spread_c=8.0, precip_mm=0.4, sun_alt=-12, night_alt=-0.8, dew=self.dew
        )
        self.assertTrue(on)
        self.assertEqual(reason, "rain")

    def test_uhubctl_refuses_usb_off(self):
        from zenith.io.dew import _uhubctl

        code, msg = _uhubctl("-l", "2", "-a", "0")
        self.assertNotEqual(code, 0)
        self.assertIn("refusing USB off", msg)
        code, msg = _uhubctl("-l", "2", "-a", "off")
        self.assertNotEqual(code, 0)

    def test_gpio_2_3_refused(self):
        from zenith.io.dew import pad_set

        self.assertFalse(pad_set(2, True)["ok"])
        self.assertFalse(pad_set(3, True)["ok"])


if __name__ == "__main__":
    unittest.main()
