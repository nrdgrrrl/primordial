from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering import Renderer
from primordial.rendering.glyphs import get_glyph_surface
from primordial.rendering.themes import OceanTheme
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome


class _GameOverSimulationStub:
    def __init__(self, stats: dict[str, object]) -> None:
        self._stats = stats

    @property
    def predator_prey_game_over_active(self) -> bool:
        return True

    def get_predator_prey_stability_stats(self) -> dict[str, object]:
        return dict(self._stats)


class RendererCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _build_settings(self) -> Settings:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()
        settings.visual_theme = "ocean"
        settings.fullscreen = False
        settings.show_hud = True
        return settings

    def test_renderer_invalidates_static_surfaces_on_hud_toggle_and_resize(self) -> None:
        settings = self._build_settings()
        screen = pygame.display.set_mode((320, 180))
        simulation = Simulation(320, 180, settings, seed=12345)
        renderer = Renderer(screen, settings)

        renderer.draw(simulation)

        self.assertIsNotNone(renderer._zone_surf_cached)
        self.assertIsNotNone(renderer._zone_label_surf_cached)

        renderer.toggle_hud()
        self.assertIsNone(renderer._zone_label_surf_cached)

        resized_screen = pygame.display.set_mode((400, 240))
        renderer.resize(400, 240, screen=resized_screen)
        self.assertIsNone(renderer._zone_surf_cached)
        self.assertIsNone(renderer._zone_label_surf_cached)

    def test_rotated_glyph_cache_reuses_steady_state_rotation(self) -> None:
        theme = OceanTheme()
        creature = Creature(x=80.0, y=60.0, genome=Genome.random())
        creature.rotation_angle = 12.0
        color = theme.get_creature_color(creature.genome.hue, creature.genome.saturation)
        glyph_size = max(32, int(creature.get_radius() * 4))
        get_glyph_surface(creature, color, glyph_size)
        surface = pygame.Surface((160, 120), pygame.SRCALPHA)

        with patch(
            "primordial.rendering.themes.pygame.transform.rotate",
            wraps=pygame.transform.rotate,
        ) as rotate_mock:
            theme.render_creature(surface, creature, time=1.0, scale=1.0)
            theme.render_creature(surface, creature, time=1.0, scale=1.0)

        self.assertEqual(rotate_mock.call_count, 1)

    def test_game_over_overlay_cache_reuses_surface_until_countdown_changes(self) -> None:
        settings = self._build_settings()
        screen = pygame.display.set_mode((320, 180))
        renderer = Renderer(screen, settings)

        stats = {
            "collapse_cause": "prey_extinction",
            "current_seed": 12345,
            "collapse_predators": 12,
            "collapse_prey": 0,
            "survival_ticks": 800,
            "collapse_rolling_average": 700.0,
            "collapse_beat_average": True,
            "highest_survival_ticks": 900,
            "collapse_was_new_highest": False,
            "adjustment_step_multiplier": 1.0,
            "adjustment_step_increase_percent": 25.0,
            "non_improving_run_streak": 0,
            "restart_countdown_seconds": 9.2,
            "collapse_dial_values": {
                "predator_contact_kill_distance_scale": 0.85,
            },
            "collapse_trial_dial": "predator_contact_kill_distance_scale",
            "collapse_trial_delta": 0.05,
        }
        simulation = _GameOverSimulationStub(stats)

        renderer._draw_predator_prey_game_over_overlay(simulation)
        first_surface = renderer._game_over_overlay_cache
        first_key = renderer._game_over_overlay_cache_key

        renderer._draw_predator_prey_game_over_overlay(simulation)

        self.assertIs(renderer._game_over_overlay_cache, first_surface)
        self.assertEqual(renderer._game_over_overlay_cache_key, first_key)

        stats["restart_countdown_seconds"] = 8.1
        renderer._draw_predator_prey_game_over_overlay(simulation)

        self.assertIsNot(renderer._game_over_overlay_cache, first_surface)

    def test_frozen_link_cache_is_built_and_reused_for_paused_world(self) -> None:
        settings = self._build_settings()
        settings.kin_line_max_distance = 120.0
        screen = pygame.display.set_mode((320, 180))
        simulation = Simulation(320, 180, settings, seed=12345)
        renderer = Renderer(screen, settings)
        lineage_id = 999
        for index, creature in enumerate(simulation.creatures[:3]):
            creature.lineage_id = lineage_id
            creature.x = 80.0 + (index * 10.0)
            creature.y = 60.0 + (index * 6.0)

        simulation.paused = True
        renderer.draw(simulation)

        frozen_surface = renderer._frozen_link_surf_cached
        self.assertIsNotNone(frozen_surface)

        renderer.draw(simulation)
        self.assertIs(renderer._frozen_link_surf_cached, frozen_surface)

    def test_disabled_link_rendering_skips_kin_lines_and_clears_frozen_cache(self) -> None:
        settings = self._build_settings()
        settings.kin_line_max_distance = 0.0
        screen = pygame.display.set_mode((320, 180))
        simulation = Simulation(320, 180, settings, seed=12345)
        renderer = Renderer(screen, settings)
        renderer._frozen_link_surf_cached = pygame.Surface((320, 180), pygame.SRCALPHA)

        with patch.object(renderer, "_draw_connection_group") as draw_group:
            renderer._draw_kin_lines(simulation)

        draw_group.assert_not_called()
        self.assertIsNone(renderer._frozen_link_surf_cached)

    def test_disabled_territory_rendering_skips_shimmer_and_keeps_translucent_zones(self) -> None:
        settings = self._build_settings()
        settings.territory_top_n = 0
        screen = pygame.display.set_mode((320, 180))
        simulation = Simulation(320, 180, settings, seed=12345)
        renderer = Renderer(screen, settings)
        renderer._shimmer_states[123] = object()  # type: ignore[assignment]

        renderer.draw(simulation)

        self.assertEqual(renderer._shimmer_states, {})
        self.assertIsNotNone(renderer._zone_surf_cached)
        translucent_pixels = [
            renderer._zone_surf_cached.get_at((int(zone.x), int(zone.y))).a
            for zone in simulation.zone_manager.zones
        ]
        self.assertTrue(any(0 < alpha < 255 for alpha in translucent_pixels))


if __name__ == "__main__":
    unittest.main()
