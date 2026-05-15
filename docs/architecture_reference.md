# Primordial — Architecture Reference

Detailed design and system documentation for the Primordial codebase. This file is a reference for humans and agents who need to understand how specific subsystems work internally.

For agent-specific instructions and project contracts, see `AGENTS.md`.

---

## Key Abstractions

### Genome (`simulation/genome.py`)

Immutable dataclass holding creature traits (all `float` 0.0–1.0):

**Original traits:**
- `speed`, `size`, `sense_radius`, `aggression`, `hue`, `saturation`, `efficiency`

**Boids trait (added in modes pass):**
- `conformity` — 0–1; controls alignment force strength in boids mode; inert (random drifts) in other modes

**Glyph traits (added in enhancement pass):**
- `complexity` — 0–1 → maps to 2–7 strokes in the glyph
- `symmetry` — 0=asymmetric, 0.33=bilateral, 0.66=3-fold radial, 1.0=4-fold radial
- `stroke_scale` — overall proportion/delicacy of strokes
- `appendages` — 0–1 → 0–4 extra limb strokes at perimeter
- `rotation_speed` — glyph rotation speed (0=still, 1=steady spin)

**Motion trait:**
- `motion_style` — 0.00–0.33=glide, 0.34–0.66=swim, 0.67–1.00=dart

**Key methods:**
- `Genome.random()` — create random genome
- `genome.mutate(rate)` — return new genome with mutated traits
- `genome.copy()` — exact copy

**Invariant:** All trait values stay in [0.0, 1.0] after mutation.

### Creature (`simulation/creature.py`)

Mutable dataclass representing a single organism:

**Core fields:** `x`, `y`, `vx`, `vy`, `energy`, `age`, `genome`, `trail`

**Added fields:**
- `lineage_id: int` — inheritable lineage identifier for kin tracking; new ID on speciation (hue mutation > 0.15)
- `rotation_angle: float` — current glyph rotation in degrees, updated each frame
- `glyph_surface: Any` — cached glyph pygame.Surface set by renderer; `None` until first render; reset to `None` to force rebuild
- `_swim_phase: float` — internal oscillation state for swim motion
- `_dart_burst_remaining: int`, `_dart_cooldown: int` — dart burst state machine

**Aging methods (selection-pressure pass):**
- `get_max_lifespan()` — 3000 + longevity × 7000 frames
- `get_age_fraction()` — current age / max_lifespan
- `get_age_speed_mult()` — 1.0 until 70% lifespan, then linear to 0.5
- `get_effective_sense_radius()` — accounts for aging after 85% lifespan

**Trail length** varies by motion style: glide=14, swim=10, dart=5 (`get_trail_length()`).

**Motion styles** (in `wander()` and `update_position()`):
- **Glide**: very gentle direction changes, slow speed
- **Swim**: moderate wandering + sinusoidal lateral oscillation applied in `update_position`
- **Dart**: mostly stationary (`vx *= 0.95`) with random bursts at ~1.8× max speed every 3–5 seconds

**Mode-specific fields:**
- `species: str` — "none" (all non-predator_prey modes), "prey", or "predator"
- `flock_id: int` — -1 (loner / not in boids mode), ≥0 = boids flock component id
- `_glyph_phase: float` — pulse animation phase; initialised to `genome.hue * 6.28`
  at spawn; updated on every cosmic-ray mutation and reproduction; in boids mode
  slowly phase-locks toward flock average via `_update_boids_glyph_phases()`

**Key methods (unchanged):**
- `update_position(dt, world_width, world_height)` — move, wrap, update trail and rotation
- `steer_toward(x, y, speed_base, world_width, world_height)` — smooth steering (dart uses stronger steer)
- `wander(speed_base)` — motion-style-aware wandering
- `distance_to(x, y, world_width, world_height)` — toroidal distance
- `get_radius()`, `get_sense_radius()`, `get_movement_cost()`

**Invariant:** Creatures always wrap around world edges.

### FoodManager (`simulation/food.py`)

Spatial bucketing for efficient nearest-neighbor queries.

**Notable method:** `resize_world(width, height)` rewraps particles and rebuilds
buckets after display/simulation size changes.

### Simulation (`simulation/simulation.py`)

Main simulation controller. Owns `creatures`, `food_manager`, `settings`.

