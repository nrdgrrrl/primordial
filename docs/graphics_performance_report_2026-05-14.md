# Graphics Performance Report - 2026-05-14

This note records the first preserved predator/prey GPU-rendering baseline after
the 30 Hz architecture change and the OpenGL renderer landing.

## Current Runtime Shape

- `predator_prey` now defaults to `render_backend = "gpu"`.
- `predator_prey` runs at `30 Hz` render and `30 Hz` simulation without changing
  the internal ecology rules or dials.
- `pygame` still owns window creation, display mode changes, input handling,
  overlays, screenshots, and renderer fallback.
- Non-`predator_prey` modes still use the existing `pygame` renderer path.
- The `pygame` renderer remains the fallback path when OpenGL is unavailable or
  GPU initialization fails.

## Benchmark Baseline

Source artifact:

- `benchmark_outputs/gpu_predator_prey_extended_20260514_143306/extended_summary.json`

Captured on the live display path at `1920x1080` with `10` seeds and `180`
seconds per seed.

- Backend: `gpu`
- Mean FPS: `29.974`
- Worst FPS: `29.961`
- Mean render: `7.77 ms`
- Worst render: `8.01 ms`
- Mean sim: `7.12 ms`
- Mean pacing idle: `17.64 ms`
- Mean active work (`render + sim`): `14.89 ms`
- Approx headroom at `30 Hz`: `18.4 ms/frame`
- Approx frame-budget headroom: `55%`

## What The Numbers Mean

The important result is that predator/prey is no longer limited by the old
CPU-heavy `pygame.Surface` world compositor. At the current `30 Hz` target, the
renderer and simulation together consume less than half of the `33.3 ms` frame
budget on this machine, leaving meaningful room for future work.

The remaining render-side hotspot is **CPU snapshot assembly**, not GPU drawing:

- Mean `snapshot_ms`: `5.57 ms`
- Mean `trails_ms`: `0.88 ms`
- Mean `creatures_ms`: `0.67 ms`

That distinction matters. The GPU passes are already relatively cheap. The next
graphics optimization opportunity is reducing Python-side snapshot construction
and upload preparation. That work is intentionally **not** part of this pass.

## Scope Boundaries

This GPU migration is intentionally narrow:

- No ecology dial changes
- No predator/prey balance changes
- No adaptive tuning behavior changes
- No simulation feature expansion
- No removal of the `pygame` fallback path

The goal of this milestone is preservation and regression protection around the
new 30 Hz GPU baseline, not a second rewrite.

## Validation Added Alongside This Baseline

- `tools/check_predator_prey_backend_parity.py`
  - Fixed-seed, fixed-tick parity check between `pygame` and `gpu`
  - Compares ecology outcomes by simulation ticks, not wall-clock time
  - Also compares the final global RNG state digest to catch render-side RNG
    contamination
- `tools/smoke_gpu_predator_prey.py`
  - Lightweight GPU initialization and render smoke
  - Confirms the backend reports `gpu`, a frame renders successfully, timing
    fields are present, and a screenshot can be saved

## Limitations

The backend parity check and GPU smoke require a live display and working
OpenGL context. They are not a replacement for the headless test suite. In CI
or dummy-SDL environments, the project still validates the `pygame` fallback
path and benchmark artifact shape through the existing automated tests.
