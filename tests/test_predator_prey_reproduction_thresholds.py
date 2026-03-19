from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

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

    def _build_creature(self, species: str, *, longevity: float = 0.5) -> Creature:
        return Creature(
            x=100.0,
            y=100.0,
            genome=Genome(longevity=longevity),
            lineage_id=1,
            species=species,
        )

    def test_predator_prey_step_uses_role_specific_predator_threshold(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 0.95
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.70
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 0.95

        predator = self._build_creature("predator", longevity=0.0)
        predator.energy = 0.72
        predator.recent_animal_energy = 0.5
        predator.age = 0
        predator.vx = 0.0
        predator.vy = 0.0
        predator.x = 20.0
        predator.y = 20.0

        prey = self._build_creature("prey", longevity=0.0)
        prey.energy = 0.10
        prey.age = 0
        prey.vx = 0.0
        prey.vy = 0.0
        prey.x = 180.0
        prey.y = 180.0

        simulation.creatures = [predator, prey]
        simulation.step()

        predator_count, _prey_count = simulation.get_species_counts()
        self.assertEqual(predator_count, 2)

    def test_predator_prey_step_uses_role_specific_prey_threshold(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["energy_to_reproduce"] = 0.70
        simulation.settings.mode_params["predator_prey"]["prey_energy_to_reproduce"] = 0.80
        simulation.settings.mode_params["predator_prey"]["predator_energy_to_reproduce"] = 0.70

        prey = self._build_creature("prey", longevity=0.0)
        prey.energy = 0.75
        prey.age = 0
        prey.vx = 0.0
        prey.vy = 0.0
        prey.x = 20.0
        prey.y = 20.0

        predator = self._build_creature("predator", longevity=0.0)
        predator.energy = 0.10
        predator.age = 0
        predator.vx = 0.0
        predator.vy = 0.0
        predator.x = 180.0
        predator.y = 180.0

        simulation.creatures = [prey, predator]
        simulation.step()

        _predator_count, prey_count = simulation.get_species_counts()
        self.assertEqual(prey_count, 1)

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

    def test_predator_prey_offspring_can_flip_species_at_birth(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"][
            "prey_to_predator_aggression_threshold"
        ] = 0.58

        prey = self._build_creature("prey", longevity=0.0)
        prey.energy = 0.90
        prey.genome = Genome(aggression=0.20, longevity=0.0)

        with patch(
            "primordial.simulation.simulation.Genome.mutate",
            return_value=Genome(aggression=0.70, longevity=0.0),
        ):
            offspring = simulation._reproduce_pp(prey, mutation_rate=0.0)

        self.assertIsNotNone(offspring)
        self.assertEqual(offspring.species, "predator")

    def test_cosmic_ray_uses_hysteresis_thresholds_for_species_flip(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = self._build_creature("predator", longevity=0.0)
        predator.genome = Genome(aggression=0.60, longevity=0.0)
        simulation.creatures = [predator]
        simulation._register_predator_life(predator, origin="initial")

        with patch(
            "primordial.simulation.simulation.Genome.mutate_one",
            return_value=(Genome(aggression=0.10, longevity=0.0), "aggression"),
        ):
            simulation._apply_cosmic_ray_pp(predator)

        self.assertEqual(predator.species, "prey")


if __name__ == "__main__":
    unittest.main()
