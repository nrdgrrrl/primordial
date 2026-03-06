from __future__ import annotations

import tempfile
import unittest
from itertools import chain, repeat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from primordial.main import (
    FIXED_SIM_TIMESTEP_SECONDS,
    MAX_ACCUMULATED_SIM_SECONDS,
    MAX_SIM_STEPS_PER_OUTER_FRAME,
    LoopTimingCollector,
    _advance_fixed_step_frame,
    _create_fixed_step_loop_state,
    _run_profile_session,
    _simulation_timing_is_suppressed,
)


class FakeSimulation:
    def __init__(self) -> None:
        self.paused = False
        self.step_calls = 0
        self._pending_attacks: list[tuple[float, float, float, float, float]] = []
        self.restored_attacks: list[tuple[float, float, float, float, float]] = []

    def step(self) -> None:
        self.step_calls += 1
        marker = float(self.step_calls)
        self._pending_attacks = [(marker, marker, marker, marker, marker)]

    def drain_active_attacks(self) -> list[tuple[float, float, float, float, float]]:
        attacks = self._pending_attacks
        self._pending_attacks = []
        return attacks

    def restore_active_attacks(
        self,
        attacks: list[tuple[float, float, float, float, float]],
    ) -> None:
        self.restored_attacks.extend(attacks)


class FakeRenderer:
    def __init__(self) -> None:
        self.draw_calls = 0
        self.debug_payloads: list[dict[str, float]] = []

    def set_external_debug_metrics(self, metrics: dict[str, float]) -> None:
        self.debug_payloads.append(dict(metrics))

    def draw(self, simulation: FakeSimulation) -> dict[str, float]:
        self.draw_calls += 1
        return {"draw_total_ms": 1.0}


class FakeClock:
    def __init__(self) -> None:
        self.tick_calls: list[int] = []

    def tick(self, fps: int) -> None:
        self.tick_calls.append(fps)


class FixedStepLoopTests(unittest.TestCase):
    def test_catch_up_runs_multiple_sim_steps_in_one_frame(self) -> None:
        runtime_loop = _create_fixed_step_loop_state()
        runtime_loop.last_tick_seconds = 0.0
        simulation = FakeSimulation()

        sim_ms, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=True,
            now=FIXED_SIM_TIMESTEP_SECONDS * 2.4,
        )

        self.assertGreaterEqual(sim_ms, 0.0)
        self.assertEqual(sim_steps, 2)
        self.assertEqual(simulation.step_calls, 2)
        self.assertEqual(clamp_frames, 0)
        self.assertEqual(dropped_seconds, 0.0)
        self.assertAlmostEqual(
            runtime_loop.accumulator_seconds,
            FIXED_SIM_TIMESTEP_SECONDS * 0.4,
            places=9,
        )

    def test_frame_rate_decoupling_preserves_simulated_progress(self) -> None:
        dt = FIXED_SIM_TIMESTEP_SECONDS
        epsilon = dt * 0.01

        def run_marks(marks: list[float]) -> int:
            runtime_loop = _create_fixed_step_loop_state()
            runtime_loop.last_tick_seconds = 0.0
            simulation = FakeSimulation()
            total_steps = 0
            for now in marks:
                _, sim_steps, _, _ = _advance_fixed_step_frame(
                    simulation,
                    runtime_loop,
                    allow_simulation=True,
                    now=now,
                )
                total_steps += sim_steps
            return total_steps

        fast_cadence_steps = run_marks(
            [dt + epsilon, (2 * dt) + epsilon, (3 * dt) + epsilon, (4 * dt) + epsilon]
        )
        slow_cadence_steps = run_marks([(2 * dt) + epsilon, (4 * dt) + epsilon])

        self.assertEqual(fast_cadence_steps, 4)
        self.assertEqual(slow_cadence_steps, 4)

    def test_clamp_drops_excess_time_and_reports_metrics(self) -> None:
        runtime_loop = _create_fixed_step_loop_state()
        runtime_loop.last_tick_seconds = 0.0
        simulation = FakeSimulation()
        overflow_seconds = FIXED_SIM_TIMESTEP_SECONDS * 2.0

        _, sim_steps, clamp_frames, dropped_seconds = _advance_fixed_step_frame(
            simulation,
            runtime_loop,
            allow_simulation=True,
            now=MAX_ACCUMULATED_SIM_SECONDS + overflow_seconds,
        )

        self.assertEqual(sim_steps, MAX_SIM_STEPS_PER_OUTER_FRAME)
        self.assertEqual(simulation.step_calls, MAX_SIM_STEPS_PER_OUTER_FRAME)
        self.assertEqual(clamp_frames, 1)
        self.assertAlmostEqual(dropped_seconds, overflow_seconds, places=9)
        self.assertAlmostEqual(runtime_loop.accumulator_seconds, 0.0, places=9)

    def test_mode_transition_suppresses_simulation_for_entire_fade(self) -> None:
        simulation = FakeSimulation()

        self.assertTrue(_simulation_timing_is_suppressed(simulation, transition_dir=1, transition_alpha=4))
        self.assertTrue(_simulation_timing_is_suppressed(simulation, transition_dir=-1, transition_alpha=120))
        self.assertFalse(_simulation_timing_is_suppressed(simulation, transition_dir=0, transition_alpha=0))

    def test_profile_loop_keeps_render_once_per_frame_with_fixed_step_catch_up(self) -> None:
        runtime_loop = _create_fixed_step_loop_state()
        runtime_loop.last_tick_seconds = 0.0
        simulation = FakeSimulation()
        renderer = FakeRenderer()
        clock = FakeClock()
        timing_collector = LoopTimingCollector(retain_samples=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = SimpleNamespace(
                target_fps=30,
                config_path=Path(temp_dir) / "config.toml",
            )
            perf_counter_values = chain(
                [
                    0.0,
                    0.001,
                    0.002,
                    0.003,
                    0.004,
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5),
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5) + 0.001,
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5) + 0.002,
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5) + 0.003,
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5) + 0.004,
                    (FIXED_SIM_TIMESTEP_SECONDS * 2.5) + 0.005,
                    61.0,
                    61.5,
                ],
                repeat(61.5),
            )

            with patch(
                "primordial.main.pygame.event.get",
                return_value=[],
            ), patch(
                "primordial.main.pygame.display.flip",
            ), patch(
                "primordial.main.time.perf_counter",
                side_effect=lambda: next(perf_counter_values),
            ):
                profile_base = _run_profile_session(
                    simulation,
                    renderer,
                    clock,
                    settings,
                    runtime_loop,
                    timing_collector,
                )

            self.assertEqual(simulation.step_calls, 2)
            self.assertEqual(renderer.draw_calls, 1)
            self.assertEqual(clock.tick_calls, [30])
            self.assertEqual(timing_collector.frame_count, 1)
            self.assertEqual(timing_collector.total_sim_steps, 2)
            self.assertEqual(timing_collector.latest_frame.sim_steps, 2)
            self.assertEqual(len(simulation.restored_attacks), 2)
            self.assertTrue(renderer.debug_payloads)
            self.assertEqual(renderer.debug_payloads[-1]["sim_steps"], 2.0)
            self.assertTrue(Path(profile_base).with_suffix(".pstats").exists())
            self.assertTrue(Path(profile_base).with_suffix(".txt").exists())
            self.assertTrue(Path(profile_base).with_suffix(".timing.json").exists())


if __name__ == "__main__":
    unittest.main()
