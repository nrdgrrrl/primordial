"""Tests for the docked HUD panel — pinned FPS, semantic grouping, single-column food bar."""

import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering.hud import HUD


class DockedHUDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _mock_simulation(self, mode="predator_prey", paused=False):
        sim = MagicMock()
        sim.settings = MagicMock()
        sim.settings.sim_mode = mode
        sim.paused = paused
        sim.population = 50
        sim.generation = 10
        sim.food_count = 100
        sim.creatures = []
        sim.food_cycle_phase = 0.4
        sim.zone_manager = MagicMock()
        sim.zone_manager.get_dominant_zone.return_value = "open_water"
        sim.get_species_counts.return_value = (10, 40)
        sim.get_species_avg_actual_speeds.return_value = (1.2, 2.3)
        sim.get_recent_predation_stats.return_value = {"recent_kills": 3, "recent_cross_band_misses": 1}
        sim.get_predator_prey_stability_stats.return_value = {
            "current_seed": 42,
            "sim_ticks": 5000,
            "survival_ticks": 3000,
            "history_window_size": 100,
            "rolling_average_survival_ticks": 2500,
            "best_recent_survival_ticks": 5000,
            "trial_active": False,
            "trial_dial": None,
            "trial_direction": "up",
            "extinction_grace_active": False,
            "extinction_grace_role": None,
            "predator_grace_remaining_ticks": 0,
            "prey_grace_remaining_ticks": 0,
        }
        sim.get_population_observability_summary.return_value = {
            "average_age_ticks": 300,
            "active_lineage_count": 8,
            "average_lineage_age_ticks": 600,
            "oldest_lineage_age_ticks": 1200,
        }
        sim.get_evolution_summary.return_value = {
            "distance": 0.05,
            "top_directions": ["speed", "sense"],
        }
        sim.get_epistasis_summary.return_value = {
            "enabled": False,
            "average_modifiers": {"speed_mult": 1.0, "sense_radius_mult": 1.0, "movement_cost_mult": 1.0},
            "top_strategy": "generalist",
            "top_strategy_share": 0.3,
        }
        sim.avg_old_age_lifespan_seconds = 60
        sim.get_hunter_grazer_counts.return_value = (10, 30, 5)
        sim.get_flock_stats.return_value = (3, 10, 20)
        sim.get_avg_conformity.return_value = 0.8
        sim.get_lineage_count.return_value = 8
        sim.get_most_variable_trait.return_value = "speed"
        sim.get_simulation_tick_hz.return_value = 60.0
        sim._frame = 100
        return sim

    def test_docked_hud_includes_fps(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation()
        surface, pos = hud.build_panel_surface(
            (300, 120),
            sim,
            60.0,
            docked=True,
        )
        self.assertGreater(surface.get_width(), 1)
        self.assertGreater(surface.get_height(), 1)

    def test_docked_hud_fps_always_visible_at_constrained_height(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation()
        surface, pos = hud.build_panel_surface(
            (300, 40),
            sim,
            60.0,
            docked=True,
        )
        self.assertGreater(surface.get_width(), 1)
        self.assertGreater(surface.get_height(), 0)

    def test_docked_hud_keeps_predator_prey_high_priority(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation(mode="predator_prey")
        surface, pos = hud.build_panel_surface(
            (300, 100),
            sim,
            60.0,
            docked=True,
        )
        self.assertGreater(surface.get_width(), 1)
        self.assertGreater(surface.get_height(), 1)

    def test_docked_food_bar_fits_one_column(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation()
        surface, pos = hud.build_panel_surface(
            (300, 120),
            sim,
            60.0,
            docked=True,
        )
        self.assertGreater(surface.get_width(), 1)
        avail_w = 300
        col_width = max(80, (avail_w - hud.padding * 2 - 8) // 2)
        self.assertLessEqual(col_width, avail_w // 2 + 10)

    def test_docked_panel_position_is_origin(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation()
        surface, pos = hud.build_panel_surface(
            (300, 120),
            sim,
            60.0,
            docked=True,
        )
        self.assertEqual(pos, (0, 0))

    def test_normal_hud_still_works(self):
        hud = HUD(font_size=16)
        sim = self._mock_simulation()
        surface, pos = hud.build_panel_surface(
            (1920, 1080),
            sim,
            60.0,
            docked=False,
        )
        self.assertGreater(surface.get_width(), 1)
        self.assertGreater(surface.get_height(), 1)
        self.assertGreater(pos[0], 0)

    def test_line_priority_classification(self):
        self.assertEqual(HUD._line_priority("[PAUSED]"), HUD._PRIORITY_CRITICAL)
        self.assertEqual(HUD._line_priority("FPS: 60"), HUD._PRIORITY_CRITICAL)
        self.assertEqual(HUD._line_priority("Predators: 10"), HUD._PRIORITY_CRITICAL)
        self.assertEqual(HUD._line_priority("Kills (3s): 3"), HUD._PRIORITY_CRITICAL)
        self.assertEqual(HUD._line_priority("Survival: 3000"), HUD._PRIORITY_CRITICAL)
        self.assertEqual(HUD._line_priority("Actual speed P:1.2"), HUD._PRIORITY_HIGH)
        self.assertEqual(HUD._line_priority("sim_ticks: 5000"), HUD._PRIORITY_HIGH)
        self.assertEqual(HUD._line_priority("Generation: 10"), HUD._PRIORITY_HIGH)
        self.assertEqual(HUD._line_priority("Zone: open_water"), HUD._PRIORITY_LOW)
        self.assertEqual(HUD._line_priority("Mode: predator_prey"), HUD._PRIORITY_LOW)
        self.assertEqual(HUD._line_priority("Dbg frame: ..."), HUD._PRIORITY_LOW)

    def test_classify_column_ecosystem_goes_left(self):
        self.assertEqual(HUD._classify_column("Predators: 10"), 0)
        self.assertEqual(HUD._classify_column("Population: 50"), 0)
        self.assertEqual(HUD._classify_column("Food: 100"), 0)
        self.assertEqual(HUD._classify_column("Survival: 3000"), 0)

    def test_classify_column_secondary_goes_right(self):
        self.assertEqual(HUD._classify_column("Zone: open_water"), 1)
        self.assertEqual(HUD._classify_column("Mode: predator_prey"), 1)
        self.assertEqual(HUD._classify_column("Theme: ocean"), 1)


if __name__ == "__main__":
    unittest.main()