from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering.action_bar import (
    FADE_DURATION_SECONDS,
    MAX_OPACITY,
    VISIBLE_DURATION_SECONDS,
    ActionBar,
    ActionBarContext,
)


class ActionBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _context(self, **overrides: object) -> ActionBarContext:
        values = {
            "runtime_mode": "normal",
            "sim_mode": "energy",
            "paused": False,
            "inspect_enabled": False,
            "settings_visible": False,
            "help_visible": False,
            "tutorial_visible": False,
            "game_over_visible": False,
        }
        values.update(overrides)
        return ActionBarContext(**values)

    def test_normal_registry_matches_runtime_shortcuts(self) -> None:
        bar = ActionBar()

        items = bar.command_items(self._context())

        self.assertEqual(
            [(item.key_label, item.action_label) for item in items],
            [
                ("S", "Settings"),
                ("H", "Help"),
                ("U", "HUD"),
                ("Space", "Pause/Resume"),
                ("F", "Fullscreen"),
                ("R", "Reset"),
                ("I", "Inspect"),
                ("+/-", "Food rate"),
                ("Esc/Q", "Quit"),
            ],
        )

    def test_predator_prey_context_includes_hold_p(self) -> None:
        bar = ActionBar()

        items = bar.command_items(self._context(sim_mode="predator_prey"))

        self.assertIn(("Hold P", "Highlight predators"), [(item.key_label, item.action_label) for item in items])

    def test_inspect_context_switches_to_inspect_commands(self) -> None:
        bar = ActionBar()

        items = bar.command_items(self._context(inspect_enabled=True))

        self.assertEqual(
            [(item.key_label, item.action_label) for item in items[:3]],
            [("I", "Exit inspect"), ("M", "Pause/Slow"), ("D", "Details")],
        )

    def test_game_over_context_prioritizes_skip_countdown(self) -> None:
        bar = ActionBar()

        items = bar.command_items(
            self._context(sim_mode="predator_prey", game_over_visible=True)
        )

        self.assertEqual(items[0].key_label, "Space")
        self.assertEqual(items[0].action_label, "Skip countdown")

    def test_opacity_tracks_visible_and_fade_windows(self) -> None:
        bar = ActionBar()
        context = self._context()

        self.assertEqual(bar.opacity(context, now=10.0), 0.0)

        bar.notify_mouse_motion((8, 0), now=10.0)
        self.assertEqual(bar.opacity(context, now=10.0), MAX_OPACITY)
        self.assertEqual(bar.opacity(context, now=10.0 + VISIBLE_DURATION_SECONDS - 0.01), MAX_OPACITY)

        faded = bar.opacity(context, now=10.0 + VISIBLE_DURATION_SECONDS + (FADE_DURATION_SECONDS / 2))
        self.assertGreater(faded, 0.0)
        self.assertLess(faded, MAX_OPACITY)

        self.assertEqual(
            bar.opacity(context, now=10.0 + VISIBLE_DURATION_SECONDS + FADE_DURATION_SECONDS + 0.01),
            0.0,
        )

        bar.notify_mouse_motion((0, 6), now=25.0)
        self.assertEqual(bar.opacity(context, now=25.0), MAX_OPACITY)

    def test_small_motion_is_ignored(self) -> None:
        bar = ActionBar()
        context = self._context()

        bar.notify_mouse_motion((1, 1), now=2.0)

        self.assertEqual(bar.opacity(context, now=2.0), 0.0)

    def test_bar_is_suppressed_for_overlays_and_non_normal_modes(self) -> None:
        bar = ActionBar()
        bar.notify_mouse_motion((5, 5), now=1.0)

        self.assertEqual(bar.opacity(self._context(settings_visible=True), now=1.5), 0.0)
        self.assertEqual(bar.opacity(self._context(help_visible=True), now=1.5), 0.0)
        self.assertEqual(bar.opacity(self._context(tutorial_visible=True), now=1.5), 0.0)
        self.assertEqual(bar.opacity(self._context(runtime_mode="screensaver"), now=1.5), 0.0)
        self.assertEqual(bar.opacity(self._context(runtime_mode="preview"), now=1.5), 0.0)

    def test_layout_has_positive_rects_and_stays_on_screen(self) -> None:
        bar = ActionBar()
        items = bar.command_items(self._context(sim_mode="predator_prey"))

        layout = bar.calculate_layout((1280, 720), items)

        self.assertGreater(layout.panel_rect.width, 0)
        self.assertGreater(layout.panel_rect.height, 0)
        self.assertLessEqual(layout.panel_rect.right, 1280)
        self.assertLessEqual(layout.panel_rect.bottom, 720)
        self.assertTrue(all(rect.width > 0 for rect in layout.row_rects))

    def test_draws_headlessly(self) -> None:
        bar = ActionBar()
        bar.notify_mouse_motion((7, 3), now=1.0)
        surface = pygame.Surface((1280, 720), pygame.SRCALPHA)

        bar.draw(surface, self._context(sim_mode="predator_prey"), now=1.5)

        alpha_values = pygame.surfarray.array_alpha(surface)
        self.assertGreater(int(alpha_values.max()), 0)

    def test_build_context_uses_runtime_simulation_state(self) -> None:
        bar = ActionBar()
        bar.set_runtime_mode("normal")
        simulation = SimpleNamespace(
            settings=SimpleNamespace(sim_mode="predator_prey"),
            paused=True,
            predator_prey_game_over_active=True,
        )

        context = bar.build_context(
            simulation,
            inspect_enabled=True,
            settings_visible=False,
            help_visible=False,
            tutorial_visible=False,
        )

        self.assertEqual(context.sim_mode, "predator_prey")
        self.assertTrue(context.paused)
        self.assertTrue(context.inspect_enabled)
        self.assertTrue(context.game_over_visible)


if __name__ == "__main__":
    unittest.main()
