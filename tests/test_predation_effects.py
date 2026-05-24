from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering import Renderer
from primordial.rendering.animations import AnimationManager, PredationDeathAnimation
from primordial.rendering.predation_effects import PredationEffectManager
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.creature import Creature
from primordial.simulation.genome import Genome


class PredationEffectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _resolve_attack_color(self, species: str, hue: float, saturation: float) -> tuple[int, int, int]:
        if species == "predator":
            return (255, 168, 116)
        return (96, 236, 255)

    def _resolve_death_color(self, event: dict) -> tuple[int, int, int]:
        if event.get("cause") == "predation":
            return (110, 238, 255)
        return (150, 170, 200)

    def _predation_event(self) -> dict:
        genome = Genome(hue=0.08, saturation=0.92)
        return {
            "x": 48.0,
            "y": 36.0,
            "genome": genome,
            "species": "prey",
            "glyph_surface": None,
            "lineage_id": 7,
            "cause": "predation",
            "predator_x": 24.0,
            "predator_y": 18.0,
            "predator_species": "predator",
            "predator_hue": 0.05,
            "predator_saturation": 0.95,
        }

    def test_predation_death_events_create_kill_effects(self) -> None:
        manager = PredationEffectManager(enabled=True, intensity=1.0, max_active=64)

        manager.process_events(
            [self._predation_event()],
            [(24.0, 18.0, 48.0, 36.0, "predator", 0.05, 0.95)],
            resolve_attack_color=self._resolve_attack_color,
            resolve_death_color=self._resolve_death_color,
            now=10.0,
        )

        self.assertEqual(manager.strike_count, 1)
        self.assertEqual(manager.kill_count, 1)
        sprites = manager.build_gpu_sprites(10.0)
        self.assertTrue(sprites.strike_core_lines)
        self.assertTrue(sprites.bloom_radials)
        self.assertTrue(sprites.ripple_radials)

    def test_non_predation_deaths_do_not_create_predation_kill_effects(self) -> None:
        manager = PredationEffectManager(enabled=True, intensity=1.0, max_active=64)
        genome = Genome(hue=0.3, saturation=0.4)
        energy_event = {
            "x": 20.0,
            "y": 22.0,
            "genome": genome,
            "species": "prey",
            "glyph_surface": None,
            "lineage_id": 2,
            "cause": "energy",
        }

        manager.process_events(
            [energy_event],
            [],
            resolve_attack_color=self._resolve_attack_color,
            resolve_death_color=self._resolve_death_color,
            now=5.0,
        )

        self.assertEqual(manager.kill_count, 0)
        self.assertEqual(manager.active_count, 0)

    def test_kill_effects_age_out_and_are_removed(self) -> None:
        manager = PredationEffectManager(enabled=True, intensity=1.0, max_active=64)
        manager.process_events(
            [self._predation_event()],
            [(24.0, 18.0, 48.0, 36.0, "predator", 0.05, 0.95)],
            resolve_attack_color=self._resolve_attack_color,
            resolve_death_color=self._resolve_death_color,
            now=1.0,
        )

        manager.build_gpu_sprites(3.0)

        self.assertEqual(manager.active_count, 0)

    def test_active_kill_effects_are_capped(self) -> None:
        manager = PredationEffectManager(enabled=True, intensity=1.0, max_active=3)
        deaths = [self._predation_event() for _ in range(4)]
        attacks = [
            (10.0 + index, 12.0, 30.0 + index, 42.0, "predator", 0.05, 0.95)
            for index in range(4)
        ]

        manager.process_events(
            deaths,
            attacks,
            resolve_attack_color=self._resolve_attack_color,
            resolve_death_color=self._resolve_death_color,
            now=2.0,
        )

        self.assertLessEqual(manager.active_count, 3)

    def test_disabling_kill_effects_prevents_new_effects(self) -> None:
        manager = PredationEffectManager(enabled=False, intensity=1.0, max_active=64)

        manager.process_events(
            [self._predation_event()],
            [(24.0, 18.0, 48.0, 36.0, "predator", 0.05, 0.95)],
            resolve_attack_color=self._resolve_attack_color,
            resolve_death_color=self._resolve_death_color,
            now=7.0,
        )

        self.assertEqual(manager.active_count, 0)

    def test_existing_death_birth_and_cosmic_animations_still_work(self) -> None:
        manager = AnimationManager(num_particles=3)
        birth_creature = Creature(x=20.0, y=20.0, genome=Genome.random())
        death_events = [self._predation_event(), {
            "x": 12.0,
            "y": 10.0,
            "genome": Genome.random(),
            "species": "prey",
            "glyph_surface": None,
            "lineage_id": 3,
            "cause": "energy",
        }]

        manager.process_events(death_events, [birth_creature], self._resolve_death_color)
        manager.add_cosmic_ray(30.0, 30.0)

        self.assertEqual(manager.active_count, 4)
        self.assertTrue(any(isinstance(anim, PredationDeathAnimation) for anim in manager._animations))
        surface = pygame.Surface((80, 60), pygame.SRCALPHA)
        manager.tick_and_draw(surface)
        self.assertGreater(surface.get_bounding_rect(min_alpha=1).width, 0)
        self.assertIsNotNone(manager.get_birth_scale(birth_creature))

    def test_renderer_clears_death_and_birth_events_without_touching_attack_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()
        settings.fullscreen = False
        settings.show_hud = False
        settings.sim_mode = "predator_prey"
        screen = pygame.display.set_mode((200, 120))
        renderer = Renderer(screen, settings)
        simulation = Simulation(200, 120, settings, seed=123)
        simulation.death_events = [self._predation_event()]
        simulation.birth_events = [Creature(x=16.0, y=16.0, genome=Genome.random())]
        simulation.active_attacks = [(24.0, 18.0, 48.0, 36.0, "predator", 0.05, 0.95)]
        simulation.cosmic_ray_events = [(60.0, 50.0)]

        renderer.draw(simulation)

        self.assertEqual(simulation.death_events, [])
        self.assertEqual(simulation.birth_events, [])
        self.assertEqual(simulation.cosmic_ray_events, [])
        self.assertEqual(len(simulation.active_attacks), 1)
