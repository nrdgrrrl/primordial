# AGENT.md — Primordial Codebase Context

This document is for AI coding agents tasked with extending or modifying the Primordial codebase.

## Project Summary

Primordial is a fullscreen Python screensaver featuring a cellular evolution simulation with bioluminescent visuals. Creatures with heritable genomes compete for food, reproduce with mutations, and evolve over time. The app is designed to run indefinitely on a monitor.

**Design philosophy:**
- Simulation and rendering are strictly decoupled
- All behavior is driven by the `Settings` dataclass — no hardcoded magic numbers
- Performance-sensitive code uses spatial bucketing (no O(n²) loops)
- Creatures are data-driven: the genome determines all behavior
- Visual themes are pluggable and don't affect simulation logic

## Architecture Map

```
primordial/                  ← project root
├── main.py                  # Top-level entry point for direct run and PyInstaller
├── build.py                 # Cross-platform build script (produces dist/primordial[.exe])
├── primordial.spec          # PyInstaller spec — commit this for reproducible builds
├── requirements.txt         # Runtime deps + pyinstaller under # build
└── primordial/              ← Python package
    ├── main.py              # Real entry point, pygame init, game loop, event handling
    ├── settings.py          # Settings dataclass — all tuneable parameters
    ├── utils/
    │   └── paths.py         # get_base_path() — resolves paths in dev + frozen builds
    ├── simulation/
    │   ├── genome.py        # Genome dataclass — heritable traits (13 traits)
    │   ├── creature.py      # Creature — position, velocity, energy, behavior, motion style
    │   ├── food.py          # Food particle and FoodManager with spatial bucketing
    │   └── simulation.py    # Simulation — orchestrates creatures, food, evolution, events
    └── rendering/
        ├── glyphs.py        # Glyph rendering system — stroke vocabulary, deterministic assembly
        ├── animations.py    # AnimationManager — death/birth animations, decoupled from sim
        ├── themes.py        # Theme ABC and implementations (OceanTheme, StubTheme)
        ├── hud.py           # HUD overlay for simulation stats
        └── renderer.py      # Renderer — draws state, kin lines, territory shimmer, animations
```

## Key Abstractions

### Genome (`simulation/genome.py`)

Immutable dataclass holding creature traits (all `float` 0.0–1.0):

**Original traits:**
- `speed`, `size`, `sense_radius`, `aggression`, `hue`, `saturation`, `efficiency`

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

**Trail length** varies by motion style: glide=14, swim=10, dart=5 (`get_trail_length()`).

**Motion styles** (in `wander()` and `update_position()`):
- **Glide**: very gentle direction changes, slow speed
- **Swim**: moderate wandering + sinusoidal lateral oscillation applied in `update_position`
- **Dart**: mostly stationary (`vx *= 0.95`) with random bursts at ~1.8× max speed every 3–5 seconds

**Key methods (unchanged):**
- `update_position(dt, world_width, world_height)` — move, wrap, update trail and rotation
- `steer_toward(x, y, speed_base, world_width, world_height)` — smooth steering (dart uses stronger steer)
- `wander(speed_base)` — motion-style-aware wandering
- `distance_to(x, y, world_width, world_height)` — toroidal distance
- `get_radius()`, `get_sense_radius()`, `get_movement_cost()`

**Invariant:** Creatures always wrap around world edges.

### FoodManager (`simulation/food.py`)

Unchanged. Spatial bucketing for efficient nearest-neighbor queries. See original docs.

### Simulation (`simulation/simulation.py`)

Main simulation controller. Owns `creatures`, `food_manager`, `settings`.

**Added fields:**
- `_next_lineage_id: int` — monotone counter for lineage ID allocation
- `death_events: list[dict]` — populated each frame when creatures die; cleared by renderer
- `birth_events: list[Creature]` — populated each frame on reproduction; cleared by renderer

**Death event dict keys:** `x`, `y`, `genome`, `glyph_surface`, `lineage_id`

**Key methods (updated):**
- `step()` — now populates `death_events` and `birth_events`; offspring inherit lineage unless hue mutation > 0.15 (speciation → new ID)
- `get_lineage_counts() -> dict[int, int]` — counts creatures per lineage_id
- `get_dominant_traits()` — now includes all 13 genome traits

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

### Settings (`settings.py`)

Single dataclass. New fields added in this pass:

```
glyph_size_base: int = 48           # base canvas size for glyphs
kin_line_max_distance: float = 120.0
kin_line_min_group: int = 3
territory_top_n: int = 3
territory_shimmer_lerp: float = 0.05
territory_fade_seconds: float = 2.0
death_animation_frames: int = 40
birth_animation_frames: int = 30
death_particle_count: int = 5
```

## Sim Mode Contract

A new simulation mode must:

