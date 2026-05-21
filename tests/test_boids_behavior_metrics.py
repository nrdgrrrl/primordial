from __future__ import annotations

from copy import deepcopy
import unittest

from primordial.settings import Settings
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome
from primordial.simulation.simulation import Simulation


class BoidsBehaviorMetricsTests(unittest.TestCase):
    def _build_settings(self, mode: str = "boids") -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.fullscreen = False
        settings.show_hud = False
        settings.initial_population = 0
        settings.max_population = 64
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def test_metrics_are_zero_when_not_in_boids_mode_or_empty(self) -> None:
        energy_sim = Simulation(320, 180, self._build_settings("energy"), bootstrap_world=False)
        boids_sim = Simulation(320, 180, self._build_settings("boids"), bootstrap_world=False)

        for simulation in (energy_sim, boids_sim):
            metrics = simulation.get_boids_behavior_metrics()
            self.assertEqual(metrics["count"], 0)
            self.assertEqual(metrics["largest"], 0)
            self.assertEqual(metrics["loners"], 0)
            self.assertEqual(metrics["largest_share"], 0.0)
            self.assertEqual(metrics["size_bands"]["small"], 0)
            self.assertEqual(metrics["member_bands"]["small"], 0)

    def test_metrics_report_small_flocks_and_loner_distribution(self) -> None:
        simulation = Simulation(1000, 600, self._build_settings("boids"), bootstrap_world=False)
        genome = Genome(
            speed=0.5,
            size=0.3,
            sense_radius=0.35,
            aggression=0.5,
            hue=0.2,
            saturation=0.8,
            efficiency=0.6,
            complexity=0.5,
            symmetry=0.5,
            stroke_scale=0.5,
            appendages=0.5,
            rotation_speed=0.5,
            motion_style=0.5,
            longevity=0.5,
            conformity=0.6,
            depth_preference=0.5,
        )
        simulation.creatures = [
            Creature(x=100.0, y=100.0, genome=genome, vx=1.0, vy=0.0, lineage_id=1),
            Creature(x=126.0, y=106.0, genome=genome, vx=1.0, vy=0.0, lineage_id=2),
            Creature(x=520.0, y=310.0, genome=genome, vx=0.0, vy=1.0, lineage_id=3),
            Creature(x=545.0, y=321.0, genome=genome, vx=0.0, vy=1.0, lineage_id=4),
            Creature(x=860.0, y=500.0, genome=genome, vx=-1.0, vy=0.0, lineage_id=5),
        ]

        metrics = simulation.get_boids_behavior_metrics()

        self.assertEqual(metrics["count"], 2)
        self.assertEqual(metrics["largest"], 2)
        self.assertEqual(metrics["loners"], 1)
        self.assertAlmostEqual(metrics["largest_share"], 0.4)
        self.assertEqual(metrics["size_bands"]["small"], 2)
        self.assertEqual(metrics["member_bands"]["small"], 4)
        self.assertGreater(metrics["nearest_neighbor_distance_mean"], 0.0)
        self.assertGreater(metrics["neighbor_count_mean"], 0.0)


if __name__ == "__main__":
    unittest.main()
