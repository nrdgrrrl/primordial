#!/usr/bin/env python3
"""
Primordial - A cellular evolution screensaver simulation.

Main entry point with game loop, event handling, and controls.
Supports Windows screensaver modes: /s (screensaver), /p HWND (preview), /c (config).
"""

from __future__ import annotations

import cProfile
import json
import logging
import platform
import pstats
import random
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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

from .rendering import Renderer
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

FIXED_SIM_TIMESTEP_SECONDS = 1.0 / 60.0
MAX_SIM_STEPS_PER_OUTER_FRAME = 5
MAX_ACCUMULATED_SIM_SECONDS = (
    FIXED_SIM_TIMESTEP_SECONDS * MAX_SIM_STEPS_PER_OUTER_FRAME
)
DEFAULT_WINDOWED_SIZE = (1280, 720)
PREDATOR_PREY_TUNING_STATE_VERSION = 1
PREDATOR_PREY_TUNING_STATE_KIND = "primordial.predator_prey_tuning_state"


@dataclass(frozen=True)
class FixedStepLoopConfig:
    """Internal fixed-step timing constants for the outer runtime loop."""

    fixed_timestep_seconds: float = FIXED_SIM_TIMESTEP_SECONDS
    max_sim_steps_per_outer_frame: int = MAX_SIM_STEPS_PER_OUTER_FRAME
    max_accumulated_seconds: float = MAX_ACCUMULATED_SIM_SECONDS
    drop_excess_accumulator: bool = True


@dataclass
class FixedStepLoopState:
    """Shared runtime loop state for interactive and profile execution."""

    config: FixedStepLoopConfig = field(default_factory=FixedStepLoopConfig)
    accumulator_seconds: float = 0.0
    last_tick_seconds: float | None = None
    dropped_seconds_total: float = 0.0
    dropped_frame_count: int = 0
    buffered_active_attacks: list[tuple[float, float, float, float, float]] = field(
        default_factory=list
    )

    def sample_elapsed(
        self,
        now: float | None = None,
        *,
        allow_accumulate: bool = True,
    ) -> float:
        """Advance the monotonic loop clock and optionally accumulate sim debt."""
        if now is None:
            now = time.perf_counter()
        if self.last_tick_seconds is None:
            self.last_tick_seconds = now
            return 0.0

        elapsed = max(0.0, now - self.last_tick_seconds)
        self.last_tick_seconds = now

        if not allow_accumulate:
            self.accumulator_seconds = 0.0
            return elapsed

        self.accumulator_seconds += elapsed
        self._clamp_accumulator()
        return elapsed

    def reset_timing_debt(self, now: float | None = None) -> None:
        """Discard accumulated sim debt and resync the loop clock."""
        self.accumulator_seconds = 0.0
        self.last_tick_seconds = time.perf_counter() if now is None else now

    def planned_sim_steps(self) -> int:
        """Expose the future fixed-step budget without executing it yet."""
        pending_steps = int(
            self.accumulator_seconds / self.config.fixed_timestep_seconds
        )
        return min(pending_steps, self.config.max_sim_steps_per_outer_frame)

    def buffer_simulation_attacks(self, simulation: Simulation) -> None:
        """Preserve current-step attack visuals behind the loop scaffold seam."""
        self.buffered_active_attacks.extend(simulation.drain_active_attacks())

    def restore_buffered_attacks(self, simulation: Simulation) -> None:
        """Restore preserved attack visuals immediately before rendering."""
        if not self.buffered_active_attacks:
            return
        simulation.restore_active_attacks(self.buffered_active_attacks)
        self.buffered_active_attacks.clear()

    def _clamp_accumulator(self) -> None:
        if not self.config.drop_excess_accumulator:
            return
        overflow = self.accumulator_seconds - self.config.max_accumulated_seconds
        if overflow <= 0.0:
            return
        self.accumulator_seconds = self.config.max_accumulated_seconds
        self.dropped_seconds_total += overflow
        self.dropped_frame_count += 1


def _create_fixed_step_loop_state() -> FixedStepLoopState:
    """Build the shared loop scaffold used by runtime and profile paths."""
    return FixedStepLoopState()


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