1. Be a class with constructor `__init__(self, width: int, height: int, settings: Settings)`
2. Implement `step(self) -> None`
3. Implement `reset(self) -> None`
4. Expose properties: `creatures`, `food_manager`, `population`, `generation`, `oldest_age`, `food_count`, `paused`, `settings`
5. Expose event queues: `death_events: list[dict]`, `birth_events: list[Creature]`
6. Add mode name to `Settings.VALID_SIM_MODES`

## Visual Theme Contract

A new theme must:

1. Inherit from `Theme` ABC
2. Implement all abstract methods including `render_creature(surface, creature, time, scale=1.0)`
3. Register in `get_theme()`
4. Add to `Settings.VALID_VISUAL_THEMES`

## Known Stubs

**Simulation modes (not implemented):**
- `predator_prey`, `boids`, `drift`

**Visual themes (not implemented):**
- `petri`, `geometric`, `chaotic`

## Performance Notes

### Glyph Caching

Glyph surfaces are cached on `creature.glyph_surface`. Building a glyph involves ~2–7 stroke draws on a small surface (32–80px); this is acceptable at creation time but must not happen every frame. The cache is invalidated when the surface size changes by more than 4px (creature grew/shrunk significantly) or when the creature reproduces (offspring has new genome → `glyph_surface = None`).

### Kin Lines

Creatures are bucketed by `lineage_id` before drawing kin lines — only within-lineage pairs are compared. With typical lineage diversity, most lineages have 1–5 members; the expected per-frame cost is O(n × avg_lineage_size), not O(n²).

### Territory Shimmer

Shimmer state is computed once per frame per dominant lineage (top 3). Centroid and spread are recomputed from the members list. This is O(n) total per frame and negligible vs. rendering cost.

### Trail Lengths

Trail lengths are motion-style-dependent (14/10/5 positions). Dart-style creatures use very short trails, reducing the per-creature draw cost for the most common burst-pause pattern.

## Do Not Break

1. **Sim/render decoupling** — `Simulation.step()` must never call pygame or modify visual state
2. **No global mutable state** — all state lives in `Simulation`, `Renderer`, or `Settings`
3. **Settings-driven behavior** — no hardcoded numbers; use `Settings` fields
4. **Toroidal world** — creatures and distance calculations must handle wrapping
5. **Genome immutability** — `Genome` is frozen; mutation returns a new instance
6. **Food spatial bucketing** — maintain bucket structure when modifying `FoodManager`
7. **Trail length cap** — always limit creature trails to `get_trail_length()` positions (not hardcoded 8)
8. **Energy bounds** — creature energy stays in [0.0, 1.0]
9. **Glyph determinism** — same genome must always produce same glyph (hash-seeded RNG)
10. **Event queue ownership** — `death_events` and `birth_events` are populated by simulation, cleared by renderer after processing

## Asset Path Resolution

All asset loading **must** use `get_base_path()` from `primordial/utils/paths.py`:

```python
from primordial.utils.paths import get_base_path

icon_path = get_base_path() / "assets" / "icon.ico"
font_path  = get_base_path() / "primordial" / "assets" / "font.ttf"
```

### Why this matters

When PyInstaller freezes the app with `--onefile`, all files are extracted at
runtime to a temporary directory and `sys._MEIPASS` is set to that directory.
Paths relative to `__file__` or the working directory won't resolve correctly
inside the bundle.

`get_base_path()` abstracts this:

| Environment | Returns |
|-------------|---------|
| Dev (source) | Project root (`Path(__file__).parent.parent.parent`) |
| PyInstaller frozen | `Path(sys._MEIPASS)` |

**Never** use bare `open("assets/foo.png")` or `Path(__file__).parent / "x"` for
files that must ship in the binary — use `get_base_path()` instead.

## Build Process

### Entry points

- `main.py` (project root) — top-level entry point; delegates to `primordial.main.main()`.
  Used by PyInstaller and can also be run directly with `python main.py`.
- `primordial/main.py` — real implementation; uses relative imports, so it cannot be
  the direct PyInstaller target.

### Building the executable

```bash
python build.py          # cleans dist/, runs PyInstaller, prints result path
pyinstaller primordial.spec  # reproducible rebuild using committed .spec file
```

`build.py` does the following:
1. Deletes `build/` and `dist/` to ensure a clean state
2. Invokes `PyInstaller.__main__.run()` programmatically with `--onefile --noconsole`
3. Attaches `--add-data=primordial/assets:primordial/assets` when that directory exists
4. Attaches `--icon=assets/icon.ico` on Windows when the file exists

### .spec file

`primordial.spec` is committed and should be updated whenever build arguments change
(new `--add-data` entries, new hidden imports, etc.). The spec is regenerated
automatically on each `python build.py` run.

### Adding new assets

1. Place the file under `primordial/assets/` (create the directory if needed)
2. Load it via `get_base_path() / "primordial" / "assets" / "filename"`
3. Add `--add-data=primordial/assets{os.pathsep}primordial/assets` to `build.py` args
   (already present if the directory exists)

## Ollama Integration Note

A future enhancement will add LLM narration. `get_dominant_traits()` now returns all 13 genome traits including the new glyph and motion traits.
