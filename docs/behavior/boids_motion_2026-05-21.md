# Boids Behavior Tuning Report - 2026-05-21

This pass focused on boids motion quality after the recent performance work made
the live behavior readable at 30 Hz.

## Pre-Change Diagnosis

- Live seeded runs on the active X11 display path confirmed the current boids
  mode collapsed into a few dense drifting balls by 30 to 60 seconds.
- The main control-loop causes were in
  `primordial/simulation/simulation.py`:
  - cohesion always pulled toward a raw local centroid, even when the local
    neighborhood was already crowded;
  - separation was too soft at very close range, so compressed groups did not
    reopen once they collapsed;
  - alignment was strong and uniform enough that dense groups moved like rigid
    pucks;
  - the neighbor/assignment graph was permissive enough to let sparse bridges
    merge visually separate groups into mega-flocks;
  - the boids energy model rewarded aligned local groups without clearly
    penalizing overcrowding or asking for moderate spacing.
- Protected areas explicitly left alone:
  - predator_prey behavior, adaptive dials, persistence, and game-over logic
  - the recent boids neighbor-cache performance structure
  - the intended 30 FPS / 30 Hz boids cadence

## Behavior Changes

1. Tightened boids flock-link assignment so sparse bridge chains do not merge
   visually separate groups into one giant flock for HUD/flock-line purposes.
2. Rebalanced the local boids force mix:
   - stronger near-contact separation with a steeper close-range boost
   - softer density-aware alignment
   - density-aware cohesion that stops pulling hard once a neighborhood is
     already compact
   - smooth low-frequency per-creature wander variation so schools bend, shear,
     and split instead of moving like rigid solids
3. Adjusted the boids initial spawn ranges to reduce blob-prone sensing while
   keeping heritable variation across speed, spacing, conformity, and cohesion.
4. Reworked boids energy/reproduction around moderate local formation quality:
   - reward alignment plus readable spacing
   - penalize crowding more clearly
   - add an explicit overpopulation tax near and above carrying capacity
   - gate reproduction to moderate, non-overcrowded local neighborhoods
5. Added boids behavior diagnostics to `Simulation` so seeded runs can report:
   - nearest-neighbor spacing
   - flock-size distribution bands
   - largest-flock share
   - loner count
   - alignment mean
   - separation/cohesion force means
   - overcrowded and dense-cluster shares

## Before / After Metrics

Offline seeded behavior metrics, seed `130363`, `1280x720`, sampled every 5
sim-seconds:

### Default boids, 90 seconds

- Population end: `26 -> 275`
- Mean flock count: `1.84 -> 13.63`
- Largest-flock share mean: `0.697 -> 0.199`
- Nearest-neighbor mean: `18.92 -> 29.79`
- Overcrowded share mean: `0.985 -> 0.273`
- Dense-cluster share mean: `0.790 -> 0.029`
- Loner mean: `0.0 -> 8.42`
- End-of-run flock bands:
  - before: `2 medium`
  - after: `5 small, 2 medium, 5 large, 1 huge`

Interpretation:

- The old run spent almost all of its time overcrowded, with nearly the whole
  population packed into a few dense groups.
- The tuned run keeps noticeably more spacing, produces several flock sizes at
  once, and reduces dense-cluster occupancy sharply instead of collapsing into a
  couple of balls.

### Stress boids, 60 seconds

- Population end: `210 -> 280`
- Mean flock count: `2.38 -> 18.62`
- Largest-flock share mean: `0.758 -> 0.240`
- Nearest-neighbor mean: `18.48 -> 30.13`
- Overcrowded share mean: `0.992 -> 0.261`
- Dense-cluster share mean: `0.971 -> 0.045`
- Loner mean: `0.0 -> 9.92`
- End-of-run flock bands:
  - before: `2 large, 1 huge`
  - after: `4 small, 9 medium, 4 large`

Interpretation:

- The stress case no longer resolves into a few giant dense masses.
- It now sustains a mix of medium and large schools with much lower dense-clump
  occupancy.

Source artifacts:

- `docs/behavior/boids_motion_2026-05-21/before/boids_behavior_metrics_before.json`
- `docs/behavior/boids_motion_2026-05-21/after/boids_behavior_metrics_after.json`

## Graphical Comparison

Required live graphical runs were captured on the active X11 display path.

Clearly named before/after screenshot sets:

- Before default 90s:
  `docs/behavior/boids_motion_2026-05-21/before/screenshots/boids/boids_default_live_90s_before__boids__seed130363/`
- After default 90s:
  `docs/behavior/boids_motion_2026-05-21/after/screenshots/boids/boids_default_live_90s_after__boids__seed130363/`
- Before stress 60s:
  `docs/behavior/boids_motion_2026-05-21/before/screenshots/boids/boids_stress_live_60s_before__boids__seed130363/`
- After stress 60s:
  `docs/behavior/boids_motion_2026-05-21/after/screenshots/boids/boids_stress_live_60s_after__boids__seed130363/`

Representative screenshots:

- Default before: `t0010s.png`, `t0030s.png`, `t0060s.png`, `t0090s.png`
- Default after: `t0010s.png`, `t0030s.png`, `t0060s.png`, `t0090s.png`
- Stress before: `t0010s.png`, `t0030s.png`, `t0060s.png`
- Stress after: `t0010s.png`, `t0030s.png`, `t0060s.png`

Observed visual difference:

- Before: a few compact balls formed quickly, drifted as rigid bodies, and left
  much of the screen empty.
- After: schools stay looser, stretch into short arcs and strings, split into
  multiple groups, and keep individuals readable inside the group motion.

## Graphical Performance

Live seeded boids runs with the tuned behavior:

- Default boids, 90s, seed `130363`
  - effective FPS overall: `29.84`
  - frame ms mean: `32.97`
  - sim ms mean: `10.76`
  - render ms mean: `14.76`
  - population mean / max: `236.12 / 276`
- Stress boids, 60s, seed `130363`, `initial_population = 220`,
  `max_population = 320`
  - effective FPS overall: `29.07`
  - frame ms mean: `33.73`
  - sim ms mean: `13.68`
  - render ms mean: `16.83`
  - population mean / max: `275.07 / 320`

Interpretation:

- Default boids remains effectively on target at 30 FPS.
- The stress case stays close to target and no longer shows the visible startup
  collapse seen before the earlier performance fix.

Source artifacts:

- `docs/behavior/boids_motion_2026-05-21/after/results.json`
- `docs/behavior/boids_motion_2026-05-21/after/per_run/`
- `docs/behavior/boids_motion_2026-05-21/after/frame_samples/`

## Shared-Code Regression Check

Predator-prey default, 90 seconds, seed `104729`, graphical loop with adaptive
tuning disabled:

- effective FPS overall: `30.04`
- frame ms mean: `33.21`
- sim ms mean: `7.80`
- render ms mean: `7.56`

Result:

- No meaningful predator-prey regression was observed from the shared
  `simulation.py` edits.

Source artifacts:

- `docs/behavior/boids_motion_2026-05-21/regression_predator_prey/predator_prey_default_90s.json`

## Remaining Concerns

- The tuned boids mode now favors multiple readable schools, but some seeds
  still spend time in long bridge-like strings between groups. The current
  result is much closer to the intended feel, but there is still room to make
  those bridge states break and recombine more elegantly.
- The boids sim cost is higher than the pre-tuning behavior because more
  creatures survive. Default remains on target, but stress headroom is narrower
  than before and should be watched if boids density rises again.