@dataclass(frozen=True)
class LoopFrameMetrics:
    """Stable outer-loop timing payload for debug and summary consumers."""

    event_ms: float
    sim_ms: float
    render_ms: float
    present_ms: float
    pacing_ms: float
    frame_ms: float
    effective_fps: float
    sim_steps: int
    clamp_frames: int
    dropped_seconds: float
    accumulator_seconds: float

    def to_debug_payload(self) -> dict[str, float]:
        """Convert the frame metrics into HUD-friendly scalar values."""
        return {
            "event_ms": self.event_ms,
            "sim_ms": self.sim_ms,
            "render_ms": self.render_ms,
            "present_ms": self.present_ms,
            "pacing_ms": self.pacing_ms,
            "frame_ms": self.frame_ms,
            "effective_fps": self.effective_fps,
            "sim_steps": float(self.sim_steps),
            "clamp_frames": float(self.clamp_frames),
            "dropped_ms": self.dropped_seconds * 1000.0,
            "accumulator_ms": self.accumulator_seconds * 1000.0,
        }


class LoopTimingCollector:
    """Aggregate per-frame loop metrics for debug display and profile summaries."""

    def __init__(self, *, retain_samples: bool) -> None:
        self.retain_samples = retain_samples
        self.frame_count = 0
        self.total_sim_steps = 0
        self.total_clamp_frames = 0
        self.total_dropped_seconds = 0.0
        self.latest_frame: LoopFrameMetrics | None = None
        self._samples: dict[str, list[float]] = {
            "event_ms": [],
            "sim_ms": [],
            "render_ms": [],
            "present_ms": [],
            "pacing_ms": [],
            "frame_ms": [],
            "effective_fps": [],
            "sim_steps": [],
        }

    def record_frame(self, frame: LoopFrameMetrics) -> None:
        """Record a completed outer-frame timing sample."""
        self.latest_frame = frame
        self.frame_count += 1
        self.total_sim_steps += frame.sim_steps
        self.total_clamp_frames += frame.clamp_frames
        self.total_dropped_seconds += frame.dropped_seconds
        if not self.retain_samples:
            return
        self._samples["event_ms"].append(frame.event_ms)
        self._samples["sim_ms"].append(frame.sim_ms)
        self._samples["render_ms"].append(frame.render_ms)
        self._samples["present_ms"].append(frame.present_ms)
        self._samples["pacing_ms"].append(frame.pacing_ms)
        self._samples["frame_ms"].append(frame.frame_ms)
        self._samples["effective_fps"].append(frame.effective_fps)
        self._samples["sim_steps"].append(float(frame.sim_steps))

    def latest_debug_payload(self) -> dict[str, float]:
        """Return the most recent complete frame payload for debug display."""
        if self.latest_frame is None:
            return {}
        return self.latest_frame.to_debug_payload()

    def build_summary(
        self,
        *,
        elapsed_wall_seconds: float,
        runtime_loop: FixedStepLoopState,
    ) -> dict[str, Any]:
        """Build a machine-readable timing summary."""
        return {
            "elapsed_wall_seconds": elapsed_wall_seconds,
            "frames_rendered": self.frame_count,
            "effective_fps_overall": (
                self.frame_count / elapsed_wall_seconds if elapsed_wall_seconds > 0 else 0.0
            ),
            "sim_steps_total": self.total_sim_steps,
            "sim_steps_per_render_frame": self._summarize_samples("sim_steps"),
            "timing_ms": {
                "event": self._summarize_samples("event_ms"),
                "sim": self._summarize_samples("sim_ms"),
                "render": self._summarize_samples("render_ms"),
                "present": self._summarize_samples("present_ms"),
                "pacing": self._summarize_samples("pacing_ms"),
                "frame": self._summarize_samples("frame_ms"),
            },
            "effective_fps": self._summarize_samples("effective_fps"),
            "clamp_drop": {
                "frame_count": self.total_clamp_frames,
                "dropped_ms_total": self.total_dropped_seconds * 1000.0,
                "final_accumulator_ms": runtime_loop.accumulator_seconds * 1000.0,
            },
            "runtime_loop": {
                "fixed_timestep_ms": runtime_loop.config.fixed_timestep_seconds * 1000.0,
                "max_sim_steps_per_outer_frame": runtime_loop.config.max_sim_steps_per_outer_frame,
                "max_accumulated_ms": runtime_loop.config.max_accumulated_seconds * 1000.0,
                "drop_excess_accumulator": runtime_loop.config.drop_excess_accumulator,
            },
        }

    def _summarize_samples(self, name: str) -> dict[str, float | int]:
        samples = self._samples[name]
        if not samples:
            return {
                "count": 0,
                "min": 0.0,
                "mean": 0.0,
                "p95": 0.0,
                "max": 0.0,
            }
        ordered = sorted(samples)
        index = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        return {
            "count": len(ordered),
            "min": ordered[0],
            "mean": sum(ordered) / len(ordered),
            "p95": ordered[index],
            "max": ordered[-1],
        }


