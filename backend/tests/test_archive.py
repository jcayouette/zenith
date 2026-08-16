from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from zenith.config.schema import ZenithSettings
from zenith.imaging import apply_colour_gains


class ArchiveStoreTests(unittest.TestCase):
    def test_save_and_list_raw_png(self):
        from zenith.archive import store

        rgb = np.zeros((32, 48, 3), dtype=np.uint8)
        rgb[:, :] = (12, 24, 48)
        settings = ZenithSettings()
        settings.camera.save_raw = True
        settings.camera.save_png = True
        settings.camera.save_jpeg = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(store, "DATA_DIR", root),
                patch("zenith.paths.DATA_DIR", root),
            ):
                saved = store.save_frame(
                    rgb_linear=rgb,
                    rgb_preview=rgb,
                    kind="night",
                    session_date=datetime(2026, 8, 14).date(),
                    when_local=datetime(2026, 8, 14, 22, 15, 3),
                    settings=settings,
                )
                self.assertTrue(saved.thumb_path.is_file())
                self.assertTrue(saved.png_path and saved.png_path.is_file())
                self.assertTrue(saved.raw_path and saved.raw_path.suffix == ".png")
                self.assertIsNone(saved.jpeg_path)
                sessions = store.list_sessions("night")
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["frames"], 1)
                detail = store.list_frames("night", saved.date)
                self.assertEqual(detail["total"], 1)
                self.assertTrue(detail["frames"][0]["raw_url"])
                self.assertTrue(store.should_save("night", settings))
                settings.camera.save_day = False
                self.assertFalse(store.should_save("day", settings))
                deleted = store.delete_session("night", saved.date)
                self.assertGreater(deleted["files"], 0)
                self.assertEqual(store.list_sessions("night"), [])

    def test_delete_session_keeps_processed(self):
        from zenith.archive import store
        from zenith.paths import product_write_path

        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        settings = ZenithSettings()
        settings.camera.save_raw = False
        settings.camera.save_png = True
        settings.camera.save_jpeg = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(store, "DATA_DIR", root),
                patch("zenith.paths.DATA_DIR", root),
            ):
                night_date = datetime(2026, 8, 14).date()
                store.save_frame(
                    rgb_linear=rgb,
                    rgb_preview=rgb,
                    kind="night",
                    session_date=night_date,
                    when_local=datetime(2026, 8, 14, 22, 0, 0),
                    settings=settings,
                )
                keogram = product_write_path(night_date, "keogram.jpg")
                keogram.write_bytes(b"keogram")
                store.delete_session("night", night_date)
                self.assertEqual(store.list_sessions("night"), [])
                self.assertTrue(keogram.is_file())
                listing = store.list_processed("keograms")
                self.assertEqual(len(listing["items"]), 1)

    def test_delete_kind_leaves_other_kind(self):
        from zenith.archive import store

        rgb = np.zeros((16, 16, 3), dtype=np.uint8)
        settings = ZenithSettings()
        settings.camera.save_raw = False
        settings.camera.save_png = True
        settings.camera.save_jpeg = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(store, "DATA_DIR", root),
                patch("zenith.paths.DATA_DIR", root),
            ):
                night_date = datetime(2026, 8, 14).date()
                day_date = datetime(2026, 8, 15).date()
                store.save_frame(
                    rgb_linear=rgb,
                    rgb_preview=rgb,
                    kind="night",
                    session_date=night_date,
                    when_local=datetime(2026, 8, 14, 22, 0, 0),
                    settings=settings,
                )
                store.save_frame(
                    rgb_linear=rgb,
                    rgb_preview=rgb,
                    kind="day",
                    session_date=day_date,
                    when_local=datetime(2026, 8, 15, 12, 0, 0),
                    settings=settings,
                )
                out = store.delete_kind("night")
                self.assertEqual(out["sessions"], 1)
                self.assertEqual(store.list_sessions("night"), [])
                self.assertEqual(len(store.list_sessions("day")), 1)
                all_out = store.delete_all()
                self.assertEqual(all_out["days"], 1)
                self.assertEqual(store.list_sessions("day"), [])


class RawDevelopTests(unittest.TestCase):
    def test_empty_folder_writes_nothing(self):
        from zenith.products.raw_develop import develop_dng_folder

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw"
            dest = Path(tmp) / "out"
            src.mkdir()
            n = develop_dng_folder(
                src, dest, bright=2.0, colour=(1.0, 1.0, 1.0), max_side=320
            )
            self.assertEqual(n, 0)


