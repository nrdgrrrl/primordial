from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.rendering import (
    Renderer,
    create_renderer,
    display_flags_for_settings,
    wants_gpu_renderer,
)
from primordial.settings import Settings


class RendererBackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def _settings(self) -> Settings:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            with patch("primordial.config.config.get_config_path", return_value=config_path):
                settings = Settings()
        settings.sim_mode = "predator_prey"
        settings.render_backend = "gpu"
        return settings

    def test_dummy_video_driver_forces_pygame_backend(self) -> None:
        settings = self._settings()

        self.assertFalse(wants_gpu_renderer(settings))
        flags = display_flags_for_settings(settings, pygame.FULLSCREEN | pygame.SCALED)
        self.assertEqual(flags, pygame.FULLSCREEN | pygame.SCALED)

        screen = pygame.display.set_mode((64, 64))
        renderer = create_renderer(screen, settings)

        self.assertIsInstance(renderer, Renderer)

    def test_gpu_display_flags_use_opengl_without_scaled_compositor(self) -> None:
        settings = self._settings()

        with (
            patch.dict(os.environ, {"SDL_VIDEODRIVER": "x11"}),
            patch("importlib.util.find_spec", return_value=object()),
        ):
            flags = display_flags_for_settings(
                settings,
                pygame.FULLSCREEN | pygame.SCALED,
            )

        self.assertTrue(flags & pygame.OPENGL)
        self.assertTrue(flags & pygame.DOUBLEBUF)
        self.assertFalse(flags & pygame.SCALED)


if __name__ == "__main__":
    unittest.main()
