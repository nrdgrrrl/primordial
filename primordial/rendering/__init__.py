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
from .hud_focus import HUDFocus
from .help_overlay import HelpOverlay
from .tutorial_overlay import TutorialOverlay
from .glyphs import build_glyph_surface, get_glyph_surface
from .animations import AnimationManager
from .inspect_mode import InspectMode, build_creature_card, display_to_world
from .creature_observation import (
    LifeStage,
    classify_life_stage,
    temperament_tags,
    format_tags,
    motion_style_label,
    depth_preference_label,
    infer_behavior_mode,
    infer_attention_target,
    AttentionTarget,
)

__all__ = [
    "Renderer", "Theme", "OceanTheme", "StubTheme", "get_theme",
    "HUD", "HUDFocus", "HelpOverlay", "TutorialOverlay", "build_glyph_surface", "get_glyph_surface", "AnimationManager",
    "create_renderer", "display_flags_for_settings", "renderer_backend_name",
    "renderer_gpu_info", "save_renderer_screenshot", "wants_gpu_renderer",
    "InspectMode", "build_creature_card", "display_to_world",
    "LifeStage", "classify_life_stage",
    "temperament_tags", "format_tags",
    "motion_style_label", "depth_preference_label",
    "infer_behavior_mode", "infer_attention_target", "AttentionTarget",
]
