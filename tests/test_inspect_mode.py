"""Unit tests for primordial.rendering.inspect_mode."""

from __future__ import annotations

import math
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame

from primordial.rendering.inspect_mode import (
    InspectMode,
    build_creature_card,
    build_creature_summary,
    build_inspect_panel_lines,
    compute_inspect_panel_placement,
    display_to_world,
    find_nearest_creature_at_display_pos,
    friendly_inspect_label,
    _format_age_value,
    _format_confidence_value,
    _format_energy_value,
    _format_velocity_value,
    _inspect_panel_width,
    _wrap_comma_separated_text,
)
from primordial.rendering.creature_observation import (
    classify_life_stage,
    temperament_tags,
    format_tags,
    motion_style_label,
    depth_preference_label,
    infer_behavior_mode,
    infer_attention_target,
    LifeStage,
    AttentionTarget,
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
    flock_id: int = -1,
    speed: float = 0.5,
    size: float = 0.5,
    sense_radius: float = 0.5,
    aggression: float = 0.5,
    efficiency: float = 0.5,
    longevity: float = 0.5,
    conformity: float = 0.5,
    motion_style: float = 0.5,
    depth_preference: float = 0.5,
    radius: float = 5.0,
    max_lifespan: int = 100,
    age_fraction: float = 0.5,
    depth_band_name: str = "mid",
    effective_sense_radius: float = 95.0,
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
        motion_style=motion_style,
        conformity=conformity,
        depth_preference=depth_preference,
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
        flock_id=flock_id,
        satiety_ticks_remaining=satiety_ticks_remaining,
        recent_animal_energy=recent_animal_energy,
    )
    creature.get_radius = MagicMock(return_value=radius)
    creature.get_age_fraction = MagicMock(return_value=age_fraction)
    creature.get_max_lifespan = MagicMock(return_value=max_lifespan)
    creature.get_depth_band_name = MagicMock(return_value=depth_band_name)
    creature.get_effective_sense_radius = MagicMock(return_value=effective_sense_radius)
    return creature


def _make_simulation(
    creatures: list | None = None,
    *,
    width: int = 800,
    height: int = 600,
) -> SimpleNamespace:
    return SimpleNamespace(creatures=creatures or [], width=width, height=height)


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


