# Task: M1.03 Timing Instrumentation and Summary Hooks

## Title
Add Core Loop Timing Instrumentation and Structured Summary Output

## Purpose
Create the instrumentation surfaces required by Milestone 1 so sim time, render time, total frame time, frame pacing, and sim-steps-per-render-frame can be measured consistently in both interactive and profile-driven runs.

## Scope
- Add a lightweight timing collector for outer-loop metrics.
- Define a stable metrics payload for runtime/debug consumption.
- Add summary aggregation suitable for benchmark-like comparison across runs.
- Add a machine-readable output path for `--profile` timing summaries.
- Reuse existing renderer timing data where practical rather than duplicating timing logic.

## Affected Files / Subsystems
- `primordial/main.py`
- `primordial/rendering/renderer.py`
- `primordial/rendering/hud.py` if debug lines need narrow extension

Subsystems:
- outer loop timing
- debug timing surface
- renderer timing exposure
- profile summary/report output

## Implementation Notes
- Measure at minimum:
  - event handling time
  - total sim batch time per outer frame
  - render time
  - present/flip time
  - total frame time
  - effective FPS
  - sim steps executed for that rendered frame
  - clamp/drop counts
- Keep per-frame measurement cheap. Aggregate in memory and emit summaries at the end of a run or through existing debug paths.
- Prefer a single metrics structure that can feed both debug display and structured profile output.
- Reuse the renderer’s existing sub-phase breakdown as an internal source, but treat total render time as the primary Milestone 1 metric.
- Avoid adding high-volume logging.
- If percentiles are included, compute them from collected samples without introducing heavy dependencies.

## Validation Steps
- Confirm instrumentation can run with debug mode off without meaningful overhead or log noise.
- Confirm debug mode still displays timing information cleanly.
- Confirm `--profile` can emit structured timing summary output alongside existing profile artifacts.
- Confirm instrumentation fields are comparable across runs and are not debug-only.

## Out Of Scope
- Fixed-step loop behavior itself
- New dashboards
- Full benchmark harness creation
- Renderer rewrite
- Ecology telemetry
