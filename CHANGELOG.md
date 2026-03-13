# Changelog

All notable changes to Primordial are documented in this file.

## [2026-03-13] — feat: predator_prey stability scoring, extinction game-over, and adaptive tuning

**What changed** (`simulation/simulation.py`, `rendering/hud.py`,
`rendering/renderer.py`, `simulation/persistence.py`, `primordial/main.py`,
`config/defaults.toml`, `config/config.py`):

- Predator-prey now scores runs by **stability**: the key metric is how many
  `sim_ticks` elapse before predators or prey collapse to zero.
- Fixed the predator-dominance rule to the stabilizing behavior:
  when predators exceed 60% of population, predator reproduction becomes harder
  by increasing their reproduction threshold by 20%.
- Removed automatic extinction rescue from normal predator-prey play.
  Species collapse now freezes the simulation, tints the screen red, shows a
  `GAME OVER` overlay with cause/seed/counts/survival ticks, highest survival
  record, and current run dial values, holds for 5 seconds, then restarts with
  a new seed.
- Pressing `Space` during predator-prey `GAME OVER` now skips the hold and
  immediately starts the next seeded run.
- Replaced predator-prey HUD generation display with `sim_ticks`, seed,
  current `survival_ticks`, rolling average survival over the last 20 completed
  runs, best recent survival, and current adaptive trial status.
- Added a bounded adaptive dial controller for a small set of ecological
  constants (`predator_contact_kill_distance_scale`,
  `predator_kill_energy_gain_cap`, `predator_hunt_sense_multiplier`,
  `prey_flee_sense_multiplier`,
  `predator_prey_scarcity_penalty_multiplier`, `food_cycle_amplitude`).
  Below-average collapses start a one-dial trial run; the next run either keeps
  or reverts the change based on survival performance.
- Predator-prey snapshots now persist adaptive tuning state, current seed,
  `sim_ticks`, `survival_ticks`, rolling history, and trial metadata.
- The adaptive predator-prey tuning state is also written on app exit and
  restored on next launch without requiring a world snapshot.

**Why:** predator-prey previously optimized for endless continuity via species
rescue, which made extinction invisible and contradicted the intended
stabilizing predator-dominance rule. The mode now exposes stability directly,
keeps run-to-run tuning bounded and explicit, and remains replayable via saved
state.

---

## [2026-03-05] — Comprehensive Audit + Optimization Pass

### Summary

This pass focused on correctness hardening, measured performance work, and
developer tooling. The app now handles malformed config data safely, avoids
several silent state-consistency failures, and exposes first-class debug/profile
CLI workflows.

---

## [2026-03-05] — fix: config validation hardening, safe coercion, and mode override safety

**What changed** (`primordial/config/config.py`, `simulation/simulation.py`):

- Reworked config merge path to be type-safe:
  - invalid types now warn and keep defaults instead of raising exceptions
  - unknown keys are explicitly warned and ignored
  - malformed section types are ignored safely
- Added validation and persistence for previously-missed fields:
  - `food_max_particles`
  - rendering config values (`glyph_size_base`, kin/shimmer/animation tuning)
- Fixed mode override coercion bug (`bool("false") -> True`) by removing runtime
  `type(fallback)` casting and validating mode overrides once at config load.
- `to_toml()` now serializes effective mode override values from `mode_params`
  instead of hardcoded static mode blocks.

**Why:** malformed or hand-edited `config.toml` values could previously crash
startup or silently coerce to incorrect values.

---

## [2026-03-05] — fix: state consistency in predation, resize/fullscreen, and boids connectivity

**What changed** (`simulation/simulation.py`, `simulation/food.py`,
`rendering/renderer.py`, `primordial/main.py`):

- Predation energy transfer is now bounded by prey energy:
  - prevents multiple attackers farming energy from already-dead targets in the
    same frame.
- Predator-prey species normalization:
  - creatures with invalid species tags are reclassified deterministically from aggression.
- Added `Simulation.resize()` + `FoodManager.resize_world()`:
  - resizes now rebuild food grid buckets safely and wrap entities into new bounds.
- Added `Renderer.resize()`:
  - recreates size-dependent surfaces, clears shimmer state, invalidates zone cache,
    and refreshes ambient particles.
- Boids flock connectivity now uses undirected adjacency semantics (if either
  boid senses the other, they connect), eliminating order-dependent flock splits.
- `_nearby_creatures()` now deduplicates wrapped cell keys only when needed to
  avoid duplicate neighbor scans at large radii.

**Why:** these paths previously allowed subtle state drift and stale geometry
after resolution changes.

---

## [2026-03-05] — perf: profile-driven simulation hot path refactor

**Baseline harness** (headless dummy SDL, 1920×1080):

- Energy mode step time:
  - pop 50: **1.284ms**
  - pop 150: **4.082ms**
  - pop 250: **7.684ms**
- Full frame (step+render) at pop 150: **25.445ms**
- Boids mode step time:
  - pop 80: **17.135ms**
  - pop 150: **16.829ms**
  - pop 250: **16.638ms**

**What changed** (`simulation/simulation.py`):

