"""Runtime loop helpers for Primordial."""

from .fixed_step import (
    FIXED_SIM_TIMESTEP_SECONDS,
    FixedStepLoopConfig,
    FixedStepLoopState,
    MAX_ACCUMULATED_SIM_SECONDS,
    MAX_SIM_STEPS_PER_OUTER_FRAME,
    advance_fixed_step_frame,
    build_fixed_step_loop_config,
    create_fixed_step_loop_state,
    get_effective_target_fps,
    get_simulation_tick_hz,
    simulation_timing_is_suppressed,
)
from .session import run_bounded_session
from .timing import LoopFrameMetrics, LoopTimingCollector, build_frame_metrics

__all__ = [
    "FIXED_SIM_TIMESTEP_SECONDS",
    "FixedStepLoopConfig",
    "FixedStepLoopState",
    "LoopFrameMetrics",
    "LoopTimingCollector",
    "MAX_ACCUMULATED_SIM_SECONDS",
    "MAX_SIM_STEPS_PER_OUTER_FRAME",
    "advance_fixed_step_frame",
    "build_fixed_step_loop_config",
    "build_frame_metrics",
    "create_fixed_step_loop_state",
    "get_effective_target_fps",
    "get_simulation_tick_hz",
    "run_bounded_session",
    "simulation_timing_is_suppressed",
]
