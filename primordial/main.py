#!/usr/bin/env python3
"""
Primordial - A cellular evolution screensaver simulation.

Main entry point with game loop, event handling, and controls.
Supports Windows screensaver modes: /s (screensaver), /p HWND (preview), /c (config).
"""

from __future__ import annotations

import json
import logging
import platform
import random
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any

import pygame

logger = logging.getLogger(__name__)

# Fix blurry rendering on Windows high-DPI displays.
# Must run before pygame.init(); silently ignored on non-Windows and older Windows.
try:
    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
except (AttributeError, OSError):
    logger.debug("DPI awareness API unavailable on this platform.")

from .rendering import (
    Renderer,
    create_renderer,
    display_flags_for_settings,
    renderer_backend_name,
    wants_gpu_renderer,
)
from .rendering.inspect_mode import InspectMode as _InspectMode
from .runtime import (
    FixedStepLoopState,
    LoopTimingCollector,
    advance_fixed_step_frame,
    build_fixed_step_loop_config,
    build_frame_metrics,
    create_fixed_step_loop_state,
    get_effective_target_fps,
    simulation_timing_is_suppressed,
)
from .runtime.profile import _run_profile_session
from .milestone_logging import PredatorPreyMilestoneLogger
from .run_logging import PredatorPreyCSVRunLogger
from .settings import Settings
from .simulation import (
    Simulation,
    SnapshotError,
    inspect_snapshot_dimensions,
    load_snapshot,
    save_snapshot,
)
from .utils.cli import RuntimeArgs
from .utils.paths import get_base_path
from .utils.screensaver import ScreensaverArgs

DEFAULT_WINDOWED_SIZE = (1280, 720)
PREDATOR_PREY_TUNING_STATE_VERSION = 1
PREDATOR_PREY_TUNING_STATE_KIND = "primordial.predator_prey_tuning_state"


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


