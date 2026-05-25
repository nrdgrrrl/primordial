"""Keyboard event handling for the interactive runtime."""

from __future__ import annotations

import pygame

from primordial.display.cursor import hide_runtime_cursor, show_interactive_cursor
from primordial.display.mode import toggle_fullscreen
from primordial.rendering import Renderer
from primordial.rendering.inspect_mode import InspectMode
from primordial.runtime import FixedStepLoopState
from primordial.settings import Settings
from primordial.simulation import Simulation


def handle_keydown(
    event: pygame.event.Event,
    simulation: Simulation,
    renderer: Renderer,
    settings: Settings,
    screen: pygame.Surface,
    mode: str,
    runtime_loop: FixedStepLoopState,
    inspect_mode: InspectMode | None = None,
) -> bool:
    """
    Handle keyboard input.

    Returns:
        True to continue running, False to quit.
    """
    key = event.key

    if key in (pygame.K_ESCAPE, pygame.K_q):
        return False
    elif key == pygame.K_u:
        renderer.toggle_hud()
    elif key == pygame.K_c:
        if renderer.hud.visible and not renderer.inspect_mode.enabled:
            renderer.hud_focus.clear_selection()
    elif key == pygame.K_h and mode != "screensaver":
        renderer.open_help_overlay()
        show_interactive_cursor()
        renderer.show_cursor = True
    elif key == pygame.K_i:
        if inspect_mode is not None:
            restore_paused = inspect_mode.was_paused_before if inspect_mode.enabled else None
            inspect_mode.toggle(simulation_paused=simulation.paused)
            if inspect_mode.enabled:
                renderer.hud_focus.clear_selection()
                simulation.paused = True
                show_interactive_cursor()
                renderer.show_cursor = True
            else:
                if restore_paused is not None:
                    simulation.paused = restore_paused
                else:
                    simulation.paused = False
                hide_cursor = (
                    settings.fullscreen
                    or bool(screen.get_flags() & pygame.FULLSCREEN)
                    or mode == "screensaver"
                )
                if hide_cursor:
                    hide_runtime_cursor()
                else:
                    show_interactive_cursor()
                renderer.show_cursor = False
                inspect_mode.clear_selection()
            runtime_loop.reset_timing_debt()
    elif key == pygame.K_m:
        if inspect_mode is not None and inspect_mode.enabled:
            inspect_mode.toggle_pause_slow()
            if inspect_mode.pause_mode == "pause":
                simulation.paused = True
            elif inspect_mode.pause_mode == "slow":
                simulation.paused = False
            inspect_mode._slow_accumulator = 0.0
            runtime_loop.reset_timing_debt()
    elif key == pygame.K_n:
        if inspect_mode is not None and inspect_mode.enabled:
            inspect_mode.set_normal_follow()
            simulation.paused = False
            runtime_loop.reset_timing_debt()
    elif key == pygame.K_d:
        if inspect_mode is not None and inspect_mode.enabled:
            inspect_mode.toggle_detail_level()
    elif key == pygame.K_s and mode != "screensaver":
        renderer.toggle_settings_overlay()
    elif key == pygame.K_SPACE:
        if simulation.predator_prey_game_over_active:
            simulation.restart_predator_prey_run()
            renderer.reset_runtime_state()
            runtime_loop.reset_timing_debt()
            return True
        if inspect_mode is not None and inspect_mode.enabled:
            runtime_loop.reset_timing_debt()
            return True
        simulation.paused = not simulation.paused
        runtime_loop.reset_timing_debt()
    elif key == pygame.K_f:
        toggle_fullscreen(settings, simulation, renderer)
    elif key == pygame.K_r:
        if settings.sim_mode == "predator_prey":
            simulation.restart_predator_prey_run()
            renderer.reset_runtime_state()
        else:
            simulation.reset()
        runtime_loop.reset_timing_debt()
    elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
        settings.food_spawn_rate = min(2.0, settings.food_spawn_rate + 0.1)
    elif key in (pygame.K_MINUS, pygame.K_UNDERSCORE, pygame.K_KP_MINUS):
        settings.food_spawn_rate = max(0.1, settings.food_spawn_rate - 0.1)

    return True
