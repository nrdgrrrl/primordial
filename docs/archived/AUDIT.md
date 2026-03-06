# Primordial Audit Report (2026-03-05)

## Summary

- Total findings: **27**
- Status totals:
  - **FIXED:** 20
  - **DEFERRED:** 5
  - **WONTFIX:** 2
- Category totals:
  - **Correctness / Robustness:** 12
  - **Performance:** 9
  - **Memory:** 3
  - **Code Quality / DX:** 3

### Most Impactful Fixes

1. **Simulation hot-path refactor (profile-driven):**
   - Energy step @ pop 150: **4.082ms → 2.005ms**
   - Full frame @ pop 150: **25.445ms → 13.425ms**
   - Boids step @ pop 150: **16.829ms → 11.887ms**
2. **Config hardening:** malformed TOML values now warn and fall back instead of crashing startup.
3. **State consistency fixes:** predation transfer now bounded by prey energy; fullscreen resize now rebuilds simulation/render spatial caches.

## Findings

| File | Category | Description | Status | Rationale |
|---|---|---|---|---|
| `primordial/config/config.py` | Correctness | Typed TOML fields were cast with raw `int/float/bool`, which could raise on wrong types or coerce incorrectly. | FIXED | Added safe coercion helpers with warnings and fallback defaults. |
| `primordial/config/config.py` | Correctness | Unknown keys were silently ignored. | FIXED | Added unknown-key warnings by section and root table. |
| `primordial/config/config.py` | Correctness | `food_max_particles` was not loaded from config. | FIXED | Added load/validate/save support. |
| `primordial/config/config.py` | Correctness | `mode_params` values were persisted as hardcoded defaults, not actual effective overrides. | FIXED | `to_toml()` now serializes effective mode override state. |
| `primordial/config/config.py` | Correctness | Runtime mode param coercion path could produce `bool("false") == True` and type drift. | FIXED | Removed runtime `type(fallback)` casting; mode overrides validated once at config load. |
| `primordial/simulation/simulation.py` | Correctness | Predation transfer could grant energy from already-dead prey in same frame. | FIXED | Energy transfer now capped by prey’s remaining energy and dead prey are skipped as targets. |
| `primordial/simulation/simulation.py` | Correctness | Predator/prey loop treated non-`predator` species as prey branch implicitly. | FIXED | Invalid species tags are normalized from aggression threshold. |
| `primordial/simulation/simulation.py` | Correctness | Boids flock assignment connectivity was order-dependent (directed edge artifact). | FIXED | Reworked to undirected adjacency graph (if either senses other, they connect). |
| `primordial/simulation/simulation.py` | Correctness | `_nearby_creatures()` could revisit wrapped cells multiple times for large search radii. | FIXED | Added conditional cell dedupe when query window exceeds grid extents. |
| `primordial/main.py`, `primordial/rendering/renderer.py`, `primordial/simulation/food.py`, `primordial/simulation/simulation.py` | Correctness | Fullscreen/window resize left stale renderer surfaces and food spatial grid geometry. | FIXED | Added `Simulation.resize()`, `FoodManager.resize_world()`, `Renderer.resize()`, and wired them into fullscreen toggle path. |
| `primordial/main.py` | Code Quality | Broad exception handling around Windows DPI awareness suppressed all errors silently. | FIXED | Replaced with targeted exception types and debug log. |
| `primordial/simulation/simulation.py` | Performance | Boids step computed neighbor scans twice each frame (`_compute_boid_forces` + flock BFS). | FIXED | Added shared per-frame boid neighbor cache reused by both systems. |
| `primordial/simulation/simulation.py` | Performance | Frequent sqrt-based distance comparisons in hunting/boids loops. | FIXED | Switched many checks to toroidal squared distance thresholds. |
| `primordial/simulation/simulation.py` | Correctness/Performance | Boids cohesion centroid math used absolute positions, causing wrap-edge artifacts and extra cost. | FIXED | Cohesion now uses averaged wrapped offset vectors. |
| `primordial/rendering/themes.py` | Performance | Age desaturation overlay allocated a new surface per creature per frame. | FIXED | Added cached age overlay surfaces keyed by radius+alpha. |
| `primordial/rendering/animations.py` | Performance | Cosmic ray and parent pulse animations allocated new surfaces each frame. | FIXED | Added frame caches (global for cosmic ring, per-color for parent pulse). |
| `primordial/rendering/settings_overlay.py` | Performance | Overlay shade surface recreated every draw. | FIXED | Cached shade surface per resolution and reused each frame. |
| `primordial/rendering/renderer.py`, `primordial/rendering/hud.py`, `primordial/main.py`, `primordial/utils/cli.py` | Code Quality / DX | No first-class debug/profile runtime workflow. | FIXED | Added `--debug`, `--profile`, `--mode`, `--theme`; debug HUD timings + FPS/pop graph; 60s profile dump flow. |
| `primordial/main.py` | Correctness / Robustness | Logging/profile outputs could crash startup on unwritable config directories. | FIXED | Added fallback output paths (working directory) for log and profile files. |
| `primordial/main.py` | Code Quality / DX | No persistent file logging suitable for screensaver mode diagnosis. | FIXED | Added stdlib logging setup writing `primordial.log` in config dir; debug mode mirrors logs to stdout. |
| `Makefile` | Code Quality / DX | Repetitive dev commands for run/build/profile/clean. | FIXED | Added `make run/debug/profile/build/clean` shortcuts. |
| `primordial/rendering/renderer.py` | Performance | Kin/flock connection rendering remains pairwise O(k²) within groups. | DEFERRED | Current frame budgets are acceptable; approximate graph thinning can be added if large flocks become common. |
| `primordial/rendering/themes.py` | Performance | Trails are still redrawn every frame for all creatures. | DEFERRED | Current implementation meets target for typical populations; persistent trail compositing is a future optimization candidate. |
| `primordial/rendering/themes.py` | Memory | Glow cache has a fixed cap but no LRU eviction policy. | DEFERRED | Cap (100) bounds growth; LRU complexity deferred unless dynamic radius churn increases cache thrash. |
| `primordial/simulation/simulation.py` | Memory | Event queues grow if simulation is stepped without renderer consumption contract. | WONTFIX | In app architecture, renderer owns queue consumption each frame; headless step-only growth is expected outside contract. |
| `primordial/rendering/renderer.py` | Correctness | Stub overlay path still exists for not-yet-implemented themes (`petri`, `geometric`, `chaotic`). | WONTFIX | Theme stubs are intentional and still listed as known stubs. |
| `build.py`, `primordial.spec` | Build / Compatibility | Build compatibility after new modules/features. | FIXED | `python build.py` succeeded on Linux; output binary produced successfully. |
| runtime benchmark harness | Memory | Long-run memory drift concern. | FIXED | 36,000-frame run: RSS `44.76MB → 45.27MB` (`+0.51MB`), stable plateau observed. |

## Notes on Deferred Items

- Deferred items were chosen because measured frame-time targets are currently met in typical runs after this pass.
- If future mode/theme work increases per-frame draw cost, prioritize:
  1. Kin/flock line thinning/sampling
  2. Trail compositing strategy changes
  3. Glow cache LRU with hit-rate instrumentation