def main(
    scr_args: ScreensaverArgs | None = None,
    runtime_args: RuntimeArgs | None = None,
) -> None:
    """Main entry point for Primordial."""
    if scr_args is None:
        scr_args = ScreensaverArgs(mode="normal")
    if runtime_args is None:
        runtime_args = RuntimeArgs()

    log_path = _configure_logging(runtime_args.debug)
    logger.info(
        "Starting Primordial mode=%s debug=%s profile=%s debug_log=%s run_log=%s",
        scr_args.mode,
        runtime_args.debug,
        runtime_args.profile,
        log_path,
        runtime_args.log,
    )

    # Config mode: show a simple settings dialog without running the simulation.
    if scr_args.mode == "config":
        _run_config_dialog()
        return

    # Initialize pygame
    pygame.init()

    # Load settings and apply runtime overrides.
    settings = Settings()
    _apply_runtime_overrides(settings, runtime_args)
    loaded_world_size = _resolve_loaded_world_size(runtime_args)
    csv_run_logger = _create_run_logger(settings, runtime_args)
    milestone_logger = _create_milestone_logger(settings, runtime_args)

    # Set up display based on mode
    if scr_args.mode == "screensaver":
        width, height = _get_fullscreen_resolution()
        flags = display_flags_for_settings(settings, pygame.FULLSCREEN | pygame.SCALED)
        screen = pygame.display.set_mode((width, height), flags)
        pygame.mouse.set_visible(False)
    elif scr_args.mode == "preview":
        # SDL_WINDOWID was already set by root main.py; just create a surface
        # that fits into the preview pane (typically ~152×112 px).
        width, height = 152, 112
        screen = pygame.display.set_mode((width, height))
        pygame.mouse.set_visible(False)
    else:
        if settings.fullscreen:
            width, height = _get_fullscreen_resolution()
            flags = display_flags_for_settings(settings, pygame.FULLSCREEN | pygame.SCALED)
            screen = pygame.display.set_mode((width, height), flags)
        else:
            if loaded_world_size is not None:
                width, height = loaded_world_size
            else:
                width = 1280
                height = 720
            screen = pygame.display.set_mode(
                (width, height),
                display_flags_for_settings(settings),
            )
        pygame.mouse.set_visible(False)

    pygame.display.set_caption("Primordial")

    if loaded_world_size is not None and loaded_world_size != (width, height):
        pygame.quit()
        raise SystemExit(
            "Loaded snapshot world size "
            f"{loaded_world_size[0]}x{loaded_world_size[1]} does not match the active "
            f"display mode size {width}x{height}."
        )

    # Initialize simulation and renderer
    try:
        if runtime_args.load:
            simulation = load_snapshot(runtime_args.load, settings=settings)
        else:
            initial_seed = None
            if settings.sim_mode == "predator_prey":
                initial_seed = random.SystemRandom().randrange(1, 2_147_483_647)
            simulation = Simulation(width, height, settings, seed=initial_seed)
            if settings.sim_mode == "predator_prey":
                persisted_tuning = _load_predator_prey_tuning_state(settings)
                if persisted_tuning is not None:
                    simulation.restore_predator_prey_tuning_state(persisted_tuning)
    except SnapshotError as exc:
        pygame.quit()
        raise SystemExit(str(exc)) from exc
    simulation.set_predator_prey_run_logger(csv_run_logger)
    simulation.set_predator_prey_milestone_logger(milestone_logger)
    if milestone_logger is not None:
        milestone_logger.log_session_start(simulation)
        if settings.sim_mode == "predator_prey":
            milestone_logger.log_run_start(simulation)
    renderer = create_renderer(screen, settings, debug=runtime_args.debug)
    renderer.resize(simulation.width, simulation.height, screen=screen)
    active_snapshot_path = _resolve_snapshot_path(
        settings,
        runtime_args.load or runtime_args.save,
    )
    renderer.settings_overlay.set_snapshot_path(str(active_snapshot_path))

    # Clock for FPS limiting
    clock = pygame.time.Clock()
    runtime_loop = create_fixed_step_loop_state(settings)
    timing_collector = LoopTimingCollector(retain_samples=False)

    if runtime_args.profile:
        if scr_args.mode != "normal":
            logger.warning("--profile is only supported in normal mode; ignoring.")
        else:
            profile_base = _run_profile_session(
                simulation,
                renderer,
                clock,
                settings,
                runtime_loop,
                timing_collector=LoopTimingCollector(retain_samples=True),
            )
            pygame.quit()
            logger.info("Profile run complete: %s.[pstats|txt|timing.json]", profile_base)
            sys.exit(0)

    # Grace period for screensaver mode: ignore all input for 2 seconds after
    # launch to absorb any spurious mouse events some systems emit at startup.
    grace_until: float = time.time() + 2.0 if scr_args.mode == "screensaver" else 0.0

    # Mode transition fade state
    _prev_mode: str = settings.sim_mode
    _transition_alpha: int = 0
    _transition_dir: int = 0  # +1=fading out, -1=fading in, 0=idle
    _transition_surf: pygame.Surface | None = None

    def _begin_mode_transition() -> None:
        nonlocal _transition_alpha, _transition_dir, _transition_surf
        _transition_alpha = 0
        _transition_dir = 1
        runtime_loop.reset_timing_debt()
        _transition_surf = pygame.Surface(
            (renderer.width, renderer.height), pygame.SRCALPHA
        )

    running = True
    while running:
        frame_start = time.perf_counter()
        event_start = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif scr_args.mode == "screensaver":
                # Quit on any real user input after the grace period.
                if time.time() > grace_until:
                    if event.type == pygame.KEYDOWN:
                        running = False
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        running = False
                    elif event.type == pygame.MOUSEMOTION:
                        # Only quit if movement exceeds threshold (avoids
                        # triggering on tiny cursor settling jitter at startup).
                        dx, dy = event.rel
                        if abs(dx) > 4 or abs(dy) > 4:
                            running = False

            elif scr_args.mode == "preview":
                # Preview pane: no input handling except QUIT (already handled above).
                pass

            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_p:
                    renderer.set_predator_highlight(False)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if renderer.inspect_mode.enabled and scr_args.mode == "normal":
                    world_x, world_y = window_to_world(event.pos[0], event.pos[1], simulation)
                    renderer.inspect_mode.select_at_world_pos(world_x, world_y, simulation)
                    mark_debug_click = getattr(renderer, "mark_debug_inspect_click", None)
                    if callable(mark_debug_click):
                        mark_debug_click(world_x, world_y)
                    if logger.isEnabledFor(logging.DEBUG):
                        _log_inspect_click_diagnostics(
                            event.pos,
                            (world_x, world_y),
                            simulation,
                            renderer,
                        )

            elif event.type == pygame.KEYDOWN:
                if renderer.settings_overlay.visible:
                    action = renderer.settings_overlay.handle_event(event)
                    if action == "apply":
                        runtime_loop.config = build_fixed_step_loop_config(settings)
                        backend_changed = (
                            renderer_backend_name(renderer)
                            != _desired_renderer_backend_name(settings)
                        )
                        display_changed = settings.fullscreen != bool(
                            renderer.screen.get_flags() & pygame.FULLSCREEN
                        )
                        if backend_changed:
                            renderer = _recreate_renderer_for_backend(
                                settings,
                                simulation,
                                debug=runtime_args.debug,
                                snapshot_path=active_snapshot_path,
                            )
                        elif display_changed:
                            _apply_display_mode(settings, simulation, renderer)
                        renderer.set_theme(settings.visual_theme)
                        renderer.set_mode(settings.sim_mode)
                        if settings.sim_mode != _prev_mode:
                            _begin_mode_transition()
                        else:
                            simulation.paused = False
                            runtime_loop.reset_timing_debt()
                    elif action == "discard" and renderer.settings_overlay.fade_dir < 0:
                        simulation.paused = False
                        runtime_loop.reset_timing_debt()
                    elif action == "save_snapshot":
                        try:
                            active_snapshot_path = save_snapshot(
                                simulation,
                                active_snapshot_path,
                            )
                        except OSError as exc:
                            renderer.settings_overlay.set_snapshot_status(
                                f"Save failed: {exc}",
                                is_error=True,
                            )
                            logger.warning(
                                "Settings overlay save failed at %s: %s",
                                active_snapshot_path,
                                exc,
                            )
                        else:
                            renderer.settings_overlay.set_snapshot_path(
                                str(active_snapshot_path)
                            )
                            renderer.settings_overlay.set_snapshot_status(
                                f"Saved snapshot to {active_snapshot_path.name}"
                            )
                            logger.info(
                                "Saved simulation snapshot from settings overlay to %s",
                                active_snapshot_path,
                            )
                    elif action == "load_snapshot":
                        if not active_snapshot_path.exists():
                            renderer.settings_overlay.set_snapshot_status(
                                (
                                    "No snapshot found yet. "
                                    f"Press V to save one at {active_snapshot_path.name} first."
                                ),
                                is_error=True,
                            )
                            logger.warning(
                                "Settings overlay load failed from %s: snapshot file missing",
                                active_snapshot_path,
                            )
                        else:
                            try:
                                loaded_simulation = load_snapshot(
                                    active_snapshot_path,
                                    settings=settings,
                                )
                            except SnapshotError as exc:
                                renderer.settings_overlay.set_snapshot_status(
                                    str(exc),
                                    is_error=True,
                                )
                                logger.warning(
                                    "Settings overlay load failed from %s: %s",
                                    active_snapshot_path,
                                    exc,
                                )
                            else:
                                simulation = _swap_loaded_simulation(
                                    loaded_simulation,
                                    settings,
                                    renderer,
                                )
                                runtime_loop.config = build_fixed_step_loop_config(settings)
                                simulation.paused = True
                                runtime_loop.reset_timing_debt()
                                renderer.settings_overlay.sync_from_settings()
                                renderer.settings_overlay.set_snapshot_path(
                                    str(active_snapshot_path)
                                )
                                renderer.settings_overlay.set_snapshot_status(
                                    f"Loaded snapshot from {active_snapshot_path.name}"
                                )
                                logger.info(
                                    "Loaded simulation snapshot from settings overlay: %s",
                                    active_snapshot_path,
                                )
                    elif action == "help":
                        opened, status_message = _open_predator_prey_help(
                            settings,
                            simulation,
                            renderer,
                        )
                        renderer.settings_overlay.pending["fullscreen"] = settings.fullscreen
                        renderer.settings_overlay.set_snapshot_status(
                            status_message,
                            is_error=not opened,
                        )
                        runtime_loop.reset_timing_debt()
                    elif action == "reset_predator_prey_dials":
                        if settings.sim_mode != "predator_prey":
                            renderer.settings_overlay.set_snapshot_status(
                                "Predator-prey dial reset is only available in predator_prey mode.",
                                is_error=True,
                            )
                        else:
                            simulation.reset_predator_prey_adaptive_tuning()
                            simulation.restart_predator_prey_run()
                            renderer.reset_runtime_state()
                            runtime_loop.reset_timing_debt()
                            _save_predator_prey_tuning_state(settings, simulation)
                            renderer.settings_overlay.set_snapshot_status(
                                "Reset predator-prey dials to baseline and cleared max ticks."
                            )
                else:
                    if event.key == pygame.K_p:
                        renderer.set_predator_highlight(True)
                    running = handle_keydown(
                        event,
                        simulation,
                        renderer,
                        settings,
                        renderer.screen,
                        scr_args.mode,
                        runtime_loop,
                        inspect_mode=renderer.inspect_mode,
                    )
                    if renderer.settings_overlay.visible:
                        _prev_mode = settings.sim_mode
                        simulation.paused = True
                        runtime_loop.reset_timing_debt()
        event_ms = (time.perf_counter() - event_start) * 1000.0

        # Mode transition: fade out → reset sim → fade in
        if _transition_dir != 0 and _transition_surf is not None:
            step = 4
            if _transition_dir == 1:
                _transition_alpha = min(200, _transition_alpha + step)
                if _transition_alpha >= 200:
                    simulation.reset()
                    simulation.paused = False
                    runtime_loop.reset_timing_debt()
                    _transition_dir = -1
            else:
                _transition_alpha = max(0, _transition_alpha - step)
                if _transition_alpha <= 0:
                    _transition_dir = 0

        if simulation.update_predator_prey_runtime(now_seconds=time.monotonic()):
            renderer.reset_runtime_state()
            runtime_loop.reset_timing_debt()

        sim_suppressed = simulation_timing_is_suppressed(
            simulation,
            _transition_dir,
            _transition_alpha,
        )

        # Inspect mode: pause or slow the simulation
        inspect_suppress = False
        if renderer.inspect_mode.enabled and not sim_suppressed:
            if renderer.inspect_mode.pause_mode == "pause":
                inspect_suppress = True
            elif renderer.inspect_mode.pause_mode == "slow":
                frame_dt = max(0.0, 1.0 / max(1, get_effective_target_fps(settings)))
                if not renderer.inspect_mode.should_step_slow(frame_dt):
                    inspect_suppress = True

        sim_ms, sim_steps, clamp_frames, dropped_seconds = advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=not sim_suppressed and not inspect_suppress,
        )

        debug_payload = timing_collector.latest_debug_payload()
        debug_payload.update({
            "event_ms": event_ms,
            "sim_ms": sim_ms,
            "sim_steps": float(sim_steps),
            "clamp_frames": float(clamp_frames),
            "dropped_ms": dropped_seconds * 1000.0,
            "accumulator_ms": runtime_loop.accumulator_seconds * 1000.0,
            "display_width": float(renderer.display_width),
            "display_height": float(renderer.display_height),
            "world_width": float(simulation.width),
            "world_height": float(simulation.height),
        })
        renderer.set_external_debug_metrics(debug_payload)
        runtime_loop.restore_buffered_attacks(simulation)
        render_metrics = renderer.draw(simulation)

        # Overlay the transition fade
        if _transition_dir != 0 and _transition_surf is not None and _transition_alpha > 0:
            if _transition_surf.get_size() != (renderer.width, renderer.height):
                _transition_surf = pygame.Surface(
                    (renderer.width, renderer.height), pygame.SRCALPHA
                )
            _transition_surf.fill((0, 0, 0, _transition_alpha))
            renderer.blit_presentation_overlay(_transition_surf)

        present_start = time.perf_counter()
        pygame.display.flip()
        present_ms = (time.perf_counter() - present_start) * 1000.0

        effective_target_fps = get_effective_target_fps(settings)
        target_fps = (
            max(1, effective_target_fps // 2)
            if scr_args.mode == "preview"
            else effective_target_fps
        )
        pacing_start = time.perf_counter()
        clock.tick(target_fps)
        pacing_ms = (time.perf_counter() - pacing_start) * 1000.0
        frame_end = time.perf_counter()

        timing_collector.record_frame(
            build_frame_metrics(
                event_ms=event_ms,
                sim_ms=sim_ms,
                render_ms=render_metrics.get("draw_total_ms", 0.0),
                present_ms=present_ms,
                pacing_ms=pacing_ms,
                frame_start=frame_start,
                frame_end=frame_end,
                sim_steps=sim_steps,
                clamp_frames=clamp_frames,
                dropped_seconds=dropped_seconds,
                accumulator_seconds=runtime_loop.accumulator_seconds,
            )
        )

    persisted_tuning_path = _save_predator_prey_tuning_state(settings, simulation)
    if persisted_tuning_path is not None:
        logger.info("Saved predator-prey tuning state to %s", persisted_tuning_path)

    if runtime_args.save:
        saved_path = save_snapshot(simulation, runtime_args.save)
        logger.info("Saved simulation snapshot to %s", saved_path)

    if milestone_logger is not None:
        milestone_logger.close()

    pygame.quit()
    sys.exit(0)


def _configure_logging(debug_enabled: bool) -> str:
    """Configure file logging (+ console logging in debug mode)."""
    if platform.system() == "Windows":
        log_dir = Path.home() / "AppData" / "Roaming" / "Primordial"
    elif platform.system() == "Darwin":
        log_dir = Path.home() / "Library" / "Application Support" / "Primordial"
    else:
        log_dir = Path.home() / ".config" / "primordial"
    preferred_path = log_dir / "primordial.log"
    fallback_path = Path.cwd() / "primordial.log"

    handlers: list[logging.Handler] = []
    active_path: Path | None = None
    fallback_reason: str | None = None

    for candidate in (preferred_path, fallback_path):
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(candidate, encoding="utf-8"))
            active_path = candidate
            break
        except OSError as exc:
            fallback_reason = str(exc)

    if not handlers:
        # Last-resort fallback: avoid startup crash even if file logging is unavailable.
        handlers.append(logging.StreamHandler(sys.stderr))
        active_path = Path("<stderr>")

    if debug_enabled:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.DEBUG if debug_enabled else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    if fallback_reason and active_path != preferred_path:
        logging.getLogger(__name__).warning(
            "Log file fallback engaged (%s). Active log path: %s",
            fallback_reason,
            active_path,
        )
    return str(active_path)


