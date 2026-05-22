from __future__ import annotations

from copy import deepcopy
import unittest

from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome
from primordial.simulation.zones import Zone, ZoneManager


class PredatorRefugeTests(unittest.TestCase):
    def _build_settings(self, mode: str = "predator_prey") -> Settings:
        settings = Settings()
        settings.mode_params = deepcopy(settings.DEFAULT_MODE_PARAMS)
        settings.sim_mode = mode
        settings.initial_population = 0
        settings.max_population = 64
        settings.food_max_particles = 32
        settings.epistasis_enabled = False
        settings.zone_count = 0
        settings.zone_strength = 0.8
        if mode in settings.mode_params and "initial_population" in settings.mode_params[mode]:
            settings.mode_params[mode]["initial_population"] = 0
        return settings

    def _build_simulation(self, mode: str = "predator_prey") -> Simulation:
        simulation = Simulation(400, 400, self._build_settings(mode))
        simulation.creatures.clear()
        simulation.food_manager.clear()
        simulation.zone_manager.zones = [
            Zone(
                x=100.0,
                y=100.0,
                radius=80.0,
                zone_type="hunting_ground",
                local_strength=1.0,
            )
        ]
        return simulation

    def _creature(
        self,
        species: str,
        *,
        x: float = 100.0,
        y: float = 100.0,
    ) -> Creature:
        creature = Creature(
            x=x,
            y=y,
            genome=Genome(),
            lineage_id=1,
            species=species,
        )
        creature.energy = 0.5
        creature.vx = 0.0
        creature.vy = 0.0
        return creature

    def test_zone_manager_public_context_helpers_report_zone_and_influence(self) -> None:
        zone_manager = ZoneManager(400, 400, 0, 0.8)
        zone_manager.zones = [
            Zone(
                x=200.0,
                y=200.0,
                radius=100.0,
                zone_type="hunting_ground",
                local_strength=0.9,
            )
        ]

        context = zone_manager.get_zone_context_at(200.0, 200.0)

        self.assertEqual(zone_manager.get_zone_type_at(200.0, 200.0), "hunting_ground")
        self.assertEqual(context.zone_type, "hunting_ground")
        self.assertGreater(context.influence, 0.0)
        self.assertEqual(zone_manager.get_zone_type_at(10.0, 10.0), None)
        self.assertEqual(zone_manager.get_zone_influence_at(10.0, 10.0), 0.0)

    def test_refuge_modifiers_are_neutral_outside_predator_prey_mode(self) -> None:
        simulation = self._build_simulation("energy")
        predator = self._creature("predator")
        simulation.creatures = [predator]

        modifiers = simulation._get_predator_refuge_modifiers(
            predator,
            simulation._build_creature_bucket(),
        )

        self.assertFalse(modifiers.active)
        self.assertEqual(modifiers.hunt_sense_mult, 1.0)
        self.assertEqual(modifiers.contact_mult, 1.0)
        self.assertEqual(modifiers.depth_transition_mult, 1.0)
        self.assertEqual(modifiers.hunting_cost_mult, 1.0)

    def test_refuge_modifiers_apply_only_to_predators(self) -> None:
        simulation = self._build_simulation("predator_prey")
        prey = self._creature("prey")
        simulation.creatures = [prey]

        modifiers = simulation._get_predator_refuge_modifiers(
            prey,
            simulation._build_creature_bucket(),
        )

        self.assertFalse(modifiers.active)
        self.assertEqual(modifiers.hunt_sense_mult, 1.0)

    def test_hunting_ground_gives_positive_but_clamped_predator_modifier(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = self._creature("predator")
        simulation.creatures = [predator]
        predator_prey = simulation.settings.mode_params["predator_prey"]
        predator_prey["predator_refuge_hunt_sense_bonus"] = 0.5
        predator_prey["predator_refuge_contact_bonus"] = 0.5
        predator_prey["predator_refuge_depth_transition_bonus"] = 0.5
        predator_prey["predator_refuge_movement_cost_reduction"] = 0.5

        modifiers = simulation._get_predator_refuge_modifiers(
            predator,
            simulation._build_creature_bucket(),
        )

        self.assertTrue(modifiers.active)
        self.assertGreater(modifiers.hunt_sense_mult, 1.0)
        self.assertGreater(modifiers.contact_mult, 1.0)
        self.assertGreater(modifiers.depth_transition_mult, 1.0)
        self.assertLess(modifiers.hunting_cost_mult, 1.0)
        self.assertLessEqual(modifiers.hunt_sense_mult, 1.12)
        self.assertLessEqual(modifiers.contact_mult, 1.12)
        self.assertLessEqual(modifiers.depth_transition_mult, 1.15)
        self.assertGreaterEqual(modifiers.hunting_cost_mult, 0.90)

    def test_high_local_predator_density_damps_refuge_modifier(self) -> None:
        simulation = self._build_simulation("predator_prey")
        predator = self._creature("predator", x=100.0, y=100.0)
        low_density_creatures = [predator]
        simulation.creatures = low_density_creatures
        low_density = simulation._get_predator_refuge_modifiers(
            predator,
            simulation._build_creature_bucket(),
        )

        crowded = [predator]
        for i in range(7):
            crowded.append(
                self._creature(
                    "predator",
                    x=105.0 + i,
                    y=100.0,
                )
            )
        simulation.creatures = crowded
        high_density = simulation._get_predator_refuge_modifiers(
            predator,
            simulation._build_creature_bucket(),
        )

        self.assertGreater(low_density.refuge_factor, high_density.refuge_factor)
        self.assertGreaterEqual(high_density.local_predator_count, 7)
        self.assertLessEqual(high_density.contact_mult, low_density.contact_mult)

    def test_no_modifier_applies_when_refuge_is_disabled(self) -> None:
        simulation = self._build_simulation("predator_prey")
        simulation.settings.mode_params["predator_prey"]["predator_refuge_enabled"] = False
        predator = self._creature("predator")
        simulation.creatures = [predator]

        modifiers = simulation._get_predator_refuge_modifiers(
            predator,
            simulation._build_creature_bucket(),
        )

        self.assertFalse(modifiers.active)
        self.assertEqual(modifiers.hunt_sense_mult, 1.0)
        self.assertEqual(modifiers.contact_mult, 1.0)


if __name__ == "__main__":
    unittest.main()
