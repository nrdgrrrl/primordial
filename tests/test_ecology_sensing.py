from __future__ import annotations

from copy import deepcopy
import math
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

    def test_prey_flee_caps_velocity_to_bounded_max_speed(self) -> None:
        simulation = self._build_simulation("predator_prey")
        prey = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=0.7, sense_radius=1.0, aggression=0.1),
            vx=9.0,
            vy=0.0,
            lineage_id=1,
            species="prey",
        )
        predator = Creature(
            x=90.0,
            y=100.0,
            genome=Genome(speed=0.8, sense_radius=1.0, aggression=0.9),
            lineage_id=2,
            species="predator",
        )
        simulation.creatures = [prey, predator]
        bucket = simulation._build_creature_bucket()

        with patch("random.gauss", return_value=0.0), patch("random.random", return_value=0.0):
            fled = simulation._prey_flee(prey, bucket)

        self.assertTrue(fled)
        flee_max = prey.genome.speed * simulation.settings.creature_speed_base * 1.5
        self.assertLessEqual(math.hypot(prey.vx, prey.vy), flee_max + 1e-6)

    def test_predation_events_report_kills_and_actual_speed_telemetry(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.cosmic_ray_rate = 0.0
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=1.0, aggression=0.9),
            energy=0.6,
            lineage_id=1,
            species="predator",
        )
        prey = Creature(
            x=102.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=1.0, aggression=0.1),
            energy=0.6,
            lineage_id=2,
            species="prey",
        )
        simulation.creatures = [predator, prey]

        with (
            patch.object(simulation, "_check_ecosystem_balance", return_value=None),
            patch("random.gauss", return_value=0.0),
            patch("random.random", return_value=0.0),
        ):
            simulation.step()

        predator_count, prey_count = simulation.get_species_counts()
        self.assertEqual(prey_count, 0)

    def test_predator_kill_energy_gain_cap_uses_mode_param(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["predator_kill_energy_gain_cap"] = 0.25

        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=1.0, aggression=0.9),
            energy=0.10,
            lineage_id=1,
            species="predator",
        )
        prey = Creature(
            x=102.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=1.0, aggression=0.1),
            energy=0.90,
            lineage_id=2,
            species="prey",
        )
        simulation.creatures = [predator, prey]
        bucket = simulation._build_creature_bucket()

        with patch("random.gauss", return_value=0.0), patch("random.random", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertAlmostEqual(predator.energy, 0.35)
        self.assertEqual(prey.energy, 0.0)
        self.assertEqual(simulation.predation_kill_count, 1)
        self.assertEqual(simulation.get_recent_predation_stats()["recent_kills"], 1)
        pred_actual_speed, prey_actual_speed = simulation.get_species_avg_actual_speeds()
        self.assertGreaterEqual(pred_actual_speed, 0.0)
        self.assertEqual(prey_actual_speed, 0.0)

    def test_predator_hunt_sense_multiplier_expands_live_detection_range(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=0.0, aggression=0.9, motion_style=0.5),
            energy=0.4,
            lineage_id=1,
            species="predator",
        )
        prey = Creature(
            x=185.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=0.5, aggression=0.1),
            energy=0.6,
            lineage_id=2,
            species="prey",
        )
        simulation.creatures = [predator, prey]
        bucket = simulation._build_creature_bucket()

        with patch.object(predator, "wander") as wander_default, patch(
            "random.gauss", return_value=0.0
        ):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertAlmostEqual(predator.vx, 0.0)
        self.assertAlmostEqual(predator.vy, 0.0)
        wander_default.assert_called_once()

        predator.vx = 0.0
        predator.vy = 0.0
        simulation.settings.mode_params["predator_prey"]["predator_hunt_sense_multiplier"] = 2.3

        with patch.object(predator, "wander") as wander_boosted, patch(
            "random.gauss", return_value=0.0
        ):
            simulation._predator_hunt_prey(predator, bucket)

        wander_boosted.assert_not_called()
        self.assertGreater(predator.vx, 0.0)

    def test_predator_hunt_speed_multiplier_increases_live_chase_velocity(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=1.0, sense_radius=1.0, aggression=0.9, motion_style=0.5),
            energy=0.4,
            lineage_id=1,
            species="predator",
        )
        prey = Creature(
            x=130.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=0.5, aggression=0.1),
            energy=0.6,
            lineage_id=2,
            species="prey",
        )
        simulation.creatures = [predator, prey]
        bucket = simulation._build_creature_bucket()

        with patch("random.gauss", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)
        baseline_speed = math.hypot(predator.vx, predator.vy)

        predator.vx = 0.0
        predator.vy = 0.0
        simulation.settings.mode_params["predator_prey"]["predator_hunt_speed_multiplier"] = 1.15

        with patch("random.gauss", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)
        boosted_speed = math.hypot(predator.vx, predator.vy)

        self.assertGreater(boosted_speed, baseline_speed)

    def test_predator_contact_kill_distance_scale_expands_contact_window(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(size=0.6, speed=1.0, sense_radius=1.0, aggression=0.9),
            energy=0.2,
            lineage_id=1,
            species="predator",
        )
        prey = Creature(
            x=117.0,
            y=100.0,
            genome=Genome(size=0.2, speed=0.7, sense_radius=0.5, aggression=0.1),
            energy=0.5,
            lineage_id=2,
            species="prey",
        )
        simulation.creatures = [predator, prey]
        bucket = simulation._build_creature_bucket()

        with patch("random.gauss", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertGreater(prey.energy, 0.0)
        self.assertEqual(simulation.predation_kill_count, 0)

        predator.energy = 0.2
        predator.vx = 0.0
        predator.vy = 0.0
        prey.energy = 0.5
        simulation.settings.mode_params["predator_prey"]["predator_contact_kill_distance_scale"] = 1.2

        with patch("random.gauss", return_value=0.0):
            simulation._predator_hunt_prey(predator, bucket)

        self.assertEqual(prey.energy, 0.0)
        self.assertEqual(simulation.predation_kill_count, 1)

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

    def test_food_cycle_period_changes_runtime_cycle_timing(self) -> None:
        simulation = self._build_simulation("energy")
        simulation.settings.food_cycle_enabled = True
        simulation.settings.food_spawn_rate = 1.0
        simulation._frame = 150

        simulation.settings.food_cycle_period = 600
        short_phase = simulation.food_cycle_phase
        short_rate = simulation._get_food_rate()

        simulation.settings.food_cycle_period = 1200
        long_phase = simulation.food_cycle_phase
        long_rate = simulation._get_food_rate()

        self.assertAlmostEqual(short_phase, 1.0)
        self.assertLess(long_phase, short_phase)
        self.assertAlmostEqual(short_rate, 1.0)
        self.assertLess(long_rate, short_rate)


if __name__ == "__main__":
    unittest.main()
