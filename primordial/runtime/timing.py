"""Frame timing payloads and aggregate loop timing summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .fixed_step import FixedStepLoopState


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

    def get_samples(self, name: str) -> list[float]:
        """Return a copy of retained samples for the requested metric."""
        return list(self._samples[name])

    def _summarize_samples(self, name: str) -> dict[str, float | int]:
        samples = self._samples[name]
        if not samples:
            return {
                "count": 0,
                "min": 0.0,
                "mean": 0.0,
                "median": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "max": 0.0,
            }
        ordered = sorted(samples)
        p95_index = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        p99_index = min(len(ordered) - 1, int(0.99 * (len(ordered) - 1)))
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
            "p95": ordered[p95_index],
            "p99": ordered[p99_index],
            "max": ordered[-1],
        }


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

