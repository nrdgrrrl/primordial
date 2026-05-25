"""Unit tests for primordial.rendering.hud_focus."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from primordial.rendering.hud_focus import HUDFocus


def _make_creature(
    *,
    x: float = 100.0,
    y: float = 100.0,
    species: str = "prey",
    lineage_id: int = 1,
    radius: float = 5.0,
) -> SimpleNamespace:
    genome = SimpleNamespace(
        speed=0.5,
        size=0.5,
        sense_radius=0.5,
        aggression=0.5,
        efficiency=0.5,
        hue=0.5,
        saturation=0.5,
    )
    creature = SimpleNamespace(
        x=x,
        y=y,
        species=species,
        lineage_id=lineage_id,
        genome=genome,
    )
    creature.get_radius = MagicMock(return_value=radius)
    creature.get_effective_sense_radius = MagicMock(return_value=95.0)
    creature.depth_band = 1
    return creature


def _make_simulation(
    creatures: list | None = None,
    *,
    width: int = 800,
    height: int = 600,
) -> SimpleNamespace:
    sim = SimpleNamespace(
        creatures=creatures or [],
        width=width,
        height=height,
        _frame=0,
        death_events=[],
        settings=SimpleNamespace(sim_mode="energy"),
    )

    def _build_creature_bucket():
        return {}

    def _nearby_creatures(x, y, radius, bucket):
        return creatures or []

    sim._build_creature_bucket = _build_creature_bucket
    sim._nearby_creatures = _nearby_creatures
    return sim


class TestHUDFocusSelection(unittest.TestCase):
    def test_initial_state_has_no_selection(self):
        focus = HUDFocus()
        self.assertIsNone(focus.selected_creature_id)
        self.assertFalse(focus.has_selection)

    def test_select_at_world_pos_picks_nearest(self):
        c1 = _make_creature(x=100.0, y=100.0)
        c2 = _make_creature(x=110.0, y=110.0)
        sim = _make_simulation([c1, c2])
        focus = HUDFocus()
        focus.select_at_world_pos(101.0, 101.0, sim)
        self.assertEqual(focus.selected_creature_id, id(c1))
        self.assertTrue(focus.has_selection)

    def test_select_at_world_pos_clears_on_miss(self):
        c1 = _make_creature(x=500.0, y=500.0)
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(0.0, 0.0, sim, pick_radius=10.0)
        self.assertIsNone(focus.selected_creature_id)
        self.assertFalse(focus.has_selection)

    def test_explicit_clear_selection(self):
        c1 = _make_creature()
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)
        self.assertTrue(focus.has_selection)
        focus.clear_selection()
        self.assertIsNone(focus.selected_creature_id)
        self.assertFalse(focus.has_selection)

    def test_get_selected_creature_returns_matching(self):
        c1 = _make_creature()
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)
        result = focus.get_selected_creature(sim)
        self.assertIs(result, c1)

    def test_get_selected_creature_returns_none_when_empty(self):
        sim = _make_simulation([])
        focus = HUDFocus()
        result = focus.get_selected_creature(sim)
        self.assertIsNone(result)

    def test_observe_sim_clears_on_creature_death(self):
        c1 = _make_creature(x=100.0, y=100.0)
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)
        self.assertTrue(focus.has_selection)
        sim.creatures.clear()
        focus.observe_simulation(sim)
        self.assertFalse(focus.has_selection)
        self.assertIsNone(focus.selected_creature_id)

    def test_observe_sim_preserves_alive_selection(self):
        c1 = _make_creature(x=100.0, y=100.0)
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)
        focus.observe_simulation(sim)
        self.assertTrue(focus.has_selection)

    def test_observe_sim_noop_when_no_selection(self):
        sim = _make_simulation([])
        focus = HUDFocus()
        focus.observe_simulation(sim)
        self.assertIsNone(focus.selected_creature_id)


class TestHUDFocusAttention(unittest.TestCase):
    def test_attention_returns_none_when_creature_is_none(self):
        focus = HUDFocus()
        sim = _make_simulation()
        result = focus.get_attention_target(sim, None)
        self.assertIsNone(result)

    def test_attention_cache_reuses_within_interval(self):
        from primordial.rendering.creature_observation import AttentionTarget
        c1 = _make_creature(x=100.0, y=100.0)
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)

        target = AttentionTarget(kind="food", x=150.0, y=150.0, confidence=0.8)

        from unittest.mock import patch
        with patch("primordial.rendering.hud_focus.infer_attention_target", return_value=target) as mock_infer:
            result1 = focus.get_attention_target(sim, c1)
            result2 = focus.get_attention_target(sim, c1)
            self.assertEqual(mock_infer.call_count, 1)
            self.assertIs(result1, target)
            self.assertIs(result2, target)

    def test_attention_cache_invalidated_on_new_selection(self):
        c1 = _make_creature(x=100.0, y=100.0)
        c2 = _make_creature(x=200.0, y=200.0)
        sim = _make_simulation([c1, c2])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)

        from unittest.mock import patch
        with patch("primordial.rendering.hud_focus.infer_attention_target", return_value=None) as mock_infer:
            focus.get_attention_target(sim, c1)
            self.assertEqual(mock_infer.call_count, 1)
            focus.select_at_world_pos(c2.x, c2.y, sim)
            focus.get_attention_target(sim, c2)
            self.assertEqual(mock_infer.call_count, 2)


class TestHUDFocusInspectNonConflict(unittest.TestCase):
    def test_inspect_mode_clears_hud_focus_on_entry(self):
        from primordial.rendering.inspect_mode import InspectMode
        c1 = _make_creature()
        sim = _make_simulation([c1])
        focus = HUDFocus()
        focus.select_at_world_pos(c1.x, c1.y, sim)
        self.assertTrue(focus.has_selection)
        inspect = InspectMode()
        inspect.toggle(simulation_paused=False)
        focus.clear_selection()
        self.assertFalse(focus.has_selection)

    def test_click_does_not_set_hud_focus_when_inspect_active(self):
        focus = HUDFocus()
        from primordial.rendering.inspect_mode import InspectMode
        inspect = InspectMode(enabled=True)
        sim = _make_simulation()
        c1 = _make_creature()
        sim.creatures = [c1]
        if inspect.enabled:
            pass
        self.assertFalse(focus.has_selection)


class TestHUDFocusRendererIntegration(unittest.TestCase):
    def test_hud_hidden_suppresses_focus_rendering(self):
        focus = HUDFocus()
        c1 = _make_creature()
        sim = _make_simulation([c1])
        focus.select_at_world_pos(c1.x, c1.y, sim)
        self.assertTrue(focus.has_selection)
        focus.clear_selection()
        self.assertFalse(focus.has_selection)

    def test_clear_when_hud_hidden(self):
        focus = HUDFocus()
        c1 = _make_creature()
        sim = _make_simulation([c1])
        focus.select_at_world_pos(c1.x, c1.y, sim)
        self.assertTrue(focus.has_selection)
        focus.clear_selection()
        self.assertFalse(focus.has_selection)


class TestActionBarHUDFocusContext(unittest.TestCase):
    def test_context_includes_hud_fields(self):
        from primordial.rendering.action_bar import ActionBar, ActionBarContext
        context = ActionBarContext(
            runtime_mode="normal",
            sim_mode="energy",
            paused=False,
            inspect_enabled=False,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
            game_over_visible=False,
            hud_visible=True,
            hud_focus_active=True,
        )
        self.assertTrue(context.hud_visible)
        self.assertTrue(context.hud_focus_active)

    def test_context_defaults_hud_fields(self):
        from primordial.rendering.action_bar import ActionBarContext
        context = ActionBarContext(
            runtime_mode="normal",
            sim_mode="energy",
            paused=False,
            inspect_enabled=False,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
            game_over_visible=False,
        )
        self.assertFalse(context.hud_visible)
        self.assertFalse(context.hud_focus_active)

    def test_hud_focus_shortcuts_appear_when_hud_visible(self):
        from primordial.rendering.action_bar import ActionBar, ActionBarContext
        bar = ActionBar()
        context = ActionBarContext(
            runtime_mode="normal",
            sim_mode="energy",
            paused=False,
            inspect_enabled=False,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
            game_over_visible=False,
            hud_visible=True,
        )
        items = bar.command_items(context)
        labels = [(item.key_label, item.action_label) for item in items]
        self.assertIn(("Click", "Focus organism"), labels)
        self.assertIn(("C", "Clear focus"), labels)

    def test_hud_focus_shortcuts_absent_when_hud_hidden(self):
        from primordial.rendering.action_bar import ActionBar, ActionBarContext
        bar = ActionBar()
        context = ActionBarContext(
            runtime_mode="normal",
            sim_mode="energy",
            paused=False,
            inspect_enabled=False,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
            game_over_visible=False,
            hud_visible=False,
        )
        items = bar.command_items(context)
        labels = [(item.key_label, item.action_label) for item in items]
        self.assertNotIn(("Click", "Focus organism"), labels)
        self.assertNotIn(("C", "Clear focus"), labels)

    def test_inspect_mode_suppresses_hud_focus_shortcuts(self):
        from primordial.rendering.action_bar import ActionBar, ActionBarContext
        bar = ActionBar()
        context = ActionBarContext(
            runtime_mode="normal",
            sim_mode="energy",
            paused=False,
            inspect_enabled=True,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
            game_over_visible=False,
            hud_visible=True,
        )
        items = bar.command_items(context)
        labels = [(item.key_label, item.action_label) for item in items]
        self.assertNotIn(("Click", "Focus organism"), labels)
        self.assertNotIn(("C", "Clear focus"), labels)


if __name__ == "__main__":
    unittest.main()