**Added fields:**
- `_next_lineage_id: int` — monotone counter for lineage ID allocation
- `death_events: list[dict]` — populated each frame when creatures die; cleared by renderer
- `birth_events: list[Creature]` — populated each frame on reproduction; cleared by renderer
- `cosmic_ray_events: list[tuple[float,float]]` — (x, y) positions for cosmic ray animations; cleared by renderer
- `active_attacks: list[tuple]` — (ax, ay, tx, ty, hue) attack lines; rebuilt per frame; consumed by renderer
- `zone_manager: ZoneManager` — fixed environmental zones; reset() regenerates them
- `_old_age_lifespans: deque[float]` — rolling last-20 natural deaths in frames
- `_predator_prey_state` — predator_prey-only stability state:
  seed, `sim_ticks`, `survival_ticks`, last-20 completed-run history,
  game-over hold state, and bounded adaptive dial trial bookkeeping

**Death event dict keys:** `x`, `y`, `genome`, `glyph_surface`, `lineage_id`, `cause` ("energy" | "age")

**Key methods (updated):**
- `step()` — populates all event queues; runs food cycle, hunting, cosmic rays, aging
- `update_predator_prey_runtime()` — holds the predator_prey `GAME OVER`
  overlay for 5 wall-clock seconds, then restarts with a new seed
- `restart_predator_prey_run()` — reset predator_prey while preserving rolling
  survival history and adaptive dial state
- `get_lineage_counts() -> dict[int, int]`
- `get_dominant_traits()` — now includes all 14 genome traits (+ longevity)
- `get_hunter_grazer_counts() -> tuple[int, int, int]` — (hunters, grazers, opportunists)
- `food_cycle_phase` property — 0.0=famine, 1.0=feast
- `avg_old_age_lifespan_seconds` property — rolling avg of last 20 natural deaths
- `get_predator_prey_stability_stats()` — current seed, `sim_ticks`,
  `survival_ticks`, rolling average, best recent, highest-ever survival,
  trial status, and game-over overlay metadata

**Invariants (all preserved):**
- `step()` never calls pygame or modifies rendering state
- Genome is still immutable; mutation returns new instance

### Renderer (`rendering/renderer.py`)

Reads simulation state and draws to pygame surface. Now orchestrates three additional visual systems.

**Key methods:**
- `draw(simulation)` — render current state (calls all sub-systems)
- `set_theme(name)`, `toggle_hud()`

**Sub-systems called in `draw()`:**
1. `process_events()` on AnimationManager (ingest death/birth events, clear queues)
2. `_draw_territory_shimmer()` — top-N lineage shimmer ellipses
3. `_draw_kin_lines()` — faint intra-lineage connection lines
4. `theme.render_creature(creature, scale=birth_scale)` — glyph + glow
5. `animation_manager.tick_and_draw()` — death effects, birth scales

**Territory shimmer state:** `_shimmer_states: dict[int, ShimmerState]` — persists across frames; centroids lerp, alpha pulses on sine wave.

**Invariant:** Renderer never mutates simulation state (death/birth event lists are cleared here after processing, which is permitted since renderer owns the consumption contract).

### Theme (`rendering/themes.py`)

Abstract base class. `render_creature` now accepts `scale: float = 1.0` parameter (backward-compatible).

**OceanTheme rendering order per creature:**
1. Trail segments (fading circles)
2. Bloom glow halo (`_create_glow_surface`)
3. Rotated glyph surface (`get_glyph_surface`)

### Glyph System (`rendering/glyphs.py`)

Procedural symbolic glyph generation from genome.

**Stroke vocabulary:**
- `_draw_arc(surface, cx, cy, size, color, alpha, angle_start, angle_sweep, radius_ratio)` — partial circle arc
- `_draw_line(...)` — straight line radiating from center
- `_draw_loop(...)` — small closed oval attached at offset point
- `_draw_fork(...)` — Y-shaped split
- `_draw_spiral(...)` — inward spiral
- `_draw_dot(...)` — small filled circle offset from center

**Key functions:**
- `build_glyph_surface(genome, color, base_size) -> pygame.Surface` — fully deterministic from genome hash seed; applies symmetry and appendages
- `get_glyph_surface(creature, color, base_size) -> pygame.Surface` — returns cached or builds fresh; caches on `creature.glyph_surface`

**Determinism guarantee:** `_genome_hash_seed()` quantizes traits to 3dp and hashes the tuple; same genome always produces same glyph.

### AnimationManager (`rendering/animations.py`)

Manages all active visual animations. Completely decoupled from simulation/.

**Animation types:**
- `DeathAnimation` — 40-frame dissolution: white flash at frame 0, glyph fades+shrinks to 0.3×, 4–6 scatter particles over 20 frames
- `BirthScaleTracker` — 30-frame ease-out-cubic scale-up from 0.2× to 1.0×; tracked per `id(creature)`
- `ParentPulse` — 15-frame expanding ring on reproducing parent (not yet wired to simulation, can be added)

