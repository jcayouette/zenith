from __future__ import annotations

import unittest

import numpy as np

from zenith.products.keogram import meridian_column
from zenith.products.startrails import count_stars


class KeogramTests(unittest.TestCase):
    def test_meridian_column_picks_center(self):
        rgb = np.zeros((40, 80, 3), dtype=np.uint8)
        rgb[:, 40] = (0, 255, 0)
        col = meridian_column(rgb, 0.0, 1)
        self.assertEqual(col.shape, (40, 3))
        self.assertTrue(np.all(col[:, 1] == 255))

    def test_count_stars_finds_peaks(self):
        rgb = np.zeros((64, 64, 3), dtype=np.uint8)
        rgb[16, 16] = 255
        rgb[48, 40] = 255
        self.assertGreaterEqual(count_stars(rgb, threshold=20), 1)


if __name__ == "__main__":
    unittest.main()