class TestToggleDetailLevel(unittest.TestCase):
    def test_switches_compact_to_detail(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_detail_level()
        self.assertEqual(mode.detail_mode, "detail")

    def test_switches_detail_to_compact(self):
        mode = InspectMode()
        mode.toggle(simulation_paused=False)
        mode.toggle_detail_level()
        mode.toggle_detail_level()
        self.assertEqual(mode.detail_mode, "compact")

    def test_no_op_when_not_enabled(self):
        mode = InspectMode()
        mode.toggle_detail_level()
        self.assertEqual(mode.detail_mode, "compact")


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

    def test_selects_at_display_pos_when_world_is_scaled(self):
        creature = _make_creature(x=400.0, y=300.0)
        sim = _make_simulation([creature], width=1600, height=1200)
        mode = InspectMode()
        mode.select_at_display_pos(200.0, 150.0, 800, 600, sim)
        self.assertEqual(mode.selected_creature_id, id(creature))


class TestFindNearestCreatureAtDisplayPos(unittest.TestCase):
    def test_returns_nearest_creature_in_display_space(self):
        c1 = _make_creature(x=400.0, y=300.0)
        c2 = _make_creature(x=1000.0, y=300.0)
        sim = _make_simulation([c1, c2], width=1600, height=1200)

        result = find_nearest_creature_at_display_pos(198.0, 149.0, 800, 600, sim)

        self.assertIs(result, c1)

    def test_returns_none_when_click_is_out_of_range(self):
        c1 = _make_creature(x=400.0, y=300.0)
        sim = _make_simulation([c1], width=1600, height=1200)

        result = find_nearest_creature_at_display_pos(700.0, 500.0, 800, 600, sim)

        self.assertIsNone(result)


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
    def test_basic_identity_fields(self):
        c1 = _make_creature(
            species="prey",
            energy=0.75,
            age=30,
            lineage_id=7,
        )
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertEqual(card["species"], "Prey")
        self.assertEqual(card["lineage"], "#7")
        self.assertIn("stage", card)
        self.assertIn("tags", card)

    def test_section_headers_present(self):
        c1 = _make_creature(species="prey")
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertIn("section_identity", card)
        self.assertIn("section_vitals", card)
        self.assertIn("section_genome", card)
        self.assertIn("section_behavior", card)

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

    def test_motion_and_depth_pref_in_card(self):
        c1 = _make_creature(motion_style=0.2, depth_preference=0.8)
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertEqual(card["motion"], "Glide")
        self.assertEqual(card["depth_pref"], "Deep")

    def test_attention_absent_without_sim_data(self):
        c1 = _make_creature(species="prey", x=100, y=100)
        sim = _make_simulation([c1])
        card = build_creature_card(c1, sim)
        self.assertNotIn("attention", card)


class TestInspectPanelPresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.font.init()

    def test_summary_builds_narrative_story(self):
        summary = build_creature_summary(
            {
                "species": "Prey",
                "stage": "Larva",
                "behavior": "fleeing",
                "depth": "surface",
                "attention": "threat",
            }
        )
        self.assertEqual(summary, "Larval prey fleeing a threat near the surface")

    def test_label_mapping_uses_friendlier_copy(self):
        self.assertEqual(friendly_inspect_label("vel"), "Moving")
        self.assertEqual(friendly_inspect_label("attention"), "Focus")
        self.assertEqual(friendly_inspect_label("recent_animal_e"), "Recent prey energy")

    def test_compact_layout_omits_details_section(self):
        mode = InspectMode(enabled=True, detail_mode="compact")
        lines = build_inspect_panel_lines(
            {
                "species": "Predator",
                "lineage": "#12",
                "stage": "Adult",
                "behavior": "hunting",
                "depth": "mid",
                "energy": "0.81",
                "vel": "0.44",
                "age": "80 / 100  (80%)",
                "tags": "Swift, Keen-eyed",
                "motion": "Dart",
                "depth_pref": "Deep",
                "speed": "0.90",
                "size": "0.40",
                "sense": "0.80",
                "aggr": "0.88",
                "eff": "0.35",
                "pos": "(120, 44)",
                "attention": "prey",
                "attention_conf": "78%",
            },
            mode,
        )
        self.assertNotIn("Details", [line.text for line in lines if line.kind == "section"])
        state_lines = [line for line in lines if line.kind == "row_pair"]
        self.assertTrue(any(line.key == "stage" and line.secondary_key == "depth" for line in state_lines))
        self.assertTrue(any(line.key == "energy" and line.secondary_key == "vel" for line in state_lines))

    def test_detail_layout_includes_details_section(self):
        mode = InspectMode(enabled=True, detail_mode="detail")
        lines = build_inspect_panel_lines(
            {
                "species": "Predator",
                "lineage": "#12",
                "stage": "Adult",
                "behavior": "hunting",
                "depth": "mid",
                "energy": "0.81",
                "vel": "0.44",
                "age": "80 / 100  (80%)",
                "tags": "Swift, Keen-eyed",
                "motion": "Dart",
                "depth_pref": "Deep",
                "speed": "0.90",
                "size": "0.40",
                "sense": "0.80",
                "aggr": "0.88",
                "eff": "0.35",
                "pos": "(120, 44)",
                "attention": "prey",
                "attention_conf": "78%",
            },
            mode,
        )
        self.assertIn("Details", [line.text for line in lines if line.kind == "section"])
        self.assertIn("row_pair", {line.kind for line in lines})

    def test_panel_placement_anchors_top_right_with_margin(self):
        placement = compute_inspect_panel_placement(1280, 720, 320, 280)
        self.assertEqual((placement.x, placement.y), (936, 24))
        self.assertEqual(placement.height, 280)

    def test_panel_placement_clamps_height_on_small_screens(self):
        placement = compute_inspect_panel_placement(320, 140, 280, 220)
        self.assertEqual((placement.x, placement.y), (16, 24))
        self.assertEqual(placement.height, 92)

    def test_status_line_uses_readable_separators(self):
        mode = InspectMode(enabled=True, pause_mode="pause", detail_mode="compact")
        lines = build_inspect_panel_lines(None, mode)
        self.assertEqual(lines[1].text, "Paused · M: slow · D: details")

    def test_interpreted_labels_put_meaning_before_raw_values(self):
        self.assertEqual(_format_energy_value("0.90"), "Full (90%)")
        self.assertEqual(_format_confidence_value("86%"), "High (86%)")
        self.assertEqual(_format_velocity_value("0.75"), "Fast (0.75/tick)")
        self.assertEqual(_format_age_value("8 / 100  (8%)"), "8% lifespan (8 / 100t)")

    def test_panel_width_stays_compact_on_large_windows(self):
        self.assertEqual(_inspect_panel_width(1280), 304)
        self.assertEqual(_inspect_panel_width(800), 220)

    def test_tag_wrapping_preserves_whole_terms_where_possible(self):
        font = pygame.font.Font(None, 20)
        wrapped = _wrap_comma_separated_text(
            font,
            "Keen-eyed, Efficient, Long-lived",
            140,
            max_lines=2,
        )
        self.assertEqual(wrapped, ["Keen-eyed, Efficient", "Long-lived"])


class TestGuessBehavior(unittest.TestCase):
    def test_starving_when_very_low_energy(self):
        c1 = _make_creature(energy=0.05)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "starving")

    def test_foraging_when_low_energy(self):
        c1 = _make_creature(energy=0.15)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "foraging")

    def test_sated_predator(self):
        c1 = _make_creature(species="predator", energy=0.5, satiety_ticks_remaining=10)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "sated")

    def test_hunting_predator_with_recent_animal(self):
        c1 = _make_creature(species="predator", energy=0.7, recent_animal_energy=0.1)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "hunting")

    def test_stalking_predator_low_energy(self):
        c1 = _make_creature(species="predator", energy=0.40, recent_animal_energy=0.08)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "stalking")

    def test_foraging_predator_no_recent_animal(self):
        c1 = _make_creature(species="predator", energy=0.5, recent_animal_energy=0.01)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "foraging")

    def test_prey_foraging(self):
        c1 = _make_creature(species="prey", energy=0.5)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "foraging")

    def test_none_species_wandering(self):
        c1 = _make_creature(species="none", energy=0.5)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "wandering")

    def test_flocking_when_flock_id(self):
        c1 = _make_creature(species="none", energy=0.5, flock_id=3)
        sim = _make_simulation([])
        self.assertEqual(infer_behavior_mode(c1, sim), "flocking")


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