def _simulation_timing_is_suppressed(
    simulation: Simulation,
    transition_dir: int = 0,
    transition_alpha: int = 0,
) -> bool:
    """Return whether fixed-step debt should be frozen for the current frame."""
    return (
        simulation.paused
        or simulation.predator_prey_game_over_active
        or transition_dir != 0
    )


def _run_planned_simulation_steps(
    simulation: Simulation,
    runtime_loop: FixedStepLoopState,
    *,
    allow_step: bool,
) -> tuple[float, int]:
    """Execute the currently budgeted fixed-step simulation work for one frame."""
    if not allow_step:
        return 0.0, 0

    sim_steps = runtime_loop.planned_sim_steps()
    if sim_steps <= 0:
        return 0.0, 0

    sim_start = time.perf_counter()
    for _ in range(sim_steps):
        simulation.step()
        runtime_loop.buffer_simulation_attacks(simulation)
    runtime_loop.accumulator_seconds = max(
        0.0,
        runtime_loop.accumulator_seconds
        - (sim_steps * runtime_loop.config.fixed_timestep_seconds),
    )
    return (time.perf_counter() - sim_start) * 1000.0, sim_steps


def _advance_fixed_step_frame(
    simulation: Simulation,
    runtime_loop: FixedStepLoopState,
    *,
    allow_simulation: bool,
    now: float | None = None,
) -> tuple[float, int, int, float]:
    """Sample elapsed time, execute planned fixed steps, and report clamp deltas."""
    dropped_frame_count_before = runtime_loop.dropped_frame_count
    dropped_seconds_before = runtime_loop.dropped_seconds_total
    runtime_loop.sample_elapsed(now=now, allow_accumulate=allow_simulation)
    sim_ms, sim_steps = _run_planned_simulation_steps(
        simulation,
        runtime_loop,
        allow_step=allow_simulation,
    )
    clamp_frames = runtime_loop.dropped_frame_count - dropped_frame_count_before
    dropped_seconds = runtime_loop.dropped_seconds_total - dropped_seconds_before
    return sim_ms, sim_steps, clamp_frames, dropped_seconds


def _build_frame_metrics(
    *,
    event_ms: float,
    sim_ms: float,
    render_ms: float,
    present_ms: float,
    pacing_ms: float,
    frame_start: float,
    frame_end: float,
    sim_steps: int,
    clamp_frames: int,
    dropped_seconds: float,
    accumulator_seconds: float,
) -> LoopFrameMetrics:
    """Create the stable frame metrics payload for one outer-loop iteration."""
    frame_ms = max(0.0, (frame_end - frame_start) * 1000.0)
    effective_fps = 1000.0 / frame_ms if frame_ms > 0.0 else 0.0
    return LoopFrameMetrics(
        event_ms=event_ms,
        sim_ms=sim_ms,
        render_ms=render_ms,
        present_ms=present_ms,
        pacing_ms=pacing_ms,
        frame_ms=frame_ms,
        effective_fps=effective_fps,
        sim_steps=sim_steps,
        clamp_frames=clamp_frames,
        dropped_seconds=dropped_seconds,
        accumulator_seconds=accumulator_seconds,
    )


