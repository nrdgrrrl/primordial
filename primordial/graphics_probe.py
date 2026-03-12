"""Small graphical resize/toggle probe for runtime regression checks."""

from __future__ import annotations

import hashlib
import json
import platform
import random
import sys
from pathlib import Path
from typing import Any

import pygame

from .main import (
    DEFAULT_WINDOWED_SIZE,
    _advance_fixed_step_frame,
    _apply_display_mode,
    _create_fixed_step_loop_state,
    _get_fullscreen_resolution,
)
from .rendering import Renderer
from .settings import Settings
from .simulation import Simulation

_EDGE_BAND_RATIO = 0.10


def run_display_toggle_probe(
    output_dir: str | Path,
    *,
    seed: int = 104729,
    start_fullscreen: bool = True,
    toggle_count: int = 4,
    mode: str = "energy",
    theme: str = "ocean",
    open_settings_overlay: bool = True,
    settle_frames: int = 2,
) -> dict[str, Any]:
    """Run a bounded graphical toggle sequence and persist screenshots + JSON."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    random.seed(seed)
    pygame.init()

    resize_calls: dict[str, list[dict[str, Any]]] = {
        "renderer": [],
        "simulation": [],
    }
    checkpoints: list[dict[str, Any]] = []

    try:
        settings = Settings()
        settings.sim_mode = mode
        settings.visual_theme = theme
        settings.show_hud = True
        settings.fullscreen = start_fullscreen

        if start_fullscreen:
            world_width, world_height = _get_fullscreen_resolution()
            flags = pygame.FULLSCREEN | pygame.SCALED
        else:
            world_width, world_height = DEFAULT_WINDOWED_SIZE
            flags = 0

        screen = pygame.display.set_mode((world_width, world_height), flags)
        pygame.display.set_caption("Primordial Graphics Toggle Probe")
        pygame.mouse.set_visible(not settings.fullscreen)

        simulation = Simulation(world_width, world_height, settings)
        renderer = Renderer(screen, settings, debug=True)
        clock = pygame.time.Clock()
        runtime_loop = _create_fixed_step_loop_state()

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
                    "incoming_display_size": (
                        list(screen.get_size()) if screen is not None else None
                    ),
                }
            )
            original_renderer_resize(width, height, screen=screen)

        def _logged_simulation_resize(width: int, height: int) -> None:
            resize_calls["simulation"].append({"size_requested": [width, height]})
            original_simulation_resize(width, height)

        renderer.resize = _logged_renderer_resize  # type: ignore[method-assign]
        simulation.resize = _logged_simulation_resize  # type: ignore[method-assign]

        simulation.paused = True
        if open_settings_overlay:
            renderer.settings_overlay.open()
            renderer.settings_overlay.pending["fullscreen"] = settings.fullscreen
        runtime_loop.reset_timing_debt()

        _render_probe_frames(
            simulation,
            renderer,
            clock,
            runtime_loop,
            frame_count=max(1, settle_frames),
            target_fps=settings.target_fps,
        )
        checkpoints.append(
            _capture_checkpoint(
                "initial_fullscreen" if start_fullscreen else "initial_windowed",
                output_path,
                simulation,
                renderer,
            )
        )

        for toggle_index in range(toggle_count):
            settings.fullscreen = not settings.fullscreen
            _apply_display_mode(settings, simulation, renderer)
            if open_settings_overlay:
                renderer.settings_overlay.pending["fullscreen"] = settings.fullscreen
            runtime_loop.reset_timing_debt()
            _render_probe_frames(
                simulation,
                renderer,
                clock,
                runtime_loop,
                frame_count=max(1, settle_frames),
                target_fps=settings.target_fps,
            )
            label = (
                f"toggle_{toggle_index + 1}_fullscreen"
                if settings.fullscreen
                else f"toggle_{toggle_index + 1}_windowed"
            )
            checkpoints.append(
                _capture_checkpoint(label, output_path, simulation, renderer)
            )

        report = _build_probe_report(
            seed=seed,
            settings=settings,
            checkpoints=checkpoints,
            resize_calls=resize_calls,
        )
        report_path = output_path / "report.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report
    finally:
        pygame.quit()


def _render_probe_frames(
    simulation: Simulation,
    renderer: Renderer,
    clock: pygame.time.Clock,
    runtime_loop,
    *,
    frame_count: int,
    target_fps: int,
) -> None:
    """Render a small number of live frames while keeping world state paused."""
    for _ in range(frame_count):
        pygame.event.get()
        sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=not simulation.paused,
        )
        renderer.set_external_debug_metrics(
            {
                "event_ms": 0.0,
                "sim_ms": sim_ms,
                "sim_steps": float(sim_steps),
                "clamp_frames": float(clamp_frames),
                "dropped_ms": dropped_seconds * 1000.0,
                "display_width": float(renderer.display_width),
                "display_height": float(renderer.display_height),
                "world_width": float(simulation.width),
                "world_height": float(simulation.height),
            }
        )
        runtime_loop.restore_buffered_attacks(simulation)
        renderer.draw(simulation)
        pygame.display.flip()
        clock.tick(max(1, target_fps))


def _capture_checkpoint(
    label: str,
    output_dir: Path,
    simulation: Simulation,
    renderer: Renderer,
) -> dict[str, Any]:
    """Persist a screenshot and capture the current runtime state."""
    screenshot_path = output_dir / f"{label}.png"
    pygame.image.save(renderer.screen, screenshot_path)

    return {
        "label": label,
        "screenshot": screenshot_path.name,
        "display_size": [renderer.display_width, renderer.display_height],
        "logical_render_size": [renderer.width, renderer.height],
        "world_size": [simulation.width, simulation.height],
        "fullscreen": bool(renderer.screen.get_flags() & pygame.FULLSCREEN),
        "food_count": len(simulation.food_manager.particles),
        "creature_count": len(simulation.creatures),
        "food_hash": _hash_positions(
            (food.x, food.y, getattr(food, "depth_band", 0))
            for food in simulation.food_manager.particles
        ),
        "creature_hash": _hash_positions(
            (creature.x, creature.y, creature.lineage_id)
            for creature in simulation.creatures
        ),
        "zone_hash": _hash_zone_state(simulation),
        "edge_counts": _build_edge_counts(simulation),
        "zones": [
            {
                "index": index,
                "type": zone.zone_type,
                "x": round(zone.x, 3),
                "y": round(zone.y, 3),
                "radius": round(zone.radius, 3),
                "local_strength": round(zone.local_strength, 5),
            }
            for index, zone in enumerate(simulation.zone_manager.zones)
        ],
    }


def _build_edge_counts(simulation: Simulation) -> dict[str, int]:
    """Capture occupancy near the right/bottom world edges."""
    min_x = simulation.width * (1.0 - _EDGE_BAND_RATIO)
    min_y = simulation.height * (1.0 - _EDGE_BAND_RATIO)
    return {
        "food_right_band": sum(
            1 for food in simulation.food_manager.particles if food.x >= min_x
        ),
        "food_bottom_band": sum(
            1 for food in simulation.food_manager.particles if food.y >= min_y
        ),
        "creatures_right_band": sum(
            1 for creature in simulation.creatures if creature.x >= min_x
        ),
        "creatures_bottom_band": sum(
            1 for creature in simulation.creatures if creature.y >= min_y
        ),
    }


def _hash_positions(values) -> str:
    digest = hashlib.sha256()
    for item in sorted(
        (round(float(x), 4), round(float(y), 4), int(marker))
        for x, y, marker in values
    ):
        digest.update(f"{item[0]:.4f},{item[1]:.4f},{item[2]}|".encode("ascii"))
    return digest.hexdigest()


def _hash_zone_state(simulation: Simulation) -> str:
    digest = hashlib.sha256()
    for zone in simulation.zone_manager.zones:
        digest.update(
            (
                f"{zone.zone_type}|{zone.x:.4f}|{zone.y:.4f}|"
                f"{zone.radius:.4f}|{zone.local_strength:.5f}|"
            ).encode("ascii")
        )
    return digest.hexdigest()


def _build_probe_report(
    *,
    seed: int,
    settings: Settings,
    checkpoints: list[dict[str, Any]],
    resize_calls: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    baseline = checkpoints[0]
    issues: list[str] = []

    def _all_match(key: str) -> bool:
        return all(checkpoint[key] == baseline[key] for checkpoint in checkpoints[1:])

    if not _all_match("world_size"):
        issues.append("Simulation world size changed across display toggles.")
    if not _all_match("food_hash"):
        issues.append("Food positions changed while probe kept simulation paused.")
    if not _all_match("creature_hash"):
        issues.append("Creature positions changed while probe kept simulation paused.")
    if not _all_match("zone_hash"):
        issues.append("Zone geometry changed across display toggles.")
    if resize_calls["simulation"]:
        issues.append("Simulation.resize() was called during presentation-only toggles.")

    saw_windowed = any(not checkpoint["fullscreen"] for checkpoint in checkpoints)
    saw_fullscreen = any(checkpoint["fullscreen"] for checkpoint in checkpoints)
    if not saw_windowed:
        issues.append("Probe never entered windowed presentation mode.")
    if not saw_fullscreen:
        issues.append("Probe never entered fullscreen presentation mode.")

    return {
        "probe": {
            "seed": seed,
            "mode": settings.sim_mode,
            "theme": settings.visual_theme,
            "start_fullscreen": checkpoints[0]["fullscreen"],
            "windowed_size_requested": list(DEFAULT_WINDOWED_SIZE),
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pygame": pygame.version.ver,
        },
        "checks": {
            "passed": not issues,
            "world_size_stable": _all_match("world_size"),
            "food_positions_stable": _all_match("food_hash"),
            "creature_positions_stable": _all_match("creature_hash"),
            "zones_stable": _all_match("zone_hash"),
            "simulation_resize_not_called": not resize_calls["simulation"],
            "entered_windowed_mode": saw_windowed,
            "entered_fullscreen_mode": saw_fullscreen,
        },
        "issues": issues,
        "resize_calls": resize_calls,
        "checkpoints": checkpoints,
    }