- Replaced repeated boids neighbor scanning with a shared per-frame neighbor cache.
- Split boids flow into:
  - `_build_boid_neighbor_cache()`
  - `_compute_boid_forces(...neighbors...)`
  - `_update_flock_assignments(...neighbor_cache...)`
- Reduced expensive distance math:
  - added toroidal squared-distance helpers
  - replaced many sqrt-based comparisons with squared thresholds
  - reused wrapped delta vectors where possible.
- Fixed toroidal cohesion behavior by averaging neighbor offset vectors rather
  than naive absolute coordinates.

**Measured result (same harness):**

- Energy mode step time:
  - pop 50: **0.803ms** (from 1.284ms, **1.60× faster**)
  - pop 150: **2.005ms** (from 4.082ms, **2.04× faster**)
  - pop 250: **3.310ms** (from 7.684ms, **2.32× faster**)
- Full frame at pop 150: **13.425ms** (from 25.445ms, **1.89× faster**)
- Boids step time:
  - pop 80: **12.535ms** (from 17.135ms, **1.37× faster**)
  - pop 150: **11.887ms** (from 16.829ms, **1.42× faster**)
  - pop 250: **12.803ms** (from 16.638ms, **1.30× faster**)

---

## [2026-03-05] — feat: runtime developer tooling (`--debug`, `--profile`, `--mode`, `--theme`)

**What changed** (`main.py`, `primordial/main.py`, `primordial/utils/cli.py`,
`rendering/renderer.py`, `rendering/hud.py`, `Makefile`):

- Added CLI runtime flags:
  - `--debug` enables debug HUD timing lines + FPS/population graph overlay
  - `--profile` runs for 60 seconds, writes `.pstats` + text report, exits
  - `--mode <name>` sets sim mode at launch without editing config
  - `--theme <name>` sets visual theme at launch without editing config
- Added tolerant runtime parser (`parse_runtime_args`) that coexists with `/s`,
  `/p`, `/c` screensaver args.
- Added per-frame debug timing pipeline:
  - external metrics from main loop (`event_ms`, `sim_ms`)
  - renderer sub-system timing breakdown shown in HUD in debug mode
  - FPS and population history mini-graphs (debug overlay)
- Hardened output paths for restricted environments:
  - log file creation falls back to working directory if config path is not writable
  - profile report writes (`.pstats` + `.txt`) fall back similarly instead of crashing
- Added `Makefile` tasks:
  - `make run`, `make debug`, `make profile`, `make build`, `make clean`

**Why:** this makes iterative tuning and future audit/profile work repeatable.

---

## [2026-03-05] — perf: reduced per-frame rendering allocations

**What changed** (`rendering/themes.py`, `rendering/animations.py`,
`rendering/settings_overlay.py`):

- Added age-overlay surface cache in `OceanTheme` (radius+alpha key) to avoid
  allocating a new greyscale wash surface per old creature per frame.
- Added frame caches for `CosmicRayAnimation` and color/frame caches for
  `ParentPulse` to eliminate per-frame temporary surface creation.
- Cached settings overlay shade surface and reuse per resolution.

**Why:** removes allocation churn and reduces GC pressure in long runs.

---

## [2026-03-05] — validation: memory + build checks

**What changed / verified:**

- 10-minute-equivalent headless run (36,000 frames) remained memory-stable:
  - RSS **44.76 MB → 45.27 MB** (`+0.51 MB`).
- PyInstaller pipeline verified after changes:
  - `python build.py` succeeded on Linux.
  - `dist/primordial` produced (33.1 MB).

---

## [2026-03-05] — All Four Simulation Modes Implemented

### Summary

This pass fully implements the three previously-stubbed simulation modes:
`predator_prey`, `boids`, and `drift`. The "coming soon" overlay has been
removed for all four modes. Each mode is genuinely distinct in its energy
model, selection pressure, visual feel, and HUD stats.

---

## [2026-03-05] — feat: drift mode — meditative evolution through pure random drift

**What changed** (`simulation/simulation.py`, `rendering/*`):

- Passive energy regen (+0.002/frame); no food; no movement cost; die only of old age
- All creatures use glide motion regardless of `motion_style` genome trait
- Very slow, smoothly curving paths via `_drift_wander()` with per-creature
  rotation direction stored in repurposed `_swim_phase` field
- Soft boundary repulsion keeps creatures away from screen edges
- Cosmic ray rate doubled (0.0006/frame default) — drift is mutation-driven
- `_drift_update_position()`: skips swim oscillation, halves glyph rotation
  speed, doubles trail length for long gossamer trails
- Zone effects applied as a very gentle energy nudge (no kill)
- HUD: population, generation, distinct lineage count, most-variable trait
- Mode defaults: pop=60, max_pop=200, mutation_rate=0.04, energy_to_reproduce=0.95

---

## [2026-03-05] — feat: boids mode — flocking simulation with evolved flock behaviour

**What changed** (`simulation/simulation.py`, `rendering/renderer.py`):

