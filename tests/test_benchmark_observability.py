from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from primordial.benchmarking import (
    OBSERVABILITY_CORE_SECTIONS,
    SCENARIOS,
    list_scenarios,
    run_benchmark,
)
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.zones import ZONE_DEFINITIONS


class BenchmarkObservabilityTests(unittest.TestCase):
    def _build_settings(self, mode: str) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.visual_theme = "ocean"
        settings.show_hud = False
        settings.fullscreen = False
        settings.initial_population = 24
        settings.max_population = 64
        settings.zone_count = 5
        settings.zone_strength = 0.8
        return settings

    def test_simulation_observability_snapshot_has_shared_core(self) -> None:
        simulation = Simulation(640, 360, self._build_settings("energy"))
        snapshot = simulation.build_observability_snapshot()

        self.assertEqual(set(OBSERVABILITY_CORE_SECTIONS), {"lineages", "strategies", "zone_occupancy"})
        self.assertEqual(snapshot["population"], simulation.population)
        self.assertIn("lineages", snapshot)
        self.assertIn("strategies", snapshot)
        self.assertIn("zone_occupancy", snapshot)
        self.assertGreaterEqual(snapshot["lineages"]["active"], 1)
        for zone_type in ZONE_DEFINITIONS:
            self.assertIn(zone_type, snapshot["zone_occupancy"])
        self.assertIn("unzoned", snapshot["zone_occupancy"])
        self.assertNotIn("species", snapshot)
        self.assertNotIn("depth", snapshot)
        self.assertNotIn("flocks", snapshot)

    def test_simulation_observability_snapshot_only_includes_mode_specific_sections_when_applicable(self) -> None:
        predator_prey_snapshot = Simulation(
            640,
            360,
            self._build_settings("predator_prey"),
        ).build_observability_snapshot()
        boids_snapshot = Simulation(
            640,
            360,
            self._build_settings("boids"),
        ).build_observability_snapshot()

        self.assertIn("species", predator_prey_snapshot)
        self.assertIn("depth", predator_prey_snapshot)
        self.assertNotIn("flocks", predator_prey_snapshot)
        self.assertIn("flocks", boids_snapshot)
        self.assertNotIn("species", boids_snapshot)
        self.assertNotIn("depth", boids_snapshot)

    def test_benchmark_scenarios_cover_representative_modes(self) -> None:
        self.assertEqual(
            list_scenarios(),
            ["boids_dense", "energy_medium", "predator_prey_medium"],
        )
        self.assertEqual(
            {SCENARIOS[scenario_id].mode for scenario_id in list_scenarios()},
            {"boids", "energy", "predator_prey"},
        )

    def test_benchmark_writes_expected_summary_shape_for_required_scenarios(self) -> None:
        expected_shared_keys = {"population", *OBSERVABILITY_CORE_SECTIONS}
        expected_optional_keys = {
            "energy_medium": set(),
            "predator_prey_medium": {"species", "depth"},
            "boids_dense": {"flocks"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            for scenario_id in ("energy_medium", "predator_prey_medium", "boids_dense"):
                output_path = Path(temp_dir) / f"{scenario_id}.json"
                with self.subTest(scenario=scenario_id):
                    payload = run_benchmark(
                        scenario_id,
                        seconds=0.2,
                        output_path=output_path,
                    )

                    self.assertTrue(output_path.exists())
                    self.assertEqual(payload["scenario"]["id"], scenario_id)
                    self.assertGreaterEqual(payload["run"]["duration_seconds"], 0.0)
                    self.assertGreaterEqual(payload["performance"]["frames_rendered"], 1)
                    self.assertGreaterEqual(payload["performance"]["sim_steps_total"], 1)
                    self.assertIn("frame_ms", payload["performance"])
                    self.assertIn("clamp_drop", payload["performance"])
                    self.assertEqual(
                        set(payload["observability"]),
                        expected_shared_keys | expected_optional_keys[scenario_id],
                    )
                    self.assertGreaterEqual(payload["observability"]["population"]["mean"], 1)
                    self.assertGreaterEqual(payload["observability"]["lineages"]["active"], 1)
                    self.assertIn("open_water", payload["observability"]["zone_occupancy"])
                    if scenario_id == "boids_dense":
                        self.assertGreaterEqual(payload["observability"]["flocks"]["count"], 1)
                        self.assertGreaterEqual(payload["observability"]["flocks"]["largest"], 1)
                    if scenario_id == "predator_prey_medium":
                        self.assertGreaterEqual(payload["observability"]["species"]["predators"], 1)
                        self.assertGreaterEqual(payload["observability"]["species"]["prey"], 1)
                        self.assertGreaterEqual(payload["observability"]["depth"]["occupied_bands"], 1)


if __name__ == "__main__":
    unittest.main()
