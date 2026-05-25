#!/usr/bin/env python3
"""
Primordial - A cellular evolution screensaver simulation.

Main entry point with game loop, event handling, and controls.
Supports Windows screensaver modes: /s (screensaver), /p HWND (preview), /c (config).
"""

from __future__ import annotations

import logging
import platform
import random
import sys
import time
from pathlib import Path

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

from .display import (
    DEFAULT_WINDOWED_SIZE,
    _get_fullscreen_resolution,
    _log_inspect_click_diagnostics,
    hide_runtime_cursor,
    restore_system_cursor,
    show_interactive_cursor,
    window_to_world,
)
from .input import handle_keydown
from .rendering import create_renderer, display_flags_for_settings
from .persistence.runtime_state import (
    _create_milestone_logger,
    _create_run_logger,
    _load_predator_prey_tuning_state,
    _resolve_snapshot_path,
    _save_predator_prey_tuning_state,
)
from .runtime import (
    LoopTimingCollector,
    advance_fixed_step_frame,
    build_frame_metrics,
    create_fixed_step_loop_state,
    get_effective_target_fps,
    simulation_timing_is_suppressed,
)
from .runtime.profile import _run_profile_session
from .runtime.settings_actions import (
    SettingsActionContext,
    handle_settings_overlay_event,
)
from .settings import Settings
from .config.config import get_config_path
from .simulation import (
    Simulation,
    SnapshotError,
    inspect_snapshot_dimensions,
    load_snapshot,
    save_snapshot,
)
from .tutorial import (
    save_tutorial_user_state,
    should_auto_start_tutorial,
)
from .utils.cli import RuntimeArgs
from .utils.screensaver import ScreensaverArgs


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

    config_existed_before_startup = get_config_path().exists()

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
        hide_runtime_cursor()
    elif scr_args.mode == "preview":
        # SDL_WINDOWID was already set by root main.py; just create a surface
        # that fits into the preview pane (typically ~152×112 px).
        width, height = 152, 112
        screen = pygame.display.set_mode((width, height))
        hide_runtime_cursor()
    else:
        if settings.fullscreen:
            width, height = _get_fullscreen_resolution()
            flags = display_flags_for_settings(settings, pygame.FULLSCREEN | pygame.SCALED)
            screen = pygame.display.set_mode((width, height), flags)
        else:
            if loaded_world_size is not None:
                width, height = loaded_world_size
            else:
                width, height = DEFAULT_WINDOWED_SIZE
            screen = pygame.display.set_mode(
                (width, height),
                display_flags_for_settings(settings),
            )
        hide_runtime_cursor()

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
    renderer.set_runtime_mode(scr_args.mode)
    renderer.resize(simulation.width, simulation.height, screen=screen)
    active_snapshot_path = _resolve_snapshot_path(
        settings,
        runtime_args.load or runtime_args.save,
    )
    renderer.settings_overlay.set_snapshot_path(str(active_snapshot_path))

    if (
        scr_args.mode == "normal"
        and renderer.hud.visible
        and not renderer.inspect_mode.enabled
    ):
        show_interactive_cursor()
        renderer.show_cursor = True

    def _apply_tutorial_pause_policy() -> None:
        if not renderer.tutorial_overlay.visible:
            return
        if renderer.tutorial_overlay.wants_simulation_paused():
            simulation.paused = True
        else:
            simulation.paused = False
        runtime_loop.reset_timing_debt()

    def _open_tutorial(*, forced: bool = False) -> None:
        renderer.close_help_overlay()
        renderer.settings_overlay.close()
        renderer.open_tutorial_overlay(
            forced=forced,
            previous_paused=simulation.paused,
        )
        _apply_tutorial_pause_policy()
        show_interactive_cursor()

    def _finish_tutorial_action(action: str | None) -> None:
        if action not in {"close", "skip", "finish"}:
            return
        save_tutorial_user_state(
            settings,
            completed=action == "finish",
            skipped=action in {"close", "skip"},
        )
        simulation.paused = renderer.tutorial_overlay.state.paused_after_exit()
        runtime_loop.reset_timing_debt()
        if (
            renderer.help_overlay.visible
            or renderer.settings_overlay.visible
            or renderer.inspect_mode.enabled
        ):
            show_interactive_cursor()
        else:
            hide_runtime_cursor()

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

    if (
        scr_args.mode == "normal"
        and (
            runtime_args.tutorial
            or should_auto_start_tutorial(
                settings,
                config_existed_before_startup=config_existed_before_startup,
            )
        )
    ):
        _open_tutorial(forced=runtime_args.tutorial)

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

            elif renderer.tutorial_overlay.visible and event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
            ):
                tutorial_action = renderer.tutorial_overlay.handle_event(event)
                _apply_tutorial_pause_policy()
                _finish_tutorial_action(tutorial_action)
                if tutorial_action not in {"close", "skip", "finish"}:
                    show_interactive_cursor()

            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_p:
                    renderer.set_predator_highlight(False)

            elif renderer.help_overlay.visible and event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
            ):
                renderer.help_overlay.handle_event(event)
                runtime_loop.reset_timing_debt()
                if renderer.help_overlay.fade_dir < 0:
                    if renderer.settings_overlay.visible or renderer.inspect_mode.enabled:
                        show_interactive_cursor()
                    else:
                        hide_runtime_cursor()
                else:
                    show_interactive_cursor()

            elif renderer.settings_overlay.visible and event.type in (
                pygame.KEYDOWN,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
            ):
                action_result = handle_settings_overlay_event(
                    event,
                    SettingsActionContext(
                        settings,
                        simulation,
                        renderer,
                        runtime_loop,
                        active_snapshot_path,
                        _prev_mode,
                        runtime_args.debug,
                        csv_run_logger=csv_run_logger,
                        milestone_logger=milestone_logger,
                    ),
                )
                simulation = action_result.simulation
                renderer = action_result.renderer
                active_snapshot_path = action_result.active_snapshot_path
                _prev_mode = action_result.previous_mode
                if renderer.tutorial_overlay.visible:
                    _apply_tutorial_pause_policy()
                    show_interactive_cursor()
                if action_result.begin_mode_transition:
                    _begin_mode_transition()
                if (
                    renderer.settings_overlay.fade_dir < 0
                    and not renderer.inspect_mode.enabled
                    and not renderer.help_overlay.visible
                    and not renderer.tutorial_overlay.visible
                ):
                    hide_runtime_cursor()
                elif renderer.settings_overlay.visible:
                    show_interactive_cursor()

            elif event.type == pygame.MOUSEMOTION and scr_args.mode == "normal":
                renderer.notify_mouse_motion(event.rel)

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
                elif renderer.hud.visible and scr_args.mode == "normal":
                    world_x, world_y = window_to_world(event.pos[0], event.pos[1], simulation)
                    renderer.hud_focus.select_at_world_pos(world_x, world_y, simulation)

            elif event.type == pygame.KEYDOWN:
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
                    show_interactive_cursor()
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

    restore_system_cursor()
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


if __name__ == "__main__":
    main()