def _apply_runtime_overrides(settings: Settings, runtime_args: RuntimeArgs) -> None:
    """Apply non-persistent CLI overrides."""
    if runtime_args.mode:
        if runtime_args.mode in settings.VALID_SIM_MODES:
            settings.sim_mode = runtime_args.mode
        else:
            logger.warning(
                "Ignoring invalid --mode '%s'. Valid: %s",
                runtime_args.mode,
                ", ".join(settings.VALID_SIM_MODES),
            )
    if runtime_args.theme:
        if runtime_args.theme in settings.VALID_VISUAL_THEMES:
            settings.visual_theme = runtime_args.theme
        else:
            logger.warning(
                "Ignoring invalid --theme '%s'. Valid: %s",
                runtime_args.theme,
                ", ".join(settings.VALID_VISUAL_THEMES),
            )
    if runtime_args.debug:
        settings.show_hud = True


def _resolve_loaded_world_size(
    runtime_args: RuntimeArgs,
) -> tuple[int, int] | None:
    """Read snapshot dimensions early so bootstrap can pick new-vs-load world size."""
    if not runtime_args.load:
        return None
    try:
        return inspect_snapshot_dimensions(runtime_args.load)
    except SnapshotError as exc:
        raise SystemExit(str(exc)) from exc


def _default_snapshot_path(settings: Settings) -> Path:
    """Return the bounded default snapshot path used by in-app save/load."""
    return Path(settings.config_path).parent / "world_snapshot.json"


