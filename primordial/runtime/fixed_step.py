"""Fixed-step simulation loop state and stepping helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from primordial.settings import Settings
    from primordial.simulation import Simulation

FIXED_SIM_TIMESTEP_SECONDS = 1.0 / 60.0
MAX_SIM_STEPS_PER_OUTER_FRAME = 5
MAX_ACCUMULATED_SIM_SECONDS = (
    FIXED_SIM_TIMESTEP_SECONDS * MAX_SIM_STEPS_PER_OUTER_FRAME
)


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
    buffered_active_attacks: list[
        tuple[float, float, float, float, str, float, float]
    ] = field(
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


def _get_effective_mode_param(
    settings: Settings | object,
    key: str,
    fallback: int | float | bool,
) -> int | float | bool:
    """Resolve an active-mode override with a safe fallback."""
    mode = getattr(settings, "sim_mode", "")
    mode_params = getattr(settings, "mode_params", {})
    if isinstance(mode_params, dict):
        values = mode_params.get(mode)
        if isinstance(values, dict) and key in values:
            return values[key]
    return fallback


def _get_effective_target_fps(settings: Settings | object) -> int:
    """Return the active mode's effective presentation cap."""
    fallback = max(1, int(getattr(settings, "target_fps", 60)))
    return max(1, int(_get_effective_mode_param(settings, "target_fps", fallback)))


def _get_simulation_tick_hz(settings: Settings | object) -> float:
    """Return the active mode's fixed simulation rate."""
    return max(
        1.0,
        float(_get_effective_mode_param(settings, "simulation_tick_hz", 60)),
    )


def _build_fixed_step_loop_config(
    settings: Settings | object | None = None,
) -> FixedStepLoopConfig:
    """Build timing config using the active mode's simulation rate when available."""
    if settings is None:
        return FixedStepLoopConfig()
    fixed_timestep_seconds = 1.0 / _get_simulation_tick_hz(settings)
    return FixedStepLoopConfig(
        fixed_timestep_seconds=fixed_timestep_seconds,
        max_sim_steps_per_outer_frame=MAX_SIM_STEPS_PER_OUTER_FRAME,
        max_accumulated_seconds=(
            fixed_timestep_seconds * MAX_SIM_STEPS_PER_OUTER_FRAME
        ),
    )


def _create_fixed_step_loop_state(
    settings: Settings | object | None = None,
) -> FixedStepLoopState:
    """Build the shared loop scaffold used by runtime and profile paths."""
    return FixedStepLoopState(config=_build_fixed_step_loop_config(settings))


def _simulation_timing_is_suppressed(
    simulation: Simulation,
    transition_dir: int = 0,
    transition_alpha: int = 0,
) -> bool:
    """Return whether fixed-step debt should be frozen for the current frame."""
    return (
        bool(getattr(simulation, "paused", False))
        or bool(getattr(simulation, "predator_prey_game_over_active", False))
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

