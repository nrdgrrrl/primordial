from __future__ import annotations

from copy import deepcopy
import random
import unittest
from unittest.mock import patch

from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome
from primordial.simulation.zones import Zone


class EcologySensingTests(unittest.TestCase):
    def _build_settings(self, mode: str = "energy") -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.visual_theme = "ocean"
        settings.show_hud = False
        settings.fullscreen = False
        settings.initial_population = 0
        settings.max_population = 32
        settings.food_max_particles = 32
        settings.zone_count = 0
        settings.zone_strength = 0.8
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def _build_simulation(self, mode: str = "energy") -> Simulation:
        simulation = Simulation(200, 200, self._build_settings(mode))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def test_zone_sensing_modifiers_create_clearer_and_obscured_habitats(self) -> None:
        simulation = self._build_simulation()
        simulation.zone_manager.zones = [
            Zone(x=50.0, y=50.0, radius=40.0, zone_type="open_water", local_strength=1.0),
            Zone(x=150.0, y=150.0, radius=40.0, zone_type="kelp_forest", local_strength=1.0),
        ]

        open_water_modifier = simulation.zone_manager.get_sensing_modifier_at(50.0, 50.0)
        kelp_modifier = simulation.zone_manager.get_sensing_modifier_at(150.0, 150.0)

        self.assertGreater(open_water_modifier, 1.0)
        self.assertLess(kelp_modifier, 1.0)
        self.assertGreater(open_water_modifier, kelp_modifier)

    def test_sense_target_position_returns_none_when_target_is_out_of_range(self) -> None:
        simulation = self._build_simulation()
        simulation.zone_manager.zones = [
            Zone(x=50.0, y=50.0, radius=60.0, zone_type="kelp_forest", local_strength=1.0),
        ]
        creature = Creature(x=50.0, y=50.0, genome=Genome(sense_radius=0.0), lineage_id=1)
        sensed = simulation._sense_target_position(creature, 100.0, 50.0)

        self.assertIsNone(sensed)

    def test_sense_target_position_returns_noisy_estimate_when_detected(self) -> None:
        simulation = self._build_simulation()
        simulation.zone_manager.zones = [
            Zone(x=50.0, y=50.0, radius=60.0, zone_type="open_water", local_strength=1.0),
        ]
        creature = Creature(x=50.0, y=50.0, genome=Genome(sense_radius=1.0), lineage_id=1)

        with patch("random.random", return_value=0.0), patch(
            "random.gauss",
            side_effect=[5.0, -7.0],
        ):
            sensed = simulation._sense_target_position(creature, 80.0, 90.0)

        self.assertEqual(sensed, (85.0, 83.0))

    def test_creature_seek_food_uses_sensed_position_not_exact_food_position(self) -> None:
        simulation = self._build_simulation()
        creature = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=1.0, motion_style=0.5),
            lineage_id=1,
        )
        simulation.food_manager.spawn(130.0, 100.0)

        with patch.object(simulation, "_sense_target_position", return_value=(100.0, 130.0)):
            simulation._creature_seek_food(creature)

        self.assertGreater(creature.vy, 0.0)
        self.assertLess(abs(creature.vx), 0.05)

    def test_lineage_branching_can_follow_ecological_trait_divergence(self) -> None:
        simulation = self._build_simulation()
        parent = Genome(
            speed=0.2,
            sense_radius=0.2,
            aggression=0.2,
            efficiency=0.2,
            longevity=0.2,
            hue=0.5,
        )
        child = Genome(
            speed=0.55,
            sense_radius=0.55,
            aggression=0.2,
            efficiency=0.2,
            longevity=0.2,
            hue=0.5,
        )
        near_child = Genome(
            speed=0.24,
            sense_radius=0.24,
            aggression=0.2,
            efficiency=0.2,
            longevity=0.2,
            hue=0.5,
        )

        self.assertTrue(simulation._should_branch_lineage(parent, child))
        self.assertFalse(simulation._should_branch_lineage(parent, near_child))

    def test_predator_prey_population_survives_seeded_window(self) -> None:
        settings = self._build_settings("predator_prey")
        settings.food_max_particles = 260
        settings.zone_count = 5
        settings.zone_strength = 0.75
        settings.mode_params["predator_prey"].update({
            "initial_population": 110,
            "predator_fraction": 0.28,
            "food_spawn_rate": 0.55,
            "mutation_rate": 0.06,
            "energy_to_reproduce": 0.72,
        })

        random.seed(12345)
        simulation = Simulation(1280, 720, settings)
        for _ in range(2400):
            simulation.step()
            if simulation.population == 0:
                break

        self.assertGreater(simulation.population, 0)

    def test_predator_prey_default_mix_survives_seeded_window(self) -> None:
        settings = self._build_settings("predator_prey")
        settings.food_max_particles = 260
        settings.zone_count = 5
        settings.zone_strength = 0.75
        settings.mode_params["predator_prey"]["initial_population"] = 120

        random.seed(12345)
        simulation = Simulation(1280, 720, settings)
        for _ in range(2400):
            simulation.step()
            if simulation.population == 0:
                break

        self.assertGreater(simulation.population, 0)

    def test_energy_population_survives_seeded_window_with_legacy_default_food_rate(self) -> None:
        settings = self._build_settings("energy")
        settings.initial_population = 80
        settings.max_population = 220
        settings.food_spawn_rate = 0.6
        settings.food_max_particles = 300
        settings.food_cycle_enabled = True
        settings.food_cycle_period = 1800
        settings.energy_to_reproduce = 0.80
        settings.zone_count = 5
        settings.zone_strength = 0.8

        random.seed(12345)
        simulation = Simulation(1280, 720, settings)
        for _ in range(3200):
            simulation.step()
            if simulation.population == 0:
                break

        self.assertGreater(simulation.population, 0)


if __name__ == "__main__":
    unittest.main()
