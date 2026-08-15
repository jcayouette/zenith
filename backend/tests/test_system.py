from __future__ import annotations

import unittest

from zenith.system.health import collect, cpu_percent_from_samples, parse_throttled


class SystemHealthTests(unittest.TestCase):
    def test_throttled_none(self):
        parsed = parse_throttled(0)
        self.assertFalse(parsed["throttled"])
        self.assertEqual(parsed["hex"], "0x0")
        self.assertFalse(any(parsed["flags"].values()))

    def test_throttled_under_voltage_now_and_history(self):
        parsed = parse_throttled(0x50001)
        self.assertTrue(parsed["flags"]["under_voltage"])
        self.assertTrue(parsed["flags"]["under_voltage_occurred"])
        self.assertTrue(parsed["flags"]["throttled_occurred"])
        self.assertTrue(parsed["throttled"])

    def test_cpu_percent_delta(self):
        prev = (1000, 800)
        curr = (1200, 850)
        # total +200, idle +50 → 75% busy
        self.assertAlmostEqual(cpu_percent_from_samples(prev, curr), 75.0)
        self.assertIsNone(cpu_percent_from_samples(curr, prev))

    def test_collect_reads_host_metrics(self):
        payload = collect()
        self.assertIn("hostname", payload)
        self.assertGreater(payload["memory"]["total_bytes"], 0)
        self.assertGreater(payload["cpu"]["cores"], 0)
        self.assertTrue(payload["disks"])
        self.assertTrue(payload["alerts"])
        self.assertNotIn("_blocks", payload["disks"][0])