class EncodeProgressTests(unittest.TestCase):
    def test_eta_uses_developed_rate(self):
        from zenith.products.encode_jobs import eta_seconds

        self.assertIsNone(eta_seconds(developed=1, remaining=100, elapsed=2.0))
        self.assertIsNone(eta_seconds(developed=10, remaining=0, elapsed=20.0))
        self.assertAlmostEqual(eta_seconds(developed=10, remaining=90, elapsed=20.0), 180.0)

    def test_skips_move_percent_without_eta(self):
        from zenith.products.encode_jobs import EncodeTracker

        jobs = EncodeTracker()
        jobs.start("day:2026-08-15", kind="day", date="2026-08-15")
        jobs.tick("day:2026-08-15", done=271, total=1497, developed=0, skipped=271)
        snap = jobs.snapshot("day:2026-08-15")
        self.assertIsNotNone(snap)
        self.assertGreater(snap["percent"], 18)
        self.assertLess(snap["percent"], 19)
        self.assertIsNone(snap["eta_seconds"])
        self.assertTrue(jobs.active("day:2026-08-15"))

    def test_folder_progress_counts_each_frame(self):
        from zenith.products.raw_develop import develop_dng_folder

        rgb = np.zeros((8, 8, 3), dtype=np.uint8)
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "raw"
            dest = Path(tmp) / "out"
            src.mkdir()
            (src / "a.dng").write_bytes(b"dng")
            (src / "b.dng").write_bytes(b"dng")
            with patch("zenith.products.raw_develop.develop_dng", return_value=rgb):
                n = develop_dng_folder(
                    src,
                    dest,
                    bright=2.0,
                    colour=(1.0, 1.0, 1.0),
                    max_side=32,
                    on_progress=calls.append,
                )
            self.assertEqual(n, 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1]["done"], 2)
            self.assertEqual(calls[-1]["total"], 2)
            self.assertEqual(calls[-1]["developed"], 2)
            self.assertTrue((dest / "a.jpg").is_file())


class ColourGainTests(unittest.TestCase):
    def test_unity_gains_are_identity(self):
        rgb = np.array([[[10, 40, 200]]], dtype=np.uint8)
        out = apply_colour_gains(rgb, 1.0, 1.0, 1.0)
        np.testing.assert_array_equal(out, rgb)

    def test_blue_gain_zero_removes_blue(self):
        rgb = np.full((12, 12, 3), 80, dtype=np.uint8)
        out = apply_colour_gains(rgb, red_gain=1.0, blue_gain=0.0)
        self.assertEqual(int(out[..., 2].max()), 0)
        self.assertGreater(int(out[..., 0].mean()), 0)

    def test_green_gain_zero_removes_green(self):
        rgb = np.full((12, 12, 3), 80, dtype=np.uint8)
        out = apply_colour_gains(rgb, red_gain=1.0, green_gain=0.0, blue_gain=1.0)
        self.assertEqual(int(out[..., 1].max()), 0)
        self.assertGreater(int(out[..., 0].mean()), 0)
        self.assertGreater(int(out[..., 2].mean()), 0)


class SettingsMergeTests(unittest.TestCase):
    def test_merge_keeps_untouched_fields(self):
        from zenith.config import store

        prev = store._cache
        store._cache = ZenithSettings()
        try:
            out = store.merge_settings({"picamera2": {"colour_gain_b": 0.5}})
            self.assertEqual(out.picamera2.colour_gain_b, 0.5)
            self.assertEqual(out.picamera2.colour_gain_r, 1.0)
            again = store.merge_settings({"picamera2": {"colour_gain_r": 1.4}})
            self.assertEqual(again.picamera2.colour_gain_r, 1.4)
            self.assertEqual(again.picamera2.colour_gain_b, 0.5)
        finally:
            store._cache = prev


class ProcessedCatalogTests(unittest.TestCase):
    def test_list_processed_reads_typed_folders(self):
        from zenith.archive import store
        from zenith.paths import product_write_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(store, "DATA_DIR", root),
                patch("zenith.paths.DATA_DIR", root),
            ):
                day = datetime(2026, 8, 14).date()
                path = product_write_path(day, "keogram.jpg")
                path.write_bytes(b"jpeg-bytes")
                listing = store.list_processed("keograms")
                self.assertEqual(len(listing["items"]), 1)
                self.assertEqual(listing["items"][0]["category"], "keograms")
                self.assertEqual(listing["counts"]["keograms"], 1)
                self.assertEqual(listing["counts"]["timelapses"], 0)
                empty = store.list_processed("timelapses")
                self.assertEqual(empty["items"], [])
                self.assertEqual(empty["counts"]["keograms"], 1)


if __name__ == "__main__":
    unittest.main()