def _predator_prey_tuning_state_path(settings: Settings) -> Path:
    """Return the persisted predator-prey tuning state file path."""
    return Path(settings.config_path).parent / "predator_prey_tuning_state.json"


def _run_log_directory(settings: Settings) -> Path:
    """Return the directory that stores optional CSV run logs."""
    if getattr(sys, "frozen", False):
        return Path(settings.config_path).parent / "run_logs"
    return get_base_path() / "run_logs"


def _run_log_csv_path(settings: Settings) -> Path:
    """Return the predator-prey stability CSV path."""
    return _run_log_directory(settings) / "predator_prey_runs.csv"


def _create_run_logger(
    settings: Settings,
    runtime_args: RuntimeArgs,
) -> PredatorPreyCSVRunLogger | None:
    """Create the optional CSV run logger when requested at launch."""
    if runtime_args.log != "csv":
        return None
    csv_path = _run_log_csv_path(settings)
    run_logger = PredatorPreyCSVRunLogger(csv_path)
    logger.info("CSV run logging enabled: %s", csv_path)
    return run_logger


def _create_milestone_logger(
    settings: Settings,
    runtime_args: RuntimeArgs,
) -> PredatorPreyMilestoneLogger | None:
    """Create the optional milestone logger when requested at launch."""
    if not runtime_args.milestone_log:
        return None
    yaml_path = _run_log_directory(settings) / runtime_args.milestone_log
    ml = PredatorPreyMilestoneLogger(yaml_path)
    return ml


