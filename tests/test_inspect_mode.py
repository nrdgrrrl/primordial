"""Unit tests for primordial.rendering.inspect_mode."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from primordial.rendering.inspect_mode import (
    InspectMode,
    build_creature_card,
    display_to_world,
    _guess_behavior,
)


def _make_creature(
    *,
    species: str = "prey",
    x: float = 100.0,
    y: float = 100.0,
    vx: float = 0.0,
    vy: float = 0.0,
    energy: float = 0.5,
    age: int = 50,
    lineage_id: int = 1,
    depth_band: int = 1,
    satiety_ticks_remaining: int = 0,
    recent_animal_energy: float = 0.0,
    speed: float = 0.5,
    size: float = 0.5,
    sense_radius: float = 0.5,
    aggression: float = 0.5,
    efficiency: float = 0.5,
    longevity: float = 0.5,
    radius: float = 5.0,
    max_lifespan: int = 100,
    age_fraction: float = 0.5,
    depth_band_name: str = "mid",
) -> SimpleNamespace:
    genome = SimpleNamespace(
        speed=speed,
        size=size,
        sense_radius=sense_radius,
        aggression=aggression,
        efficiency=efficiency,
        longevity=longevity,
        hue=0.5,
        saturation=0.5,
        complexity=0.5,
        symmetry=0.5,
        stroke_scale=0.5,
        appendages=0.3,
        rotation_speed=0.3,
        motion_style=0.5,
        conformity=0.5,
        depth_preference=0.5,
    )
    creature = SimpleNamespace(
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        energy=energy,
        age=age,
        genome=genome,
        species=species,
        lineage_id=lineage_id,
        depth_band=depth_band,
        satiety_ticks_remaining=satiety_ticks_remaining,
        recent_animal_energy=recent_animal_energy,
    )
    creature.get_radius = MagicMock(return_value=radius)
    creature.get_age_fraction = MagicMock(return_value=age_fraction)
    creature.get_max_lifespan = MagicMock(return_value=max_lifespan)
    creature.get_depth_band_name = MagicMock(return_value=depth_band_name)
    return creature


def _make_simulation(creatures: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(creatures=creatures or [])


class TestInspectModeToggle(unittest.TestCase):
    def test_toggle_on_remembers_prior_paused_state(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=True)
        self.assertTrue(mode.enabled)
        self.assertEqual(mode.pause_mode, "pause")
        self.assertTrue(mode.was_paused_before)

    def test_toggle_on_when_not_paused(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        self.assertTrue(mode.enabled)
        self.assertFalse(mode.was_paused_before)

    def test_toggle_off_clears_state(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.selected_creature_id = 42
        mode.toggle(simulation_paused=False)
        self.assertFalse(mode.enabled)
        self.assertIsNone(mode.selected_creature_id)
        self.assertIsNone(mode.was_paused_before)

    def test_toggle_resets_accumulator(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.pause_mode = "slow"
        mode._slow_accumulator = 99.0
        mode.toggle(simulation_paused=False)
        mode.toggle(simulation_paused=False)
        self.assertAlmostEqual(mode._slow_accumulator, 0.0)

    def test_toggle_cycle_preserves_prior_paused(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=True)
        was = mode.was_paused_before
        mode.toggle(simulation_paused=False)
        self.assertTrue(was)


class TestTogglePauseSlow(unittest.TestCase):
    def test_switches_pause_to_slow(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()
        self.assertEqual(mode.pause_mode, "slow")

    def test_switches_slow_to_pause(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()
        mode.toggle_pause_slow()
        self.assertEqual(mode.pause_mode, "pause")

    def test_no_op_when_not_enabled(self):
        mode = InspectMode()
        mode.toggle_pause_slow()
        self.assertEqual(mode.pause_mode, "pause")

    def test_resets_accumulator(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.pause_mode = "slow"
        mode._slow_accumulator = 99.0
        mode.toggle_pause_slow()
        self.assertAlmostEqual(mode._slow_accumulator, 0.0)


class TestShouldSuppressSim(unittest.TestCase):
    def test_suppress_when_enabled_and_pause(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        self.assertTrue(mode.should_suppress_sim)

    def test_not_suppress_when_slow(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()
        self.assertFalse(mode.should_suppress_sim)

    def test_not_suppress_when_disabled(self):
        mode = InspectMode()
        self.assertFalse(mode.should_suppress_sim)


class TestShouldStepSlow(unittest.TestCase):
    def test_returns_false_when_not_enabled(self):
        mode = InspectMode()
        self.assertFalse(mode.should_step_slow(1.0))

    def test_returns_false_when_pause_mode(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        self.assertFalse(mode.should_step_slow(1.0))

    def test_fires_at_slow_hz(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()  # switch to slow (2 Hz → 0.5s interval)
        self.assertFalse(mode.should_step_slow(0.1))  # acc=0.1
        self.assertFalse(mode.should_step_slow(0.1))  # acc=0.2
        self.assertFalse(mode.should_step_slow(0.1))  # acc=0.3
        self.assertFalse(mode.should_step_slow(0.1))  # acc=0.4
        self.assertTrue(mode.should_step_slow(0.2))    # acc=0.6 → fires, residual 0.1

    def test_accumulator_residual(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()
        mode.should_step_slow(0.6)
        self.assertGreater(mode._slow_accumulator, 0.0)

    def test_exact_tick_interval_fires(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_pause_slow()
        dt = 1.0 / mode.slow_hz
        self.assertTrue(mode.should_step_slow(dt))


class TestSelectAtWorldPos(unittest.TestCase):
    def test_selects_nearest_creature(self):
        c1 = _make_creature(x=100.0, y=100.0)
        c2 = _make_creature(x=110.0, y=110.0)
        sim = _make_simulation([c1, c2])
        mode = InspectMode()
        mode.select_at_world_pos(101.0, 101.0, sim)
        self.assertEqual(mode.selected_creature_id, id(c1))

    def test_clears_when_no_creature_in_range(self):
        c1 = _make_creature(x=500.0, y=500.0)
        sim = _make_simulation([c1])
        mode = InspectMode()
        mode.selected_creature_id = id(c1)
        mode.select_at_world_pos(0.0, 0.0, sim, pick_radius=10.0)
        self.assertIsNone(mode.selected_creature_id)

    def test_custom_pick_radius(self):
        c1 = _make_creature(x=100.0, y=100.0)
        sim = _make_simulation([c1])
        mode = InspectMode()
        mode.select_at_world_pos(120.0, 100.0, sim, pick_radius=30.0)
        self.assertEqual(mode.selected_creature_id, id(c1))

    def test_picks_closest_when_multiple_in_range(self):
        c1 = _make_creature(x=100.0, y=100.0)
        c2 = _make_creature(x=102.0, y=100.0)
        sim = _make_simulation([c1, c2])
        mode = InspectMode()
        mode.select_at_world_pos(103.0, 100.0, sim)
        self.assertEqual(mode.selected_creature_id, id(c2))

    def test_empty_simulation_clears_selection(self):
        sim = _make_simulation([])
        mode = InspectMode()
        mode.select_at_world_pos(100.0, 100.0, sim)
        self.assertIsNone(mode.selected_creature_id)


class TestGetSelectedCreature(unittest.TestCase):
    def test_returns_selected_creature(self):
        c1 = _make_creature()
        sim = _make_simulation([c1])
        mode = InspectMode()
        mode.selected_creature_id = id(c1)
        result = mode.get_selected_creature(sim)
        self.assertIs(result, c1)

    def test_returns_none_when_no_selection(self):
        sim = _make_simulation([])
        mode = InspectMode()
        self.assertIsNone(mode.get_selected_creature(sim))

    def test_clears_stale_selection(self):
        c1 = _make_creature()
        sim = _make_simulation([])
        mode = InspectMode()
        mode.selected_creature_id = id(c1)
        result = mode.get_selected_creature(sim)
        self.assertIsNone(result)
        self.assertIsNone(mode.selected_creature_id)

    def test_returns_none_after_creature_removed(self):
        c1 = _make_creature()
        sim = _make_simulation([c1])
        mode = InspectMode()
        mode.select_at_world_pos(c1.x, c1.y, sim)
        self.assertIsNotNone(mode.get_selected_creature(sim))
        sim.creatures.clear()
        self.assertIsNone(mode.get_selected_creature(sim))


class TestClearSelection(unittest.TestCase):
    def test_clears_selection_without_exiting(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.selected_creature_id = 42
        mode.clear_selection()
        self.assertTrue(mode.enabled)
        self.assertIsNone(mode.selected_creature_id)


class TestBuildCreatureCard(unittest.TestCase):
    def test_basic_fields(self):
        c1 = _make_creature(
            species="prey",
            energy=0.75,
            age=30,
            lineage_id=7,
            x=200.0,
            y=300.0,
            vx=1.5,
            vy=2.5,
        )
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertEqual(card["species"], "Prey")
        self.assertEqual(card["lineage"], "#7")
        self.assertIn("30", card["age"])
        self.assertEqual(card["energy"], "0.75")
        self.assertEqual(card["pos"], "(200, 300)")
        vel = math.sqrt(1.5**2 + 2.5**2)
        self.assertEqual(card["vel"], f"{vel:.2f}")

    def test_predator_fields(self):
        c1 = _make_creature(
            species="predator",
            recent_animal_energy=0.123,
            satiety_ticks_remaining=5,
        )
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertIn("recent_animal_e", card)
        self.assertIn("satiety", card)
        self.assertEqual(card["satiety"], "5t")

    def test_prey_no_predator_fields(self):
        c1 = _make_creature(species="prey")
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertNotIn("recent_animal_e", card)
        self.assertNotIn("satiety", card)

    def test_behavior_key_present(self):
        c1 = _make_creature(species="prey")
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertIn("behavior", card)

    def test_genome_traits(self):
        c1 = _make_creature(speed=0.8, size=0.3, sense_radius=0.6, aggression=0.9, efficiency=0.4)
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertEqual(card["speed"], "0.80")
        self.assertEqual(card["size"], "0.30")
        self.assertEqual(card["sense"], "0.60")
        self.assertEqual(card["aggr"], "0.90")
        self.assertEqual(card["eff"], "0.40")


class TestGuessBehavior(unittest.TestCase):
    def test_hungry_when_low_energy(self):
        c1 = _make_creature(energy=0.10)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "hungry / at risk")

    def test_sated_predator(self):
        c1 = _make_creature(species="predator", energy=0.5, satiety_ticks_remaining=10)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "sated / close-range hunting")

    def test_hunting_predator_with_recent_animal(self):
        c1 = _make_creature(species="predator", energy=0.5, recent_animal_energy=0.1)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "hunting")

    def test_foraging_predator_no_recent_animal(self):
        c1 = _make_creature(species="predator", energy=0.5, recent_animal_energy=0.01)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "foraging or hunting")

    def test_prey_foraging(self):
        c1 = _make_creature(species="prey", energy=0.5)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "foraging")

    def test_none_species_wandering(self):
        c1 = _make_creature(species="none", energy=0.5)
        sim = _make_simulation([])
        self.assertEqual(_guess_behavior(c1, sim), "wandering / foraging")


class TestDisplayToWorld(unittest.TestCase):
    def test_identity_mapping(self):
        wx, wy = display_to_world(100, 200, 800, 600, 800, 600)
        self.assertAlmostEqual(wx, 100.0)
        self.assertAlmostEqual(wy, 200.0)

    def test_scaled_up(self):
        wx, wy = display_to_world(100, 200, 400, 300, 800, 600)
        self.assertAlmostEqual(wx, 200.0)
        self.assertAlmostEqual(wy, 400.0)

    def test_zero_display_size_clamped(self):
        wx, wy = display_to_world(100, 200, 0, 0, 800, 600)
        self.assertAlmostEqual(wx, 800.0 * 100)
        self.assertAlmostEqual(wy, 600.0 * 200)

    def test_fractional_coordinates(self):
        wx, wy = display_to_world(50, 50, 100, 100, 200, 200)
        self.assertAlmostEqual(wx, 100.0)
        self.assertAlmostEqual(wy, 100.0)


if __name__ == "__main__":
    unittest.main()