**Key methods:**
- `process_events(death_events, birth_events, get_color)` — create animations from event queues
- `get_birth_scale(creature) -> float | None` — query current scale override for a creature
- `tick_and_draw(surface)` — advance + draw all active animations

### ZoneManager (`simulation/zones.py`)

Generates and manages fixed environmental zones at startup.

**Zone types** (defined in `ZONE_DEFINITIONS` dict):

| Zone | Favours | Penalises | BG colour |
|------|---------|-----------|-----------|
| `warm_vent` | efficiency↑, size↑ | speed↑ | deep amber |
| `open_water` | speed↑, size↓ | aggression↑ | pale blue |
| `kelp_forest` | sense_radius↑, aggression↓ | speed↑ | deep green |
| `hunting_ground` | aggression↑, speed↑ | longevity↑ | deep red |
| `deep_trench` | longevity↑, size↓ | efficiency↑ | deep indigo |

**Zone effect application** (per creature per frame):
1. For each zone, compute distance weight (0 at edge, 1 at centre).
2. Compute `_trait_effect(zone_type, genome)`: favoured traits → negative value (cheaper energy), penalised → positive (costlier).
3. Sum contributions × weight × strength → clamp to [0.75, 1.25].
4. Multiply creature's total `energy_cost` by this modifier.

**Performance:** O(zone_count) per creature per frame — trivial even at 250 creatures.

**HUD helper:** `get_dominant_zone(creatures)` returns label of the zone containing the most creatures (by highest overlap weight).

### Aggression Behaviour Tiers

Three tiers defined by `genome.aggression`:

| Tier | Range | Behaviour | Cost | Advantage |
|------|-------|-----------|------|-----------|
| Hunter | > 0.6 | Seeks nearest creature ≤1.3× own radius within `sense×1.5`; attacks within `radius×4` | `aggression×0.0012/frame` drain; 0.85× food sense | Attack gain `aggression×0.008×size_ratio/frame` |
| Opportunist | 0.4–0.6 | Eats food; attacks creatures <60% own size nearby | Moderate | None |
| Grazer | < 0.4 | Pure food-seeking | None | +20% food efficiency bonus |

Hunting uses a **creature spatial bucket** (150px cells, built per frame) to avoid O(n²) scanning. Only cells within `sense_radius` distance are checked.

Attack lines rendered by `renderer._draw_attack_lines()` — thin 1px hue-colored lines, alpha 40.

### Lifespan / Aging System

**`genome.longevity`** (new trait, 0–1): controls max lifespan.

`max_lifespan = 3000 + longevity × 7000` frames (50s–167s at 60fps).

Aging effects (computed by creature methods, applied in `update_position` and `simulation.step`):

| Life fraction | Speed effect | Sense effect |
|---------------|-------------|-------------|
| 0–70% | ×1.0 | ×1.0 |
| 70–100% | ×1.0 → ×0.5 linearly | ×1.0 |
| 85–100% | ×1.0 | ×1.0 → ×0.6 linearly |

**r/K tradeoff:** High longevity = long-lived but pays `longevity×0.0004/frame` maintenance. Low longevity = cheap but dies young.

Visual: grey wash overlay applied at blit time (not glyph cache) reaches alpha 160 at max lifespan.

**HUD:** "Oldest" stat shows `N% lifespan` rather than raw frames.

### Food Cycle

Sinusoidal spawn rate: `food_spawn_rate × (0.5 + 0.5 × sin(2π × t / food_cycle_period))`.  Phase 0 = famine (near-zero spawn); phase 1 = feast (2× base rate).  `food_cycle_phase` property exposed for HUD bar.

### Cosmic Rays

Each frame each living creature has `cosmic_ray_rate` chance of a single-trait mutation via `genome.mutate_one(std=0.15)`.  If the hit trait is `hue` and shift > 0.2, a new `lineage_id` is allocated (visible speciation).  Position emitted to `simulation.cosmic_ray_events` → `CosmicRayAnimation` (20-frame expanding white ring, alpha 50).

### Selection Pressure — How the Systems Interact

All four systems create converging selection pressure:

1. **Food cycle** drives boom/bust population oscillation.  During famine, only the most energy-efficient creatures survive.  This selects for high `efficiency` (grazers) and high `longevity` (creatures that can outlast famine on stored energy).

2. **Aggression / predation** creates a frequency-dependent layer on top of the food cycle.  Hunters thrive when prey density is high (feast); struggle during famine when prey is also starving.  This prevents hunters from completely eliminating grazers: when grazers become rare, hunting becomes unprofitable and hunter numbers drop, allowing grazers to recover.

