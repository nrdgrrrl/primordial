# Changelog

All notable changes to Primordial are documented in this file.

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
