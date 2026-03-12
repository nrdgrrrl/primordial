from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from primordial.graphics_probe import run_display_toggle_probe


class GraphicsProbeTests(unittest.TestCase):
    def test_probe_captures_screenshots_and_report_without_mutating_world(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "primordial.graphics_probe._get_fullscreen_resolution",
            return_value=(1920, 1080),
        ), patch(
            "primordial.main._get_fullscreen_resolution",
            return_value=(1920, 1080),
        ), patch(
            "primordial.graphics_probe.pygame.SCALED",
            0,
        ), patch(
            "primordial.main.pygame.SCALED",
            0,
        ):
            report = run_display_toggle_probe(
                temp_dir,
                seed=12345,
                start_fullscreen=True,
                toggle_count=2,
                settle_frames=1,
            )

            self.assertTrue(report["checks"]["passed"])
            self.assertEqual(report["resize_calls"]["simulation"], [])
            self.assertGreaterEqual(len(report["checkpoints"]), 3)

            initial = report["checkpoints"][0]
            windowed = report["checkpoints"][1]
            restored = report["checkpoints"][2]

            self.assertEqual(initial["world_size"], [1920, 1080])
            self.assertTrue(initial["fullscreen"])
            self.assertFalse(windowed["fullscreen"])
            self.assertTrue(restored["fullscreen"])
            self.assertEqual(restored["display_size"], initial["display_size"])
            self.assertEqual(initial["world_size"], restored["world_size"])
            self.assertEqual(initial["food_hash"], restored["food_hash"])
            self.assertEqual(initial["zone_hash"], restored["zone_hash"])

            report_path = Path(temp_dir) / "report.json"
            self.assertTrue(report_path.exists())
            for checkpoint in report["checkpoints"]:
                self.assertTrue((Path(temp_dir) / checkpoint["screenshot"]).exists())


if __name__ == "__main__":
    unittest.main()
