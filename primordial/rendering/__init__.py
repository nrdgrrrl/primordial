"""Rendering module - all draw calls, themes, effects."""

from .renderer import Renderer
from .backend import (
    create_renderer,
    display_flags_for_settings,
    renderer_backend_name,
    renderer_gpu_info,
    save_renderer_screenshot,
    wants_gpu_renderer,
)
from .themes import Theme, OceanTheme, StubTheme, get_theme
from .hud import HUD
from .glyphs import build_glyph_surface, get_glyph_surface
from .animations import AnimationManager
from .inspect_mode import InspectMode, build_creature_card, display_to_world

__all__ = [
    "Renderer", "Theme", "OceanTheme", "StubTheme", "get_theme",
    "HUD", "build_glyph_surface", "get_glyph_surface", "AnimationManager",
    "create_renderer", "display_flags_for_settings", "renderer_backend_name",
    "renderer_gpu_info", "save_renderer_screenshot", "wants_gpu_renderer",
    "InspectMode", "build_creature_card", "display_to_world",
]