3. **Zones** add spatial texture.  Creatures in `hunting_ground` evolve higher aggression and speed; creatures in `kelp_forest` or `deep_trench` evolve toward low aggression, high sense_radius, or high longevity.  This produces regionally distinct phenotypes visible in glyph appearance.

4. **Cosmic rays** act as a continuous mutation floor, preventing fixation.  At 0.0003/frame with 100 creatures, there's ~1 cosmic ray per 33 frames (~0.5s).  This continuously re-introduces rare phenotypes, preventing permanent extinction of any strategy.

**Expected equilibrium:** Hunter-heavy population (H:G ratio ~4:1) with:
- Average aggression drifting toward 0.6–0.8
- Average efficiency co-rising (hunters who also forage well survive famine)
- Grazers persisting as minority, cycling in abundance with feast periods
- Zone-adapted local clusters visible in glyph shape families by generation 300

**Selection speed levers:**
- Increase `mutation_rate` (faster drift, less genetic diversity)
- Increase `cosmic_ray_rate` (more random jumps, maintains diversity)
- Increase `food_cycle_period` (longer feast/famine — more dramatic selection)
- Increase `zone_strength` (stronger regional pressure)
- Decrease `food_max_particles` (sharper famines — stronger selection per cycle)
- Increase `aggression * drain` coefficient — makes hunters riskier, slows aggression takeover

### Configuration (`config/config.py`)

`Config` now loads committed canonical defaults from `primordial/config/defaults.toml`
and layers the platform user `config.toml` on top. Python owns validation,
coercion, clamping, typed access, and derived values only.

Canonical user-meaningful defaults currently include:

```
# Original glyph/animation fields:
glyph_size_base: int = 48
kin_line_max_distance: float = 120.0
kin_line_min_group: int = 3
territory_top_n: int = 3
territory_shimmer_lerp: float = 0.05
territory_fade_seconds: float = 2.0
death_animation_frames: int = 40
birth_animation_frames: int = 30
death_particle_count: int = 5

# Selection-pressure pass fields:
food_max_particles: int = 300       # food cap; lower = sharper famines
food_cycle_period: int = 1800       # frames per boom/bust cycle (~30s)
food_cycle_enabled: bool = True
cosmic_ray_rate: float = 0.0003     # prob/creature/frame for spontaneous mutation
zone_count: int = 5                  # number of environmental zones at startup
zone_strength: float = 0.8          # global zone effect multiplier (0 = disabled)
```

## Performance Notes

### Measured Baselines (2026-03-05)

Headless benchmark harness (`SDL_VIDEODRIVER=dummy`, 1920×1080):

- **Energy mode step time (before → after audit pass):**
  - pop 50: `1.284ms → 0.803ms`
  - pop 150: `4.082ms → 2.005ms`
  - pop 250: `7.684ms → 3.310ms`
- **Full frame time @ pop 150 (step + render):**
  - `25.445ms → 13.425ms`
- **Boids step time (before → after):**
  - pop 80: `17.135ms → 12.535ms`
  - pop 150: `16.829ms → 11.887ms`
  - pop 250: `16.638ms → 12.803ms`

### Hot-path Approaches Used

- **Boids neighbor reuse:** `_build_boid_neighbor_cache()` computes neighbors once per frame; both force computation and flock BFS reuse it.
- **Distance math reductions:** frequent sqrt distance checks were replaced by toroidal squared-distance comparisons (`_distance_sq`), only taking sqrt when normalization is needed.
- **Toroidal cohesion fix:** boids cohesion now averages wrapped offset vectors rather than absolute coordinates, avoiding edge-wrap centroid artifacts.
- **Render allocation cleanup:** cached age-overlay surfaces, cached cosmic-ray frame surfaces, cached parent-pulse color/frame surfaces, and cached settings shade surface.
- **Resize safety:** `Simulation.resize()` + `Renderer.resize()` prevent stale grids/surfaces after fullscreen/window changes.

### Memory Stability Check

10-minute-equivalent headless run (36,000 frames, energy mode, pop=180):

- RSS `44.76 MB → 45.27 MB` (`+0.51 MB`).
- No unbounded growth observed in simulation-owned structures during continuous stepping.

## Boids Flock Detection Algorithm

1. Pre-compute neighbor list per creature using spatial bucket (O(n × local_density))
2. BFS connected-components: two creatures connected if either's `sense_radius*1.5` covers the other
3. Singletons (flock size = 1) assigned `flock_id = -1`
4. Performance: O(n × avg_neighborhood) ≈ O(3000) at pop=300, well within 60fps budget
5. Phase sync: `_update_boids_glyph_phases()` lerps each creature's `_glyph_phase` toward
   circular flock average by factor 0.05 per frame