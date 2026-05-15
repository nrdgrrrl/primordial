"""Bounded runtime session loop shared by profiling and benchmarks."""

from __future__ import annotations

import time
from typing import Callable

import pygame

from primordial.rendering import Renderer
from primordial.simulation import Simulation

from .fixed_step import FixedStepLoopState, advance_fixed_step_frame
from .timing import LoopTimingCollector, build_frame_metrics


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

        sim_ms, sim_steps, clamp_frames, dropped_seconds = advance_fixed_step_frame(
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
        if frame_observer is not None:
            frame_observer(simulation)
        if quit_requested:
            break

    return max(0.0, time.perf_counter() - start_time)
