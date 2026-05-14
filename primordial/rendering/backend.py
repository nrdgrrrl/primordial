"""Renderer backend selection helpers."""

from __future__ import annotations

import importlib.util
import logging
import os
from typing import TYPE_CHECKING

import pygame

from .renderer import Renderer

if TYPE_CHECKING:
    from ..settings import Settings

logger = logging.getLogger(__name__)


def wants_gpu_renderer(settings: Settings) -> bool:
    """Return whether the active mode should request the OpenGL renderer."""
    if getattr(settings, "sim_mode", "") != "predator_prey":
        return False
    if getattr(settings, "render_backend", "pygame") != "gpu":
        return False
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return False
    return importlib.util.find_spec("OpenGL.GL") is not None


def display_flags_for_settings(settings: Settings, base_flags: int = 0) -> int:
    """Return display flags compatible with the requested renderer backend."""
    if not wants_gpu_renderer(settings):
        return base_flags
    flags = base_flags & ~pygame.SCALED
    return flags | pygame.OPENGL | pygame.DOUBLEBUF


def create_renderer(
    screen: pygame.Surface,
    settings: Settings,
    *,
    debug: bool = False,
) -> Renderer | object:
    """Create the active renderer, falling back to pygame when GPU is unavailable."""
    if wants_gpu_renderer(settings):
        try:
            from .gpu_renderer import PredatorPreyGpuRenderer

            return PredatorPreyGpuRenderer(screen, settings, debug=debug)
        except Exception:
            logger.exception("GPU renderer initialization failed; falling back to pygame.")
            if screen.get_flags() & pygame.OPENGL:
                fallback_flags = screen.get_flags() & ~pygame.OPENGL & ~pygame.DOUBLEBUF
                screen = pygame.display.set_mode(screen.get_size(), fallback_flags)
    return Renderer(screen, settings, debug=debug)


def renderer_backend_name(renderer: object) -> str:
    """Return a stable backend name for metrics and logs."""
    return str(getattr(renderer, "backend_name", "pygame"))


def renderer_gpu_info(renderer: object) -> dict[str, str]:
    """Return GPU identity metadata when available."""
    info = getattr(renderer, "gpu_info", None)
    if isinstance(info, dict):
        return {str(key): str(value) for key, value in info.items()}
    return {}


def save_renderer_screenshot(renderer: object, path) -> None:
    """Save a screenshot from either pygame or OpenGL renderers."""
    save = getattr(renderer, "save_screenshot", None)
    if callable(save):
        save(path)
        return
    pygame.image.save(renderer.screen, path)
