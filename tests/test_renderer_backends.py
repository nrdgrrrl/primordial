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

from primordial.rendering import (
    Renderer,
    create_renderer,
    display_flags_for_settings,
    wants_gpu_renderer,
)
from primordial.rendering.gpu_renderer import (
    PredatorPreyGpuRenderer,
    _OverlayTextureSlot,
    _TEXTURE_FRAGMENT_SHADER,
)
from primordial.settings import Settings


class FakeGpuScreen:
    def __init__(self, flags: int) -> None:
        self._flags = flags

    def get_flags(self) -> int:
        return self._flags


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

    def test_gpu_ui_texture_shader_does_not_double_flip_uploaded_surface(self) -> None:
        self.assertIn("texture(u_texture, v_uv)", _TEXTURE_FRAGMENT_SHADER)
        self.assertNotIn("1.0 - v_uv.y", _TEXTURE_FRAGMENT_SHADER)

    def test_gpu_windowed_viewport_policy_uses_logical_window_size(self) -> None:
        renderer = PredatorPreyGpuRenderer.__new__(PredatorPreyGpuRenderer)
        renderer.screen = FakeGpuScreen(0)
        renderer.window_width = 1280
        renderer.window_height = 720
        renderer.drawable_width = 1920
        renderer.drawable_height = 1080

        self.assertEqual(renderer._active_gl_viewport_policy(), "logical_window")
        self.assertEqual(renderer._active_gl_viewport_size(), (1280, 720))

    def test_gpu_fullscreen_viewport_policy_uses_drawable_size(self) -> None:
        renderer = PredatorPreyGpuRenderer.__new__(PredatorPreyGpuRenderer)
        renderer.screen = FakeGpuScreen(pygame.FULLSCREEN)
        renderer.window_width = 1280
        renderer.window_height = 720
        renderer.drawable_width = 1920
        renderer.drawable_height = 1080

        self.assertEqual(renderer._active_gl_viewport_policy(), "drawable_fullscreen")
        self.assertEqual(renderer._active_gl_viewport_size(), (1920, 1080))

    def test_gpu_zone_labels_draw_when_hud_visible(self) -> None:
        renderer = PredatorPreyGpuRenderer.__new__(PredatorPreyGpuRenderer)
        renderer.width = 320
        renderer.height = 180
        renderer.hud = SimpleNamespace(visible=True)
        renderer._debug_font = pygame.font.Font(None, 18)
        renderer._ui_surface = pygame.Surface((320, 180), pygame.SRCALPHA)
        renderer._zone_label_cache_key = None
        renderer._zone_label_surface = None
        simulation = SimpleNamespace(
            zone_manager=SimpleNamespace(
                zones=[
                    SimpleNamespace(
                        zone_type="open_water",
                        x=160.0,
                        y=90.0,
                        radius=60.0,
                    )
                ]
            )
        )

        renderer._draw_zone_labels(simulation)

        self.assertIsNotNone(renderer._zone_label_surface)
        self.assertGreater(renderer._ui_surface.get_bounding_rect(min_alpha=1).width, 0)

    def test_gpu_zone_labels_not_drawn_when_hud_hidden(self) -> None:
        renderer = PredatorPreyGpuRenderer.__new__(PredatorPreyGpuRenderer)
        renderer.width = 320
        renderer.height = 180
        renderer.hud = SimpleNamespace(
            visible=False,
            render=lambda surface, simulation, fps, debug_lines=None: None,
        )
        renderer._debug_font = pygame.font.Font(None, 18)
        renderer._ui_surface = pygame.Surface((320, 180), pygame.SRCALPHA)
        renderer._zone_label_cache_key = None
        renderer._zone_label_surface = None
        renderer.fps = 0.0
        renderer.settings_overlay = SimpleNamespace(
            visible=True,
            fade=0.0,
            update=lambda: None,
            draw=lambda surface: None,
        )
        renderer.help_overlay = SimpleNamespace(
            visible=False,
            fade=0.0,
            update=lambda: None,
            draw=lambda surface: None,
        )
        renderer.tutorial_overlay = SimpleNamespace(
            visible=False,
            fade=0.0,
            update=lambda: None,
            draw=lambda surface: None,
            set_runtime_context=lambda **kwargs: None,
        )
        renderer.inspect_mode = SimpleNamespace(enabled=False)
        renderer.action_bar = SimpleNamespace(
            build_context=lambda *args, **kwargs: None,
            opacity=lambda context: 0.0,
            draw=lambda surface, context: None,
        )
        renderer.debug_enabled = False
        renderer._debug_timing = {}
        renderer._draw_game_over_overlay = lambda simulation: None
        renderer._draw_inspect_overlay = lambda simulation: None
        drawn = {"called": False}
        renderer._draw_surface_texture = lambda surface: drawn.__setitem__("called", True)
        simulation = SimpleNamespace(predator_prey_game_over_active=False)

        renderer._draw_ui(simulation)

        self.assertIsNone(renderer._zone_label_surface)
        self.assertEqual(renderer._ui_surface.get_bounding_rect(min_alpha=1).size, (0, 0))
        self.assertTrue(drawn["called"])

    def test_action_bar_alpha_changes_do_not_force_fallback_ui_upload(self) -> None:
        renderer = PredatorPreyGpuRenderer.__new__(PredatorPreyGpuRenderer)
        renderer.width = 320
        renderer.height = 180
        renderer.fps = 0.0
        renderer.settings = SimpleNamespace(inspect_visual_quality="balanced")
        renderer.debug_enabled = False
        renderer._debug_timing = {}
        renderer._overlay_textures_supported = True
        renderer._overlay_textures = {
            "hud": _OverlayTextureSlot(),
            "zone_labels": _OverlayTextureSlot(),
            "inspect_panel": _OverlayTextureSlot(),
            "inspect_graph": _OverlayTextureSlot(),
            "action_bar": _OverlayTextureSlot(),
            "fallback_ui": _OverlayTextureSlot(),
        }
        renderer.hud = SimpleNamespace(
            visible=False,
            build_panel_surface=lambda *args, **kwargs: (
                pygame.Surface((1, 1), pygame.SRCALPHA),
                (0, 0),
            ),
        )
        renderer.settings_overlay = SimpleNamespace(visible=False, fade=0.0)
        renderer.help_overlay = SimpleNamespace(visible=False, fade=0.0)
        renderer.tutorial_overlay = SimpleNamespace(visible=False, fade=0.0)
        renderer.inspect_mode = SimpleNamespace(enabled=False)
        action_bar_surface = pygame.Surface((120, 32), pygame.SRCALPHA)
        alpha_state = {"value": 0.8}
        renderer.action_bar = SimpleNamespace(
            build_context=lambda *args, **kwargs: "ctx",
            opacity=lambda context: alpha_state["value"],
            overlay_state=lambda screen_size, context: (
                action_bar_surface,
                pygame.Rect(10, 20, 120, 32),
                alpha_state["value"],
            ),
        )
        uploads: list[tuple[str, tuple[object, ...]]] = []
        draws: list[tuple[str, float]] = []
        fallback_called = {"value": 0}
        renderer._upload_overlay_surface = (
            lambda name, surface, content_key: uploads.append((name, content_key)) or 0.5
        )
        renderer._draw_overlay_texture = (
            lambda name, rect, alpha=1.0: draws.append((name, alpha))
        )
        renderer._draw_surface_texture = lambda surface: fallback_called.__setitem__(
            "value",
            fallback_called["value"] + 1,
        )
        simulation = SimpleNamespace(predator_prey_game_over_active=False)

        renderer._draw_ui(simulation)
        alpha_state["value"] = 0.35
        renderer._draw_ui(simulation)

        self.assertEqual(fallback_called["value"], 0)
        self.assertEqual([name for name, _key in uploads], ["action_bar", "action_bar"])
        self.assertEqual(uploads[0][1], uploads[1][1])
        self.assertEqual(draws, [("action_bar", 0.8), ("action_bar", 0.35)])


if __name__ == "__main__":
    unittest.main()
