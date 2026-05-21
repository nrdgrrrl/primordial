# Boids Graphical Performance Report - 2026-05-21

This report records the live-display investigation and fix pass for boids mode.
All acceptance evidence below comes from real pygame windows on the active
display path at `1920x1080`, not SDL dummy mode.

## Pre-Change Diagnosis

- Top bottleneck: boids startup was primarily simulation-bound in
  `primordial/simulation/simulation.py`, especially
  `_build_boid_neighbor_cache()` and `_update_flock_assignments()`.
- Amplifier: the fixed-step loop in `primordial/runtime/fixed_step.py` was
  forced into 4 to 5 boids sim steps per rendered frame during startup, which
  produced visible catch-up stutter and frequent accumulator clamp drops.
- Secondary render cost: boids flock lines were not a hotspot. The measured
  pygame render cost came mostly from trails and creature draws in
  `primordial/rendering/renderer.py` and `primordial/rendering/themes.py`.
- Protected path status: predator_prey was already stable on its dedicated GPU
  renderer path at ~30 FPS and was treated as regression-sensitive.

Representative pre-change live profile findings (`boids_default_profile_live_60s_pre`):

- `_build_boid_neighbor_cache`: `28.804s` cumulative
- `_update_flock_assignments`: `11.451s` cumulative
- `Renderer.draw`: `9.828s` cumulative
- `_draw_creature_trails`: `5.115s` cumulative

## Changes Made

1. Replaced the old boids neighbor-cache plus separate flock-BFS path with one
   pairwise pass over the existing spatial buckets.
   Files: `primordial/simulation/simulation.py`
2. Made boids mode explicitly target `30 FPS` and `30 Hz` fixed-step timing so
   the mode stays pinned to the intended cadence instead of chasing a 60 Hz
   path it cannot hold at startup density.
   Files: `primordial/config/defaults.toml`, `primordial/scenarios.py`,
   `tests/test_fixed_step_loop.py`, `tests/test_benchmark_observability.py`
3. Reused per-frame creature render state across trail and body passes and
   expanded the ocean glow cache to reduce repeated pygame work without
   removing visuals.
   Files: `primordial/rendering/renderer.py`,
   `primordial/rendering/themes.py`, `tests/test_renderer_caches.py`

## Before / After

### Boids Default, Live, 90s, fullscreen, seed `130363`

Before:

- FPS mean / median / 1% low / min: `58.22 / 62.03 / 8.50 / 6.52`
- Startup 0-10s FPS mean: `17.28`
- Steady-state FPS mean: `59.52`
- frame ms p50 / p95 / p99: `16.12 / 48.05 / 110.01`
- sim ms mean: `6.68`
- render ms mean: `7.71`
- population mean / max: `79.40 / 254`

After:

- FPS mean / median / 1% low / min: `30.19 / 30.25 / 24.19 / 20.04`
- Startup 0-10s FPS mean: `30.04`
- Steady-state FPS mean: `30.21`
- frame ms p50 / p95 / p99: `33.06 / 33.94 / 38.32`
- sim ms mean: `6.17`
- render ms mean: `11.73`
- population mean / max: `151.99 / 266`

Interpretation:

- The old default path looked numerically fast on average only because it was
  chasing `60 FPS` while collapsing into very bad startup stalls and deep
  1% lows.
- The fixed boids path is now visibly smooth and correctly paced around the
  intended `30 FPS` from startup onward.

### Boids Stress, Live, 60s, fullscreen, seed `130363`

Stress override:

- `initial_population = 220`
- `max_population = 320`

Before:

- FPS mean / median / 1% low / min: `52.17 / 61.11 / 6.05 / 5.00`
- Startup 0-10s FPS mean: `9.69`
- Steady-state FPS mean: `53.99`
- frame ms p50 / p95 / p99: `16.36 / 116.24 / 149.95`
- sim ms mean: `14.10`
- render ms mean: `9.98`

After:

- FPS mean / median / 1% low / min: `29.70 / 30.14 / 19.22 / 11.48`
- Startup 0-10s FPS mean: `29.65`
- Steady-state FPS mean: `29.71`
- frame ms p50 / p95 / p99: `33.18 / 39.36 / 48.60`
- sim ms mean: `9.32`
- render ms mean: `14.23`

Interpretation:

- The stress case no longer collapses into single-digit startup FPS.
- It stays very close to the 30 FPS cap with much tighter frame-time tails.

### Predator_Prey Regression Checks

Predator prey default, live, 90s, fullscreen, seed `104729`:

- Before FPS mean / startup / steady: `30.34 / 30.25 / 30.35`
- After FPS mean / startup / steady: `30.33 / 30.23 / 30.35`
- Before sim / render ms mean: `6.82 / 8.23`
- After sim / render ms mean: `6.88 / 8.43`

Predator prey debug+HUD, live, 60s, fullscreen, seed `104729`:

- Before FPS mean / startup / steady: `30.26 / 30.15 / 30.28`
- After FPS mean / startup / steady: `30.22 / 30.08 / 30.25`
- Before sim / render ms mean: `6.66 / 11.29`
- After sim / render ms mean: `6.50 / 11.29`

Conclusion:

- No meaningful predator_prey regression was observed.
- Ecology, adaptive tuning, persistence, and game-over semantics were not
  changed in this pass.

## GPU Offload Consideration

GPU offload was considered and not implemented for boids in this pass.

Why:

- The measured pre-change root cause was not flock-line drawing or a generic
  alpha compositor failure. It was boids simulation neighbor/connectivity work
  plus fixed-step catch-up amplification.
- Predator_prey already has a narrow GPU path with different snapshot and draw
  architecture. Extending that path to boids would be a larger renderer rewrite,
  not a measured first fix.
- The targeted CPU-side simulation and pacing changes were sufficient to hit
  the live `30 FPS` goal in default boids mode while keeping predator_prey
  stable.

## Artifacts

Pre-change artifacts:

- `docs/performance/prechange_graphical_2026-05-21/prechange_summary.json`
- `docs/performance/prechange_graphical_2026-05-21/raw/`
- `docs/performance/prechange_graphical_2026-05-21/screenshots/`
- `docs/performance/prechange_graphical_2026-05-21/profiles/`

Post-change artifacts:

- `docs/performance/postchange_graphical_2026-05-21/postchange_summary.json`
- `docs/performance/postchange_graphical_2026-05-21/raw/`
- `docs/performance/postchange_graphical_2026-05-21/screenshots/`
- `docs/performance/postchange_graphical_2026-05-21/profiles/`

Representative screenshots used to confirm the live path:

- Pre boids default: `docs/performance/prechange_graphical_2026-05-21/screenshots/boids_default_live_90s_pre/t0001s.png`
- Post boids default: `docs/performance/postchange_graphical_2026-05-21/screenshots/boids_default_live_90s_post/t0001s.png`
- Pre predator_prey default: `docs/performance/prechange_graphical_2026-05-21/screenshots/predator_prey_default_live_90s_pre/t0001s.png`
- Post predator_prey default: `docs/performance/postchange_graphical_2026-05-21/screenshots/predator_prey_default_live_90s_post/t0001s.png`

## Remaining Risks

- The boids stress case is much better behaved but still has tighter headroom
  than default boids. If boids population or visual density rises further, the
  next measured optimization target is still the pygame trail/body render path.
- The new boids neighbor builder is faster and avoids the old double-pass
  graph construction, but it is still the hottest boids simulation helper in
  post-change cProfile data.
