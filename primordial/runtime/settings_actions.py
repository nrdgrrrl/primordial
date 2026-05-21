"""Settings overlay action handling for the interactive runtime."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

import pygame

from primordial.display import (
    _apply_display_mode,
    _desired_renderer_backend_name,
    _recreate_renderer_for_backend,
    hide_runtime_cursor,
)
from primordial.persistence.runtime_state import (
    _save_predator_prey_tuning_state,
)
from primordial.rendering import display_flags_for_settings, renderer_backend_name
from primordial.simulation import SnapshotError, load_snapshot, save_snapshot

from .fixed_step import FixedStepLoopState, build_fixed_step_loop_config

if TYPE_CHECKING:
    from primordial.rendering import Renderer
    from primordial.settings import Settings
    from primordial.simulation import Simulation

logger = logging.getLogger(__name__)


@dataclass
class SettingsActionContext:
    """Mutable runtime references needed by settings overlay actions."""

    settings: Settings
    simulation: Simulation
    renderer: Renderer
    runtime_loop: FixedStepLoopState
    active_snapshot_path: Path
    previous_mode: str
    debug: bool
    csv_run_logger: Any = None
    milestone_logger: Any = None


@dataclass
class SettingsActionResult:
    """Updated runtime references after a settings overlay action."""

    simulation: Simulation
    renderer: Renderer
    active_snapshot_path: Path
    previous_mode: str
    begin_mode_transition: bool = False


def handle_settings_overlay_event(
    event: pygame.event.Event,
    context: SettingsActionContext,
) -> SettingsActionResult:
    """Handle one keyboard or mouse event while the settings overlay is visible."""
    action = context.renderer.settings_overlay.handle_event(event)
    result = SettingsActionResult(
        simulation=context.simulation,
        renderer=context.renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=context.previous_mode,
    )
    if action is None:
        return result

    if action == "apply":
        return _apply_runtime_settings_change(context)

    if action == "reset":
        return _apply_runtime_settings_change(context, sync_overlay=True)

    if action == "discard" and context.renderer.settings_overlay.fade_dir < 0:
        context.simulation.paused = False
        context.runtime_loop.reset_timing_debt()
        return result

    if action == "save_snapshot":
        return _handle_save_snapshot(context)

    if action == "load_snapshot":
        return _handle_load_snapshot(context)

    if action == "help":
        return _handle_help(context)

    if action == "tutorial":
        return _handle_tutorial(context)

    if action == "reset_predator_prey_dials":
        return _handle_reset_predator_prey_dials(context)

    return result


def _apply_runtime_settings_change(
    context: SettingsActionContext,
    *,
    sync_overlay: bool = False,
) -> SettingsActionResult:
    """Apply live runtime changes after overlay settings mutate."""
    settings = context.settings
    simulation = context.simulation
    renderer = context.renderer

    context.runtime_loop.config = build_fixed_step_loop_config(settings)
    backend_changed = (
        renderer_backend_name(renderer) != _desired_renderer_backend_name(settings)
    )
    display_changed = settings.fullscreen != bool(
        renderer.screen.get_flags() & pygame.FULLSCREEN
    )

    if backend_changed:
        renderer = _recreate_renderer_for_backend(
            settings,
            simulation,
            debug=context.debug,
            snapshot_path=context.active_snapshot_path,
        )
    elif display_changed:
        _apply_display_mode(settings, simulation, renderer)

    renderer.set_theme(settings.visual_theme)
    renderer.set_mode(settings.sim_mode)

    if sync_overlay:
        renderer.settings_overlay.sync_from_settings()
        renderer.settings_overlay.set_snapshot_path(str(context.active_snapshot_path))
        renderer.settings_overlay.set_snapshot_status("Reset settings to defaults.")

    begin_mode_transition = settings.sim_mode != context.previous_mode
    if not begin_mode_transition:
        simulation.paused = False
        context.runtime_loop.reset_timing_debt()

    return SettingsActionResult(
        simulation=simulation,
        renderer=renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=(
            settings.sim_mode if begin_mode_transition else context.previous_mode
        ),
        begin_mode_transition=begin_mode_transition,
    )


def _handle_save_snapshot(context: SettingsActionContext) -> SettingsActionResult:
    active_snapshot_path = context.active_snapshot_path
    try:
        active_snapshot_path = save_snapshot(
            context.simulation,
            active_snapshot_path,
        )
    except OSError as exc:
        context.renderer.settings_overlay.set_snapshot_status(
            f"Save failed: {exc}",
            is_error=True,
        )
        logger.warning(
            "Settings overlay save failed at %s: %s",
            context.active_snapshot_path,
            exc,
        )
    else:
        context.renderer.settings_overlay.set_snapshot_path(str(active_snapshot_path))
        context.renderer.settings_overlay.set_snapshot_status(
            f"Saved snapshot to {active_snapshot_path.name}"
        )
        logger.info(
            "Saved simulation snapshot from settings overlay to %s",
            active_snapshot_path,
        )
    return SettingsActionResult(
        simulation=context.simulation,
        renderer=context.renderer,
        active_snapshot_path=active_snapshot_path,
        previous_mode=context.previous_mode,
    )


def _handle_load_snapshot(context: SettingsActionContext) -> SettingsActionResult:
    if not context.active_snapshot_path.exists():
        context.renderer.settings_overlay.set_snapshot_status(
            (
                "No snapshot found yet. "
                f"Press V to save one at {context.active_snapshot_path.name} first."
            ),
            is_error=True,
        )
        logger.warning(
            "Settings overlay load failed from %s: snapshot file missing",
            context.active_snapshot_path,
        )
        return SettingsActionResult(
            simulation=context.simulation,
            renderer=context.renderer,
            active_snapshot_path=context.active_snapshot_path,
            previous_mode=context.previous_mode,
        )

    try:
        loaded_simulation = load_snapshot(
            context.active_snapshot_path,
            settings=context.settings,
        )
    except SnapshotError as exc:
        context.renderer.settings_overlay.set_snapshot_status(
            str(exc),
            is_error=True,
        )
        logger.warning(
            "Settings overlay load failed from %s: %s",
            context.active_snapshot_path,
            exc,
        )
        return SettingsActionResult(
            simulation=context.simulation,
            renderer=context.renderer,
            active_snapshot_path=context.active_snapshot_path,
            previous_mode=context.previous_mode,
        )

    simulation = _swap_loaded_simulation(
        loaded_simulation,
        context.settings,
        context.renderer,
    )
    _attach_predator_prey_loggers(
        simulation,
        context.csv_run_logger,
        context.milestone_logger,
    )
    context.runtime_loop.config = build_fixed_step_loop_config(context.settings)
    simulation.paused = True
    context.runtime_loop.reset_timing_debt()
    context.renderer.settings_overlay.sync_from_settings()
    context.renderer.settings_overlay.set_snapshot_path(
        str(context.active_snapshot_path)
    )
    context.renderer.settings_overlay.set_snapshot_status(
        f"Loaded snapshot from {context.active_snapshot_path.name}"
    )
    logger.info(
        "Loaded simulation snapshot from settings overlay: %s",
        context.active_snapshot_path,
    )
    return SettingsActionResult(
        simulation=simulation,
        renderer=context.renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=context.previous_mode,
    )


def _handle_help(context: SettingsActionContext) -> SettingsActionResult:
    context.renderer.open_help_overlay()
    status_message = "Opened in-app predator-prey guide."
    if context.renderer.help_overlay.status_message:
        status_message = context.renderer.help_overlay.status_message
    context.renderer.settings_overlay.set_snapshot_status(
        status_message,
        is_error=bool(context.renderer.help_overlay.status_message),
    )
    context.runtime_loop.reset_timing_debt()
    return SettingsActionResult(
        simulation=context.simulation,
        renderer=context.renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=context.previous_mode,
    )


def _handle_tutorial(context: SettingsActionContext) -> SettingsActionResult:
    previous_paused = context.simulation.paused
    context.renderer.open_tutorial_overlay(
        forced=True,
        previous_paused=previous_paused,
    )
    context.simulation.paused = context.renderer.tutorial_overlay.wants_simulation_paused()
    context.renderer.settings_overlay.close()
    context.renderer.settings_overlay.set_snapshot_status("Started in-game tutorial.")
    context.runtime_loop.reset_timing_debt()
    return SettingsActionResult(
        simulation=context.simulation,
        renderer=context.renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=context.previous_mode,
    )


def _handle_reset_predator_prey_dials(
    context: SettingsActionContext,
) -> SettingsActionResult:
    if context.settings.sim_mode != "predator_prey":
        context.renderer.settings_overlay.set_snapshot_status(
            "Predator-prey dial reset is only available in predator_prey mode.",
            is_error=True,
        )
    else:
        context.simulation.reset_predator_prey_adaptive_tuning()
        context.simulation.restart_predator_prey_run()
        context.renderer.reset_runtime_state()
        context.runtime_loop.reset_timing_debt()
        _save_predator_prey_tuning_state(context.settings, context.simulation)
        context.renderer.settings_overlay.set_snapshot_status(
            "Reset predator-prey dials to baseline and cleared max ticks."
        )
    return SettingsActionResult(
        simulation=context.simulation,
        renderer=context.renderer,
        active_snapshot_path=context.active_snapshot_path,
        previous_mode=context.previous_mode,
    )


def _attach_predator_prey_loggers(
    simulation: Simulation,
    csv_run_logger: Any,
    milestone_logger: Any,
) -> None:
    simulation.set_predator_prey_run_logger(csv_run_logger)
    simulation.set_predator_prey_milestone_logger(milestone_logger)


def _swap_loaded_simulation(
    simulation: Simulation,
    settings: Settings,
    renderer: Renderer,
) -> Simulation:
    """Install a loaded simulation into the live runtime without special sim logic."""
    if (simulation.width, simulation.height) != (renderer.width, renderer.height):
        base_flags = pygame.FULLSCREEN | pygame.SCALED if settings.fullscreen else 0
        flags = display_flags_for_settings(settings, base_flags)
        screen = pygame.display.set_mode((simulation.width, simulation.height), flags)
        hide_runtime_cursor()
        renderer.resize(simulation.width, simulation.height, screen=screen)
    renderer.set_mode(settings.sim_mode)
    renderer.reset_runtime_state()
    return simulation
