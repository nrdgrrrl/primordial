from __future__ import annotations

from copy import deepcopy
import math
import random
import unittest

from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.genome import Genome
from primordial.simulation.phenotype import resolve_effective_phenotype


class PhenotypeEpistasisTests(unittest.TestCase):
    def _build_settings(self, mode: str = "energy", *, epistasis_enabled: bool = True) -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.visual_theme = "ocean"
        settings.show_hud = False
        settings.fullscreen = False
        settings.initial_population = 0
        settings.max_population = 48
        settings.food_max_particles = 64
        settings.zone_count = 0
        settings.zone_strength = 0.8
        settings.epistasis_enabled = epistasis_enabled
        settings.epistasis_strength = 1.0
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def _build_simulation(self, mode: str = "energy", *, epistasis_enabled: bool = True) -> Simulation:
        simulation = Simulation(320, 180, self._build_settings(mode, epistasis_enabled=epistasis_enabled))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = []
        return simulation

    def test_effective_phenotype_is_deterministic_for_same_genome(self) -> None:
        genome = Genome(
            speed=0.82,
            size=0.22,
            sense_radius=0.77,
            efficiency=0.63,
            complexity=0.68,
            symmetry=0.74,
            appendages=0.31,
            motion_style=0.28,
            longevity=0.54,
            depth_preference=0.88,
        )

        first = resolve_effective_phenotype(genome, species="prey")
        second = resolve_effective_phenotype(genome, species="prey")

        self.assertEqual(first, second)

    def test_disabling_epistasis_returns_neutral_modifiers(self) -> None:
        phenotype = resolve_effective_phenotype(
            Genome(speed=1.0, size=1.0, sense_radius=1.0, complexity=1.0),
            species="predator",
            epistasis_enabled=False,
            epistasis_strength=1.0,
        )

        self.assertEqual(phenotype.speed_mult, 1.0)
        self.assertEqual(phenotype.movement_cost_mult, 1.0)
        self.assertEqual(phenotype.metabolic_cost_mult, 1.0)
        self.assertEqual(phenotype.sense_radius_mult, 1.0)
        self.assertEqual(phenotype.reproduction_threshold_mult, 1.0)
        self.assertEqual(phenotype.predation_contact_mult, 1.0)
        self.assertEqual(phenotype.flee_agility_mult, 1.0)
        self.assertEqual(phenotype.depth_transition_mult, 1.0)
        self.assertEqual(phenotype.in_band_sense_mult, 1.0)
        self.assertEqual(phenotype.cross_band_sense_mult, 1.0)

    def test_modifiers_are_clamped_and_finite(self) -> None:
        phenotype = resolve_effective_phenotype(
            Genome(
                speed=1.0,
                size=1.0,
                sense_radius=1.0,
                efficiency=0.0,
                complexity=1.0,
                symmetry=0.0,
                appendages=1.0,
                motion_style=1.0,
                longevity=1.0,
                depth_preference=1.0,
                aggression=1.0,
            ),
            species="predator",
            epistasis_enabled=True,
            epistasis_strength=1.5,
        )

        for value in (
            phenotype.speed_mult,
            phenotype.movement_cost_mult,
            phenotype.metabolic_cost_mult,
            phenotype.sense_radius_mult,
            phenotype.food_efficiency_mult,
            phenotype.reproduction_threshold_mult,
            phenotype.predation_contact_mult,
            phenotype.flee_agility_mult,
            phenotype.depth_transition_mult,
            phenotype.in_band_sense_mult,
            phenotype.cross_band_sense_mult,
        ):
            self.assertTrue(math.isfinite(value))
            self.assertGreater(value, 0.0)

    def test_high_speed_large_body_costs_more_than_high_speed_small_body(self) -> None:
        large_fast = resolve_effective_phenotype(
            Genome(speed=0.95, size=0.90),
            species="predator",
        )
        small_fast = resolve_effective_phenotype(
            Genome(speed=0.95, size=0.20),
            species="predator",
        )

        self.assertGreater(large_fast.movement_cost_mult, small_fast.movement_cost_mult)

    def test_high_longevity_increases_reproduction_burden(self) -> None:
        short_lived = resolve_effective_phenotype(Genome(longevity=0.0), species="prey")
        long_lived = resolve_effective_phenotype(Genome(longevity=1.0), species="prey")

        self.assertGreater(
            long_lived.reproduction_threshold_mult,
            short_lived.reproduction_threshold_mult,
        )

    def test_depth_specialists_gain_in_band_but_lose_cross_band_sensing(self) -> None:
        specialist = resolve_effective_phenotype(
            Genome(depth_preference=0.95),
            species="predator",
        )
        generalist = resolve_effective_phenotype(
            Genome(depth_preference=0.50),
            species="predator",
        )

        self.assertGreater(specialist.in_band_sense_mult, generalist.in_band_sense_mult)
        self.assertLess(specialist.cross_band_sense_mult, generalist.cross_band_sense_mult)

    def test_headless_predator_prey_runs_with_epistasis_enabled(self) -> None:
        settings = self._build_settings("predator_prey", epistasis_enabled=True)
        settings.mode_params["predator_prey"]["initial_population"] = 48
        settings.mode_params["predator_prey"]["predator_fraction"] = 0.22
        settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.70

        random.seed(20260522)
        simulation = Simulation(640, 360, settings)
        for _ in range(180):
            simulation.step()

        self.assertGreater(simulation.population, 0)
        self.assertTrue(simulation.get_epistasis_summary()["enabled"])

    def test_headless_predator_prey_runs_with_epistasis_disabled(self) -> None:
        settings = self._build_settings("predator_prey", epistasis_enabled=False)
        settings.mode_params["predator_prey"]["initial_population"] = 48
        settings.mode_params["predator_prey"]["predator_fraction"] = 0.22
        settings.mode_params["predator_prey"]["food_spawn_rate"] = 0.70

        random.seed(20260522)
        simulation = Simulation(640, 360, settings)
        for _ in range(180):
            simulation.step()

        self.assertGreater(simulation.population, 0)
        self.assertFalse(simulation.get_epistasis_summary()["enabled"])

    def test_energy_boids_and_drift_still_step_with_epistasis_enabled(self) -> None:
        for mode in ("energy", "boids", "drift"):
            with self.subTest(mode=mode):
                settings = self._build_settings(mode, epistasis_enabled=True)
                settings.initial_population = 24
                if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
                    settings.mode_params[mode]["initial_population"] = 24
                random.seed(4242)
                simulation = Simulation(480, 270, settings)
                for _ in range(90):
                    simulation.step()
                self.assertGreaterEqual(simulation.population, 0)
                self.assertTrue(
                    all(
                        math.isfinite(creature.energy) and 0.0 <= creature.energy <= 1.0
                        for creature in simulation.creatures
                    )
                )


if __name__ == "__main__":
    unittest.main()