- No food; energy from being in a well-formed flock (3–12 neighbours optimal)
- Three genome-controlled boid rules:
  - Separation: avoid crowding (strength = `aggression`)
  - Alignment: match flock heading (strength = `conformity`)
  - Cohesion: steer toward flock centroid (strength = `efficiency`)
- Energy model: optimal band regenerates at rate ∝ alignment quality;
  isolation (<3 neighbours) and crowding (>12) both drain energy
- Flock detection: BFS connected-components via spatial bucket pre-computation;
  O(n × avg_neighborhood) per frame; singletons get `flock_id = -1`
- Glyph pulse phase-sync: each frame, `_glyph_phase` lerps toward flock
  circular average → synchronized bioluminescent pulse within each flock
- Flock lines: faint lines drawn between same-flock creatures (replaces kin
  lines in boids mode); loners show no connections
- HUD: flock count, avg/largest flock size, avg conformity trait, loner count
- Mode defaults: pop=150, max_pop=300, mutation_rate=0.07, energy_to_reproduce=0.72

---

## [2026-03-05] — feat: predator_prey mode — Lotka-Volterra ecosystem

**What changed** (`simulation/simulation.py`):

- Init: 30% predators (warm hues 0.48–0.88, aggression 0.62–0.95),
  70% prey (cool hues 0.05–0.45, aggression 0.0–0.38)
- Predators: hunt nearest prey within `sense_radius*2`; kill on contact
  (energy gain = `prey.size * 3 * 0.1`); pay 1.4× movement cost;
  wander when no prey found; ignore food
- Prey: flee nearest predator within `sense_radius*1.2`; seek food when safe
- Ecosystem balance:
  - >60% predators: increase predator reproduction threshold by 20%
  - <15% prey: predators pay 2× energy cost (prey scarcity)
  - Predators extinct: convert 3 highest-aggression prey → prevents sim death
  - Prey extinct: convert 10 lowest-aggression predators → prevents sim death
- Cosmic ray species flip: aggression crossing 0.5 triggers species conversion
  + new lineage_id (visible speciation event)
- HUD: predator/prey counts, avg speed per species, food cycle bar
- Mode defaults: pop=120, predator_fraction=0.30, food_spawn_rate=0.5,
  mutation_rate=0.08, energy_to_reproduce=0.70

---

## [2026-03-05] — feat: conformity genome trait + species/flock_id/glyph_phase fields

**What changed** (`simulation/genome.py`, `simulation/creature.py`):

- `Genome`: 15th trait `conformity` (0.0–1.0) controls boids alignment
  strength; inert in other modes (drifts randomly via normal mutation)
- `Genome`: updated `random()`, `mutate()`, `copy()`, `mutate_one()`
- `Creature`: `species: str` field ("none"|"prey"|"predator")
- `Creature`: `flock_id: int` field (-1=loner, >=0=flock component id)
- `Creature`: `_glyph_phase: float` — initialised to `genome.hue * 6.28`
  at spawn; updated on mutations and births to track hue; in boids mode
  slowly phase-locks toward flock average for synchronized pulse effect
- `OceanTheme`: pulse animation now uses `creature._glyph_phase` instead
  of `genome.hue * 6.28` (behavior identical in non-boids modes)
- `Creature.spawn()`: added `species` parameter

---

## [2026-03-05] — feat: mode-specific HUD, renderer flock lines, config mode_params, transition fade

**What changed** (`rendering/hud.py`, `rendering/renderer.py`, `config/config.py`, `main.py`):

- HUD: mode-aware rendering — each mode shows relevant stats only:
  - energy: H/G/O counts, food cycle bar, zone, avg lifespan (unchanged)
  - predator_prey: predator/prey counts, avg speed per species, food cycle bar
  - boids: flock count, avg/largest flock, avg conformity, loner count
  - drift: population, generation, lineage count, most-variable trait
- Renderer: removed "coming soon" stub overlay for all four modes
- Renderer: `_draw_flock_lines()` — faint lines between same-flock creatures
  in boids mode; drawn instead of kin lines
- Renderer: `set_mode()` updates stub detection and invalidates zone cache
- Config: `mode_params` dict loaded from `[modes.*]` TOML sections;
  default `[modes.predator_prey/boids/drift]` sections written to config.toml
- Main loop: 2-second fade-to-black transition when mode changes in settings
  overlay; simulation resets at peak opacity and fades back in

---

## [2026-03-05] — audit + config persistence + in-app settings overlay

### Audit pass
- Fixed correctness edge cases in `Simulation`: guarded `max_population` and `food_cycle_period` divisors to prevent divide-by-zero, and hard-clamped food-cycle spawn rate to never go negative.
- Hardened preview argument parsing: `/p` with non-positive HWND now falls back to normal mode to avoid unstable preview embedding.
- Confirmed existing behavior: death events are enqueued for every removal path and consumed by renderer each frame; reproduction returns exactly one offspring per successful parent check; lineage IDs are monotonic via `_alloc_lineage_id`.
- Deferred larger algorithmic refactors (e.g., shimmer centroid O(n) stats) because current code already uses spatial bucketing in hot simulation paths and holds 60fps target on typical loads.

