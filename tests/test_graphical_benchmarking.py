from __future__ import annotations

from copy import deepcopy
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from primordial.graphical_benchmarking import (
    DisplayContext,
    RunSpec,
    SuitePaths,
    _run_single_graphical_benchmark,
)
from primordial.settings import Settings
from primordial.simulation import Simulation


class GraphicalBenchmarkingTests(unittest.TestCase):
    def _build_settings(self) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.fullscreen = False
        settings.show_hud = False
        return settings

    def test_predator_prey_adaptive_tuning_can_be_disabled_for_benchmark_runs(self) -> None:
        simulation = Simulation(640, 360, self._build_settings(), seed=12345)
        simulation.reset_predator_prey_adaptive_tuning()
        simulation.set_predator_prey_adaptive_tuning_enabled(False)

        state = simulation._predator_prey_state
        state.run_history.append(500)
        simulation._finalize_predator_prey_run(250)

        self.assertFalse(state.adaptive_tuning.trial_active)
        self.assertNotEqual(state.adaptive_tuning.last_decision, "trial_started")

    def test_graphical_benchmark_run_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            suite_paths = SuitePaths(
                root=root,
                per_run=root / "per_run",
                frame_samples=root / "frame_samples",
                screenshots=root / "screenshots",
                profiles=root / "profiles",
                logs=root / "logs",
                analysis_bundle=root / "analysis_bundle",
            )
            for path in (
                suite_paths.root,
                suite_paths.per_run,
                suite_paths.frame_samples,
                suite_paths.screenshots,
                suite_paths.profiles,
                suite_paths.logs,
                suite_paths.analysis_bundle,
            ):
                path.mkdir(parents=True, exist_ok=True)

            display_context = DisplayContext(
                display_path="virtual_graphical",
                visible_display=False,
                driver="dummy",
                desktop_resolution=(1280, 720),
                desktop_sizes=[[1280, 720]],
                display_env=None,
                wayland_display=None,
                session_type=None,
            )
            run_result = _run_single_graphical_benchmark(
                RunSpec(
                    scenario="test_short_windowed",
                    mode="energy",
                    seed=12345,
                    duration_seconds=0.2,
                    fullscreen=False,
                    screenshot_times=(0.05,),
                ),
                suite_paths,
                display_context,
            )

            self.assertGreaterEqual(run_result["performance"]["frames_rendered"], 1)
            self.assertTrue(Path(run_result["frame_samples_file"]).exists())
            self.assertTrue((suite_paths.per_run / f"{run_result['run_id']}.json").exists())
            self.assertGreaterEqual(len(run_result["checkpoints"]), 1)
            for checkpoint in run_result["checkpoints"]:
                self.assertTrue(Path(checkpoint["screenshot"]).exists())


if __name__ == "__main__":
    unittest.main()
