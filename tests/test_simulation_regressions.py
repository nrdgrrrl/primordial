from __future__ import annotations

from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome


class SimulationRegressionTests(unittest.TestCase):
    def _build_settings(self, mode: str) -> Settings:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.initial_population = 0
        settings.max_population = 32
        settings.population_safety_limit = 256
        settings.food_max_particles = 64
        settings.zone_count = 0
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def _build_simulation(self, mode: str) -> Simulation:
        simulation = Simulation(200, 200, self._build_settings(mode))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def test_predator_prey_uses_mode_specific_food_spawn_rate(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.food_spawn_rate = 1.0
        simulation.settings.food_cycle_enabled = False
        simulation.settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.0

        simulation._spawn_food()

        self.assertEqual(simulation._get_food_rate(), 0.0)
        self.assertEqual(len(simulation.food_manager.particles), 0)

    def test_predator_prey_removes_prey_killed_after_its_own_turn_in_same_frame(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.0
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 1.0
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 1.0
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 1.0
        simulation.settings.mode_params["predator_prey"][
            "predator_recent_animal_energy_required"
        ] = 1.0

        prey = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=0.0, sense_radius=0.0, aggression=0.0, longevity=0.0),
            lineage_id=1,
            species="prey",
            energy=0.2,
        )
        predator = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=0.0, sense_radius=0.0, aggression=1.0, longevity=0.0),
            lineage_id=2,
            species="predator",
            energy=0.4,
        )
        prey.depth_band = 1
        predator.depth_band = 1
        simulation.creatures = [prey, predator]

        with patch.object(simulation, "_update_predator_prey_depth_band", return_value=None):
            with patch.object(simulation, "_prey_flee", return_value=False):
                with patch.object(simulation, "_creature_seek_food", return_value=None):
                    simulation.step()

        self.assertEqual(len(simulation.creatures), 1)
        self.assertIs(simulation.creatures[0], predator)
        self.assertEqual(simulation.death_events[0]["cause"], "predation")

    def test_energy_mode_removes_zero_energy_victim_before_its_turn(self) -> None:
        simulation = self._build_simulation("energy")
        simulation.settings.energy_to_reproduce = 1.0

        hunter = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=0.0, aggression=1.0, size=1.0, sense_radius=1.0, longevity=0.0),
            lineage_id=1,
            energy=0.4,
        )
        prey = Creature(
            x=100.0,
            y=100.0,
            genome=Genome(speed=0.0, aggression=0.0, size=0.2, sense_radius=0.0, longevity=0.0),
            lineage_id=2,
            energy=0.001,
        )
        simulation.creatures = [hunter, prey]

        simulation.step()

        self.assertEqual(len(simulation.creatures), 1)
        self.assertIs(simulation.creatures[0], hunter)
        self.assertEqual(simulation.death_events[0]["cause"], "energy")

    def test_energy_mode_treats_max_population_as_soft_carrying_capacity(self) -> None:
        simulation = self._build_simulation("energy")
        simulation.settings.max_population = 5
        simulation.settings.population_safety_limit = 10
        simulation.settings.energy_to_reproduce = 0.8

        simulation.creatures = [
            Creature(
                x=20.0 + (idx * 20.0),
                y=40.0,
                genome=Genome(speed=0.0, aggression=0.0, sense_radius=0.0, longevity=0.0),
                lineage_id=idx + 1,
                energy=0.9,
            )
            for idx in range(4)
        ]

        simulation.step()

        self.assertEqual(simulation.population, 8)

    def test_population_safety_limit_stops_same_frame_birth_queues(self) -> None:
        simulation = self._build_simulation("energy")
        simulation.settings.max_population = 5
        simulation.settings.population_safety_limit = 6
        simulation.settings.energy_to_reproduce = 0.8

        simulation.creatures = [
            Creature(
                x=20.0 + (idx * 20.0),
                y=40.0,
                genome=Genome(speed=0.0, aggression=0.0, sense_radius=0.0, longevity=0.0),
                lineage_id=idx + 1,
                energy=0.9,
            )
            for idx in range(4)
        ]

        simulation.step()

        self.assertEqual(simulation.population, 6)


if __name__ == "__main__":
    unittest.main()
