from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.display.cursor import (
    hide_runtime_cursor,
    restore_system_cursor,
    show_interactive_cursor,
)
from primordial.rendering.settings_overlay import SettingsOverlay
from primordial.rendering.settings_metadata import (
    CATEGORY_ACTIONS,
    CATEGORY_ECOLOGY,
    CATEGORY_SIMULATION,
    SETTING_CATEGORIES,
    build_action_items,
    build_settings_fields,
)
from primordial.rendering.settings_layout import calculate_settings_layout
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
            settings.epistasis_enabled = False
            settings.epistasis_strength = 0.40
            serialized = settings.to_toml()

        self.assertIn('mode = "predator_prey"', serialized)
        self.assertIn("fullscreen = false", serialized)
        self.assertIn("show_hud = false", serialized)
        self.assertIn("epistasis_enabled = false", serialized)
        self.assertIn("epistasis_strength = 0.4000", serialized)
        self.assertIn("stability_history_size = 20", serialized)
        self.assertIn("adaptive_step_escalation_runs = 5", serialized)
        self.assertIn("adaptive_step_escalation_percent = 25.0000", serialized)
        self.assertIn("adaptive_trial_seed_count = 2", serialized)
        self.assertIn("adaptive_max_consecutive_retry_trials = 2", serialized)
        self.assertIn("adaptive_survival_deadband = 50", serialized)
        self.assertIn("adaptive_near_extinction_predator_floor = 5", serialized)
        self.assertIn("adaptive_near_extinction_prey_floor = 5", serialized)

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

    def test_starting_predators_field_only_appears_for_predator_prey_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()

            self.assertNotIn(
                "Starting Predators",
                [field.label for field in overlay._visible_fields()],
            )

            overlay.pending["sim_mode"] = "predator_prey"

            self.assertIn(
                "Starting Predators",
                [field.label for field in overlay._visible_fields()],
            )

    def test_settings_overlay_apply_saves_predator_fraction_mode_param(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["mode_param:predator_prey:predator_fraction"] = 0.11

            action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

            self.assertEqual(action, "apply")
            self.assertEqual(settings.mode_params["predator_prey"]["predator_fraction"], 0.11)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("predator_fraction = 0.1100", saved)

    def test_settings_overlay_routes_food_spawn_rate_to_active_mode_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            settings.food_spawn_rate = 0.8
            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["mode_param:predator_prey:food_spawn_rate"] = 0.2

            action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

            self.assertEqual(action, "apply")
            self.assertEqual(settings.food_spawn_rate, 0.8)
            self.assertEqual(settings.mode_params["predator_prey"]["food_spawn_rate"], 0.2)

    def test_settings_overlay_routes_carrying_capacity_to_active_mode_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "boids"
            settings.max_population = 220
            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["mode_param:boids:max_population"] = 180

            action = overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))

            self.assertEqual(action, "apply")
            self.assertEqual(settings.max_population, 220)
            self.assertEqual(settings.mode_params["boids"]["max_population"], 180)

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
            self.assertEqual(overlay._format_value(field), "1800f / 30.0s")

    def test_food_cycle_length_seconds_display_uses_active_mode_sim_tick_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            settings.food_cycle_period = 1800
            overlay = SettingsOverlay(settings)
            field = next(f for f in overlay.fields if f.attr == "food_cycle_period")
            overlay.sync_from_settings()

            self.assertEqual(overlay._format_value(field), "1800f / 60.0s")

    def test_settings_metadata_has_categories_descriptions_and_reset_markers(self) -> None:
        fields = build_settings_fields()
        actions = build_action_items()

        categories = {field.section for field in fields}
        self.assertIn(CATEGORY_SIMULATION, categories)
        self.assertIn(CATEGORY_ECOLOGY, categories)
        self.assertIn(CATEGORY_ACTIONS, SETTING_CATEGORIES)
        self.assertNotIn("Visual Theme", {field.label for field in fields})
        self.assertNotIn("visual_theme", {field.attr for field in fields})
        self.assertTrue(all(field.description for field in fields))
        self.assertTrue(all(action.description for action in actions))

        initial_population = next(
            field for field in fields if field.attr == "initial_population"
        )
        self.assertEqual(initial_population.label, "Initial Population")
        self.assertTrue(initial_population.requires_reset)
        self.assertIn("new run", initial_population.description)

        scarcity = next(
            field
            for field in fields
            if field.mode_param_key == "predator_prey_scarcity_penalty_multiplier"
        )
        self.assertEqual(scarcity.label, "Predator Scarcity Penalty")
        self.assertEqual(scarcity.section, CATEGORY_ECOLOGY)

    def test_tab_cycles_categories_without_losing_selection_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            self.assertEqual(overlay.navigation.category, CATEGORY_SIMULATION)

            overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
            self.assertEqual(overlay.selected, 1)
            overlay.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_TAB))

            self.assertNotEqual(overlay.navigation.category, CATEGORY_SIMULATION)
            self.assertEqual(overlay.selected, 0)

            overlay.handle_event(
                pygame.event.Event(
                    pygame.KEYDOWN,
                    key=pygame.K_TAB,
                    mod=pygame.KMOD_SHIFT,
                )
            )
            self.assertEqual(overlay.navigation.category, CATEGORY_SIMULATION)
            self.assertEqual(overlay.selected, 1)

    def test_actions_category_explains_predator_prey_dial_reset(self) -> None:
        actions = build_action_items()
        dial_reset = next(
            action for action in actions if action.action == "reset_predator_prey_dials"
        )

        self.assertEqual(dial_reset.shortcut, "D D")
        self.assertTrue(dial_reset.destructive)
        self.assertIn("baseline", dial_reset.description)
        self.assertIn("fresh predator-prey run", dial_reset.description)

    def test_space_runs_selected_action_from_actions_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.navigation.set_category(CATEGORY_ACTIONS, overlay._item_count_for_category(CATEGORY_ACTIONS))

            action = overlay.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
            )

            self.assertEqual(action, "save_snapshot")

    def test_draw_smoke_uses_fixed_footer_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            for _ in range(20):
                overlay.update()

            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)

            self.assertGreater(surface.get_bounding_rect().width, 0)

    def test_settings_layout_keeps_long_category_and_label_columns_positive(self) -> None:
        category_font = pygame.font.Font(None, 24)
        item_font = pygame.font.Font(None, 24)
        count_font = pygame.font.Font(None, 18)

        layout = calculate_settings_layout(
            (1024, 768),
            categories=SETTING_CATEGORIES,
            item_labels=[
                "Predator Reproduction Energy",
                "Kin Line Shimmer Strength",
                "Reset Predator-Prey Dials",
            ],
            category_font=category_font,
            item_font=item_font,
            count_font=count_font,
        )

        self.assertGreaterEqual(layout.sidebar_rect.width, 190)
        self.assertGreaterEqual(layout.list_rect.width, 360)
        self.assertGreaterEqual(layout.details_rect.width, 220)
        self.assertLess(layout.sidebar_rect.right, layout.list_rect.left)
        self.assertLess(layout.list_rect.right, layout.details_rect.left)

    def test_settings_overlay_hit_regions_remain_inside_drawn_panel_after_layout_polish(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            settings.sim_mode = "predator_prey"
            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["sim_mode"] = "predator_prey"
            overlay.navigation.set_category(CATEGORY_ECOLOGY, overlay._item_count_for_category(CATEGORY_ECOLOGY))
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)

            panel = overlay._last_panel_rect
            category_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "category" and region.category == CATEGORY_ECOLOGY
            )
            value_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "value" and region.row_index == 2 and region.direction == 1
            )

            self.assertTrue(panel.contains(category_region.rect))
            self.assertTrue(panel.contains(value_region.rect))
            self.assertGreater(value_region.rect.width, 0)

    def test_mouse_click_category_switches_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)
            display_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "category" and region.category == "Display"
            )

            action = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=display_region.rect.center,
                )
            )

            self.assertIsNone(action)
            self.assertEqual(overlay.navigation.category, "Display")
            self.assertEqual(overlay.selected, 0)

    def test_mouse_click_setting_row_selects_without_changing_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)
            row_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "row" and region.row_index == 2
            )

            overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=row_region.rect.center,
                )
            )

            self.assertEqual(overlay.selected, 2)

    def test_mouse_value_controls_change_enum_bool_and_numeric_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)
            enum_value = next(
                region
                for region in overlay._hit_regions
                if region.kind == "value" and region.row_index == 0 and region.direction == 1
            )
            overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=enum_value.rect.center,
                )
            )
            self.assertEqual(overlay.pending["sim_mode"], "predator_prey")

            overlay.navigation.set_category("Display", overlay._item_count_for_category("Display"))
            overlay.draw(surface)
            fullscreen_row = next(
                index
                for index, item in enumerate(overlay._visible_items_for_active_category())
                if getattr(item, "attr", "") == "fullscreen"
            )
            bool_value = next(
                region
                for region in overlay._hit_regions
                if region.kind == "value" and region.row_index == fullscreen_row and region.direction == 1
            )
            old_fullscreen = overlay.pending["fullscreen"]
            overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=bool_value.rect.center,
                )
            )
            self.assertEqual(overlay.pending["fullscreen"], (not old_fullscreen))

            overlay.navigation.set_category(CATEGORY_SIMULATION, overlay._item_count_for_category(CATEGORY_SIMULATION))
            overlay.draw(surface)
            numeric_value = next(
                region
                for region in overlay._hit_regions
                if region.kind == "value" and region.row_index == 1 and region.direction == 1
            )
            old_population = overlay.pending["mode_param:predator_prey:initial_population"]
            overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=numeric_value.rect.center,
                )
            )
            self.assertGreater(
                overlay.pending["mode_param:predator_prey:initial_population"],
                old_population,
            )

    def test_mouse_wheel_scrolls_setting_list_within_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.navigation.set_category(CATEGORY_ECOLOGY, overlay._item_count_for_category(CATEGORY_ECOLOGY))
            overlay.pending["sim_mode"] = "predator_prey"
            surface = pygame.Surface((720, 520), pygame.SRCALPHA)
            overlay.draw(surface)

            overlay.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=-10))
            self.assertGreaterEqual(overlay._first_visible_row, 0)
            scrolled_row = overlay._first_visible_row

            overlay.handle_event(pygame.event.Event(pygame.MOUSEWHEEL, y=10))
            self.assertLessEqual(overlay._first_visible_row, scrolled_row)
            self.assertGreaterEqual(overlay._first_visible_row, 0)

    def test_mouse_footer_apply_and_discard_use_keyboard_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            overlay.pending["sim_mode"] = "boids"
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.draw(surface)
            apply_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "footer" and region.action == "apply"
            )

            action = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=apply_region.rect.center,
                )
            )

            self.assertEqual(action, "apply")
            self.assertEqual(settings.sim_mode, "boids")

            overlay.open()
            overlay.pending["sim_mode"] = "drift"
            overlay.draw(surface)
            discard_region = next(
                region
                for region in overlay._hit_regions
                if region.kind == "footer" and region.action == "discard"
            )
            action = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=discard_region.rect.center,
                )
            )

            self.assertEqual(action, "discard")
            self.assertEqual(settings.sim_mode, "boids")

    def test_mouse_action_buttons_dispatch_save_and_confirm_reset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()

            overlay = SettingsOverlay(settings)
            overlay.open()
            surface = pygame.Surface((1024, 768), pygame.SRCALPHA)
            overlay.navigation.set_category(CATEGORY_ACTIONS, overlay._item_count_for_category(CATEGORY_ACTIONS))
            overlay.draw(surface)
            save_button = next(
                region
                for region in overlay._hit_regions
                if region.kind == "action" and region.row_index == 0
            )

            action = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=save_button.rect.center,
                )
            )
            self.assertEqual(action, "save_snapshot")

            overlay.draw(surface)
            reset_button = next(
                region
                for region in overlay._hit_regions
                if region.kind == "footer" and region.action == "reset"
            )
            first_click = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=reset_button.rect.center,
                )
            )
            second_click = overlay.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN,
                    button=1,
                    pos=reset_button.rect.center,
                )
            )

            self.assertIsNone(first_click)
            self.assertEqual(second_click, "reset")

    def test_cursor_helpers_hide_runtime_and_restore_interactive_visibility(self) -> None:
        with patch("primordial.display.cursor.pygame.mouse.set_visible") as set_visible:
            hide_runtime_cursor()
            show_interactive_cursor()
            restore_system_cursor()

        self.assertEqual(
            [call.args[0] for call in set_visible.call_args_list],
            [False, True, True],
        )


if __name__ == "__main__":
    unittest.main()
