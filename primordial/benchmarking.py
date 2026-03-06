"""Bounded benchmark helpers for milestone and regression checks."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import random
import sys
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from .main import (
    LoopTimingCollector,
    _create_fixed_step_loop_state,
    run_bounded_session,
)
from .rendering import Renderer
from .scenarios import (
    SCENARIOS,
    ScenarioDefinition as BenchmarkScenario,
    apply_scenario_settings,
    get_scenario,
    list_scenarios,
)
from .settings import Settings
from .simulation import Simulation
from .simulation.zones import ZONE_DEFINITIONS


OBSERVABILITY_CORE_SECTIONS = (
    "lineages",
    "strategies",
    "zone_occupancy",
)

OBSERVABILITY_OPTIONAL_SECTIONS_BY_MODE: dict[str, tuple[str, ...]] = {
    "boids": ("flocks",),
    "predator_prey": ("species",),
}


class ObservabilityCollector:
    """Collect summary-oriented simulation health samples across a run."""

    def __init__(self, mode: str) -> None:
        self._mode = mode
        self._population_samples: list[int] = []
        self._latest_snapshot: dict[str, Any] | None = None

    def record_frame(self, simulation: Simulation) -> None:
        snapshot = simulation.build_observability_snapshot()
        self._population_samples.append(int(snapshot["population"]))
        self._latest_snapshot = snapshot

    def build_summary(self) -> dict[str, Any]:
        if self._latest_snapshot is None:
            return _build_empty_observability_summary(self._mode)

        samples = self._population_samples or [int(self._latest_snapshot["population"])]
        summary = {
            "population": {
                "min": min(samples),
                "mean": sum(samples) / len(samples),
                "max": max(samples),
            },
            "lineages": dict(self._latest_snapshot["lineages"]),
            "strategies": dict(self._latest_snapshot["strategies"]),
            "zone_occupancy": dict(self._latest_snapshot["zone_occupancy"]),
        }
        for section in OBSERVABILITY_OPTIONAL_SECTIONS_BY_MODE.get(self._mode, ()):
            if section in self._latest_snapshot:
                summary[section] = dict(self._latest_snapshot[section])
        return summary


def run_benchmark(
    scenario_id: str,
    *,
    seconds: float,
    output_path: str | Path,
) -> dict[str, Any]:
    """Run a bounded benchmark scenario and write a JSON summary."""
    scenario = get_scenario(scenario_id)
    output = Path(output_path)

    random.seed(scenario.seed)
    started_at = datetime.now(timezone.utc).isoformat()

    pygame.init()
    try:
        screen = pygame.display.set_mode((scenario.width, scenario.height))
        pygame.display.set_caption(f"Primordial Benchmark: {scenario.id}")

        settings = Settings()
        apply_scenario_settings(settings, scenario)

        simulation = Simulation(scenario.width, scenario.height, settings)
        renderer = Renderer(screen, settings, debug=False)
        clock = pygame.time.Clock()
        runtime_loop = _create_fixed_step_loop_state()
        timing_collector = LoopTimingCollector(retain_samples=True)
        observability = ObservabilityCollector(scenario.mode)

        elapsed_wall_seconds = run_bounded_session(
            simulation,
            renderer,
            clock,
            runtime_loop,
            timing_collector,
            duration_seconds=seconds,
            target_fps=settings.target_fps,
            frame_observer=observability.record_frame,
        )
        if timing_collector.frame_count == 0:
            observability.record_frame(simulation)
        payload = _build_benchmark_payload(
            scenario=scenario,
            seconds_requested=seconds,
            started_at=started_at,
            elapsed_wall_seconds=elapsed_wall_seconds,
            timing_summary=timing_collector.build_summary(
                elapsed_wall_seconds=elapsed_wall_seconds,
                runtime_loop=runtime_loop,
            ),
            observability_summary=observability.build_summary(),
            settings=settings,
        )
    finally:
        pygame.quit()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload
def _build_benchmark_payload(
    *,
    scenario: BenchmarkScenario,
    seconds_requested: float,
    started_at: str,
    elapsed_wall_seconds: float,
    timing_summary: dict[str, Any],
    observability_summary: dict[str, Any],
    settings: Settings,
) -> dict[str, Any]:
    timing_ms = timing_summary["timing_ms"]
    return {
        "scenario": {
            "id": scenario.id,
            "mode": scenario.mode,
            "seed": scenario.seed,
            "width": scenario.width,
            "height": scenario.height,
        },
        "run": {
            "started_at": started_at,
            "duration_seconds": elapsed_wall_seconds,
            "duration_seconds_requested": seconds_requested,
            "target_fps": settings.target_fps,
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "pygame": pygame.version.ver,
        },
        "performance": {
            "frames_rendered": timing_summary["frames_rendered"],
            "effective_fps_overall": timing_summary["effective_fps_overall"],
            "sim_steps_total": timing_summary["sim_steps_total"],
            "sim_steps_per_render_frame": timing_summary["sim_steps_per_render_frame"],
            "frame_ms": timing_ms["frame"],
            "sim_ms": timing_ms["sim"],
            "render_ms": timing_ms["render"],
            "present_ms": timing_ms["present"],
            "pacing_ms": timing_ms["pacing"],
            "clamp_drop": timing_summary["clamp_drop"],
            "runtime_loop": timing_summary["runtime_loop"],
        },
        "observability": observability_summary,
    }


def _build_empty_observability_summary(mode: str) -> dict[str, Any]:
    empty_zones = {zone_type: 0 for zone_type in ZONE_DEFINITIONS}
    empty_zones["unzoned"] = 0
    summary: dict[str, Any] = {
        "population": {"min": 0, "mean": 0.0, "max": 0},
        "lineages": {"active": 0},
        "strategies": {"hunters": 0, "grazers": 0, "opportunists": 0},
        "zone_occupancy": empty_zones,
    }
    for section in OBSERVABILITY_OPTIONAL_SECTIONS_BY_MODE.get(mode, ()):
        if section == "species":
            summary[section] = {"predators": 0, "prey": 0}
        elif section == "flocks":
            summary[section] = {"count": 0, "average_size": 0.0, "largest": 0, "loners": 0}
    return summary