class TestClassifyLifeStage(unittest.TestCase):
    def test_larva(self):
        c = _make_creature(age_fraction=0.01)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Larva")

    def test_juvenile(self):
        c = _make_creature(age_fraction=0.20)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Juvenile")

    def test_young_adult(self):
        c = _make_creature(age_fraction=0.50)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Young adult")

    def test_adult(self):
        c = _make_creature(age_fraction=0.70)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Adult")

    def test_elder(self):
        c = _make_creature(age_fraction=0.90)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Elder")

    def test_decrepit(self):
        c = _make_creature(age_fraction=0.98)
        stage = classify_life_stage(c)
        self.assertEqual(stage.label, "Decrepit")

    def test_returns_age_fraction(self):
        c = _make_creature(age_fraction=0.42)
        stage = classify_life_stage(c)
        self.assertAlmostEqual(stage.age_fraction, 0.42)


class TestTemperamentTags(unittest.TestCase):
    def test_aggressive_tag(self):
        c = _make_creature(aggression=0.80)
        self.assertIn("Aggressive", temperament_tags(c))

    def test_docile_tag(self):
        c = _make_creature(aggression=0.20)
        self.assertIn("Docile", temperament_tags(c))

    def test_no_middling_tags(self):
        c = _make_creature(aggression=0.5, speed=0.5, size=0.5)
        tags = temperament_tags(c)
        for t in ["Aggressive", "Docile", "Swift", "Sluggish", "Large", "Tiny"]:
            self.assertNotIn(t, tags)

    def test_swift_tag(self):
        c = _make_creature(speed=0.75)
        self.assertIn("Swift", temperament_tags(c))

    def test_keen_eyed_tag(self):
        c = _make_creature(sense_radius=0.80)
        self.assertIn("Keen-eyed", temperament_tags(c))

    def test_efficient_tag(self):
        c = _make_creature(efficiency=0.75)
        self.assertIn("Efficient", temperament_tags(c))

    def test_long_lived_tag(self):
        c = _make_creature(longevity=0.80)
        self.assertIn("Long-lived", temperament_tags(c))

    def test_flockish_tag(self):
        c = _make_creature(conformity=0.75)
        self.assertIn("Flockish", temperament_tags(c))

    def test_loner_tag(self):
        c = _make_creature(conformity=0.20)
        self.assertIn("Loner", temperament_tags(c))


class TestFormatTags(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(format_tags([]), "—")

    def test_up_to_max(self):
        self.assertEqual(format_tags(["A", "B", "C", "D"], max_tags=3), "A, B, C")

    def test_fewer_than_max(self):
        self.assertEqual(format_tags(["A", "B"], max_tags=5), "A, B")


class TestMotionStyleLabel(unittest.TestCase):
    def test_glide(self):
        self.assertEqual(motion_style_label(0.1), "Glide")

    def test_swim(self):
        self.assertEqual(motion_style_label(0.5), "Swim")

    def test_dart(self):
        self.assertEqual(motion_style_label(0.8), "Dart")

    def test_boundary_glide_swim(self):
        self.assertEqual(motion_style_label(0.34), "Swim")

    def test_boundary_swim_dart(self):
        self.assertEqual(motion_style_label(0.67), "Dart")


class TestDepthPreferenceLabel(unittest.TestCase):
    def test_surface(self):
        self.assertEqual(depth_preference_label(0.1), "Surface")

    def test_mid(self):
        self.assertEqual(depth_preference_label(0.5), "Mid")

    def test_deep(self):
        self.assertEqual(depth_preference_label(0.9), "Deep")


class TestInferAttentionTarget(unittest.TestCase):
    def test_returns_none_when_no_sim_data(self):
        c = _make_creature(species="prey", x=100, y=100)
        sim = _make_simulation([c])
        result = infer_attention_target(c, sim)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
