"""Real graphical benchmark harness for Primordial."""

from __future__ import annotations

import cProfile
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import gzip
import json
import logging
import math
import os
from pathlib import Path
import platform
import pstats
import random
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any
import zipfile

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from .graphics_probe import _build_edge_counts, _hash_zone_state
from .main import (
    DEFAULT_WINDOWED_SIZE,
    LoopTimingCollector,
    _advance_fixed_step_frame,
    _apply_display_mode,
    _build_frame_metrics,
    _create_fixed_step_loop_state,
    _get_fullscreen_resolution,
    _simulation_timing_is_suppressed,
)
from .rendering import Renderer
from .settings import Settings
from .simulation import Simulation

logger = logging.getLogger(__name__)

FULLSCREEN_FLAGS = pygame.FULLSCREEN | pygame.SCALED
REPRESENTATIVE_SCREENSHOT_LIMIT = 18
PROFILE_SECONDS = 60.0
TRANSITION_SETTLE_SECONDS = 1.0
TRANSITION_ANALYSIS_WINDOW_SECONDS = 5.0
ALL_MODE_SEEDS = (
    104729,
    130363,
    161803,
    271828,
    314159,
    524287,
)
PREDATOR_PREY_EXTRA_SEEDS = (
    6700417,
    1000003,
    15485863,
    179424673,
)


@dataclass(frozen=True)
class ToggleAction:
    at_seconds: float
    fullscreen: bool
    label: str


@dataclass(frozen=True)
class RunSpec:
    scenario: str
    mode: str
    seed: int
    duration_seconds: float
    fullscreen: bool
    screenshot_times: tuple[float, ...]
    toggles: tuple[ToggleAction, ...] = ()
    notes: str = ""

    @property
    def run_id(self) -> str:
        return f"{self.scenario}__{self.mode}__seed{self.seed}"


@dataclass
class DisplayContext:
    display_path: str
    visible_display: bool
    driver: str
    desktop_resolution: tuple[int, int]
    desktop_sizes: list[list[int]]
    display_env: str | None
    wayland_display: str | None
    session_type: str | None


@dataclass
class SuitePaths:
    root: Path
    per_run: Path
    frame_samples: Path
    screenshots: Path
    profiles: Path
    logs: Path
    analysis_bundle: Path