### Persistent config (TOML)
- Replaced dataclass-backed settings with `Config` class in `primordial/config/config.py`.
- Added platform-aware config path resolution and automatic directory creation.
- Added first-run default `config.toml` creation, corruption backup (`config.toml.bak`), typed attribute merge/validation, and save/reset APIs.
- Kept `primordial/settings.py` as compatibility alias (`Settings = Config`) to minimize call-site churn.

### In-app settings screen
- Added renderer-owned `SettingsOverlay` panel (`S` key in normal mode): keyboard-driven navigation and edit controls, 20-frame fade in/out, semi-transparent pause overlay, apply/discard/reset behavior.
- Settings apply on Enter and are auto-saved to user config; close via S/Escape discards unapplied edits.
- Settings marked as requiring reset are annotated in UI; explicit simulation reset remains user-driven.

### Documentation
- Added `AUDIT.md` with file-by-file findings and status markers (FIXED/DEFERRED/WONTFIX).
- Updated README and AGENT docs to describe Config/TOML architecture, platform config paths, and settings overlay workflow.

---

## [2026-03-04] — Evolution Selection Pressure Pass

### Summary

This pass adds four interacting selection systems so that evolution is visible
and meaningful over hundreds of generations.  All systems create genuine
tradeoffs; the visual tone stays calm and meditative throughout.

---

## [2026-03-04] — docs: AGENT.md and README updated for selection-pressure pass

**What changed:**  Added zone architecture, aggression behaviour tiers,
aging/longevity, and Selection Pressure section to AGENT.md.  Added
"Watching Evolution" and "Tuning" sections to README.md.

---

## [2026-03-04] — feat: tuning — selection pressure balance, spatial bucket

**What changed:**

*`settings.py`:*
- `food_spawn_rate` 0.4 → 0.6 (base rate; cycle makes it 0–1.2/frame)
- `food_max_particles` 500 → 300 (lower cap means famine buffer empties faster)
- `food_cycle_period` 1800 (30s per cycle)
- `max_population` 300 → 220 (crowding penalty starts at 110 creatures)
- `energy_to_reproduce` 0.75 → 0.80 (requires sustained feeding, not just lucky burst)
- `mutation_rate` 0.05 → 0.06 (faster trait drift — visible change by gen 300)

*`simulation/simulation.py`:*
- Aggression drain tuned to `aggression * 0.0012/frame` — hunters pay a real cost
  but can offset it with successful attacks
- Attack drain tuned to `aggression * 0.008 * size_ratio/frame` — frequency-
  dependent: profitable in dense prey environment, marginal in sparse