def run_bounded_session(
    simulation: Simulation,
    renderer: Renderer,
    clock: pygame.time.Clock,
    runtime_loop: FixedStepLoopState,
    timing_collector: LoopTimingCollector,
    *,
    duration_seconds: float,
    target_fps: int,
    frame_observer: Callable[[Simulation], None] | None = None,
    pump_events: bool = True,
) -> float:
    """Run a bounded render/sim session and return elapsed wall time."""
    start_time = time.perf_counter()
    end_time = start_time + duration_seconds

    while time.perf_counter() < end_time:
        frame_start = time.perf_counter()
        event_start = time.perf_counter()
        events = pygame.event.get() if pump_events else []
        quit_requested = False
        for event in events:
            if event.type == pygame.QUIT:
                quit_requested = True
                break
        event_ms = (time.perf_counter() - event_start) * 1000.0

        sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=True,
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
        present_start = time.perf_counter()
        pygame.display.flip()
        present_ms = (time.perf_counter() - present_start) * 1000.0
        pacing_start = time.perf_counter()
        clock.tick(max(1, target_fps))
        pacing_ms = (time.perf_counter() - pacing_start) * 1000.0
        frame_end = time.perf_counter()
        timing_collector.record_frame(
            _build_frame_metrics(
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
        if frame_observer is not None:
            frame_observer(simulation)
        if quit_requested:
            break

    return max(0.0, time.perf_counter() - start_time)


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
        "Starting Primordial mode=%s debug=%s profile=%s log=%s",
        scr_args.mode,
        runtime_args.debug,
        runtime_args.profile,
        log_path,
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

    # Set up display based on mode
    if scr_args.mode == "screensaver":
        width, height = _get_fullscreen_resolution()
        screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
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
            screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
        else:
            if loaded_world_size is not None:
                width, height = loaded_world_size
            else:
                width = 1280
                height = 720
            screen = pygame.display.set_mode((width, height))
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
    renderer = Renderer(screen, settings, debug=runtime_args.debug)
    active_snapshot_path = _resolve_snapshot_path(
        settings,
        runtime_args.load or runtime_args.save,
    )
    renderer.settings_overlay.set_snapshot_path(str(active_snapshot_path))

    # Clock for FPS limiting
    clock = pygame.time.Clock()
    runtime_loop = _create_fixed_step_loop_state()
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

            elif event.type == pygame.KEYDOWN:
                if renderer.settings_overlay.visible:
                    action = renderer.settings_overlay.handle_event(event)
                    if action == "apply":
                        if settings.fullscreen != bool(renderer.screen.get_flags() & pygame.FULLSCREEN):
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

        sim_suppressed = _simulation_timing_is_suppressed(
            simulation,
            _transition_dir,
            _transition_alpha,
        )
        sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=not sim_suppressed,
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

        target_fps = settings.target_fps // 2 if scr_args.mode == "preview" else settings.target_fps
        pacing_start = time.perf_counter()
        clock.tick(target_fps)
        pacing_ms = (time.perf_counter() - pacing_start) * 1000.0
        frame_end = time.perf_counter()

        timing_collector.record_frame(
            _build_frame_metrics(
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
        flags = pygame.FULLSCREEN | pygame.SCALED if settings.fullscreen else 0
        screen = pygame.display.set_mode((simulation.width, simulation.height), flags)
        pygame.mouse.set_visible(not settings.fullscreen)
        renderer.resize(simulation.width, simulation.height, screen=screen)
    renderer.set_mode(settings.sim_mode)
    renderer.reset_runtime_state()
    return simulation


def _run_profile_session(
    simulation: Simulation,
    renderer: Renderer,
    clock: pygame.time.Clock,
    settings: Settings,
    runtime_loop: FixedStepLoopState,
    timing_collector: LoopTimingCollector,
) -> str:
    """
    Run a 60-second profile session, dump .pstats and text report, then return base path.
    """
    out_dir = Path(settings.config_path).parent
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base_name = f"profile-{stamp}"

    profiler = cProfile.Profile()
    logger.info("Running 60-second profile session...")
    profiler.enable()
    elapsed_wall_seconds = run_bounded_session(
        simulation,
        renderer,
        clock,
        runtime_loop,
        timing_collector,
        duration_seconds=60.0,
        target_fps=settings.target_fps,
    )
    profiler.disable()

    for candidate_dir in (out_dir, Path.cwd()):
        try:
            candidate_dir.mkdir(parents=True, exist_ok=True)
            base = candidate_dir / base_name
            pstats_path = base.with_suffix(".pstats")
            text_path = base.with_suffix(".txt")
            timing_path = base.with_suffix(".timing.json")
            profiler.dump_stats(str(pstats_path))
            with text_path.open("w", encoding="utf-8") as fp:
                stats = pstats.Stats(profiler, stream=fp).sort_stats("cumulative")
                stats.print_stats(120)
            with timing_path.open("w", encoding="utf-8") as fp:
                json.dump(
                    timing_collector.build_summary(
                        elapsed_wall_seconds=elapsed_wall_seconds,
                        runtime_loop=runtime_loop,
                    ),
                    fp,
                    indent=2,
                    sort_keys=True,
                )
            if candidate_dir != out_dir:
                logger.warning("Profile output fallback path in use: %s", candidate_dir)
            return str(base)
        except OSError as exc:
            logger.warning("Profile write failed at %s: %s", candidate_dir, exc)

    raise RuntimeError("Unable to write profile output to any candidate directory.")


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
            ("Target FPS", str(settings.target_fps)),
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


def _apply_display_mode(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """Apply the current display mode without mutating simulation world state."""
    if settings.fullscreen:
        width, height = _get_fullscreen_resolution()
        flags = pygame.FULLSCREEN | pygame.SCALED
    else:
        width, height = DEFAULT_WINDOWED_SIZE
        flags = 0

    screen = pygame.display.set_mode((width, height), flags)
    pygame.mouse.set_visible(not settings.fullscreen)
    renderer.resize(simulation.width, simulation.height, screen=screen)


if __name__ == "__main__":
    main()
