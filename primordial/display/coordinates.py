"""Coordinate transforms and display diagnostics."""

from __future__ import annotations

import json
import logging

import pygame

from primordial.rendering import renderer_backend_name
from primordial.rendering.presentation_layout import PresentationLayout
from primordial.simulation import Simulation

from .mode import DEFAULT_WINDOWED_SIZE

logger = logging.getLogger(__name__)


def _get_window_size(fallback: tuple[int, int] = DEFAULT_WINDOWED_SIZE) -> tuple[int, int]:
    """Return SDL logical window size used by mouse event coordinates."""
    window_width = fallback[0]
    window_height = fallback[1]
    get_window_size = getattr(pygame.display, "get_window_size", None)
    if callable(get_window_size):
        try:
            queried_width, queried_height = get_window_size()
        except pygame.error:
            queried_width, queried_height = 0, 0
        if queried_width > 0 and queried_height > 0:
            window_width = int(queried_width)
            window_height = int(queried_height)
    return max(1, window_width), max(1, window_height)


def window_to_world(
    event_x: float,
    event_y: float,
    simulation: Simulation,
) -> tuple[float, float]:
    """Map SDL mouse-event coordinates into simulation world coordinates."""
    window_w, window_h = _get_window_size((simulation.width, simulation.height))
    return (
        event_x * simulation.width / max(1, window_w),
        event_y * simulation.height / max(1, window_h),
    )


def window_to_world_with_layout(
    event_x: float,
    event_y: float,
    simulation: Simulation,
    layout: PresentationLayout | None,
) -> tuple[float, float]:
    """Map SDL mouse-event coordinates into simulation world coordinates.

    When a gutter layout is active, uses the play viewport coordinate transform
    to map the click through the scaled/offset viewport. When the layout is
    None or not in gutter mode, falls back to simple proportional mapping.
    """
    if layout is not None and layout.is_gutter_layout:
        return layout.screen_to_world(event_x, event_y)
    return window_to_world(event_x, event_y, simulation)


def world_to_window(
    world_x: float,
    world_y: float,
    simulation: Simulation,
) -> tuple[float, float]:
    """Map simulation world coordinates into SDL logical window coordinates."""
    window_w, window_h = _get_window_size((simulation.width, simulation.height))
    return (
        world_x * max(1, window_w) / max(1, simulation.width),
        world_y * max(1, window_h) / max(1, simulation.height),
    )


def _get_display_window_size(renderer: object) -> tuple[int, int, int, int]:
    """Return renderer display size and SDL window size for diagnostics."""
    display_width = max(1, int(getattr(renderer, "display_width", 0)))
    display_height = max(1, int(getattr(renderer, "display_height", 0)))
    window_width, window_height = _get_window_size((display_width, display_height))
    return display_width, display_height, window_width, window_height


def _get_gl_viewport() -> list[int] | None:
    """Return the current OpenGL viewport for diagnostics when a GL context exists."""
    try:
        from OpenGL.GL import GL_VIEWPORT, glGetIntegerv

        viewport = glGetIntegerv(GL_VIEWPORT)
    except Exception:
        return None
    try:
        return [int(value) for value in viewport]
    except TypeError:
        return None


def _log_inspect_click_diagnostics(
    event_pos: tuple[int, int],
    world_pos: tuple[float, float],
    simulation: Simulation,
    renderer: object,
) -> None:
    """Emit enough inspect-click data to diagnose platform coordinate offsets."""
    display_width, display_height, window_width, window_height = _get_display_window_size(renderer)
    selected = renderer.inspect_mode.get_selected_creature(simulation)
    mouse_pos = pygame.mouse.get_pos()
    flags = int(renderer.screen.get_flags()) if hasattr(renderer, "screen") else 0
    backend = renderer_backend_name(renderer)

    selected_payload: dict[str, float | int | str | None] = {
        "id": None,
        "species": None,
        "world_x": None,
        "world_y": None,
        "render_window_x": None,
        "render_window_y": None,
        "delta_from_event_x": None,
        "delta_from_event_y": None,
    }
    if selected is not None:
        render_window_x, render_window_y = world_to_window(selected.x, selected.y, simulation)
        selected_payload = {
            "id": id(selected),
            "species": selected.species,
            "world_x": round(float(selected.x), 3),
            "world_y": round(float(selected.y), 3),
            "render_window_x": round(render_window_x, 3),
            "render_window_y": round(render_window_y, 3),
            "delta_from_event_x": round(render_window_x - event_pos[0], 3),
            "delta_from_event_y": round(render_window_y - event_pos[1], 3),
        }

    logger.debug(
        "INSPECT_CLICK_DIAGNOSTIC %s",
        json.dumps(
            {
                "backend": backend,
                "fullscreen": bool(flags & pygame.FULLSCREEN),
                "opengl": bool(flags & pygame.OPENGL),
                "scaled": bool(flags & pygame.SCALED),
                "event_pos": [int(event_pos[0]), int(event_pos[1])],
                "mouse_get_pos": [int(mouse_pos[0]), int(mouse_pos[1])],
                "mapped_world_pos": [round(float(world_pos[0]), 3), round(float(world_pos[1]), 3)],
                "display_size": [display_width, display_height],
                "window_size": [window_width, window_height],
                "screen_size": list(renderer.screen.get_size()) if hasattr(renderer, "screen") else None,
                "renderer_size": [
                    int(getattr(renderer, "width", 0)),
                    int(getattr(renderer, "height", 0)),
                ],
                "renderer_display_size": [
                    int(getattr(renderer, "display_width", 0)),
                    int(getattr(renderer, "display_height", 0)),
                ],
                "world_size": [int(simulation.width), int(simulation.height)],
                "gl_viewport": _get_gl_viewport(),
                "selected": selected_payload,
            },
            sort_keys=True,
        ),
    )
