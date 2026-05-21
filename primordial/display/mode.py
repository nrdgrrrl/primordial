"""Display mode setup and fullscreen/windowed transitions."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pygame

from primordial.display.cursor import hide_runtime_cursor
from primordial.rendering import (
    Renderer,
    create_renderer,
    display_flags_for_settings,
    wants_gpu_renderer,
)
from primordial.settings import Settings
from primordial.simulation import Simulation

logger = logging.getLogger(__name__)

DEFAULT_WINDOWED_SIZE = (1280, 720)


def _get_fullscreen_resolution() -> tuple[int, int]:
    """Resolve the desktop/native resolution used for fullscreen mode."""
    get_desktop_sizes = getattr(pygame.display, "get_desktop_sizes", None)
    if callable(get_desktop_sizes):
        try:
            desktop_sizes = get_desktop_sizes()
        except pygame.error:
            desktop_sizes = []
        if desktop_sizes:
            return desktop_sizes[0]

    display_info = pygame.display.Info()
    return display_info.current_w, display_info.current_h


def toggle_fullscreen(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """Toggle between fullscreen and windowed mode."""
    settings.fullscreen = not settings.fullscreen
    _apply_display_mode(settings, simulation, renderer)


def _force_windowed_mode(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """Recreate the display explicitly in windowed mode."""
    if not settings.fullscreen and not bool(renderer.screen.get_flags() & pygame.FULLSCREEN):
        return
    settings.fullscreen = False
    _apply_display_mode(settings, simulation, renderer)


def _desired_renderer_backend_name(settings: Settings) -> str:
    """Return the backend name implied by the current mode/config/environment."""
    return "gpu" if wants_gpu_renderer(settings) else "pygame"


def _display_mode_size(settings: Settings) -> tuple[tuple[int, int], int]:
    """Return the active logical world/window size plus pygame base flags."""
    if settings.fullscreen:
        return _get_fullscreen_resolution(), pygame.FULLSCREEN | pygame.SCALED
    return DEFAULT_WINDOWED_SIZE, 0


def _log_display_mode_coordinate_state(
    settings: Settings,
    simulation: Simulation,
    renderer: object,
    *,
    phase: str,
) -> None:
    """Log coordinate-space invariants after display mode changes."""
    from .coordinates import _get_display_window_size, _get_gl_viewport

    display_width, display_height, window_width, window_height = _get_display_window_size(renderer)
    screen = getattr(renderer, "screen", None)
    screen_size = list(screen.get_size()) if hasattr(screen, "get_size") else None
    payload = {
        "phase": phase,
        "fullscreen": bool(settings.fullscreen),
        "window_size": [window_width, window_height],
        "drawable_size": [
            int(getattr(renderer, "drawable_width", display_width)),
            int(getattr(renderer, "drawable_height", display_height)),
        ],
        "screen_size": screen_size,
        "renderer_size": [
            int(getattr(renderer, "width", 0)),
            int(getattr(renderer, "height", 0)),
        ],
        "simulation_size": [int(simulation.width), int(simulation.height)],
        "gl_viewport": _get_gl_viewport(),
    }
    logger.debug("DISPLAY_MODE_COORDINATE_STATE %s", json.dumps(payload, sort_keys=True))

    renderer_size = (int(getattr(renderer, "width", 0)), int(getattr(renderer, "height", 0)))
    simulation_size = (int(simulation.width), int(simulation.height))
    if renderer_size != simulation_size:
        logger.warning(
            "Display mode coordinate invariant mismatch: renderer_size=%s simulation_size=%s",
            renderer_size,
            simulation_size,
        )
    if not settings.fullscreen and simulation_size != DEFAULT_WINDOWED_SIZE:
        logger.warning(
            "Windowed mode world size mismatch: simulation_size=%s expected=%s",
            simulation_size,
            DEFAULT_WINDOWED_SIZE,
        )


def _recreate_renderer_for_backend(
    settings: Settings,
    simulation: Simulation,
    *,
    debug: bool,
    snapshot_path: Path,
) -> Renderer:
    """Recreate the display and renderer when backend requirements change."""
    display_size, base_flags = _display_mode_size(settings)

    screen = pygame.display.set_mode(
        display_size,
        display_flags_for_settings(settings, base_flags),
    )
    hide_runtime_cursor()
    simulation.resize(*display_size)
    renderer = create_renderer(screen, settings, debug=debug)
    renderer.resize(*display_size, screen=screen)
    renderer.reset_runtime_state()
    renderer.settings_overlay.set_snapshot_path(str(snapshot_path))
    _log_display_mode_coordinate_state(
        settings,
        simulation,
        renderer,
        phase="recreate_renderer_for_backend",
    )
    return renderer


def _apply_display_mode(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """Apply the current display mode and resize the simulation world to match."""
    (width, height), base_flags = _display_mode_size(settings)

    flags = display_flags_for_settings(settings, base_flags)
    screen = pygame.display.set_mode((width, height), flags)
    hide_runtime_cursor()
    simulation.resize(width, height)
    renderer.resize(width, height, screen=screen)
    renderer.reset_runtime_state()
    _log_display_mode_coordinate_state(
        settings,
        simulation,
        renderer,
        phase="apply_display_mode",
    )
