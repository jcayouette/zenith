from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from zenith.products.keogram import meridian_column
from zenith.products.startrails import Startrails, count_stars


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


class StartrailsTests(unittest.TestCase):
    def test_max_stack_keeps_brighter_pixels(self):
        trails = Startrails()
        a = np.zeros((32, 32, 3), dtype=np.uint8)
        a[10, 10] = (40, 40, 40)
        b = np.zeros((32, 32, 3), dtype=np.uint8)
        b[10, 10] = (200, 180, 90)
        b[20, 8] = (255, 255, 255)
        self.assertTrue(trails.maybe_add(a, 0.1, stars=20, min_stars=1, adu_min=0.0, adu_max=1.0))
        self.assertTrue(trails.maybe_add(b, 0.1, stars=20, min_stars=1, adu_min=0.0, adu_max=1.0))
        self.assertEqual(trails.frames_used, 2)
        self.assertIsNotNone(trails.stack)
        assert trails.stack is not None
        self.assertEqual(tuple(trails.stack[10, 10]), (200, 180, 90))
        self.assertEqual(tuple(trails.stack[20, 8]), (255, 255, 255))

    def test_rejects_cloudy_frames(self):
        trails = Startrails()
        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        self.assertFalse(trails.maybe_add(rgb, 0.1, stars=2, min_stars=12, adu_min=0.0, adu_max=1.0))
        self.assertEqual(trails.frames_used, 0)
        self.assertEqual(trails.frames_seen, 1)

    def test_writes_processed_startrails_path(self):
        from zenith.products.service import ProductService

        trails = Startrails()
        rgb = np.full((24, 24, 3), 30, dtype=np.uint8)
        rgb[5, 5] = 255
        trails.maybe_add(rgb, 0.12, stars=40, min_stars=1, adu_min=0.0, adu_max=1.0)
        day = date(2026, 8, 17)
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("zenith.paths.DATA_DIR", root):
                ProductService()._persist_trails(trails, day, force=True)
            jpg = root / "processed" / "startrails" / "2026-08-17" / "startrails.jpg"
            meta = root / "processed" / "startrails" / "2026-08-17" / "startrails.json"
            self.assertTrue(jpg.is_file(), jpg)
            self.assertTrue(meta.is_file(), meta)


class DetectTests(unittest.TestCase):
    def test_finds_diagonal_streak(self):
        from zenith.products.detect import StreakDetector

        det = StreakDetector()
        prev = np.zeros((160, 160, 3), dtype=np.uint8)
        curr = prev.copy()
        for i in range(20, 90):
            curr[i, i] = 255
            curr[i, i + 1] = 255
            curr[i + 1, i] = 220
        self.assertEqual(det.feed(prev, min_length=10, min_aspect=2.0, now_s=1.0), [])
        hits = det.feed(curr, min_length=10, min_aspect=2.0, now_s=2.0)
        self.assertGreaterEqual(len(hits), 1)
        self.assertGreater(hits[0].length_px, 20)
        self.assertGreater(hits[0].aspect, 2.0)


if __name__ == "__main__":
    unittest.main()
