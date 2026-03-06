from __future__ import annotations

from copy import deepcopy
import random
import unittest
from unittest.mock import patch

from primordial.analysis import generate_history_artifact
from primordial.settings import Settings
from primordial.simulation import Simulation, build_snapshot, load_snapshot_payload
from primordial.simulation.creature import Creature
from primordial.simulation.depth import DEPTH_DEEP, DEPTH_MID, DEPTH_SURFACE
from primordial.simulation.food import Food
from primordial.simulation.genome import Genome


class M5DepthTests(unittest.TestCase):
    def _build_settings(self) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = "predator_prey"
        settings.visual_theme = "ocean"
        settings.show_hud = False
        settings.fullscreen = False
        settings.initial_population = 0
        settings.max_population = 32
        settings.food_max_particles = 32
        settings.zone_count = 0
        settings.zone_strength = 0.0
        settings.mode_params["predator_prey"]["initial_population"] = 0
        return settings

    def _build_simulation(self) -> Simulation:
        simulation = Simulation(200, 200, self._build_settings())
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def test_prey_food_access_is_limited_to_its_current_depth_band(self) -> None:
        simulation = self._build_simulation()
        prey = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(
                speed=1.0,
                sense_radius=1.0,
                efficiency=1.0,
                aggression=0.1,
                depth_preference=0.0,
            ),
            energy=0.3,
            lineage_id=1,
            species="prey",
            depth_band=DEPTH_SURFACE,
        )
        simulation.creatures.append(prey)
        simulation.food_manager.particles = [
            Food(x=100.0, y=100.0, energy=0.2, depth_band=DEPTH_DEEP, twinkle_phase=0.0),
        ]
        simulation.food_manager.rebuild_buckets()

        with patch("random.random", return_value=1.0):
            simulation._creature_seek_food(prey)

        self.assertEqual(prey.depth_band, DEPTH_SURFACE)
        self.assertEqual(len(simulation.food_manager.particles), 1)
        self.assertAlmostEqual(prey.energy, 0.3)

        simulation.food_manager.spawn(100.0, 100.0, depth_band=DEPTH_SURFACE)
        with patch("random.gauss", return_value=0.0):
            simulation._creature_seek_food(prey)

        self.assertEqual(len(simulation.food_manager.particles), 1)
        self.assertGreater(prey.energy, 0.3)

    def test_depth_separation_penalizes_sensing_and_blocks_cross_band_kills(self) -> None:
        simulation = self._build_simulation()
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=1.0, aggression=0.9, depth_preference=0.0),
            energy=0.6,
            lineage_id=1,
            species="predator",
            depth_band=DEPTH_SURFACE,
        )
        prey = Creature(
            x=103.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=1.0, aggression=0.1, depth_preference=1.0),
            energy=0.7,
            lineage_id=2,
            species="prey",
            depth_band=DEPTH_DEEP,
        )
        simulation.creatures = [predator, prey]
        bucket = simulation._build_creature_bucket()

        same_band_range = simulation._get_effective_sensing_range(
            predator,
            multiplier=2.0,
            target_depth_band=DEPTH_SURFACE,
        )
        deep_band_range = simulation._get_effective_sensing_range(
            predator,
            multiplier=2.0,
            target_depth_band=DEPTH_DEEP,
        )

        self.assertLess(deep_band_range, same_band_range)

        with patch("random.gauss", return_value=0.0), patch("random.random", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertGreater(prey.energy, 0.0)

        predator.depth_band = DEPTH_DEEP
        with patch("random.gauss", return_value=0.0), patch("random.random", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertEqual(prey.energy, 0.0)

    def test_depth_snapshot_round_trip_and_backward_safe_loading(self) -> None:
        simulation = self._build_simulation()
        creature = Creature(
            x=30.0,
            y=40.0,
            genome=Genome(depth_preference=1.0, aggression=0.8),
            energy=0.8,
            lineage_id=11,
            species="predator",
            depth_band=DEPTH_DEEP,
        )
        simulation.creatures = [creature]
        simulation.food_manager.particles = [
            Food(x=10.0, y=20.0, energy=0.2, depth_band=DEPTH_SURFACE, twinkle_phase=0.0),
        ]
        simulation.food_manager.rebuild_buckets()

        payload = build_snapshot(simulation)
        self.assertEqual(payload["world"]["creatures"][0]["depth_band"], DEPTH_DEEP)
        self.assertEqual(payload["world"]["creatures"][0]["genome"]["depth_preference"], 1.0)
        self.assertEqual(payload["world"]["food"]["particles"][0]["depth_band"], DEPTH_SURFACE)

        loaded = load_snapshot_payload(payload, settings=self._build_settings())
        self.assertEqual(loaded.creatures[0].depth_band, DEPTH_DEEP)
        self.assertEqual(loaded.creatures[0].genome.depth_preference, 1.0)
        self.assertEqual(loaded.food_manager.particles[0].depth_band, DEPTH_SURFACE)

        legacy_payload = deepcopy(payload)
        legacy_payload["world"]["creatures"][0].pop("depth_band")
        legacy_payload["world"]["creatures"][0]["genome"].pop("depth_preference")
        legacy_payload["world"]["food"]["particles"][0].pop("depth_band")

        legacy_loaded = load_snapshot_payload(legacy_payload, settings=self._build_settings())
        self.assertEqual(legacy_loaded.creatures[0].depth_band, DEPTH_MID)
        self.assertEqual(legacy_loaded.creatures[0].genome.depth_preference, 0.5)
        self.assertEqual(legacy_loaded.food_manager.particles[0].depth_band, DEPTH_MID)

    def test_observability_and_history_artifacts_include_depth_summary(self) -> None:
        simulation = self._build_simulation()
        simulation.creatures = [
            Creature(x=10.0, y=10.0, genome=Genome(depth_preference=0.0), lineage_id=1, species="prey", depth_band=DEPTH_SURFACE),
            Creature(x=20.0, y=20.0, genome=Genome(depth_preference=0.4), lineage_id=2, species="predator", depth_band=DEPTH_MID),
            Creature(x=30.0, y=30.0, genome=Genome(depth_preference=1.0), lineage_id=3, species="prey", depth_band=DEPTH_DEEP),
        ]

        snapshot = simulation.build_observability_snapshot()
        self.assertEqual(snapshot["depth"]["surface"], 1)
        self.assertEqual(snapshot["depth"]["mid"], 1)
        self.assertEqual(snapshot["depth"]["deep"], 1)
        self.assertEqual(snapshot["depth"]["occupied_bands"], 3)

        history = generate_history_artifact(
            "predator_prey_medium",
            steps=40,
            sample_every=20,
            seed=161803,
        )
        self.assertIn("depth", history["series"][0])
        self.assertIn("depth_history", history["summary"])
        self.assertIn("dominant_band_end", history["summary"]["depth_history"])
        self.assertGreaterEqual(history["summary"]["depth_history"]["occupied_bands_end"], 1)


if __name__ == "__main__":
    unittest.main()
