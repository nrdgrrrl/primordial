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
    _build_inspect_follow_run_specs,
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
            self.assertIn("simulation_tick_hz", run_result)
            self.assertEqual(run_result["render_backend"], "pygame")
            self.assertTrue(Path(run_result["frame_samples_file"]).exists())
            self.assertTrue((suite_paths.per_run / f"{run_result['run_id']}.json").exists())
            self.assertIn("draw_total_ms", run_result["performance"]["render_breakdown_mean_ms"])
            self.assertIn("draw_total_ms", run_result["performance"]["render_breakdown_ms"])
            self.assertIn("p95", run_result["performance"]["render_breakdown_ms"]["draw_total_ms"])
            self.assertGreaterEqual(len(run_result["checkpoints"]), 1)
            for checkpoint in run_result["checkpoints"]:
                self.assertTrue(Path(checkpoint["screenshot"]).exists())

    def test_inspect_follow_suite_builds_required_scenarios(self) -> None:
        specs = _build_inspect_follow_run_specs(fullscreen=False)

        self.assertEqual(
            [spec.scenario for spec in specs],
            [
                "inspect_follow_baseline_hud_off",
                "inspect_follow_hud_only",
                "inspect_gutter_no_selection",
                "inspect_selected_panel_paused",
                "inspect_selected_graph_disabled",
                "inspect_selected_attention_disabled",
                "inspect_selected_panel_frozen",
                "inspect_follow_paused",
                "inspect_follow_slow",
                "inspect_follow_normal",
                "inspect_follow_normal_action_bar_hidden",
            ],
        )
        self.assertEqual(specs[0].show_hud, False)
        self.assertFalse(specs[2].inspect_select_creature)
        self.assertTrue(specs[3].inspect_select_creature)
        self.assertTrue(specs[4].inspect_disable_graph)
        self.assertTrue(specs[5].inspect_disable_attention_line)
        self.assertTrue(specs[6].inspect_freeze_panel_refresh)
        self.assertEqual(specs[7].inspect_scenario, "pause")
        self.assertEqual(specs[9].inspect_scenario, "normal")
        self.assertTrue(specs[9].action_bar_visible)
        self.assertFalse(specs[5].action_bar_visible)


if __name__ == "__main__":
    unittest.main()