class FrameSampleWriter:
    """Stream raw frame samples to a compressed CSV file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = gzip.open(self.path, "wt", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(
            self._fp,
            fieldnames=[
                "frame_index",
                "elapsed_wall_seconds",
                "event_ms",
                "sim_ms",
                "render_ms",
                "present_ms",
                "pacing_ms",
                "frame_ms",
                "effective_fps",
                "sim_steps",
                "clamp_frames",
                "dropped_ms",
                "accumulator_ms",
                "population",
                "food_count",
                "predator_count",
                "prey_count",
                "sim_ticks",
                "current_seed",
                "game_over_active",
                "display_width",
                "display_height",
                "logical_width",
                "logical_height",
                "fullscreen",
            ],
        )
        self._writer.writeheader()

    def write(self, row: dict[str, Any]) -> None:
        self._writer.writerow(row)

    def close(self) -> None:
        self._fp.close()


def run_graphical_benchmark_suite(
    *,
    output_root: Path,
    command: str,
    collect_profiles: bool = True,
) -> dict[str, Any]:
    """Run the full graphical benchmark matrix and write packaged results."""
    suite_paths = _create_suite_paths(output_root)
    _configure_file_logging(suite_paths.logs / "benchmark_runner.log")
    display_context = collect_display_context()
    environment_info = _collect_environment_info(display_context)
    environment_path = suite_paths.root / "ENVIRONMENT.md"
    environment_path.write_text(environment_info, encoding="utf-8")

    run_specs = _build_default_run_specs()
    logger.info("Starting graphical benchmark suite with %d runs", len(run_specs))

    run_results: list[dict[str, Any]] = []
    for index, spec in enumerate(run_specs, start=1):
        logger.info(
            "Run %d/%d: %s mode=%s seed=%d duration=%.1fs",
            index,
            len(run_specs),
            spec.scenario,
            spec.mode,
            spec.seed,
            spec.duration_seconds,
        )
        run_results.append(
            _run_single_graphical_benchmark(
                spec,
                suite_paths,
                display_context,
            )
        )

    profile_results: list[dict[str, Any]] = []
    if collect_profiles:
        for mode, seed in _build_profile_specs():
            logger.info("Profile run: mode=%s seed=%d duration=%.1fs", mode, seed, PROFILE_SECONDS)
            profile_results.append(
                _run_profile_capture(
                    mode=mode,
                    seed=seed,
                    duration_seconds=PROFILE_SECONDS,
                    output_dir=suite_paths.profiles,
                    display_context=display_context,
                )
            )

    runs_csv_path = suite_paths.root / "runs.csv"
    _write_runs_csv(runs_csv_path, run_results)

    transition_findings = _build_transition_findings(run_results)
    transition_findings_path = suite_paths.root / "transition_findings.md"
    transition_findings_path.write_text(transition_findings, encoding="utf-8")

    aggregate_results = _build_aggregate_results(
        run_results=run_results,
        profile_results=profile_results,
        display_context=display_context,
        command=command,
        root=suite_paths.root,
    )
    aggregate_path = suite_paths.root / "aggregate_results.json"
    aggregate_path.write_text(
        json.dumps(aggregate_results, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    results_path = suite_paths.root / "results.json"
    shutil.copy2(aggregate_path, results_path)

    summary_text = _build_summary_markdown(
        aggregate_results=aggregate_results,
        run_results=run_results,
        profile_results=profile_results,
        display_context=display_context,
        command=command,
    )
    summary_path = suite_paths.root / "SUMMARY.md"
    summary_path.write_text(summary_text, encoding="utf-8")

    _populate_analysis_bundle(
        suite_paths=suite_paths,
        summary_path=summary_path,
        aggregate_path=aggregate_path,
        runs_csv_path=runs_csv_path,
        transition_findings_path=transition_findings_path,
        environment_path=environment_path,
        run_results=run_results,
    )

    analysis_zip_path = suite_paths.root / "analysis_bundle.zip"
    _zip_directory(suite_paths.analysis_bundle, analysis_zip_path)
    full_archive_path = suite_paths.root / "full_benchmark_archive.zip"
    _zip_directory(
        suite_paths.root,
        full_archive_path,
        exclude_names={full_archive_path.name},
    )

    aggregate_results["artifacts"] = {
        "summary": str(summary_path),
        "aggregate_results": str(aggregate_path),
        "results": str(results_path),
        "runs_csv": str(runs_csv_path),
        "transition_findings": str(transition_findings_path),
        "environment": str(environment_path),
        "analysis_bundle_dir": str(suite_paths.analysis_bundle),
        "analysis_bundle_zip": str(analysis_zip_path),
        "full_benchmark_archive_zip": str(full_archive_path),
    }
    aggregate_path.write_text(
        json.dumps(aggregate_results, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    shutil.copy2(aggregate_path, results_path)
    return aggregate_results


def collect_display_context() -> DisplayContext:
    """Inspect the active graphical backend without forcing a dummy path."""
    pygame.init()
    try:
        pygame.display.init()
        driver = pygame.display.get_driver()
        desktop_sizes_raw = getattr(pygame.display, "get_desktop_sizes", lambda: [])()
        desktop_sizes = [list(size) for size in desktop_sizes_raw]
        desktop_resolution = (
            tuple(desktop_sizes_raw[0]) if desktop_sizes_raw else _get_fullscreen_resolution()
        )
    finally:
        pygame.quit()

    display_env = os.environ.get("DISPLAY")
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    session_type = os.environ.get("XDG_SESSION_TYPE")
    visible_display = bool(display_env)
    display_path = "live_display" if visible_display else "virtual_graphical"
    return DisplayContext(
        display_path=display_path,
        visible_display=visible_display,
        driver=driver,
        desktop_resolution=(int(desktop_resolution[0]), int(desktop_resolution[1])),
        desktop_sizes=desktop_sizes,
        display_env=display_env,
        wayland_display=wayland_display,
        session_type=session_type,
    )


def _collect_environment_info(display_context: DisplayContext) -> str:
    git_head = _run_command_capture(["git", "rev-parse", "HEAD"])
    git_status = _run_command_capture(["git", "status", "--short"])
    xrandr_current = _run_command_capture(["xrandr", "--current"])
    lines = [
        "# Environment",
        "",
        f"- Timestamp (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"- OS: {platform.platform()}",
        f"- Python: {sys.version.split()[0]}",
        f"- pygame: {pygame.version.ver}",
        f"- SDL display driver: {display_context.driver}",
        f"- Display path used: {display_context.display_path}",
        f"- Visible display: {'yes' if display_context.visible_display else 'no'}",
        f"- DISPLAY: {display_context.display_env or '(unset)'}",
        f"- WAYLAND_DISPLAY: {display_context.wayland_display or '(unset)'}",
        f"- XDG_SESSION_TYPE: {display_context.session_type or '(unset)'}",
        (
            "- Desktop/native resolution: "
            f"{display_context.desktop_resolution[0]}x{display_context.desktop_resolution[1]}"
        ),
        f"- Desktop sizes reported by pygame: {display_context.desktop_sizes}",
        f"- Git HEAD: {git_head or '(unavailable)'}",
        "",
        "## Git Status",
        "",
        "```text",
        git_status or "(clean or unavailable)",
        "```",
        "",
        "## xrandr --current",
        "",
        "```text",
        xrandr_current or "(unavailable)",
        "```",
        "",
    ]
    return "\n".join(lines)


def _build_default_run_specs() -> list[RunSpec]:
    run_specs: list[RunSpec] = []
    native_start = 1.0
    for mode in ("energy", "predator_prey", "boids", "drift"):
        for seed in ALL_MODE_SEEDS:
            run_specs.append(
                RunSpec(
                    scenario="baseline_fullscreen",
                    mode=mode,
                    seed=seed,
                    duration_seconds=90.0,
                    fullscreen=True,
                    screenshot_times=(native_start, 45.0, 89.0),
                )
            )

    predator_seeds = ALL_MODE_SEEDS + PREDATOR_PREY_EXTRA_SEEDS
    for seed in predator_seeds:
        run_specs.append(
            RunSpec(
                scenario="predator_prey_extended_fullscreen",
                mode="predator_prey",
                seed=seed,
                duration_seconds=180.0,
                fullscreen=True,
                screenshot_times=(native_start, 90.0, 179.0),
            )
        )

    toggles = (
        ToggleAction(60.0, False, "fullscreen_to_windowed"),
        ToggleAction(120.0, True, "windowed_to_fullscreen"),
    )
    for seed in ALL_MODE_SEEDS:
        run_specs.append(
            RunSpec(
                scenario="predator_prey_transition",
                mode="predator_prey",
                seed=seed,
                duration_seconds=180.0,
                fullscreen=True,
                screenshot_times=(native_start, 30.0, 90.0, 150.0, 179.0),
                toggles=toggles,
                notes="Start fullscreen, toggle to windowed at 60s, restore fullscreen at 120s.",
            )
        )

    for seed in ALL_MODE_SEEDS[:2]:
        run_specs.append(
            RunSpec(
                scenario="predator_prey_soak",
                mode="predator_prey",
                seed=seed,
                duration_seconds=600.0,
                fullscreen=True,
                screenshot_times=(native_start, 300.0, 599.0),
            )
        )
    return run_specs


def _build_profile_specs() -> list[tuple[str, int]]:
    return [
        ("energy", ALL_MODE_SEEDS[0]),
        ("predator_prey", ALL_MODE_SEEDS[0]),
        ("boids", ALL_MODE_SEEDS[0]),
        ("drift", ALL_MODE_SEEDS[0]),
    ]


def _create_suite_paths(root: Path) -> SuitePaths:
    per_run = root / "per_run"
    frame_samples = root / "frame_samples"
    screenshots = root / "screenshots"
    profiles = root / "profiles"
    logs = root / "logs"
    analysis_bundle = root / "analysis_bundle"
    for path in (root, per_run, frame_samples, screenshots, profiles, logs, analysis_bundle):
        path.mkdir(parents=True, exist_ok=True)
    return SuitePaths(
        root=root,
        per_run=per_run,
        frame_samples=frame_samples,
        screenshots=screenshots,
        profiles=profiles,
        logs=logs,
        analysis_bundle=analysis_bundle,
    )


def _configure_file_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def _run_single_graphical_benchmark(
    spec: RunSpec,
    suite_paths: SuitePaths,
    display_context: DisplayContext,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    run_seed = int(spec.seed)
    frame_writer = FrameSampleWriter(suite_paths.frame_samples / f"{spec.run_id}.frames.csv.gz")
    screenshot_dir = suite_paths.screenshots / spec.mode / spec.run_id
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    per_run_path = suite_paths.per_run / f"{spec.run_id}.json"

    random.seed(run_seed)
    pygame.init()
    resize_calls: dict[str, list[dict[str, Any]]] = {"renderer": [], "simulation": []}
    checkpoints: list[dict[str, Any]] = []
    observability_samples: list[dict[str, Any]] = []
    render_breakdown_sums: dict[str, float] = {}
    render_breakdown_counts: dict[str, int] = {}
    population_samples: list[int] = []
    food_samples: list[int] = []
    predator_samples: list[int] = []
    prey_samples: list[int] = []
    restart_seed_changes = 0
    previous_current_seed: int | None = None
    toggles_completed = 0
    completed_screenshots: set[str] = set()
    pending_toggle_actions = list(spec.toggles)
    pending_after_toggle: list[dict[str, Any]] = []
    last_observability_sample_seconds = -1.0

    try:
        settings = Settings()
        settings.sim_mode = spec.mode
        settings.fullscreen = spec.fullscreen
        settings.show_hud = False

        world_width, world_height, screen = _create_display_for_run(settings)
        pygame.display.set_caption(f"Primordial Benchmark: {spec.run_id}")
        pygame.mouse.set_visible(not settings.fullscreen)

        if spec.mode == "predator_prey":
            simulation = Simulation(world_width, world_height, settings, seed=run_seed)
            simulation.reset_predator_prey_adaptive_tuning()
            simulation.set_predator_prey_adaptive_tuning_enabled(False)
        else:
            simulation = Simulation(world_width, world_height, settings)
        renderer = Renderer(screen, settings, debug=False)
        clock = pygame.time.Clock()
        runtime_loop = _create_fixed_step_loop_state()
        timing_collector = LoopTimingCollector(retain_samples=True)

        original_renderer_resize = renderer.resize
        original_simulation_resize = simulation.resize

        def _logged_renderer_resize(
            width: int,
            height: int,
            screen: pygame.Surface | None = None,
        ) -> None:
            resize_calls["renderer"].append(
                {
                    "logical_size_requested": [width, height],
                    "incoming_display_size": list(screen.get_size()) if screen is not None else None,
                }
            )
            original_renderer_resize(width, height, screen=screen)

        def _logged_simulation_resize(width: int, height: int) -> None:
            resize_calls["simulation"].append({"size_requested": [width, height]})
            original_simulation_resize(width, height)

        renderer.resize = _logged_renderer_resize  # type: ignore[method-assign]
        simulation.resize = _logged_simulation_resize  # type: ignore[method-assign]

        start_time = time.perf_counter()
        next_screenshot_times = list(spec.screenshot_times)
        frame_index = 0
        quit_requested = False

        while True:
            elapsed_wall_seconds = time.perf_counter() - start_time
            if elapsed_wall_seconds >= spec.duration_seconds or quit_requested:
                break

            frame_start = time.perf_counter()
            event_start = time.perf_counter()
            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    quit_requested = True
                    break
            event_ms = (time.perf_counter() - event_start) * 1000.0

            if simulation.update_predator_prey_runtime(now_seconds=time.monotonic()):
                renderer.reset_runtime_state()
                runtime_loop.reset_timing_debt()

            sim_suppressed = _simulation_timing_is_suppressed(simulation)
            sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
                simulation,
                runtime_loop,
                allow_simulation=not sim_suppressed,
            )

            debug_payload = timing_collector.latest_debug_payload()
            debug_payload.update(
                {
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
                }
            )
            renderer.set_external_debug_metrics(debug_payload)
            runtime_loop.restore_buffered_attacks(simulation)
            render_metrics = renderer.draw(simulation)
            present_start = time.perf_counter()
            pygame.display.flip()
            present_ms = (time.perf_counter() - present_start) * 1000.0
            pacing_start = time.perf_counter()
            clock.tick(max(1, settings.target_fps))
            pacing_ms = (time.perf_counter() - pacing_start) * 1000.0
            frame_end = time.perf_counter()

            frame_metrics = _build_frame_metrics(
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
            timing_collector.record_frame(frame_metrics)
            frame_index += 1
            elapsed_wall_seconds = frame_end - start_time

            for key, value in render_metrics.items():
                if not key.endswith("_ms"):
                    continue
                render_breakdown_sums[key] = render_breakdown_sums.get(key, 0.0) + float(value)
                render_breakdown_counts[key] = render_breakdown_counts.get(key, 0) + 1

            predator_count, prey_count = (0, 0)
            sim_ticks = timing_collector.total_sim_steps
            current_seed: int | None = None
            game_over_active = False
            if spec.mode == "predator_prey":
                predator_count, prey_count = simulation.get_species_counts()
                stability_stats = simulation.get_predator_prey_stability_stats()
                sim_ticks = int(stability_stats["sim_ticks"])
                current_seed = (
                    int(stability_stats["current_seed"])
                    if stability_stats["current_seed"] is not None
                    else None
                )
                game_over_active = bool(stability_stats["game_over_active"])
                if previous_current_seed is not None and current_seed is not None and current_seed != previous_current_seed:
                    restart_seed_changes += 1
                if current_seed is not None:
                    previous_current_seed = current_seed

            population_samples.append(simulation.population)
            food_samples.append(simulation.food_count)
            if spec.mode == "predator_prey":
                predator_samples.append(predator_count)
                prey_samples.append(prey_count)

            frame_writer.write(
                {
                    "frame_index": frame_index,
                    "elapsed_wall_seconds": f"{elapsed_wall_seconds:.6f}",
                    "event_ms": f"{frame_metrics.event_ms:.6f}",
                    "sim_ms": f"{frame_metrics.sim_ms:.6f}",
                    "render_ms": f"{frame_metrics.render_ms:.6f}",
                    "present_ms": f"{frame_metrics.present_ms:.6f}",
                    "pacing_ms": f"{frame_metrics.pacing_ms:.6f}",
                    "frame_ms": f"{frame_metrics.frame_ms:.6f}",
                    "effective_fps": f"{frame_metrics.effective_fps:.6f}",
                    "sim_steps": frame_metrics.sim_steps,
                    "clamp_frames": frame_metrics.clamp_frames,
                    "dropped_ms": f"{frame_metrics.dropped_seconds * 1000.0:.6f}",
                    "accumulator_ms": f"{frame_metrics.accumulator_seconds * 1000.0:.6f}",
                    "population": simulation.population,
                    "food_count": simulation.food_count,
                    "predator_count": predator_count,
                    "prey_count": prey_count,
                    "sim_ticks": sim_ticks,
                    "current_seed": current_seed if current_seed is not None else "",
                    "game_over_active": int(game_over_active),
                    "display_width": renderer.display_width,
                    "display_height": renderer.display_height,
                    "logical_width": renderer.width,
                    "logical_height": renderer.height,
                    "fullscreen": int(bool(renderer.screen.get_flags() & pygame.FULLSCREEN)),
                }
            )

            if elapsed_wall_seconds - last_observability_sample_seconds >= 1.0:
                sample = simulation.build_observability_snapshot()
                sample["elapsed_wall_seconds"] = round(elapsed_wall_seconds, 3)
                sample["food_count"] = simulation.food_count
                if spec.mode == "predator_prey":
                    sample["stability"] = simulation.get_predator_prey_stability_stats()
                observability_samples.append(sample)
                last_observability_sample_seconds = elapsed_wall_seconds

            while next_screenshot_times and elapsed_wall_seconds >= next_screenshot_times[0]:
                target_seconds = next_screenshot_times.pop(0)
                label = f"t{int(target_seconds):04d}s"
                if label not in completed_screenshots:
                    checkpoints.append(
                        _capture_checkpoint(
                            label=label,
                            output_dir=screenshot_dir,
                            simulation=simulation,
                            renderer=renderer,
                            elapsed_wall_seconds=elapsed_wall_seconds,
                            frame_index=frame_index,
                        )
                    )
                    completed_screenshots.add(label)

            while pending_toggle_actions and elapsed_wall_seconds >= pending_toggle_actions[0].at_seconds:
                action = pending_toggle_actions.pop(0)
                pre_label = f"pre_{action.label}"
                checkpoints.append(
                    _capture_checkpoint(
                        label=pre_label,
                        output_dir=screenshot_dir,
                        simulation=simulation,
                        renderer=renderer,
                        elapsed_wall_seconds=elapsed_wall_seconds,
                        frame_index=frame_index,
                    )
                )
                settings.fullscreen = action.fullscreen
                _apply_display_mode(settings, simulation, renderer)
                runtime_loop.reset_timing_debt()
                toggles_completed += 1
                pending_after_toggle.append(
                    {
                        "capture_after_seconds": elapsed_wall_seconds + TRANSITION_SETTLE_SECONDS,
                        "label": f"post_{action.label}",
                    }
                )

            ready_after_toggle = [
                item for item in pending_after_toggle if elapsed_wall_seconds >= item["capture_after_seconds"]
            ]
            pending_after_toggle = [
                item for item in pending_after_toggle if elapsed_wall_seconds < item["capture_after_seconds"]
            ]
            for item in ready_after_toggle:
                checkpoints.append(
                    _capture_checkpoint(
                        label=str(item["label"]),
                        output_dir=screenshot_dir,
                        simulation=simulation,
                        renderer=renderer,
                        elapsed_wall_seconds=elapsed_wall_seconds,
                        frame_index=frame_index,
                    )
                )

        if "final" not in completed_screenshots:
            checkpoints.append(
                _capture_checkpoint(
                    label="final",
                    output_dir=screenshot_dir,
                    simulation=simulation,
                    renderer=renderer,
                    elapsed_wall_seconds=min(spec.duration_seconds, time.perf_counter() - start_time),
                    frame_index=frame_index,
                )
            )

        frame_writer.close()
        elapsed_wall_seconds = max(0.0, time.perf_counter() - start_time)
        timing_summary = timing_collector.build_summary(
            elapsed_wall_seconds=elapsed_wall_seconds,
            runtime_loop=runtime_loop,
        )
        run_result = _build_run_result(
            spec=spec,
            settings=settings,
            display_context=display_context,
            started_at=started_at,
            elapsed_wall_seconds=elapsed_wall_seconds,
            timing_collector=timing_collector,
            timing_summary=timing_summary,
            simulation=simulation,
            renderer=renderer,
            resize_calls=resize_calls,
            checkpoints=checkpoints,
            observability_samples=observability_samples,
            population_samples=population_samples,
            food_samples=food_samples,
            predator_samples=predator_samples,
            prey_samples=prey_samples,
            render_breakdown_sums=render_breakdown_sums,
            render_breakdown_counts=render_breakdown_counts,
            frame_samples_path=suite_paths.frame_samples / f"{spec.run_id}.frames.csv.gz",
            restart_seed_changes=restart_seed_changes,
            toggles_completed=toggles_completed,
        )
        per_run_path.write_text(
            json.dumps(run_result, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return run_result
    finally:
        try:
            frame_writer.close()
        except OSError:
            pass
        pygame.quit()


def _build_run_result(
    *,
    spec: RunSpec,
    settings: Settings,
    display_context: DisplayContext,
    started_at: str,
    elapsed_wall_seconds: float,
    timing_collector: LoopTimingCollector,
    timing_summary: dict[str, Any],
    simulation: Simulation,
    renderer: Renderer,
    resize_calls: dict[str, list[dict[str, Any]]],
    checkpoints: list[dict[str, Any]],
    observability_samples: list[dict[str, Any]],
    population_samples: list[int],
    food_samples: list[int],
    predator_samples: list[int],
    prey_samples: list[int],
    render_breakdown_sums: dict[str, float],
    render_breakdown_counts: dict[str, int],
    frame_samples_path: Path,
    restart_seed_changes: int,
    toggles_completed: int,
) -> dict[str, Any]:
    final_snapshot = simulation.build_observability_snapshot()
    if spec.mode == "predator_prey":
        final_stability = simulation.get_predator_prey_stability_stats()
    else:
        final_stability = None

    timing_ms = timing_summary["timing_ms"]
    effective_fps_summary = timing_summary["effective_fps"]
    render_breakdown_mean_ms = {
        key: (render_breakdown_sums[key] / render_breakdown_counts[key])
        for key in sorted(render_breakdown_sums)
        if render_breakdown_counts.get(key)
    }
    current_display_size = [renderer.display_width, renderer.display_height]
    run_result = {
        "run_id": spec.run_id,
        "scenario": spec.scenario,
        "mode": spec.mode,
        "seed": spec.seed,
        "display_path": display_context.display_path,
        "visible_display": display_context.visible_display,
        "started_at": started_at,
        "duration_seconds_requested": spec.duration_seconds,
        "duration_seconds_actual": elapsed_wall_seconds,
        "fullscreen": spec.fullscreen,
        "target_fps": settings.target_fps,
        "notes": spec.notes,
        "resolution": {
            "world": [simulation.width, simulation.height],
            "initial_display": checkpoints[0]["display_size"] if checkpoints else current_display_size,
            "final_display": current_display_size,
            "windowed_target": list(DEFAULT_WINDOWED_SIZE),
            "desktop_native": list(display_context.desktop_resolution),
        },
        "performance": {
            "sim_ticks_advanced": timing_summary["sim_steps_total"],
            "frames_rendered": timing_summary["frames_rendered"],
            "effective_fps_overall": timing_summary["effective_fps_overall"],
            "effective_fps_frame_stats": effective_fps_summary,
            "frame_ms": timing_ms["frame"],
            "event_ms": timing_ms["event"],
            "sim_ms": timing_ms["sim"],
            "render_ms": timing_ms["render"],
            "present_ms": timing_ms["present"],
            "pacing_ms": timing_ms["pacing"],
            "sim_steps_per_render_frame": timing_summary["sim_steps_per_render_frame"],
            "clamp_drop": timing_summary["clamp_drop"],
            "render_breakdown_mean_ms": render_breakdown_mean_ms,
        },
        "population_summary": {
            "population": _summarize_numeric(population_samples),
            "food_count": _summarize_numeric(food_samples),
            "predator_count": _summarize_numeric(predator_samples),
            "prey_count": _summarize_numeric(prey_samples),
        },
        "final_observability": final_snapshot,
        "final_stability": final_stability,
        "observability_samples": observability_samples,
        "checkpoints": checkpoints,
        "transition_checks": _build_transition_structural_checks(
            spec=spec,
            checkpoints=checkpoints,
            resize_calls=resize_calls,
        ),
        "resize_calls": resize_calls,
        "frame_samples_file": str(frame_samples_path),
        "restart_seed_changes": restart_seed_changes,
        "toggles_completed": toggles_completed,
        "settings_snapshot": _build_settings_snapshot(settings, spec.mode),
        "platform": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pygame": pygame.version.ver,
            "display_driver": display_context.driver,
        },
    }
    run_result["dominant_cost"] = _determine_dominant_cost(
        effective_fps_overall=float(run_result["performance"]["effective_fps_overall"]),
        target_fps=settings.target_fps,
        sim_mean=float(run_result["performance"]["sim_ms"]["mean"]),
        render_mean=float(run_result["performance"]["render_ms"]["mean"]),
        present_mean=float(run_result["performance"]["present_ms"]["mean"]),
        pacing_mean=float(run_result["performance"]["pacing_ms"]["mean"]),
    )
    return run_result


def _build_transition_structural_checks(
    *,
    spec: RunSpec,
    checkpoints: list[dict[str, Any]],
    resize_calls: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    if not spec.toggles:
        return {
            "expected_toggles": 0,
            "world_size_stable": True,
            "zone_hash_stable": True,
            "simulation_resize_not_called": not resize_calls["simulation"],
            "fullscreen_sequence_ok": True,
        }

    relevant = [
        checkpoint
        for checkpoint in checkpoints
        if checkpoint["label"].startswith("pre_") or checkpoint["label"].startswith("post_")
    ]
    expected_sequence = [True, False, True]
    actual_sequence = [
        relevant[0]["fullscreen"],
        *[checkpoint["fullscreen"] for checkpoint in relevant if checkpoint["label"].startswith("post_")],
    ] if relevant else []
    world_size_stable = len({tuple(checkpoint["world_size"]) for checkpoint in relevant}) <= 1
    zone_hash_stable = len({checkpoint["zone_hash"] for checkpoint in relevant}) <= 1
    fullscreen_sequence_ok = actual_sequence[: len(expected_sequence)] == expected_sequence[: len(actual_sequence)]
    return {
        "expected_toggles": len(spec.toggles),
        "captured_transition_checkpoints": len(relevant),
        "world_size_stable": world_size_stable,
        "zone_hash_stable": zone_hash_stable,
        "simulation_resize_not_called": not resize_calls["simulation"],
        "fullscreen_sequence_ok": fullscreen_sequence_ok,
    }


def _capture_checkpoint(
    *,
    label: str,
    output_dir: Path,
    simulation: Simulation,
    renderer: Renderer,
    elapsed_wall_seconds: float,
    frame_index: int,
) -> dict[str, Any]:
    screenshot_path = output_dir / f"{label}.png"
    pygame.image.save(renderer.screen, screenshot_path)
    snapshot = simulation.build_observability_snapshot()
    predator_count, prey_count = (
        simulation.get_species_counts()
        if simulation.settings.sim_mode == "predator_prey"
        else (0, 0)
    )
    return {
        "label": label,
        "elapsed_wall_seconds": round(elapsed_wall_seconds, 3),
        "frame_index": frame_index,
        "screenshot": str(screenshot_path),
        "display_size": [renderer.display_width, renderer.display_height],
        "logical_render_size": [renderer.width, renderer.height],
        "world_size": [simulation.width, simulation.height],
        "fullscreen": bool(renderer.screen.get_flags() & pygame.FULLSCREEN),
        "population": simulation.population,
        "food_count": simulation.food_count,
        "predator_count": predator_count,
        "prey_count": prey_count,
        "zone_hash": _hash_zone_state(simulation),
        "edge_counts": _build_edge_counts(simulation),
        "observability": snapshot,
    }


def _run_profile_capture(
    *,
    mode: str,
    seed: int,
    duration_seconds: float,
    output_dir: Path,
    display_context: DisplayContext,
) -> dict[str, Any]:
    random.seed(seed)
    pygame.init()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = output_dir / f"profile__{mode}__seed{seed}__{stamp}"
    try:
        settings = Settings()
        settings.sim_mode = mode
        settings.fullscreen = True
        settings.show_hud = False
        world_width, world_height, screen = _create_display_for_run(settings)
        if mode == "predator_prey":
            simulation = Simulation(world_width, world_height, settings, seed=seed)
            simulation.reset_predator_prey_adaptive_tuning()
            simulation.set_predator_prey_adaptive_tuning_enabled(False)
        else:
            simulation = Simulation(world_width, world_height, settings)
        renderer = Renderer(screen, settings, debug=False)
        clock = pygame.time.Clock()
        runtime_loop = _create_fixed_step_loop_state()
        timing_collector = LoopTimingCollector(retain_samples=True)
        profiler = cProfile.Profile()

        profiler.enable()
        start_time = time.perf_counter()
        while time.perf_counter() - start_time < duration_seconds:
            event_start = time.perf_counter()
            quit_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_requested = True
                    break
            event_ms = (time.perf_counter() - event_start) * 1000.0
            if quit_requested:
                break

            if simulation.update_predator_prey_runtime(now_seconds=time.monotonic()):
                renderer.reset_runtime_state()
                runtime_loop.reset_timing_debt()

            sim_suppressed = _simulation_timing_is_suppressed(simulation)
            sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
                simulation,
                runtime_loop,
                allow_simulation=not sim_suppressed,
            )
            renderer.set_external_debug_metrics({})
            runtime_loop.restore_buffered_attacks(simulation)
            frame_start = time.perf_counter()
            render_metrics = renderer.draw(simulation)
            present_start = time.perf_counter()
            pygame.display.flip()
            present_ms = (time.perf_counter() - present_start) * 1000.0
            pacing_start = time.perf_counter()
            clock.tick(max(1, settings.target_fps))
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
        profiler.disable()

        elapsed_wall_seconds = max(0.0, time.perf_counter() - start_time)
        pstats_path = base.with_suffix(".pstats")
        text_path = base.with_suffix(".txt")
        timing_path = base.with_suffix(".timing.json")
        profiler.dump_stats(str(pstats_path))
        with text_path.open("w", encoding="utf-8") as fp:
            stats = pstats.Stats(profiler, stream=fp).sort_stats("cumulative")
            stats.print_stats(120)
        timing_path.write_text(
            json.dumps(
                timing_collector.build_summary(
                    elapsed_wall_seconds=elapsed_wall_seconds,
                    runtime_loop=runtime_loop,
                ),
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return {
            "mode": mode,
            "seed": seed,
            "duration_seconds_actual": elapsed_wall_seconds,
            "display_path": display_context.display_path,
            "files": {
                "pstats": str(pstats_path),
                "text": str(text_path),
                "timing": str(timing_path),
            },
        }
    finally:
        pygame.quit()


def _write_runs_csv(path: Path, run_results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "run_id",
        "scenario",
        "mode",
        "seed",
        "display_path",
        "fullscreen",
        "duration_seconds_requested",
        "duration_seconds_actual",
        "world_width",
        "world_height",
        "display_width",
        "display_height",
        "target_fps",
        "frames_rendered",
        "sim_ticks_advanced",
        "effective_fps_overall",
        "frame_ms_mean",
        "frame_ms_median",
        "frame_ms_p95",
        "frame_ms_p99",
        "frame_ms_max",
        "event_ms_mean",
        "event_ms_median",
        "event_ms_p95",
        "event_ms_max",
        "sim_ms_mean",
        "sim_ms_median",
        "sim_ms_p95",
        "sim_ms_p99",
        "sim_ms_max",
        "render_ms_mean",
        "render_ms_median",
        "render_ms_p95",
        "render_ms_p99",
        "render_ms_max",
        "present_ms_mean",
        "present_ms_median",
        "present_ms_p95",
        "present_ms_p99",
        "present_ms_max",
        "pacing_ms_mean",
        "pacing_ms_median",
        "pacing_ms_p95",
        "pacing_ms_p99",
        "pacing_ms_max",
        "clamp_frames",
        "dropped_ms_total",
        "population_mean",
        "population_max",
        "food_mean",
        "predator_mean",
        "prey_mean",
        "dominant_cost",
    ]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for run in run_results:
            perf = run["performance"]
            writer.writerow(
                {
                    "run_id": run["run_id"],
                    "scenario": run["scenario"],
                    "mode": run["mode"],
                    "seed": run["seed"],
                    "display_path": run["display_path"],
                    "fullscreen": int(run["fullscreen"]),
                    "duration_seconds_requested": run["duration_seconds_requested"],
                    "duration_seconds_actual": run["duration_seconds_actual"],
                    "world_width": run["resolution"]["world"][0],
                    "world_height": run["resolution"]["world"][1],
                    "display_width": run["resolution"]["final_display"][0],
                    "display_height": run["resolution"]["final_display"][1],
                    "target_fps": run["target_fps"],
                    "frames_rendered": perf["frames_rendered"],
                    "sim_ticks_advanced": perf["sim_ticks_advanced"],
                    "effective_fps_overall": perf["effective_fps_overall"],
                    "frame_ms_mean": perf["frame_ms"]["mean"],
                    "frame_ms_median": perf["frame_ms"]["median"],
                    "frame_ms_p95": perf["frame_ms"]["p95"],
                    "frame_ms_p99": perf["frame_ms"]["p99"],
                    "frame_ms_max": perf["frame_ms"]["max"],
                    "event_ms_mean": perf["event_ms"]["mean"],
                    "event_ms_median": perf["event_ms"]["median"],
                    "event_ms_p95": perf["event_ms"]["p95"],
                    "event_ms_max": perf["event_ms"]["max"],
                    "sim_ms_mean": perf["sim_ms"]["mean"],
                    "sim_ms_median": perf["sim_ms"]["median"],
                    "sim_ms_p95": perf["sim_ms"]["p95"],
                    "sim_ms_p99": perf["sim_ms"]["p99"],
                    "sim_ms_max": perf["sim_ms"]["max"],
                    "render_ms_mean": perf["render_ms"]["mean"],
                    "render_ms_median": perf["render_ms"]["median"],
                    "render_ms_p95": perf["render_ms"]["p95"],
                    "render_ms_p99": perf["render_ms"]["p99"],
                    "render_ms_max": perf["render_ms"]["max"],
                    "present_ms_mean": perf["present_ms"]["mean"],
                    "present_ms_median": perf["present_ms"]["median"],
                    "present_ms_p95": perf["present_ms"]["p95"],
                    "present_ms_p99": perf["present_ms"]["p99"],
                    "present_ms_max": perf["present_ms"]["max"],
                    "pacing_ms_mean": perf["pacing_ms"]["mean"],
                    "pacing_ms_median": perf["pacing_ms"]["median"],
                    "pacing_ms_p95": perf["pacing_ms"]["p95"],
                    "pacing_ms_p99": perf["pacing_ms"]["p99"],
                    "pacing_ms_max": perf["pacing_ms"]["max"],
                    "clamp_frames": perf["clamp_drop"]["frame_count"],
                    "dropped_ms_total": perf["clamp_drop"]["dropped_ms_total"],
                    "population_mean": run["population_summary"]["population"]["mean"],
                    "population_max": run["population_summary"]["population"]["max"],
                    "food_mean": run["population_summary"]["food_count"]["mean"],
                    "predator_mean": run["population_summary"]["predator_count"]["mean"],
                    "prey_mean": run["population_summary"]["prey_count"]["mean"],
                    "dominant_cost": run["dominant_cost"]["bucket"],
                }
            )


def _build_aggregate_results(
    *,
    run_results: list[dict[str, Any]],
    profile_results: list[dict[str, Any]],
    display_context: DisplayContext,
    command: str,
    root: Path,
) -> dict[str, Any]:
    scenarios = sorted({run["scenario"] for run in run_results})
    modes = sorted({run["mode"] for run in run_results})
    scenario_aggregates = {
        scenario: _aggregate_group([run for run in run_results if run["scenario"] == scenario])
        for scenario in scenarios
    }
    mode_aggregates = {
        mode: _aggregate_group([run for run in run_results if run["mode"] == mode])
        for mode in modes
    }
    aggregate = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "command": command,
        "display": asdict(display_context),
        "matrix": {
            "completed_runs": len(run_results),
            "completed_profiles": len(profile_results),
            "scenarios": scenarios,
            "modes": modes,
        },
        "scenario_aggregates": scenario_aggregates,
        "mode_aggregates": mode_aggregates,
        "profiles": profile_results,
        "runs": [_build_compact_run_summary(run) for run in run_results],
    }
    aggregate["transition_summary"] = _build_transition_summary(run_results)
    aggregate["answers"] = _build_analysis_answers(aggregate)
    return aggregate


def _aggregate_group(group_runs: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = {
        "effective_fps_overall": [float(run["performance"]["effective_fps_overall"]) for run in group_runs],
        "frame_ms_mean": [float(run["performance"]["frame_ms"]["mean"]) for run in group_runs],
        "frame_ms_median": [float(run["performance"]["frame_ms"]["median"]) for run in group_runs],
        "frame_ms_p95": [float(run["performance"]["frame_ms"]["p95"]) for run in group_runs],
        "frame_ms_p99": [float(run["performance"]["frame_ms"]["p99"]) for run in group_runs],
        "sim_ms_mean": [float(run["performance"]["sim_ms"]["mean"]) for run in group_runs],
        "render_ms_mean": [float(run["performance"]["render_ms"]["mean"]) for run in group_runs],
        "present_ms_mean": [float(run["performance"]["present_ms"]["mean"]) for run in group_runs],
        "pacing_ms_mean": [float(run["performance"]["pacing_ms"]["mean"]) for run in group_runs],
        "population_mean": [float(run["population_summary"]["population"]["mean"]) for run in group_runs],
        "population_max": [float(run["population_summary"]["population"]["max"]) for run in group_runs],
        "predator_mean": [float(run["population_summary"]["predator_count"]["mean"]) for run in group_runs],
        "prey_mean": [float(run["population_summary"]["prey_count"]["mean"]) for run in group_runs],
    }
    timing_distribution = _aggregate_timing_distributions(group_runs)
    best_seed_run = max(group_runs, key=lambda run: run["performance"]["effective_fps_overall"])
    worst_seed_run = min(group_runs, key=lambda run: run["performance"]["effective_fps_overall"])
    median_seed_run = sorted(
        group_runs,
        key=lambda run: run["performance"]["effective_fps_overall"],
    )[len(group_runs) // 2]
    clamp_issue_runs = sum(1 for run in group_runs if run["performance"]["clamp_drop"]["frame_count"] > 0)
    sub60_runs = sum(1 for run in group_runs if run["performance"]["effective_fps_overall"] < 59.5)
    dominant_buckets = [run["dominant_cost"]["bucket"] for run in group_runs]
    dominant_bucket = _mode_or_mixed(dominant_buckets)
    return {
        "run_count": len(group_runs),
        "timing_distribution": timing_distribution,
        "seed_variance": {
            key: _variance_summary(values)
            for key, values in metrics.items()
        },
        "best_seed": _build_compact_run_summary(best_seed_run),
        "median_seed": _build_compact_run_summary(median_seed_run),
        "worst_seed": _build_compact_run_summary(worst_seed_run),
        "sub_60_fps_runs": sub60_runs,
        "clamp_issue_runs": clamp_issue_runs,
        "dropped_ms_total": sum(
            float(run["performance"]["clamp_drop"]["dropped_ms_total"])
            for run in group_runs
        ),
        "dominant_cost": {
            "bucket": dominant_bucket,
            "counts": {
                bucket: dominant_buckets.count(bucket)
                for bucket in sorted(set(dominant_buckets))
            },
        },
    }


def _aggregate_timing_distributions(group_runs: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = ("frame_ms", "event_ms", "sim_ms", "render_ms", "present_ms", "pacing_ms")
    aggregated: dict[str, Any] = {}
    for metric in metrics:
        values: list[float] = []
        for run in group_runs:
            frame_samples_path = Path(run["frame_samples_file"])
            with gzip.open(frame_samples_path, "rt", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                values.extend(float(row[metric]) for row in reader)
        aggregated[metric] = _summarize_numeric(values)
    return aggregated


def _build_compact_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run["run_id"],
        "scenario": run["scenario"],
        "mode": run["mode"],
        "seed": run["seed"],
        "effective_fps_overall": run["performance"]["effective_fps_overall"],
        "frame_ms_mean": run["performance"]["frame_ms"]["mean"],
        "sim_ms_mean": run["performance"]["sim_ms"]["mean"],
        "render_ms_mean": run["performance"]["render_ms"]["mean"],
        "present_ms_mean": run["performance"]["present_ms"]["mean"],
        "pacing_ms_mean": run["performance"]["pacing_ms"]["mean"],
        "clamp_frames": run["performance"]["clamp_drop"]["frame_count"],
        "dominant_cost": run["dominant_cost"]["bucket"],
        "frame_samples_file": run["frame_samples_file"],
        "per_run_json": str(Path(run["frame_samples_file"]).parents[1] / "per_run" / f"{run['run_id']}.json"),
    }


def _build_analysis_answers(aggregate: dict[str, Any]) -> dict[str, str]:
    mode_answers = {
        mode: data["dominant_cost"]["bucket"]
        for mode, data in aggregate["mode_aggregates"].items()
    }
    predator_fullscreen = aggregate["scenario_aggregates"].get("predator_prey_extended_fullscreen")
    predator_transition = aggregate["scenario_aggregates"].get("predator_prey_transition")
    if predator_fullscreen is None:
        return {
            "per_mode_dominant_costs": ", ".join(f"{mode}={bucket}" for mode, bucket in mode_answers.items()),
            "predator_prey_fullscreen_dominant_cost": "unavailable",
            "predator_prey_60_fps_miss_reason": "unavailable",
            "fullscreen_native_main_reason_if_missing": "unavailable",
            "toggle_anomalies": "unavailable",
            "optimize_next": "unavailable",
            "native_kernels_later": "unavailable",
        }
    predator_bucket = predator_fullscreen["dominant_cost"]["bucket"]
    predator_timing = predator_fullscreen["timing_distribution"]
    transition_bucket = predator_transition["dominant_cost"]["bucket"] if predator_transition is not None else "unavailable"
    transition_summary = aggregate.get("transition_summary", {})
    transition_structural_ok = bool(transition_summary.get("structural_ok", False))
    if predator_fullscreen["sub_60_fps_runs"] > 0:
        miss_reason = predator_bucket
    else:
        miss_reason = "present/pacing"
    optimize_next = predator_bucket
    if not transition_structural_ok and transition_bucket != "unavailable":
        optimize_next = "resize/fullscreen handling"
    return {
        "per_mode_dominant_costs": ", ".join(f"{mode}={bucket}" for mode, bucket in mode_answers.items()),
        "predator_prey_fullscreen_dominant_cost": predator_bucket,
        "predator_prey_60_fps_miss_reason": miss_reason,
        "fullscreen_native_main_reason_if_missing": (
            predator_bucket if predator_fullscreen["sub_60_fps_runs"] > 0 else "not missing target in all runs"
        ),
        "toggle_anomalies": (
            "no structural anomalies detected; timing shifted across toggles but world size and display transitions stayed consistent"
            if transition_structural_ok
            else "structural transition anomalies detected"
        ),
        "optimize_next": optimize_next,
        "native_kernels_later": _native_kernel_answer(predator_timing, predator_bucket),
    }


def _native_kernel_answer(predator_timing: dict[str, Any], predator_bucket: str) -> str:
    sim_mean = float(predator_timing["sim_ms"]["mean"])
    render_mean = float(predator_timing["render_ms"]["mean"])
    if predator_bucket == "simulation" and sim_mean > (render_mean * 1.5):
        return "Measured fullscreen predator_prey runs are simulation-dominated; native kernels are justified only if targeted at the hot simulation path."
    return "The current data does not justify native kernels yet; it does not isolate a simulation hotspot strongly enough over rendering/presentation."


def _build_transition_findings(run_results: list[dict[str, Any]]) -> str:
    transition_runs = [run for run in run_results if run["scenario"] == "predator_prey_transition"]
    lines = [
        "# Transition Findings",
        "",
        "The checks below focus on fullscreen -> windowed -> fullscreen predator_prey runs.",
        "",
    ]
    for run in transition_runs:
        checks = run["transition_checks"]
        timing_windows = _analyze_transition_timing_windows(run)
        lines.extend(
            [
                f"## {run['run_id']}",
                "",
                f"- Fullscreen sequence ok: {checks['fullscreen_sequence_ok']}",
                f"- World size stable: {checks['world_size_stable']}",
                f"- Simulation resize not called: {checks['simulation_resize_not_called']}",
                "- Zone hash stability is not used as a correctness verdict here because live runs evolve local zone state over time.",
                f"- Toggle timing deltas: {timing_windows}",
                "",
            ]
        )
    return "\n".join(lines)


def _build_transition_summary(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    transition_runs = [run for run in run_results if run["scenario"] == "predator_prey_transition"]
    if not transition_runs:
        return {
            "run_count": 0,
            "structural_ok": False,
            "fullscreen_sequence_ok_runs": 0,
            "world_size_stable_runs": 0,
            "simulation_resize_clean_runs": 0,
        }
    fullscreen_sequence_ok_runs = sum(
        1 for run in transition_runs if run["transition_checks"]["fullscreen_sequence_ok"]
    )
    world_size_stable_runs = sum(
        1 for run in transition_runs if run["transition_checks"]["world_size_stable"]
    )
    simulation_resize_clean_runs = sum(
        1 for run in transition_runs if run["transition_checks"]["simulation_resize_not_called"]
    )
    structural_ok = (
        fullscreen_sequence_ok_runs == len(transition_runs)
        and world_size_stable_runs == len(transition_runs)
        and simulation_resize_clean_runs == len(transition_runs)
    )
    return {
        "run_count": len(transition_runs),
        "structural_ok": structural_ok,
        "fullscreen_sequence_ok_runs": fullscreen_sequence_ok_runs,
        "world_size_stable_runs": world_size_stable_runs,
        "simulation_resize_clean_runs": simulation_resize_clean_runs,
    }


def _analyze_transition_timing_windows(run: dict[str, Any]) -> str:
    checkpoint_map = {checkpoint["label"]: checkpoint for checkpoint in run["checkpoints"]}
    summaries: list[str] = []
    for action_label in ("fullscreen_to_windowed", "windowed_to_fullscreen"):
        pre = checkpoint_map.get(f"pre_{action_label}")
        post = checkpoint_map.get(f"post_{action_label}")
        if pre is None or post is None:
            continue
        before = _summarize_frame_window(
            Path(run["frame_samples_file"]),
            start=max(0.0, float(pre["elapsed_wall_seconds"]) - TRANSITION_ANALYSIS_WINDOW_SECONDS),
            end=float(pre["elapsed_wall_seconds"]),
        )
        after = _summarize_frame_window(
            Path(run["frame_samples_file"]),
            start=float(post["elapsed_wall_seconds"]),
            end=float(post["elapsed_wall_seconds"]) + TRANSITION_ANALYSIS_WINDOW_SECONDS,
        )
        summaries.append(
            (
                f"{action_label}: "
                f"fps {before['effective_fps']:.2f}->{after['effective_fps']:.2f}, "
                f"frame_ms {before['frame_ms']:.2f}->{after['frame_ms']:.2f}, "
                f"sim_ms {before['sim_ms']:.2f}->{after['sim_ms']:.2f}, "
                f"render_ms {before['render_ms']:.2f}->{after['render_ms']:.2f}"
            )
        )
    return "; ".join(summaries) if summaries else "no transition checkpoints captured"


def _summarize_frame_window(path: Path, *, start: float, end: float) -> dict[str, float]:
    values: dict[str, list[float]] = {
        "effective_fps": [],
        "frame_ms": [],
        "sim_ms": [],
        "render_ms": [],
    }
    with gzip.open(path, "rt", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            elapsed = float(row["elapsed_wall_seconds"])
            if elapsed < start or elapsed > end:
                continue
            for key in values:
                values[key].append(float(row[key]))
    return {
        key: (sum(items) / len(items) if items else 0.0)
        for key, items in values.items()
    }


def _build_summary_markdown(
    *,
    aggregate_results: dict[str, Any],
    run_results: list[dict[str, Any]],
    profile_results: list[dict[str, Any]],
    display_context: DisplayContext,
    command: str,
) -> str:
    lines = [
        "# Graphical Benchmark Summary",
        "",
        f"- Display path used: {display_context.display_path}",
        f"- Visible display: {'yes' if display_context.visible_display else 'no'}",
        f"- SDL driver: {display_context.driver}",
        f"- Native desktop resolution: {display_context.desktop_resolution[0]}x{display_context.desktop_resolution[1]}",
        f"- Command run: `{command}`",
        f"- Completed runs: {len(run_results)}",
        f"- Collected profiles: {len(profile_results)}",
        "",
        "## Benchmark Matrix Completed",
        "",
        "- Baseline fullscreen sweep: energy, predator_prey, boids, drift; 6 seeds; 90s each",
        "- Predator_prey extended fullscreen sweep: 10 seeds; 180s each",
        "- Predator_prey transition sweep: 6 seeds; 60s fullscreen -> 60s windowed -> 60s fullscreen",
        "- Predator_prey soak: 2 seeds; 600s each",
        "",
        "## Major Findings By Mode",
        "",
    ]
    for mode, data in aggregate_results["mode_aggregates"].items():
        timing = data["timing_distribution"]
        lines.extend(
            [
                f"### {mode}",
                "",
                f"- Dominant cost: {data['dominant_cost']['bucket']}",
                f"- Effective FPS overall mean across seeds: {data['seed_variance']['effective_fps_overall']['mean']:.2f}",
                f"- frame_ms mean / p95 / p99: {timing['frame_ms']['mean']:.2f} / {timing['frame_ms']['p95']:.2f} / {timing['frame_ms']['p99']:.2f}",
                f"- sim_ms mean / p95 / p99: {timing['sim_ms']['mean']:.2f} / {timing['sim_ms']['p95']:.2f} / {timing['sim_ms']['p99']:.2f}",
                f"- render_ms mean / p95 / p99: {timing['render_ms']['mean']:.2f} / {timing['render_ms']['p95']:.2f} / {timing['render_ms']['p99']:.2f}",
                f"- present_ms mean / p95 / p99: {timing['present_ms']['mean']:.2f} / {timing['present_ms']['p95']:.2f} / {timing['present_ms']['p99']:.2f}",
                f"- pacing_ms mean / p95 / p99: {timing['pacing_ms']['mean']:.2f} / {timing['pacing_ms']['p95']:.2f} / {timing['pacing_ms']['p99']:.2f}",
                f"- Sub-60-FPS runs: {data['sub_60_fps_runs']} / {data['run_count']}",
                "",
            ]
        )

    predator = aggregate_results["scenario_aggregates"].get("predator_prey_extended_fullscreen")
    if predator is not None:
        predator_seed_var = predator["seed_variance"]
        lines.extend(
            [
                "## Predator_Prey Conclusion",
                "",
                f"- Dominant cost in fullscreen native-resolution live runs: {predator['dominant_cost']['bucket']}",
                f"- Seed variance FPS mean / stddev: {predator_seed_var['effective_fps_overall']['mean']:.2f} / {predator_seed_var['effective_fps_overall']['stdev']:.2f}",
                f"- Seed variance sim_ms mean / stddev: {predator_seed_var['sim_ms_mean']['mean']:.2f} / {predator_seed_var['sim_ms_mean']['stdev']:.2f}",
                f"- Seed variance render_ms mean / stddev: {predator_seed_var['render_ms_mean']['mean']:.2f} / {predator_seed_var['render_ms_mean']['stdev']:.2f}",
                f"- Best seed: {predator['best_seed']['seed']} ({predator['best_seed']['effective_fps_overall']:.2f} FPS)",
                f"- Median seed: {predator['median_seed']['seed']} ({predator['median_seed']['effective_fps_overall']:.2f} FPS)",
                f"- Worst seed: {predator['worst_seed']['seed']} ({predator['worst_seed']['effective_fps_overall']:.2f} FPS)",
                "",
                "## Analysis Questions",
                "",
                "1. For each mode, what is the dominant cost in live graphical runs?",
            ]
        )
    else:
        lines.extend(
            [
                "## Analysis Questions",
                "",
                "1. For each mode, what is the dominant cost in live graphical runs?",
            ]
        )
    for mode, data in aggregate_results["mode_aggregates"].items():
        lines.append(f"   - {mode}: {data['dominant_cost']['bucket']}")
    answers = aggregate_results["answers"]
    lines.extend(
        [
            "2. In predator_prey specifically, what is the dominant cost in fullscreen native-resolution live graphical runs?",
            f"   - {answers['predator_prey_fullscreen_dominant_cost']}",
            "3. Is predator_prey missing 60 FPS because of sim_ms, render_ms, present_ms, or a combination?",
            f"   - {answers['predator_prey_60_fps_miss_reason']}",
            "4. In fullscreen native-resolution use, what is the main reason performance misses target, if it misses?",
            f"   - {answers['fullscreen_native_main_reason_if_missing']}",
            "5. Do fullscreen/windowed toggles introduce any correctness or rendering anomalies?",
            f"   - {answers['toggle_anomalies']}",
            "6. Based on measured evidence only, what should be optimized next?",
            f"   - {answers['optimize_next']}",
            "7. If you recommend native kernels later, state exactly why the data supports that. If it does not support that yet, say so plainly.",
            f"   - {answers['native_kernels_later']}",
            "",
        ]
    )
    return "\n".join(lines)


def _populate_analysis_bundle(
    *,
    suite_paths: SuitePaths,
    summary_path: Path,
    aggregate_path: Path,
    runs_csv_path: Path,
    transition_findings_path: Path,
    environment_path: Path,
    run_results: list[dict[str, Any]],
) -> None:
    shutil.copy2(summary_path, suite_paths.analysis_bundle / summary_path.name)
    shutil.copy2(aggregate_path, suite_paths.analysis_bundle / aggregate_path.name)
    shutil.copy2(runs_csv_path, suite_paths.analysis_bundle / runs_csv_path.name)
    shutil.copy2(transition_findings_path, suite_paths.analysis_bundle / transition_findings_path.name)
    shutil.copy2(environment_path, suite_paths.analysis_bundle / environment_path.name)
    screenshots_dir = suite_paths.analysis_bundle / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    for screenshot_path in _select_representative_screenshots(run_results):
        destination = screenshots_dir / screenshot_path.name
        shutil.copy2(screenshot_path, destination)


def _select_representative_screenshots(run_results: list[dict[str, Any]]) -> list[Path]:
    selected: list[Path] = []
    seen_modes: set[str] = set()
    for run in run_results:
        if run["mode"] not in seen_modes and run["checkpoints"]:
            selected.append(Path(run["checkpoints"][0]["screenshot"]))
            seen_modes.add(run["mode"])
    predator_extended = [
        run for run in run_results if run["scenario"] == "predator_prey_extended_fullscreen"
    ]
    if predator_extended:
        selected.extend(
            Path(checkpoint["screenshot"])
            for checkpoint in predator_extended[0]["checkpoints"][:3]
        )
    predator_transition = [
        run for run in run_results if run["scenario"] == "predator_prey_transition"
    ]
    if predator_transition:
        transition_checkpoints = [
            checkpoint
            for checkpoint in predator_transition[0]["checkpoints"]
            if checkpoint["label"].startswith("pre_") or checkpoint["label"].startswith("post_")
        ]
        selected.extend(Path(checkpoint["screenshot"]) for checkpoint in transition_checkpoints[:6])
    predator_soak = [run for run in run_results if run["scenario"] == "predator_prey_soak"]
    if predator_soak and predator_soak[0]["checkpoints"]:
        selected.append(Path(predator_soak[0]["checkpoints"][-1]["screenshot"]))
    deduped: list[Path] = []
    seen_paths: set[Path] = set()
    for path in selected:
        if path in seen_paths:
            continue
        deduped.append(path)
        seen_paths.add(path)
        if len(deduped) >= REPRESENTATIVE_SCREENSHOT_LIMIT:
            break
    return deduped


def _zip_directory(
    source_dir: Path,
    output_path: Path,
    *,
    exclude_names: set[str] | None = None,
) -> None:
    exclude_names = exclude_names or set()
    temp_output = output_path.with_suffix(output_path.suffix + ".tmp")
    if temp_output.exists():
        temp_output.unlink()
    with zipfile.ZipFile(temp_output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(source_dir.rglob("*")):
            if path.name in exclude_names:
                continue
            if path == temp_output:
                continue
            zf.write(path, arcname=path.relative_to(source_dir))
    temp_output.replace(output_path)


def _create_display_for_run(settings: Settings) -> tuple[int, int, pygame.Surface]:
    if settings.fullscreen:
        width, height = _get_fullscreen_resolution()
        screen = pygame.display.set_mode((width, height), FULLSCREEN_FLAGS)
    else:
        width, height = DEFAULT_WINDOWED_SIZE
        screen = pygame.display.set_mode((width, height))
    return width, height, screen


def _build_settings_snapshot(settings: Settings, mode: str) -> dict[str, Any]:
    return {
        "sim_mode": settings.sim_mode,
        "visual_theme": settings.visual_theme,
        "fullscreen": settings.fullscreen,
        "target_fps": settings.target_fps,
        "show_hud": settings.show_hud,
        "initial_population": settings.initial_population,
        "max_population": settings.max_population,
        "food_spawn_rate": settings.food_spawn_rate,
        "food_max_particles": settings.food_max_particles,
        "food_cycle_enabled": settings.food_cycle_enabled,
        "food_cycle_period": settings.food_cycle_period,
        "mutation_rate": settings.mutation_rate,
        "cosmic_ray_rate": settings.cosmic_ray_rate,
        "energy_to_reproduce": settings.energy_to_reproduce,
        "zone_count": settings.zone_count,
        "zone_strength": settings.zone_strength,
        "mode_params": dict(settings.mode_params.get(mode, {})),
    }


def _summarize_numeric(values: list[int] | list[float]) -> dict[str, float | int]:
    if not values:
        return {
            "count": 0,
            "min": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }
    ordered = sorted(float(value) for value in values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 0:
        median = (ordered[middle - 1] + ordered[middle]) / 2.0
    else:
        median = ordered[middle]
    return {
        "count": len(ordered),
        "min": ordered[0],
        "mean": sum(ordered) / len(ordered),
        "median": median,
        "p95": ordered[min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))],
        "p99": ordered[min(len(ordered) - 1, int(0.99 * (len(ordered) - 1)))],
        "max": ordered[-1],
    }


def _variance_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0.0,
            "mean": 0.0,
            "median": 0.0,
            "variance": 0.0,
            "stdev": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    variance = statistics.pvariance(values) if len(values) > 1 else 0.0
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "count": float(len(values)),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "variance": variance,
        "stdev": stdev,
        "min": min(values),
        "max": max(values),
    }


def _determine_dominant_cost(
    *,
    effective_fps_overall: float,
    target_fps: int,
    sim_mean: float,
    render_mean: float,
    present_mean: float,
    pacing_mean: float,
) -> dict[str, Any]:
    if effective_fps_overall >= max(1.0, target_fps - 0.5) and pacing_mean > max(sim_mean, render_mean, present_mean):
        return {
            "bucket": "presentation/pacing",
            "reason": "At or near target FPS; pacing wait dominates completed frames.",
        }

    costs = {
        "simulation": sim_mean,
        "rendering": render_mean,
        "presentation/pacing": max(present_mean, pacing_mean),
    }
    sorted_costs = sorted(costs.items(), key=lambda item: item[1], reverse=True)
    if not sorted_costs or sorted_costs[0][1] <= 0.0:
        return {"bucket": "unclear", "reason": "No measurable timing cost."}

    top_name, top_value = sorted_costs[0]
    second_value = sorted_costs[1][1] if len(sorted_costs) > 1 else 0.0
    if top_value <= 0.0:
        bucket = "unclear"
        reason = "All timing buckets were near zero."
    elif second_value > 0.0 and top_value / second_value < 1.15:
        bucket = "mixed"
        reason = "Leading timing buckets were within 15% of each other."
    else:
        bucket = top_name
        reason = f"{top_name} had the largest mean frame cost."
    return {"bucket": bucket, "reason": reason}


def _mode_or_mixed(values: list[str]) -> str:
    if not values:
        return "unclear"
    unique = sorted(set(values))
    if len(unique) == 1:
        return unique[0]
    counts = {value: values.count(value) for value in unique}
    top_value = max(counts.values())
    top = [name for name, count in counts.items() if count == top_value]
    if len(top) == 1:
        return top[0]
    return "mixed"


def _run_command_capture(argv: list[str]) -> str:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            encoding="utf-8",
        )
    except OSError:
        return ""
    if completed.returncode != 0 and not completed.stdout.strip():
        return completed.stderr.strip()
    return completed.stdout.strip()
