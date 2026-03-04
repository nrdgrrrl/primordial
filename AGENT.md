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
primordial/
├── main.py              # Entry point, pygame init, game loop, event handling
├── settings.py          # Settings dataclass — all tuneable parameters
├── simulation/
│   ├── genome.py        # Genome dataclass — heritable traits
│   ├── creature.py      # Creature dataclass — position, velocity, energy, behavior
│   ├── food.py          # Food particle and FoodManager with spatial bucketing
│   └── simulation.py    # Simulation class — orchestrates creatures, food, evolution
└── rendering/
    ├── themes.py        # Theme ABC and implementations (OceanTheme, StubTheme)
    ├── hud.py           # HUD overlay for simulation stats
    └── renderer.py      # Renderer class — draws simulation state to screen
```

## Key Abstractions

### Genome (`simulation/genome.py`)

Immutable dataclass holding creature traits (all `float` 0.0–1.0):
- `speed`, `size`, `sense_radius`, `aggression`, `hue`, `saturation`, `efficiency`

**Key methods:**
- `Genome.random()` — create random genome
- `genome.mutate(rate)` — return new genome with mutated traits

**Invariant:** All trait values must stay in [0.0, 1.0] range after mutation.

### Creature (`simulation/creature.py`)

Mutable dataclass representing a single organism:
- Position (`x`, `y`), velocity (`vx`, `vy`), `energy`, `age`, `genome`, `trail`

**Key methods:**
- `update_position(dt, world_width, world_height)` — move and wrap
- `steer_toward(x, y, speed_base, world_width, world_height)` — smooth steering
- `wander(speed_base)` — random wandering when no food nearby
- `distance_to(x, y, world_width, world_height)` — toroidal distance
- `get_radius()`, `get_sense_radius()`, `get_movement_cost()`

**Invariant:** Creatures always wrap around world edges (toroidal topology).

### FoodManager (`simulation/food.py`)

Manages all food particles with **spatial bucketing** for efficient neighbor queries.

**Key methods:**
- `spawn()`, `spawn_batch(count)` — create food particles
- `remove(food)` — remove eaten particle
- `find_nearest(x, y, max_radius)` — O(1) average-case lookup using spatial hash

**Invariant:** Maximum 500 food particles; bucket size is 100 pixels.

### Simulation (`simulation/simulation.py`)

Main simulation controller. Owns `creatures` list, `food_manager`, and `settings`.

**Key methods:**
- `step()` — advance simulation by one frame (spawn food, move creatures, handle eating/reproduction/death)
- `reset()` — reinitialize simulation
- `get_dominant_traits()` — returns average genome traits (for LLM narration)

**Properties:**
- `population`, `generation`, `oldest_age`, `food_count`, `paused`

**Invariant:** `step()` must not modify rendering state; simulation is render-agnostic.

### Renderer (`rendering/renderer.py`)

Reads simulation state and draws to pygame surface. Owns `theme`, `hud`, `ambient_particles`.

**Key methods:**
- `draw(simulation)` — render current state
- `set_theme(name)` — change visual theme
- `toggle_hud()` — toggle HUD visibility

**Invariant:** Renderer never mutates simulation state.

### Theme (`rendering/themes.py`)

Abstract base class for visual styling.

**Required methods:**
- `name` (property), `background_color` (property)
- `render_creature(surface, creature, time)`
- `render_food(surface, food, time)`
- `render_ambient(surface, particles, time)`
- `create_ambient_particles(width, height, count)`

**Factory:** `get_theme(name)` returns appropriate theme instance.

### Settings (`settings.py`)

Single dataclass holding all configuration. No global mutable state — pass `Settings` instance to constructors.

## Sim Mode Contract

A new simulation mode must:

1. Be a class with constructor `__init__(self, width: int, height: int, settings: Settings)`
2. Implement `step(self) -> None` to advance simulation by one frame
3. Implement `reset(self) -> None` to reinitialize
4. Expose these properties:
   - `creatures: list[Creature]` — current living creatures
   - `food_manager: FoodManager` — food particle manager
   - `population: int` — current creature count
   - `generation: int` — reproduction counter
   - `oldest_age: int` — age of oldest creature
   - `food_count: int` — current food count
   - `paused: bool` — pause state
   - `settings: Settings` — settings reference
5. Add mode name to `Settings.VALID_SIM_MODES`
6. Update `main.py` to instantiate based on `settings.sim_mode`

## Visual Theme Contract

A new theme must:

1. Inherit from `Theme` ABC in `rendering/themes.py`
2. Implement all abstract methods (see Key Abstractions above)
3. Be registered in `get_theme()` function
4. Add theme name to `Settings.VALID_VISUAL_THEMES`

## Known Stubs

**Simulation modes (not implemented):**
- `predator_prey` — creatures can eat each other based on size/aggression
- `boids` — flocking behavior
- `drift` — passive floating without food-seeking

**Visual themes (not implemented):**
- `petri` — microscope/petri dish aesthetic
- `geometric` — abstract geometric shapes
- `chaotic` — vibrant, high-contrast colors

Each stub shows a "coming soon" overlay. Implementation requires creating the mode/theme class and removing the stub check.

## Ollama Integration Note

A future enhancement will add LLM narration that reads:
- `simulation.generation`
- `simulation.population`
- `simulation.get_dominant_traits()`

The architecture already supports this — `get_dominant_traits()` returns a dict of average trait values. A narrator module can periodically query these and generate commentary.

## Performance Notes

### Spatial Bucketing

`FoodManager` uses a grid-based spatial hash (bucket size 100px) to avoid O(n²) creature-food collision checks. When a creature seeks food:

1. Determine which buckets are within `sense_radius`
2. Only check food particles in those buckets
3. Average case: O(1) per creature; worst case: O(k) where k = particles in range

### Creature Count

With 300 creatures and 500 food particles:
- Per-frame: ~300 food lookups + ~300 position updates
- Each lookup checks ~4-9 buckets on average
- Target: 60 FPS on modern CPU

### Rendering

- Glow surfaces are cached by size/color to avoid repeated creation
- Trails are limited to 8 positions per creature
- Ambient particles use simple sinusoidal movement (no physics)

## Do Not Break

1. **Sim/render decoupling** — `Simulation.step()` must never call pygame or modify visual state
2. **No global mutable state** — all state lives in `Simulation`, `Renderer`, or `Settings` instances
3. **Settings-driven behavior** — no hardcoded numbers; use `Settings` fields
4. **Toroidal world** — creatures and distance calculations must handle wrapping
5. **Genome immutability** — `Genome` is frozen; mutation returns a new instance
6. **Food spatial bucketing** — maintain bucket structure when modifying `FoodManager`
7. **Trail length cap** — always limit creature trails to 8 positions
8. **Energy bounds** — creature energy should stay in [0.0, 1.0] range