def _load_predator_prey_tuning_state(settings: Settings) -> dict[str, Any] | None:
    path = _predator_prey_tuning_state_path(settings)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Unable to read predator-prey tuning state from %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != PREDATOR_PREY_TUNING_STATE_VERSION:
        return None
    if payload.get("kind") != PREDATOR_PREY_TUNING_STATE_KIND:
        return None
    state = payload.get("state")
    return state if isinstance(state, dict) else None


def _save_predator_prey_tuning_state(settings: Settings, simulation: Simulation) -> Path | None:
    if settings.sim_mode != "predator_prey":
        return None
    path = _predator_prey_tuning_state_path(settings)
    payload = {
        "version": PREDATOR_PREY_TUNING_STATE_VERSION,
        "kind": PREDATOR_PREY_TUNING_STATE_KIND,
        "state": simulation.export_predator_prey_tuning_state(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        logger.warning("Unable to save predator-prey tuning state to %s: %s", path, exc)
        return None
    return path


def _resolve_snapshot_path(
    settings: Settings,
    active_snapshot_path: str | Path | None,
) -> Path:
    """Reuse the active session path when present, otherwise use the default path."""
    if active_snapshot_path is None:
        return _default_snapshot_path(settings)
    return Path(active_snapshot_path)


def _predator_prey_help_path() -> Path:
    """Resolve the bundled predator/prey system guide path."""
    return get_base_path() / "docs" / "predator_prey_system_guide.md"


def _open_predator_prey_help(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> tuple[bool, str]:
    """Open the predator/prey guide in the user's browser, exiting fullscreen first."""
    help_path = _predator_prey_help_path()
    if not help_path.exists():
        return False, f"Help file missing: {help_path.name}"

    if settings.fullscreen or bool(renderer.screen.get_flags() & pygame.FULLSCREEN):
        _force_windowed_mode(settings, simulation, renderer)

    try:
        opened = webbrowser.open_new_tab(help_path.resolve().as_uri())
    except (OSError, webbrowser.Error) as exc:
        logger.warning("Help launch failed for %s: %s", help_path, exc)
        return False, f"Help launch failed: {exc}"

    if not opened:
        logger.warning("Browser reported failure opening help file: %s", help_path)
        return False, f"Help launch failed for {help_path.name}"

    logger.info("Opened predator/prey guide in browser: %s", help_path)
    return True, f"Opened {help_path.name} in browser"


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
        pygame.mouse.set_visible(not settings.fullscreen)
        renderer.resize(simulation.width, simulation.height, screen=screen)
    renderer.set_mode(settings.sim_mode)
    renderer.reset_runtime_state()
    return simulation


def _run_config_dialog() -> None:
    """Show a minimal config/about dialog when launched with /c."""
    pygame.init()

    width, height = 400, 300
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Primordial Screensaver")
    pygame.mouse.set_visible(True)

    settings = Settings()

    settings_path = str(settings.config_path)

    font_title = pygame.font.Font(None, 28)
    font_body = pygame.font.Font(None, 20)
    font_small = pygame.font.Font(None, 17)

    BG = (10, 15, 30)
    TITLE_COLOR = (120, 200, 255)
    TEXT_COLOR = (180, 210, 240)
    DIM_COLOR = (100, 130, 160)
    BTN_COLOR = (40, 80, 140)
    BTN_HOVER = (60, 110, 180)
    BTN_TEXT = (220, 240, 255)

    btn_rect = pygame.Rect(width // 2 - 50, height - 55, 100, 36)

    clock = pygame.time.Clock()
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_rect.collidepoint(mouse_pos):
                    running = False

        screen.fill(BG)

        # Title
        title_surf = font_title.render("Primordial Screensaver", True, TITLE_COLOR)
        screen.blit(title_surf, (width // 2 - title_surf.get_width() // 2, 24))

        # Divider
        pygame.draw.line(screen, (40, 60, 100), (30, 58), (width - 30, 58), 1)

        # Current settings
        lines = [
            ("Sim Mode", settings.sim_mode),
            ("Visual Theme", settings.visual_theme),
            ("Population", str(settings.initial_population)),
            ("Target FPS", str(get_effective_target_fps(settings))),
        ]
        y = 72
        for label, value in lines:
            label_surf = font_body.render(f"{label}:", True, DIM_COLOR)
            value_surf = font_body.render(value, True, TEXT_COLOR)
            screen.blit(label_surf, (40, y))
            screen.blit(value_surf, (180, y))
            y += 26

        # Divider
        pygame.draw.line(screen, (40, 60, 100), (30, y + 4), (width - 30, y + 4), 1)
        y += 14

        # Edit instructions
        edit_surf = font_small.render("Edit config.toml to configure:", True, DIM_COLOR)
        screen.blit(edit_surf, (40, y))
        y += 18
        path_surf = font_small.render(settings_path, True, TEXT_COLOR)
        screen.blit(path_surf, (40, y))

        # OK button
        hover = btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, BTN_HOVER if hover else BTN_COLOR, btn_rect, border_radius=6)
        ok_surf = font_body.render("OK", True, BTN_TEXT)
        screen.blit(ok_surf, (btn_rect.centerx - ok_surf.get_width() // 2,
                               btn_rect.centery - ok_surf.get_height() // 2))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit(0)


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
    elif key == pygame.K_h:
        renderer.toggle_hud()
    elif key == pygame.K_i:
        if inspect_mode is not None:
            was_enabled = inspect_mode.enabled
            inspect_mode.toggle(simulation_paused=simulation.paused)
            if inspect_mode.enabled:
                simulation.paused = True
                pygame.mouse.set_visible(True)
                renderer.show_cursor = True
            else:
                restore_paused = inspect_mode.was_paused_before
                if restore_paused is not None:
                    simulation.paused = restore_paused
                else:
                    simulation.paused = False
                hide_cursor = (
                    settings.fullscreen
                    or bool(screen.get_flags() & pygame.FULLSCREEN)
                    or mode == "screensaver"
                )
                pygame.mouse.set_visible(not hide_cursor)
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
) -> object:
    """Recreate the display and renderer when backend requirements change."""
    display_size, base_flags = _display_mode_size(settings)

    screen = pygame.display.set_mode(
        display_size,
        display_flags_for_settings(settings, base_flags),
    )
    pygame.mouse.set_visible(not settings.fullscreen)
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
    pygame.mouse.set_visible(not settings.fullscreen)
    simulation.resize(width, height)
    renderer.resize(width, height, screen=screen)
    renderer.reset_runtime_state()
    _log_display_mode_coordinate_state(
        settings,
        simulation,
        renderer,
        phase="apply_display_mode",
    )


if __name__ == "__main__":
    main()