- Grazer efficiency bonus raised to 20% (from spec's 15%) to ensure coexistence
- Prey size cap: hunters only attack creatures ≤ 1.3× own radius

*Creature spatial bucket:*  `_build_creature_bucket()` / `_nearby_creatures()`
builds a 150px grid hash each frame and limits hunting queries to local cells.
Reduces hunt step from O(n²) to O(n × local_density).
Result: 476 fps sim-only at pop=100 on 1920×1080 (well above 60fps target).

*Initial state:*  Creatures start with `energy=0.7`; 200 food particles
pre-seeded so the population doesn't starve before the cycle's first feast.

**Tuning rationale:**

The core balance challenge: with predation providing a second energy source,
hunters can survive famine by eating prey (which are also stressed by famine).
This dampens the boom/bust oscillation and allows hunters to gradually dominate.
The chosen parameters create frequency-dependent selection: hunting is
marginally profitable at high population density (feast) and marginally
unprofitable when prey is scarce (famine).  In practice, observed dynamics
are run-dependent: some seeds reach hunter/grazer coexistence around H:G 4:1;
others evolve toward hunter dominance.  Grazers are continuously re-introduced
by cosmic ray mutations (0.0003 rate × 100 creatures ≈ 1 mutation every 33
frames) so complete extinction requires sustained predation pressure over many
generations.

Expected observable dynamics at 1920×1080:
- Population: 36–230 range, oscillating with food cycle
- Hunters dominate after ~generation 100 in most runs
- Average aggression rises to 0.6–0.8 by generation 500
- Average efficiency rises in parallel (both traits co-selected)
- Rare grazers persist as a minority throughout

**Why these specific values:**
- food_spawn_rate=0.6 × 2 = 1.2 at feast; feeds 200 creatures comfortably
- food_max_particles=300: at 100 creatures, 300 food = 3 per creature; at
  famine they draw down the buffer in ~200 frames — a visible scarcity
- energy_to_reproduce=0.80: creatures need to eat ~4 food particles after
  splitting; achievable in feast but not guaranteed in famine
- Spatial bucket at 150px cells keeps hunting O(n × local) not O(n²)

---

## [2026-03-04] — feat: HUD updates — H/G/O counts, food bar, zone, avg lifespan

**What changed** (`rendering/hud.py`):

- **Oldest**: now shown as `N% lifespan` instead of raw frames — more meaningful
  since max lifespan varies by `longevity` genome trait
- **H:N G:N O:N**: live count of hunters (aggression > 0.6), grazers (< 0.4),
  and opportunists; updates every frame
- **Avg lifespan**: rolling average of last 20 natural (old-age) deaths in
  seconds; `—` until first natural death occurs
- **Zone**: dominant zone label (zone type containing the most creatures at
  this instant; `—` if no creatures are inside any zone)
- **Food cycle bar**: 80px horizontal bar with "Famine" ← → "Feast" labels;
  colour gradient red→green tracks `food_cycle_phase`; updated every frame

---

## [2026-03-04] — feat: rendering — cosmic ray rings, zone backgrounds, attack lines, aging grey

**What changed:**

*`rendering/animations.py`:*
- `CosmicRayAnimation`: 20-frame expanding white ring, max alpha 50, radius
  6→30px.  Added `add_cosmic_ray()` to `AnimationManager`.

*`rendering/renderer.py`:*
- `_draw_zone_backgrounds()`: soft atmospheric radial gradients drawn
  beneath territory shimmer; per-zone color at alpha 0–20; zones are static.
- `_draw_attack_lines()`: 1px lines from attacker to target, hue color
  alpha 40.  Consumes `simulation.active_attacks` each frame.
- Cosmic ray events consumed from `simulation.cosmic_ray_events` → animations.

*`rendering/themes.py`:*
- Age desaturation: after blitting glyph, overlay a grey circle (alpha up to
  160) on creatures past 70% max lifespan.  Applied at blit time — glyph cache
  NOT invalidated.  Subtle until ~85%, obvious at 100%.

---

## [2026-03-04] — feat: environmental zone system

**What changed** (`simulation/zones.py` new):

Five zone types: `warm_vent`, `open_water`, `kelp_forest`, `hunting_ground`,
`deep_trench`.  At startup, `ZoneManager` places `zone_count` (default 5)
circles randomly across the world, each 18–30% of the shorter screen
dimension in radius.

Each zone type favours 2 traits and penalises 1 trait via energy cost
multipliers (up to ±20% per zone, capped [0.75, 1.25] aggregate).
`get_energy_modifier(creature)` is O(zone_count) per creature per frame.
`get_dominant_zone(creatures)` for HUD: returns the zone label most creatures
currently overlap.

Zone rendering: `renderer._draw_zone_backgrounds()` draws each zone as
concentric circles with alpha 0–20, giving subtle screen regions.

---

## [2026-03-04] — feat: food cycle, aggression/hunting, cosmic rays, aging deaths

**What changed** (`simulation/simulation.py` rewritten):

*Food cycle:*  `_get_food_rate()` = `food_spawn_rate × (0.5 + 0.5×sin(2π×t/period))`.
`food_cycle_phase` property exposed for HUD bar.  Pre-seeded with 200 particles.

*Aggression tiers:*
- Hunters (> 0.6): seek nearest creature within `sense×1.5`, steer toward it,
  attack at `radius×4` range.  Fallback food-seek uses 0.85× sense radius.
- Grazers (< 0.4): pure food-seeking with 20% efficiency bonus at eat time.
- Opportunists (0.4–0.6): eat food + opportunistic attack vs tiny nearby prey.
Hunters pay `aggression×0.0012/frame`; must hunt to compensate.

*Cosmic rays:*  Per-frame per-creature chance → `mutate_one(std=0.15)`.
Hue shift > 0.2 → new `lineage_id`.  Position emitted to `cosmic_ray_events`.

*Aging deaths:*  Creatures dying at `age >= max_lifespan` → cause="age"; ages
tracked in rolling deque for `avg_old_age_lifespan_seconds` property.

*New event queues:*  `cosmic_ray_events`, `active_attacks` (rebuilt per frame).
New queries: `get_hunter_grazer_counts()`, `get_dominant_traits()` now includes
`longevity`.

---

## [2026-03-04] — feat: settings tuning, longevity genome trait, creature aging system

**What changed:**

*`settings.py`:*  Added `food_cycle_period` (1800), `food_cycle_enabled`,
`cosmic_ray_rate` (0.0003), `zone_count` (5), `zone_strength` (0.8),
`food_max_particles` (300).

*`genome.py`:*  Added `longevity` trait (0=short-lived, 1=long-lived);
updated `random()`, `mutate()`, `copy()`.  Added `mutate_one()` for cosmic-ray
single-trait mutation (picks one trait, Gaussian std=0.15).

*`creature.py`:*  Added `get_max_lifespan()` (3000–10000 frames based on
longevity), `get_age_fraction()`, `get_age_speed_mult()` (declines to 0.5×
after 70% lifespan), `get_effective_sense_radius()` (declines to 0.6× after
85% lifespan).  `update_position()` applies age speed mult before moving.
`Creature.spawn()` now accepts optional `energy` parameter.

---

## [2026-03-04] - Windows Screensaver Pass

### Summary

This pass converts Primordial into a proper Windows `.scr` screensaver file while
keeping it launchable as a normal app on both Linux and Windows.

---

## [2026-03-04] - docs: README, AGENT.md, CHANGELOG updated for screensaver pass

**What changed:**

- README.md: added "Screensaver Installation (Windows)" section documenting Method 1
  (right-click Install) and Method 2 (manual copy to System32), uninstall steps, and
  updated Distribution section to mention `dist/primordial.scr` alongside `.exe`
- AGENT.md: updated architecture map to include `utils/screensaver.py`; added
  "Screensaver Argument Parsing" section documenting the four modes, the SDL_WINDOWID
  trick and why ordering matters, screensaver input-quit behaviour and grace period,
  and the dual `.exe`/`.scr` build output

**Why:** Future agents need to understand the screensaver argument contract, the SDL
preview embedding mechanism, and the build output to safely extend or modify this pass.

---

## [2026-03-04] - feat: Windows .scr screensaver — arg parsing, modes, config dialog, build output

**What changed:**

*`primordial/utils/screensaver.py` (new):*
- `ScreensaverArgs` dataclass with `mode: str` and optional `preview_hwnd: int`
- `parse_screensaver_args()` — maps `/s`, `/p HWND`, `/c`, and no-args to the four modes

*`main.py` (root):*
- Parse screensaver args at the very top before importing `primordial.main`
- Set `os.environ["SDL_WINDOWID"]` for preview mode before the import so it lands
  before `pygame.init()` is called inside the package

*`primordial/main.py`:*
- `main()` now accepts optional `scr_args: ScreensaverArgs` parameter (defaults to normal)
- `screensaver` mode: fullscreen SCALED, hidden cursor, quit on KEYDOWN /
  MOUSEBUTTONDOWN / MOUSEMOTION > 4px, 2-second startup grace period
- `preview` mode: 152×112 window (SDL renders into HWND via SDL_WINDOWID), half tick
  rate to save CPU, no input handling beyond QUIT
- `config` mode: standalone 400×300 pygame dialog with app title, current settings
  (sim_mode, visual_theme, population, FPS), path to settings.py, OK button —
  no simulation started
- `normal` mode: existing behaviour fully preserved

*`build.py`:*
- After PyInstaller on Windows, copy `dist/primordial.exe` → `dist/primordial.scr`
- Attach `--version-file=version.txt` on Windows when the file exists

**Why:** Windows identifies screensaver binaries solely by the `.scr` extension and
passes `/s`, `/p`, `/c` arguments to control the execution mode. The SDL_WINDOWID
env var is the standard mechanism for embedding a pygame/SDL window into an existing
HWND for the screensaver preview pane. The grace period prevents false-quit from
cursor settling jitter that some systems emit at screensaver activation.

---

## [2026-03-04] - Windows Compatibility and PyInstaller Packaging

### Summary

This pass makes Primordial fully runnable on Windows and produces a self-contained
standalone `primordial.exe` via PyInstaller. All existing Linux functionality is preserved.

---

## [2026-03-04] - docs: README, AGENT.md updated for Windows/packaging pass

**What changed:** Added "Distribution" section to README.md documenting how to build the
executable, expected size, deployment, reproducible builds, and per-platform test status.
Updated AGENT.md architecture map to include new files (`utils/paths.py`, `main.py`, `build.py`,
`primordial.spec`) and added two new sections: "Asset Path Resolution" (explaining `get_base_path()`
and PyInstaller frozen environment detection) and "Build Process" (entry points, build steps,
spec file, and how to add new assets).

**Why:** Future agents and contributors need to understand when and why to use `get_base_path()`,
how the dual entry-point structure works, and how to reproduce or extend the build.

---

## [2026-03-04] - feat: PyInstaller packaging — build.py, main.py entry point, primordial.spec

**What changed:**

- Added top-level `main.py` as the PyInstaller entry point; it delegates to `primordial.main.main()`
  and also works for direct `python main.py` execution (the package uses relative imports so it
  could not be the direct build target itself)
- Added `build.py`: cross-platform build script that cleans previous artifacts, invokes
  `PyInstaller.__main__.run()` programmatically with `--onefile --noconsole --clean`, automatically
  includes `primordial/assets/` via `--add-data` when the directory exists, and applies
  `--icon=assets/icon.ico` on Windows when present
- Committed `primordial.spec` generated by the first successful build — allows reproducible
  rebuilds via `pyinstaller primordial.spec`
- Added `pyinstaller` to `requirements.txt` under a `# build` comment

**Platform testing:**
- ✅ Linux x86-64: `dist/primordial` built successfully, 31.9 MB
- ❌ Windows x86-64: untested (no Windows runner available; build is expected to work, producing `dist/primordial.exe`)

**Why:** The screensaver should run on Windows without requiring Python or pip. A single-file
executable is the most practical distribution format for a screensaver.

---

## [2026-03-04] - feat: Windows compatibility — DPI awareness, FULLSCREEN|SCALED, utils/paths.py

**What changed:**

*`primordial/main.py`:*
- Added `ctypes.windll.shcore.SetProcessDpiAwareness(2)` call before `pygame.init()` to fix
  blurry rendering on Windows high-DPI displays; wrapped in `try/except` so it silently no-ops
  on Linux/Mac and older Windows versions that lack `shcore`
- Changed fullscreen `set_mode` flags from `pygame.FULLSCREEN` to `pygame.FULLSCREEN | pygame.SCALED`
  in both the initial setup and `toggle_fullscreen()`; `SCALED` instructs pygame to handle DPI
  scaling internally, preventing the wrong-resolution issue on Windows

*`primordial/utils/paths.py` (new):*
- `get_base_path() -> Path` — returns `Path(sys._MEIPASS)` when running as a PyInstaller frozen
  bundle, or the project root (`Path(__file__).parent.parent.parent`) when running from source
- All future asset loading must use this helper (see AGENT.md)

*Audit findings (no changes required):*
- No `pygame.font.SysFont` calls — `pygame.font.Font(None, size)` already used throughout ✓
- No `os.system()` or shell calls ✓
- No string-based path construction (`os.path.join`, bare strings) for asset loading ✓
- `.gitignore` already excludes `.venv/` and `__pycache__/` ✓

**Why:** `pygame.SCALED` is the correct flag for Windows DPI-aware fullscreen. Without it, pygame
renders at the OS-upscaled resolution and appears blurry on 4K/HiDPI monitors. The DPI awareness
call prevents Windows from applying its own bitmap scaling before pygame sees the display size.

---

## [2026-03-04] - Enhancement Pass: Symbolic Glyphs and Behavioural Systems

### Summary

Five major systems added in this pass: procedurally generated symbolic glyph creatures, kin connection lines, territory shimmer for dominant lineages, death/birth animations, and three visible motion styles. The energy simulation and ocean theme are fully preserved.

---

## [2026-03-04] - Documentation: AGENT.md, README.md updated for enhancement pass

**What changed:** Updated AGENT.md with new class descriptions, trait list, event queue contract, performance notes for glyphs/kin lines/shimmer, and updated Do Not Break invariants. Updated README.md with full explanation of glyph traits, motion styles, new visual systems, settings, and extended project structure.

**Why:** Agents and users need accurate documentation to extend or understand the new systems. AGENT.md is the primary reference for future AI work on this codebase.

---

## [2026-03-04] - feat: Glyph rendering, kin lines, territory shimmer, and animations

**What changed:**

*Glyph system (`rendering/glyphs.py`):*
- Stroke vocabulary: arc, line, loop, fork, spiral, dot — six primitive drawing functions
- `build_glyph_surface(genome, color, base_size)` builds a fully deterministic glyph from genome hash seed
- Symmetry applied by rotating/mirroring the base stroke set (asymmetric / bilateral / 3-fold / 4-fold)
- Appendages: 0–4 evenly-spaced perimeter limb strokes from `genome.appendages`
- `get_glyph_surface(creature, color, size)` caches on `creature.glyph_surface`; rebuilt when `None`

*AnimationManager (`rendering/animations.py`):*
- `DeathAnimation`: 40-frame dissolution — frame-0 white flash, glyph fades to 0 alpha and shrinks to 0.3×, 4–6 scatter particles drift and fade over 20 frames
- `BirthScaleTracker`: 30-frame ease-out-cubic scale-up from 0.2× to 1.0×, tracked per `id(creature)`
- `ParentPulse`: 15-frame expanding ring on reproducing parent
- `AnimationManager.process_events()` ingests simulation death/birth event queues each frame
- `get_birth_scale(creature)` returns active scale override or None

*OceanTheme (`themes.py`):*
- `render_creature` now draws: trail → bloom glow halo → rotated glyph
- `scale` parameter added (default 1.0) for birth animation integration; backward-compatible

*Renderer (`rendering/renderer.py`):*
- Kin connection lines: creatures bucketed by lineage_id; lines drawn for groups of 3+ within 120px; alpha 15–30 inversely proportional to distance
- Territory shimmer: top-3 lineages get soft pulsing radial gradient ellipse; sine-wave alpha with per-lineage random period (4–6s); centroid lerps each frame; 2-second fade when lineage drops out of top 3
- AnimationManager integrated: processes events, tick_and_draw each frame; birth scale applied per-creature

**Why:** The glyph system makes creatures visually expressive and genetically legible — you can see family resemblance between kin. Kin lines and territory shimmer make population dynamics visible in the world without UI elements. Death/birth animations add biological weight to the simulation events that were previously invisible.

---

## [2026-03-04] - feat: Genome traits, lineage system, motion styles, and event queues

**What changed:**

*Genome (`simulation/genome.py`):*
- Added 6 new traits: `complexity`, `symmetry`, `stroke_scale`, `appendages`, `rotation_speed`, `motion_style`
- All follow the same 0–1 float range and mutation rules as existing traits
- `random()`, `mutate()`, `copy()` updated to include all 13 traits

*Creature (`simulation/creature.py`):*
- `lineage_id: int` — inherited lineage identifier for kin tracking
- `rotation_angle: float` — updated each frame; used by renderer to rotate glyph
- `glyph_surface: Any` — cache slot for renderer; `None` until first render
- Variable trail length: glide=14, swim=10, dart=5 positions (`get_trail_length()`)
- Swim oscillation: perpendicular sine component added to velocity in `update_position`
- Dart state machine: burst/cooldown timers; slow drift between bursts, fast snap toward food
- `steer_toward` enhanced: dart style uses 0.25 steer strength and 1.5× speed multiplier
- `wander` dispatches to `_wander_glide`, `_wander_swim`, `_wander_dart`

*Simulation (`simulation/simulation.py`):*
- `_next_lineage_id` counter; each initial creature gets its own lineage
- Speciation on reproduction: if offspring hue diverges > 0.15, it starts a new lineage
- `death_events: list[dict]` — populated on creature death; cleared by renderer
- `birth_events: list[Creature]` — populated on reproduction; cleared by renderer
- `get_lineage_counts() -> dict[int, int]` for renderer territory shimmer
- `get_dominant_traits()` updated to include all 13 traits

*Settings (`settings.py`):*
- New tuneable values: `glyph_size_base`, `kin_line_max_distance`, `kin_line_min_group`, `territory_top_n`, `territory_shimmer_lerp`, `territory_fade_seconds`, `death_animation_frames`, `birth_animation_frames`, `death_particle_count`

**Why:** The genome expansion provides the raw data for all new visual systems. Lineage tracking with speciation creates natural groupings that kin lines and territory shimmer can visualize. Event queues decouple animation triggering from simulation logic, preserving the sim/render boundary.

---

## [2026-03-04] - Initial Implementation

**What changed:** Created the complete Primordial screensaver application with energy mode simulation and ocean visual theme fully implemented. The project includes genome-based creatures with heritable traits, food particles with spatial bucketing for performance, smooth steering behavior, mutation/reproduction mechanics, and bioluminescent visual effects.

**Why:** This is the foundation of the project. The architecture was designed for extensibility — sim modes and visual themes are pluggable, simulation and rendering are decoupled, and all parameters are settings-driven. Energy mode and ocean theme serve as reference implementations for future modes/themes.

---

## [2026-03-04] - Project Scaffolding

**What changed:** Created project structure with virtual environment, installed pygame and numpy, initialized git repository, and set up .gitignore.

**Why:** Established clean project foundation with proper dependency isolation via venv, version control via git, and exclusion of generated files via .gitignore.

---

## [2026-03-04] - Settings System

**What changed:** Implemented Settings dataclass with validation for sim modes and visual themes, serialization methods, and all tuneable parameters.

**Why:** Central configuration ensures no hardcoded values and makes behavior easily adjustable. Validation catches invalid mode/theme names early.

---

## [2026-03-04] - Genome and Creature Systems

**What changed:** Implemented immutable Genome dataclass with random generation and mutation. Implemented Creature class with position, velocity, energy, steering behavior, and toroidal world handling.

**Why:** The genome system is the core of evolution — immutability ensures predictable mutation behavior. Smooth steering (vs. teleportation) makes movement visually pleasing. Toroidal topology removes edge effects.

---

## [2026-03-04] - Food System with Spatial Bucketing

**What changed:** Implemented Food particle and FoodManager with grid-based spatial hashing for efficient nearest-neighbor queries.

**Why:** With 300 creatures and 500 food particles, brute-force O(n²) lookup would kill framerate. Spatial bucketing brings this to O(1) average case per query, enabling smooth 60 FPS.

---

## [2026-03-04] - Energy Mode Simulation

**What changed:** Implemented the full energy mode simulation loop: food spawning, food-seeking with smooth steering, eating mechanics, energy-based reproduction with mutation, death from energy depletion, and overcrowding population control.

**Why:** Energy mode is the primary simulation. The loop order matters: spawn food → creatures act → reproduction → death cleanup. Overcrowding penalty creates natural population cycles.

---

## [2026-03-04] - Ocean Theme and Rendering

**What changed:** Implemented ocean theme with deep blue background, bioluminescent color palette, glowing blob creatures with trails, pulsing animation, twinkling food particles, and ambient depth particles.

**Why:** Visual appeal is critical for a screensaver. The glow effect uses concentric circles with decreasing alpha. Colors are mapped from genome hue to a cool-tones palette. Ambient particles add depth perception.

---

## [2026-03-04] - HUD System

**What changed:** Implemented toggleable HUD showing generation, population, oldest creature age, food count, current mode/theme, and FPS.

**Why:** HUD provides insight into simulation state without being intrusive. Semi-transparent panel with small font keeps it unobtrusive. Toggle (H key) lets users hide it for pure screensaver experience.

---

## [2026-03-04] - Main Loop and Controls

**What changed:** Implemented main entry point with pygame initialization, fullscreen/windowed support, game loop with FPS limiting, and keyboard controls (ESC/Q quit, H HUD, Space pause, F fullscreen, R reset, +/- food rate).

**Why:** Clean separation of concerns: main.py handles pygame setup and input, delegates simulation to Simulation class, delegates rendering to Renderer. Controls follow screensaver conventions.

---

## [2026-03-04] - Stub Modes and Documentation

**What changed:** Added stub themes that show "coming soon" overlay, created comprehensive README.md with installation/usage/extension guides, and AGENT.md with architectural documentation for future AI agents.

**Why:** Stubs make the settings system complete while clearly indicating unimplemented features. Documentation enables both human users and AI agents to understand and extend the codebase.
