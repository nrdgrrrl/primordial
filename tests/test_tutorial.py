from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering.tutorial_layout import calculate_tutorial_layout
from primordial.rendering.tutorial_overlay import TutorialOverlay
from primordial.tutorial import (
    TUTORIAL_SEEN_VERSION,
    TutorialState,
    build_default_tutorial_steps,
    load_tutorial_user_state,
    save_tutorial_user_state,
    should_auto_start_tutorial,
)
from primordial.utils.cli import parse_runtime_args


class FakeSettings:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path


class TutorialModelTests(unittest.TestCase):
    def test_default_steps_have_unique_ids_and_required_text(self) -> None:
        steps = build_default_tutorial_steps()

        self.assertGreaterEqual(len(steps), 10)
        self.assertEqual(len({step.id for step in steps}), len(steps))
        for step in steps:
            self.assertTrue(step.title.strip())
            self.assertTrue(step.body.strip())
            self.assertTrue(step.phase.strip())

    def test_state_next_back_finish_and_skip_bounds(self) -> None:
        state = TutorialState()
        state.start(previous_paused=False)

        state.back()
        self.assertEqual(state.current_index, 0)

        state.next()
        self.assertEqual(state.current_index, 1)
        state.back()
        self.assertEqual(state.current_index, 0)

        state.current_index = len(state.steps) - 1
        self.assertEqual(state.next(), "finish")
        self.assertFalse(state.active)
        self.assertTrue(state.completed)

        state.start(previous_paused=True)
        self.assertEqual(state.skip(), "skip")
        self.assertTrue(state.skipped)

    def test_text_scroll_bounds_are_clamped(self) -> None:
        state = TutorialState()
        state.set_text_bounds(line_count=20, visible_lines=5)
        state.scroll_text(100)
        self.assertEqual(state.text_scroll, 15)
        state.scroll_text(-100)
        self.assertEqual(state.text_scroll, 0)


class TutorialPersistenceTests(unittest.TestCase):
    def test_fresh_state_auto_starts_only_when_config_was_new(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = FakeSettings(Path(temp_dir) / "config.toml")

            self.assertTrue(
                should_auto_start_tutorial(
                    settings,
                    config_existed_before_startup=False,
                )
            )
            self.assertFalse(
                should_auto_start_tutorial(
                    settings,
                    config_existed_before_startup=True,
                )
            )

    def test_completed_or_skipped_state_suppresses_auto_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = FakeSettings(Path(temp_dir) / "config.toml")

            save_tutorial_user_state(settings, skipped=True)
            state = load_tutorial_user_state(settings)

            self.assertEqual(state.skipped_version, TUTORIAL_SEEN_VERSION)
            self.assertFalse(
                should_auto_start_tutorial(
                    settings,
                    config_existed_before_startup=False,
                )
            )

    def test_cli_tutorial_flag_parses_with_mode(self) -> None:
        args = parse_runtime_args(["--tutorial", "--mode", "predator_prey"])

        self.assertTrue(args.tutorial)
        self.assertEqual(args.mode, "predator_prey")

    def test_cli_show_tutorial_alias_parses(self) -> None:
        self.assertTrue(parse_runtime_args(["--show-tutorial"]).tutorial)


class TutorialOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_layout_has_positive_body_footer_and_button_regions(self) -> None:
        layout = calculate_tutorial_layout((1280, 720), highlight="hud")

        self.assertGreater(layout.body_rect.width, 0)
        self.assertGreater(layout.body_rect.height, 0)
        self.assertLess(layout.body_rect.bottom, layout.footer_rect.y)
        self.assertTrue(layout.back_rect.width > 0)
        self.assertTrue(layout.next_rect.width > 0)

    def test_overlay_draws_headlessly_and_mouse_buttons_advance(self) -> None:
        screen = pygame.Surface((1280, 720))
        overlay = TutorialOverlay()
        overlay.open(previous_paused=False)
        overlay.fade = 20
        overlay.draw(screen)

        next_region = next(region for region in overlay._hit_regions if region.action == "next")
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=next_region.rect.center)
        )

        self.assertEqual(overlay.state.current_index, 1)

        overlay.draw(screen)
        back_region = next(region for region in overlay._hit_regions if region.action == "back")
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=back_region.rect.center)
        )

        self.assertEqual(overlay.state.current_index, 0)

    def test_keyboard_finish_and_escape_close_return_actions(self) -> None:
        overlay = TutorialOverlay()
        overlay.open(previous_paused=True)
        overlay.state.current_index = len(overlay.state.steps) - 1

        action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

        self.assertEqual(action, "finish")
        self.assertEqual(overlay.fade_dir, -1)
        self.assertEqual(overlay.restore_pause_value(), True)

        overlay.open(previous_paused=False)
        action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

        self.assertEqual(action, "close")
        self.assertEqual(overlay.fade_dir, -1)


if __name__ == "__main__":
    unittest.main()
