from __future__ import annotations

from copy import deepcopy
import random
import tempfile
import unittest
from pathlib import Path

from primordial.settings import Settings
from primordial.simulation import (
    SnapshotError,
    Simulation,
    build_snapshot,
    inspect_snapshot_dimensions,
    load_snapshot,
    load_snapshot_payload,
    save_snapshot,
)


class SimulationPersistenceTests(unittest.TestCase):
    def _build_settings(self, mode: str) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.visual_theme = "ocean"
        settings.show_hud = False
        settings.fullscreen = False
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 96
        settings.zone_count = 5
        settings.zone_strength = 0.8
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def test_save_load_round_trip_and_resume_match_energy_mode(self) -> None:
        settings = self._build_settings("energy")
        settings.initial_population = 24
        settings.max_population = 48
        settings.food_max_particles = 120

        random.seed(12345)
        simulation = Simulation(320, 180, settings)
        for _ in range(120):
            simulation.step()

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "world.json"
            save_snapshot(simulation, snapshot_path)
            loaded = load_snapshot(snapshot_path, settings=self._build_settings("energy"))

            saved_payload = build_snapshot(simulation)
            loaded_payload = build_snapshot(loaded)
            self.assertEqual(saved_payload, loaded_payload)

            creature_payload = saved_payload["world"]["creatures"][0]
            self.assertNotIn("trail", creature_payload)
            self.assertNotIn("rotation_angle", creature_payload)
            self.assertNotIn("glyph_surface", creature_payload)
            self.assertNotIn("death_events", saved_payload["world"])
            self.assertNotIn("birth_events", saved_payload["world"])
            self.assertNotIn("cosmic_ray_events", saved_payload["world"])
            self.assertNotIn("active_attacks", saved_payload["world"])

            reference_rng_state = random.getstate()
            random.setstate(reference_rng_state)
            for _ in range(40):
                simulation.step()
            advanced_original = build_snapshot(simulation)

            random.setstate(reference_rng_state)
            for _ in range(40):
                loaded.step()
            advanced_loaded = build_snapshot(loaded)

            self.assertEqual(advanced_original, advanced_loaded)

    def test_save_load_round_trip_and_resume_match_predator_prey_mode(self) -> None:
        settings = self._build_settings("predator_prey")
        settings.initial_population = 28
        settings.max_population = 52
        settings.food_max_particles = 110

        random.seed(24680)
        simulation = Simulation(360, 200, settings)
        for _ in range(90):
            simulation.step()

        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_path = Path(temp_dir) / "world.json"
            save_snapshot(simulation, snapshot_path)

            self.assertEqual((360, 200), inspect_snapshot_dimensions(snapshot_path))

            loaded = load_snapshot(
                snapshot_path,
                settings=self._build_settings("predator_prey"),
            )

            saved_payload = build_snapshot(simulation)
            loaded_payload = build_snapshot(loaded)
            self.assertEqual(saved_payload, loaded_payload)
            if saved_payload["world"]["creatures"]:
                self.assertIn("depth_band", saved_payload["world"]["creatures"][0])
                self.assertIn(
                    "depth_preference",
                    saved_payload["world"]["creatures"][0]["genome"],
                )
            if saved_payload["world"]["food"]["particles"]:
                self.assertIn("depth_band", saved_payload["world"]["food"]["particles"][0])

            reference_rng_state = random.getstate()
            random.setstate(reference_rng_state)
            for _ in range(35):
                simulation.step()
            advanced_original = build_snapshot(simulation)

            random.setstate(reference_rng_state)
            for _ in range(35):
                loaded.step()
            advanced_loaded = build_snapshot(loaded)

            self.assertEqual(advanced_original, advanced_loaded)

    def test_load_rebuilds_boids_flock_state_without_persisting_it(self) -> None:
        settings = self._build_settings("boids")
        settings.mode_params["boids"].update({
            "initial_population": 40,
            "max_population": 48,
            "mutation_rate": 0.05,
            "energy_to_reproduce": 0.85,
            "food_cycle_enabled": False,
            "zone_strength": 0.5,
        })

        random.seed(54321)
        simulation = Simulation(480, 270, settings)
        for _ in range(30):
            simulation.step()

        snapshot = build_snapshot(simulation)
        creature_payload = snapshot["world"]["creatures"][0]
        self.assertNotIn("flock_id", creature_payload)
        self.assertNotIn("_flock_sizes", snapshot["world"])

        loaded = load_snapshot_payload(snapshot, settings=self._build_settings("boids"))

        self.assertEqual(simulation.get_flock_stats(), loaded.get_flock_stats())
        self.assertEqual(
            sum(1 for creature in simulation.creatures if creature.flock_id != -1),
            sum(1 for creature in loaded.creatures if creature.flock_id != -1),
        )

    def test_load_rejects_unsupported_snapshot_version(self) -> None:
        settings = self._build_settings("energy")
        simulation = Simulation(200, 120, settings)
        snapshot = build_snapshot(simulation)
        snapshot["version"] = 999

        with self.assertRaises(SnapshotError):
            load_snapshot_payload(snapshot, settings=self._build_settings("energy"))

    def test_inspect_snapshot_dimensions_raises_snapshot_error_for_invalid_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.json"

            with self.assertRaises(SnapshotError):
                inspect_snapshot_dimensions(missing_path)

            invalid_path = Path(temp_dir) / "invalid.json"
            invalid_path.write_text("{not-json", encoding="utf-8")

            with self.assertRaises(SnapshotError):
                inspect_snapshot_dimensions(invalid_path)


if __name__ == "__main__":
    unittest.main()
