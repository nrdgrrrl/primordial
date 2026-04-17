# Graphics Performance Report - 2026-04-17

This report captures the result of the live graphical benchmark run and the
implications for the next optimization pass.

## Benchmark Context

- Display path: `live_display`
- Visible display: yes
- SDL driver: `x11`
- Native desktop resolution: `1920x1080`
- Benchmark command: `tools/run_graphical_benchmarks.py --skip-profiles`
- Completed runs: `42`
- Collected profiles: `0`

The benchmark covered:

- Baseline fullscreen sweep: `energy`, `predator_prey`, `boids`, `drift`
- Predator-prey extended fullscreen sweep
- Predator-prey transition sweep
- Predator-prey soak sweep

## High-Level Result

The graphics-side changes materially improved live performance without reducing
visual quality.

The biggest confirmed wins were:

- `predator_prey` FPS improved from `42.19` to `53.33`
- `energy` FPS improved from `49.60` to `60.30`
- `boids` FPS improved from `38.10` to `48.68`
- `drift` FPS improved slightly from `29.38` to `30.63`

The important secondary result is that the render path remains the dominant
bottleneck. Simulation is still visible in the timings, but it does not explain
the missed frame budget in the graphics-bound modes.

## Before / After Comparison

### Baseline fullscreen sweep

- FPS: `40.18` -> `47.70`
- Frame time: `24.68 ms` -> `20.89 ms`
- Render time: `18.31 ms` -> `12.45 ms`
- Sim time: `4.46 ms` -> `4.74 ms`
- Present time: `1.18 ms` -> `1.16 ms`

### Predator-prey extended fullscreen sweep

- FPS: `42.43` -> `54.83`
- Frame time: `23.38 ms` -> `18.04 ms`
- Render time: `16.83 ms` -> `11.02 ms`
- Sim time: `4.67 ms` -> `5.64 ms`
- Present time: `1.17 ms` -> `1.13 ms`

### Predator-prey transition sweep

- FPS: `41.32` -> `52.95`
- Frame time: `23.90 ms` -> `18.59 ms`
- Render time: `17.14 ms` -> `11.60 ms`
- Sim time: `4.76 ms` -> `5.75 ms`
- Present time: `1.00 ms` -> `0.98 ms`

### Predator-prey soak sweep

- FPS: `39.18` -> `53.28`
- Frame time: `25.36 ms` -> `18.59 ms`
- Render time: `18.13 ms` -> `11.30 ms`
- Sim time: `5.35 ms` -> `6.05 ms`
- Present time: `1.17 ms` -> `1.13 ms`

## Interpretation

The benchmark data supports the following conclusions:

1. Rendering was the main bottleneck before the changes.
2. Rendering is still the main bottleneck after the changes.
3. The implemented renderer work was effective because render time fell by
   roughly one third across the main workloads.
4. The simulation side did not become the dominant bottleneck. In some runs,
   simulation time increased slightly, but the frame budget is still driven by
   graphics work.
5. Presentation cost stayed small and stable around `~1 ms`, so the final
   screen copy / present path is not the primary problem.

The current benchmark therefore supports continuing to optimize the renderer
instead of switching focus to native simulation kernels.

## Current Mode-Level Findings

- `boids`: mixed cost, with rendering and simulation both contributing
- `drift`: rendering-dominated
- `energy`: rendering-dominated
- `predator_prey`: rendering-dominated

For `predator_prey`, the important point is that the workload is now much
closer to the 60 FPS target, but it is still not consistently there at native
resolution in live display mode.

## What Was Likely Gained

The changes appear to have helped by removing avoidable graphics overhead:

- direct-to-screen rendering when the display and logical sizes match
- cached static background composition
- tiled trail rendering rather than full-surface trail compositing
- expanded rotated glyph caching
- better visibility into render-stage timing

These are exact-preserving changes. They reduce CPU-side compositing work
without lowering image quality.

## Recommended Next Steps

The next pass should stay on the graphics side and should be narrow and
measurement-driven.

1. Profile the remaining render hotspots in the worst offenders, especially
   `drift` and the long-tail `predator_prey` runs.
2. Break render time down further into sub-stage costs inside creature drawing,
   zone composition, and any remaining per-frame alpha work.
3. Look for redundant allocations, conversions, and repeated surface
   composition in the draw path.
4. Keep quality unchanged. Do not use reduced resolution, shorter trails,
   cheaper effects, or lower fidelity as a substitute for a faster renderer.
5. Re-run the same benchmark matrix after each focused renderer change so the
   effect remains attributable.

## Evidence

The canonical benchmark artifacts are under:

- `benchmark_outputs/graphical_benchmark_20260417_145334/`
- `benchmark_outputs/graphical_benchmark_20260402_123041/`

The current benchmark summary explicitly reports the new live-display numbers
and confirms that rendering remains the dominant cost.
