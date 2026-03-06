# Milestone 2: Performance Headroom and Lightweight Observability

## Purpose

Milestone 2 exists to buy a modest amount of performance headroom now that Milestone 1 has protected simulation timing, and to add a small amount of low-cost telemetry so future simulation work is not tuned blind.

This milestone should stay narrow. It is not a rendering rewrite, a benchmark framework expansion, or a general observability platform.

## Goals

- Improve one or two measured hotspots enough to create practical runtime headroom.
- Add a lightweight benchmark/summary path that can be run non-interactively.
- Emit a small structured observability payload that is comparable across runs.
- Preserve simulation correctness while making performance work measurable.

## In Scope

### 1. One targeted performance pass

Use measured data from the existing profile output to optimize a small number of high-value hotspots.

Good candidates:
- alpha-heavy rendering passes
- kin/flock line drawing
- shimmer/trail work
- one dense simulation kernel if it is still a proven bottleneck after measurement

The implementation should stay bounded and reviewable.

### 2. A scriptable benchmark path

Add a small repository-local benchmark script, expected to live under `tools/`, that can:
- run a bounded scenario for a fixed duration
- write structured JSON output to a known path
- expose enough timing information to compare runs

This does not need to replace `--profile`. It only needs to provide a fast, repeatable milestone check surface.

### 3. Tier 1 observability summary

Add low-cost, run-level observability fields that help answer whether the simulation is healthy.

Target fields should stay simple:
- active lineage count
- basic strategy ratios or counts
- basic zone occupancy summary
- population min/mean/max
- boids/flock summary when relevant

The output should be summary-oriented, not per-frame logging.

### 4. Correctness protection

Performance work must not break the fixed-step loop, event behavior, or basic simulation invariants.

Tests added in this milestone should focus on:
- preserving simulation progression semantics
- validating observability output shape
- validating benchmark output shape

## Non-Goals

- GPU renderer migration
- process/thread architecture changes
- broad simulation redesign
- deep ecology additions
- dashboards, live graphs, or external telemetry systems
- replacing the existing profile flow
- large documentation systems or milestone sub-task trees

## Acceptance Shape

Milestone 2 is complete when:

```bash
python tools/run_milestone.py
```

passes all checks defined in [`docs/acceptance_M2.yaml`](/home/victoria/projects/primordial/docs/acceptance_M2.yaml).

Those checks should verify:
- regression tests still pass
- the benchmark script exists and runs
- benchmark JSON is produced in a known location
- benchmark JSON contains the required timing and observability fields
- performance thresholds for the selected scenarios are met
- clamp/drop behavior remains healthy in the benchmark scenarios

## Implementation Guidance

- Prefer one small optimization that clearly moves measured numbers over multiple speculative changes.
- Prefer summary JSON over verbose logs.
- Prefer deterministic or bounded benchmark scenarios over ad hoc manual profiling.
- Keep any new instrumentation cheap enough that it can stay enabled in the benchmark path without distorting results materially.
- Make meaningful git commits as coherent chunks of work land.
- Prefer commits that reflect actual milestone progress, such as benchmark harness creation, observability output, or a measured optimization, rather than one large final commit.

## Exit Criteria

Milestone 2 should leave the repository with:
- one clear benchmark entry point
- one clear JSON output shape for performance and observability summaries
- one or two measurable improvements backed by automated checks
- confidence that simulation correctness is still intact
