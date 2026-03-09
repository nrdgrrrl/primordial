from __future__ import annotations

from copy import deepcopy
import unittest

from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome


class PredatorPreyReproductionThresholdTests(unittest.TestCase):
    def _build_settings(self, mode: str = "predator_prey") -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.initial_population = 0
        settings.max_population = 32
        settings.food_max_particles = 32
        settings.zone_count = 0
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def _build_simulation(self, mode: str = "predator_prey") -> Simulation:
        simulation = Simulation(200, 200, self._build_settings(mode))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def _build_creature(self, species: str) -> Creature:
        return Creature(
            x=100.0,
            y=100.0,
            genome=Genome(),
            lineage_id=1,
            species=species,
        )

    def test_prey_uses_role_specific_threshold_in_predator_prey_mode(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 0.70
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 0.81
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.72

        prey = self._build_creature("prey")

        self.assertEqual(simulation._get_reproduction_threshold(prey), 0.81)

    def test_predator_uses_role_specific_threshold_in_predator_prey_mode(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 0.70
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 0.80
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.71

        predator = self._build_creature("predator")

        self.assertEqual(simulation._get_reproduction_threshold(predator), 0.71)

    def test_predator_prey_falls_back_to_shared_threshold_when_role_specific_values_absent(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 0.73
        simulation.settings.mode_params["predator_prey"].pop("prey_energy_to_reproduce", None)
        simulation.settings.mode_params["predator_prey"].pop("predator_energy_to_reproduce", None)

        prey = self._build_creature("prey")
        predator = self._build_creature("predator")

        self.assertEqual(simulation._get_reproduction_threshold(prey), 0.73)
        self.assertEqual(simulation._get_reproduction_threshold(predator), 0.73)

    def test_non_predator_prey_modes_keep_shared_threshold_behavior(self) -> None:
        simulation = self._build_simulation("energy")
        simulation.settings.energy_to_reproduce = 0.84
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 0.80
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.72

        creature = self._build_creature("prey")

        self.assertEqual(simulation._get_reproduction_threshold(creature), 0.84)


if __name__ == "__main__":
    unittest.main()
