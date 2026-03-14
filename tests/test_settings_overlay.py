from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering.settings_overlay import SettingsOverlay
from primordial.settings import Settings


class SettingsOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def test_to_toml_serializes_without_format_keyerror(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            settings.fullscreen = False
            settings.show_hud = False
            serialized = settings.to_toml()

        self.assertIn('mode = "predator_prey"', serialized)
        self.assertIn("fullscreen = false", serialized)
        self.assertIn("show_hud = false", serialized)
        self.assertIn("stability_history_size = 20", serialized)
        self.assertIn("adaptive_step_escalation_runs = 5", serialized)
        self.assertIn("adaptive_step_escalation_percent = 25.0000", serialized)
        self.assertIn("adaptive_trial_seed_count = 3", serialized)

    def test_settings_overlay_apply_saves_mode_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.fullscreen = False
            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["sim_mode"] = "boids"

            action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

            self.assertEqual(action, "apply")
            self.assertEqual(settings.sim_mode, "boids")
            self.assertTrue(config_path.exists())
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn('mode = "boids"', saved)

    def test_settings_overlay_emits_save_load_and_help_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()

            save_action = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_v)
            )
            load_action = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l)
            )
            help_action = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h)
            )

            self.assertEqual(save_action, "save_snapshot")
            self.assertEqual(load_action, "load_snapshot")
            self.assertEqual(help_action, "help")

    def test_settings_overlay_emits_predator_prey_dial_reset_action(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            overlay = SettingsOverlay(settings)
            overlay.open()

            first_press = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d)
            )
            second_press = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d)
            )

            self.assertIsNone(first_press)
            self.assertEqual(second_press, "reset_predator_prey_dials")

    def test_food_cycle_length_field_uses_clear_label_and_seconds_display(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.food_cycle_period = 1800
            overlay = SettingsOverlay(settings)
            field = next(f for f in overlay.fields if f.attr == "food_cycle_period")
            overlay.sync_from_settings()

            self.assertEqual(field.label, "Food Cycle Length")
            self.assertEqual(overlay._format_value(field), "< 1800f / 30.0s >")


if __name__ == "__main__":
    unittest.main()
