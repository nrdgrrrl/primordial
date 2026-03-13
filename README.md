# Primordial

A beautiful cellular evolution screensaver simulation with bioluminescent visuals. Watch glowing symbolic creatures evolve, compete for food, and adapt to their environment in an endless cycle of life and death.

Primordial is designed to run indefinitely on a monitor as a living screensaver, featuring smooth animations, emergent behavior, deep-sea aesthetics, and procedurally generated creature glyphs.

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd primordial

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Running

```bash
# Make sure your virtual environment is activated
source .venv/bin/activate

# Run (normal mode)
python main.py

# Launch a specific mode/theme for this run only
python main.py --mode boids --theme ocean

# Enable debug overlays and verbose console logging
python main.py --debug

# Run a 60-second cProfile capture and exit
python main.py --profile

# Resume a saved world, then save the updated snapshot on exit
python main.py --load build/world.json --save build/world.json
```

Predator-prey snapshots also persist the current seed, `sim_ticks`,
`survival_ticks`, rolling last-20 survival history, and adaptive dial trial
state. Separately, the adaptive predator-prey tuning state is saved on app exit
and reloaded on the next launch, so dial progress survives without a world
snapshot.

The screensaver will launch in fullscreen mode by default.

### Runtime CLI Flags

| Flag | Effect |
|---|---|
| `--debug` | Enables debug HUD timing lines, FPS/population graph overlay, and verbose console logging |
| `--profile` | Runs for 60 seconds, writes `.pstats` + text profile report to config directory, then exits |
| `--mode <name>` | Launch override: `energy`, `predator_prey`, `boids`, `drift` |
| `--theme <name>` | Launch override: `ocean`, `petri`, `geometric`, `chaotic` |
| `--load <path>` | Load a saved simulation world snapshot instead of creating a new world |
| `--save <path>` | Save the current world snapshot to the given path on exit |

### Make Targets

```bash
make run       # python main.py
make debug     # python main.py --debug
make profile   # python main.py --profile
make build     # python build.py
make clean     # remove build/dist and __pycache__ dirs
```

## Keyboard Controls

| Key | Action |
|-----|--------|
| `ESC` or `Q` | Quit the screensaver |
| `H` | Toggle HUD (heads-up display) |
| `Space` | Pause/unpause simulation, or skip the predator_prey `GAME OVER` wait and restart immediately |
| `F` | Toggle fullscreen/windowed mode |
| `R` | Reset simulation (new population) |
| `S` | Open in-app settings overlay (disabled in /s screensaver mode) |
| Hold `P` | Highlight predators while held in `predator_prey` mode |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

## Performance

Recent profile-driven optimization (2026-03-05) improved headless benchmark performance significantly:

- Energy mode step @ pop 150: `4.082ms → 2.005ms`
- Energy mode full frame @ pop 150: `25.445ms → 13.425ms`
- Boids mode step @ pop 150: `16.829ms → 11.887ms`

At 1920×1080 this keeps typical runs within the 60fps target envelope in normal mode, with heavy boids scenes still the most expensive.

## Design & Behavior Documentation

For a thorough human-readable guide to how the simulation works as a living system — especially predator_prey mode — see **[docs/predator_prey_system_guide.md](docs/predator_prey_system_guide.md)**. It covers world mechanics, predator/prey ecology, evolutionary features, observability gaps, and a design assessment.

## How It Works

### The Genome System

Each creature has a **genome** — a set of 15 heritable traits that determine its characteristics. All traits are floats in the range 0.0–1.0 and can mutate slightly each generation.

#### Survival Traits

| Trait | Range | Effect |
|-------|-------|--------|
| **speed** | 0–1 | Maximum movement speed multiplier |
| **size** | 0–1 | Body radius (4–12 pixels); larger = more collision area but higher energy cost |
| **sense_radius** | 0–1 | Food detection range (40–150 pixels); declines after 85% of max lifespan |
| **aggression** | 0–1 | Feeding strategy: <0.4 = grazer (+20% food efficiency, ignores prey), >0.6 = hunter (seeks and drains nearby creatures), 0.4–0.6 = opportunist |
| **efficiency** | 0–1 | Energy extraction rate from food |
| **longevity** | 0–1 | Maximum lifespan: 0 = ~3000 frames (~50s), 1 = ~10000 frames (~2.8min); high longevity costs energy each frame |
| **hue** | 0–1 | Base color hue (heritable; hue drift > 0.15 triggers speciation) |
| **saturation** | 0–1 | Color saturation |

#### Glyph Traits — What You See

Each creature's body is a **procedurally generated symbolic glyph** derived entirely from its genome. Related creatures look visually related; mutations produce similar but distinct offspring.

| Trait | Range | Visual Effect |
|-------|-------|---------------|
| **complexity** | 0–1 | Number of strokes: 0 → 2 strokes, 1 → 7 strokes |
| **symmetry** | 0–1 | 0–0.33: asymmetric; 0.33–0.66: bilateral mirror; 0.66–0.83: 3-fold radial; 0.83–1.0: 4-fold radial |
| **stroke_scale** | 0–1 | Overall size and delicacy of strokes (low = compact, high = spread) |
| **appendages** | 0–1 | 0–4 extra limb strokes radiating from the glyph perimeter |
| **rotation_speed** | 0–1 | Glyph slowly drifts (0) to steadily spins (1) |

Glyphs are built from a **stroke vocabulary**: arcs, straight lines, loops (small ovals), forks (Y-splits), spirals, and dots. The combination chosen is always the same for a given genome — so you can learn to recognize lineages by glyph family resemblance.

#### Social Trait — Flocking Behaviour

| Trait | Range | Effect |
|-------|-------|--------|
| **conformity** | 0–1 | Tendency to align velocity with neighbours (0 = pure individualist, 1 = strong aligner). Primarily expressed in **boids** mode but is heritable and evolves under selection pressure in all modes. |

#### Motion Trait — How They Move

| Trait | Range | Behavior |
|-------|-------|----------|
| **motion_style** | 0–0.33 | **Glide** — smooth continuous curves, slow gentle drift. Long smooth trail (14 positions). |
| | 0.34–0.66 | **Swim** — sinusoidal lateral oscillation added to forward velocity. Undulating motion. Medium trail (10 positions). |
| | 0.67–1.00 | **Dart** — mostly stationary with periodic fast bursts (1.8× max speed). Short sharp trail (5 positions). |

### What to Look For Visually

- **Kin connection lines**: faint thin lines connect creatures of the same lineage when 3+ kin are within 120 pixels. Watch these webs form, drift, and dissolve as lineages evolve.
- **Territory shimmer**: the top 3 most populous lineages get a soft pulsing elliptical glow at their centroid. This "presence" shifts as lineages grow and shrink. It pulses on a 4–6 second sine wave.
- **Birth budding**: new creatures pop into existence at 0.2× scale and ease out to full size over 30 frames — a smooth "budding" effect.
- **Death dissolution**: dying creatures flash white, then shrink and fade over 40 frames, scattering 4–6 dim particles outward.
- **Glyph rotation**: each creature's glyph rotates at a rate set by `rotation_speed` — gliders barely turn, some creatures spin continuously.
- **Population cycles**: the overcrowding energy penalty creates boom-bust cycles. Watch population rise, crash, and re-stabilize.
- **Speciation events**: when a creature's offspring inherits a hue mutation > 0.15, it gets a new lineage ID. Kin lines for the old lineage gradually fade as the old line dies out and new lines emerge.
- **Aging**: creatures past 70% of their max lifespan gradually grey out. Ancient creatures become visibly desaturated and slower — a soft visual indicator of senescence.
- **Cosmic rays**: a faint white ring briefly expands around a creature struck by a spontaneous single-trait mutation. Watch for these in slow periods — they can seed sudden new lineage directions.
- **Attack lines**: when a hunter drains a nearby creature, a thin colored thread briefly connects them.
- **Zone backgrounds**: subtle radial tints mark the 5 environmental zones (warm vent, open water, kelp forest, hunting ground, deep trench). Creatures that evolve for their zone gain an energy advantage.

### Watching Evolution

Over a 10–30 minute run, you can observe real selection pressure at work:

- **Glyph family divergence**: At startup, all glyphs look similar (random mutations from a common ancestor). After ~5 minutes, distinct visual clans emerge — recognizable by glyph shape, symmetry type, and rotation. Kin lines help trace which families dominate which regions.

- **Hunter/grazer balance shifting with food cycles**: The HUD shows `H:N G:N O:N` counts. During feast phases (food bar toward right), grazers can outpace hunters. During famines, hunters profit from harvesting grazers — watch the ratio flip. At equilibrium, hunters and grazers coexist through frequency-dependent selection: hunting is only profitable when prey are plentiful.

- **Zone adaptation**: Creatures gradually cluster in zones that favor their trait profile. A high-efficiency lineage will tend to concentrate near warm vents; fast aggressive hunters gravitate toward hunting grounds. This takes many generations — look for the territory shimmer centroid drifting toward favorable zones.

- **Longevity vs. fecundity tradeoff**: High-longevity creatures live longer but pay an energy tax each frame and reproduce less often. During stable boom periods, you'll see long-lived types persist; during crashes, short-lived fast-reproducers may bounce back faster. The HUD shows average old-age lifespan in seconds.

- **Cosmic ray injections**: Occasionally a creature's glyph shape visibly changes without reproduction. This is a cosmic ray hit — a single-trait mutation. These are most visible as sudden glyph asymmetry shifts or rotation speed jumps in long-lived lineages.

### Evolution

1. **Food Seeking**: Creatures sense nearby food and steer toward it; sense radius declines with age
2. **Eating**: Touching food gains energy scaled by `efficiency`; grazers get a +20% bonus
3. **Hunting**: Hunters (aggression > 0.6) seek and drain energy from smaller nearby creatures; deal damage proportional to size ratio and aggression
4. **Energy Cost**: Movement costs energy proportional to speed × size; high aggression and high longevity each add a continuous metabolic drain
5. **Food Cycles**: Food spawn rate oscillates sinusoidally over ~30 seconds — alternating feast and famine. Boom-bust ecological cycles emerge from this pressure.
6. **Zones**: Five environmental zones grant ±20% energy modifiers based on trait matching. Creatures evolve toward zones that favor their profile.
7. **Reproduction**: At energy ≥ 0.8, split into parent + offspring (halved energy each); offspring genome is mutated
8. **Mutation**: Each of 15 traits has a ~6% chance of shifting (gaussian, std 0.08), clamped to 0–1
9. **Cosmic Rays**: Each creature has a small per-frame chance of a single spontaneous trait mutation (independent of reproduction)
10. **Aging**: Creatures have a maximum lifespan determined by `longevity`. Speed declines after 70% of max lifespan; sense radius after 85%. Death by old age emits scatter particles.
11. **Speciation**: If hue mutates more than 0.15 in one step, the offspring starts a new lineage
12. **Death**: Energy depleted or max lifespan reached → 40-frame dissolution animation, scatter particles, then removed
13. **Natural Selection**: Traits that find food efficiently, survive predation, and thrive in local zones spread

### Population Dynamics

- Population is soft-capped at `max_population` (default 220)
- When population exceeds 50% of max, energy costs increase quadratically
- Food cycles, predation, and aging interact to produce complex boom-bust dynamics
- Energy/boids/drift expose generation counts; predator_prey tracks `sim_ticks`,
  run `survival_ticks`, and rolling stability stats instead

## Simulation Modes

Primordial ships with four fully independent simulation modes selectable in the settings overlay (`S`) or via the user `config.toml`.

### Energy Mode (default)

The classic Primordial experience. Creatures forage for food, hunt each other, and evolve under Darwinian selection pressure. Features food cycles (feast/famine), environmental zones, hunter/grazer arms races, and kin territory shimmer.

**Best for:** watching genuine natural selection and glyph-family divergence over 10–30 minute runs.

HUD shows: population, generation count, hunter/grazer/opportunist ratio, dominant trait values, food cycle bar.

### Predator Prey Mode

A Lotka-Volterra ecosystem where creatures are born as either **predator** (30%) or **prey** (70%). Predators hunt prey on contact, prey flee from nearby predators, and the success metric is **stability**: how many simulation ticks the run survives before either species collapses to zero.

- Arms race evolution: predator aggression and prey speed evolve under mutual selection pressure.
- Cosmic ray hits can flip species identity when aggression crosses the 0.5 threshold.
- When predators exceed 60% of the population, predator reproduction becomes harder: their reproduction threshold increases by 20%.
- Extinction is terminal in this mode: predator or prey collapse freezes the run, tints the screen red, shows a `GAME OVER` overlay for 5 seconds, then restarts with a new seed.
- Pressing `Space` during that `GAME OVER` screen skips the wait and starts the next seeded run immediately.
- The `GAME OVER` overlay also shows the current run's adaptive dial values, highlights the dial changed for that run with its up/down delta, and marks the highest survival tick record when a run sets a new best.
- The HUD shows `sim_ticks`, current seed, current `survival_ticks`, rolling average survival over the last 20 completed runs, and best recent survival.
- A small adaptive tuning pass tweaks one bounded ecological dial at a time after below-average collapses, then keeps or reverts the trial result on the next run. That tuning state is written on exit and restored on the next launch.
- Predators render in warm hues (high hue), prey in cool hues (low hue).

**Best for:** watching whether predator/prey coexistence remains stable across many seeded runs.

HUD shows: predator count, prey count, avg predator speed vs. avg prey speed, `sim_ticks`, seed, survival stats, and trial-dial status.

### Boids Mode

A Reynolds boids flocking simulation where genome traits directly control the three boid forces:

| Force | Controlled by |
|-------|---------------|
| Separation (avoid crowding) | `aggression` |
| Alignment (match velocity) | `conformity` |
| Cohesion (stay with group) | `efficiency` |

Creatures gain a small passive energy bonus for being in a flock of 3–12 neighbours (optimal flock size). Flocks are detected each frame via BFS on the neighbour graph. Creatures in the same flock synchronise their glyph pulse phase over time — flocks pulse together.

Kin lines are replaced by **flock lines**: faint connections between creatures sharing a flock ID.

**Best for:** mesmerising murmuration-style motion and watching emergent flock structures form and break apart.

HUD shows: population, flock count, largest flock size, average conformity, generation count.

### Drift Mode

A purely aesthetic, meditative mode inspired by genetic drift — evolution without selection. There is no food. Creatures regen energy passively (+0.002/frame) and can only die of old age. All creatures use the glide motion style regardless of genome. Cosmic ray rate is doubled, causing continuous gentle mutation visible as glyph shimmer.

- Very slow, dreamlike movement: halved rotation speed, doubled trail length.
- No hunger, no predation, no zones — only time and mutation.
- Populations are smaller (default 60) for a quieter, more spacious canvas.

**Best for:** a calm ambient display, and observing pure neutral genetic drift detached from selection pressure.

HUD shows: population, generation count, lineage count, most variable trait (the trait currently drifting fastest), average conformity.

## Which Mode Should I Use?

| If you want… | Use |
|---|---|
| Classic evolution — food, predation, zones | **energy** |
| Oscillating predator/prey population cycles | **predator_prey** |
| Flocking murmurations and emergent group behaviour | **boids** |
| A calm ambient display, pure visual drift | **drift** |

You can switch modes at any time with `S` → change Mode → Apply. The simulation fades to black, resets with the new mode's starting population, and fades back in.

## Settings

Configuration is TOML-backed and persistent across app updates.

- Press **`S`** in normal mode to open the in-app settings overlay.
- Press **`H`** while the settings overlay is open to launch the local predator/prey guide in your browser; Primordial drops out of fullscreen first if needed.
- Canonical repo-tracked defaults live in [`primordial/config/defaults.toml`](/home/victoria/projects/primordial/primordial/config/defaults.toml).
- The runtime user override file is editable by hand as `config.toml`.
- User config locations:
  - **Windows:** `~/AppData/Roaming/Primordial/config.toml`
  - **macOS:** `~/Library/Application Support/Primordial/config.toml`
  - **Linux:** `~/.config/primordial/config.toml`
- Load order is: committed canonical defaults first, then the platform user config file as overrides.
- On first run, Primordial writes a user `config.toml` populated from the canonical defaults.
- Runtime logs are written beside config as `primordial.log` (all modes, including screensaver).

### Settings Reference

| Section | Key | Type / Range | Description |
|---|---|---|---|
| simulation | mode | enum: energy/predator_prey/boids/drift | Active simulation mode |
| simulation | initial_population | int >= 0 | Initial creature count (requires reset) |
| simulation | max_population | int >= 1 | Soft population cap |
| simulation | food_spawn_rate | float >= 0 | Base food spawn rate |
| simulation | food_max_particles | int >= 1 | Hard cap on world food particles |
| simulation | food_cycle_enabled | bool | Enables feast/famine cycle |
| simulation | food_cycle_period | int >= 1 | Frames per food cycle |
| simulation | mutation_rate | float 0..1 | Per-trait mutation chance |
| simulation | cosmic_ray_rate | float 0..1 | Per-frame spontaneous mutation chance |
| simulation | energy_to_reproduce | float 0.05..1 | Reproduction energy threshold |
| simulation | creature_speed_base | float > 0 | Global movement scale |
| simulation | zone_count | int >= 0 | Number of generated environmental zones |
| simulation | zone_strength | float 0..1 | Zone effect intensity |
| display | visual_theme | enum: ocean/petri/geometric/chaotic | Rendering theme |
| display | fullscreen | bool | Fullscreen/windowed mode |
| display | target_fps | int >= 1 | Frame limit |
| display | show_hud | bool | HUD visibility |
| rendering | glyph_size_base, kin/shimmer/animation fields | validated numeric ranges | Renderer tuning knobs (advanced) |

Mode-specific tuning keys:

| Section | Key | Type / Range | Description |
|---|---|---|---|
| modes.predator_prey | prey_energy_to_reproduce | float 0.05..1 | Prey-only reproduction threshold in `predator_prey`; falls back to shared `simulation.energy_to_reproduce` if absent |
| modes.predator_prey | predator_energy_to_reproduce | float 0.05..1 | Predator-only reproduction threshold in `predator_prey`; falls back to shared `simulation.energy_to_reproduce` if absent |
| modes.predator_prey | prey_flee_sense_multiplier | float 0.1..5 | Multiplier applied to prey threat sensing while fleeing |
| modes.predator_prey | predator_prey_scarcity_penalty_multiplier | float 0.1..5 | Extra predator energy-cost multiplier when prey fall below 15% of population |
| modes.predator_prey | food_cycle_amplitude | float 0..1 | Blend between constant food rate (`0`) and the full feast/famine swing (`1`) |

These mode-table tuning keys live in TOML config authority today; the in-app settings overlay still edits only the top-level settings fields.

### Tuning

These are the levers most likely to change the feel of the simulation:

| Goal | Setting | Change |
|------|---------|--------|
| More dramatic famines | `food_max_particles` | Lower (e.g. 150) |
| Slower food cycles | `food_cycle_period` | Higher (e.g. 3600) |
| Disable food cycles | `food_cycle_enabled` | `False` |
| More predation pressure | `cosmic_ray_rate` + `mutation_rate` | Higher (more trait diversity) |
| Faster evolution | `mutation_rate` | Higher (e.g. 0.10) |
| Longer-lived creatures | (genome evolves) | Reduce `food_max_particles` — famines favor longevity |
| More zone influence | `zone_strength` | Higher (max 1.0) |
| Disable zones | `zone_strength` | `0.0` |
| Bigger populations | `max_population` | Higher (300+), expect more hunting noise |
| Disable cosmic rays | `cosmic_ray_rate` | `0.0` |

## Project Structure

```
primordial/
├── main.py                  # Top-level launcher (screensaver args + runtime CLI flags)
├── Makefile                 # run/debug/profile/build/clean shortcuts
├── primordial/
│   ├── __init__.py
│   ├── main.py              # Real entry point, game loop, controls, logging
│   ├── config/              # Config loader plus committed canonical defaults TOML
│   ├── settings.py          # Compatibility alias to Config
│   ├── utils/
│   │   ├── screensaver.py   # /s /p /c parsing
│   │   ├── cli.py           # --debug/--profile/--mode/--theme parsing
│   │   └── paths.py         # Frozen/dev path resolver
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── creature.py      # Creature class with motion styles and aging
│   │   ├── food.py          # Food and FoodManager (spatial bucket)
│   │   ├── genome.py        # Genome — 15 heritable traits
│   │   ├── zones.py         # Environmental zones and ZoneManager
│   │   └── simulation.py    # Main simulation logic + event queues
│   └── rendering/
│       ├── __init__.py
│       ├── glyphs.py        # Procedural glyph generation from genome
│       ├── animations.py    # AnimationManager — death/birth effects
│       ├── hud.py           # Heads-up display
│       ├── renderer.py      # Main renderer + kin lines + shimmer
│       └── themes.py        # Visual themes (OceanTheme, StubTheme)
├── requirements.txt
├── README.md
├── AGENT.md
├── CHANGELOG.md
└── .gitignore
```




## Extending Primordial

### Adding a New Simulation Mode

All modes live inside the single `Simulation` class in `primordial/simulation/simulation.py` as `_step_<mode>()` / `_spawn_initial_population_<mode>()` methods. To add a mode:

1. Add a `_spawn_initial_population_<name>()` method and dispatch it from `_spawn_initial_population()`.
2. Add a `_step_<name>()` method and dispatch it from `step()`.
3. Add the mode name to `Config.VALID_SIM_MODES`.
4. Add the canonical defaults in [`primordial/config/defaults.toml`](/home/victoria/projects/primordial/primordial/config/defaults.toml), including an explicit `[modes.<name>]` section for any mode-specific knobs.
5. Update config parsing/serialization in [`primordial/config/config.py`](/home/victoria/projects/primordial/primordial/config/config.py).
6. Add the settings overlay option list and HUD lines in `hud.py` (`_lines_<name>()` + dispatch in `render()`).

See AGENT.md for the full Sim Mode Contract.

### Adding a New Visual Theme

1. Create a class in `themes.py` inheriting from `Theme`
2. Implement all abstract methods including `render_creature(surface, creature, time, scale=1.0)`
3. Register in `get_theme()`
4. Add name to `Config.VALID_VISUAL_THEMES`

## Screensaver Installation (Windows)

### Method 1 — Right-click install (recommended)

1. Build: `python build.py`
2. Right-click `dist/primordial.scr` → **Install**
3. Open **Screensaver Settings** → select **Primordial** → **OK**

### Method 2 — Manual

1. Build: `python build.py`
2. Copy `dist/primordial.scr` to `C:\Windows\System32\`
3. Open **Screensaver Settings** → select **Primordial** → **OK**

### To uninstall

Delete `primordial.scr` from `C:\Windows\System32\`.

> **Note:** The `.scr` file is self-contained — no other files or Python installation needed.

---

## Distribution

### Run from source

Follow the Installation and Running steps above. Requires Python 3.12+ and the dependencies in `requirements.txt`.

### Build a standalone executable

```bash
# Activate your virtual environment first
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Run the build script
python build.py
```

This produces:
- **Linux/Mac:** `dist/primordial` — a single self-contained ELF/Mach-O binary
- **Windows:** `dist/primordial.exe` — a single self-contained PE executable (direct launch)
- **Windows:** `dist/primordial.scr` — identical copy of the `.exe`, installable as a screensaver

Expected output size is **~30–50 MB** (pygame + numpy bundled in).

#### Deploy

Just copy `dist/primordial.exe` (Windows) or `dist/primordial` (Linux) to any machine — no Python, no pip, no installation required. Double-click on Windows; `chmod +x primordial && ./primordial` on Linux.

#### Reproducible builds

After the first `python build.py` run, PyInstaller writes `primordial.spec` to the project root. Subsequent builds can use it directly for identical results:

```bash
pyinstaller primordial.spec
```

#### Platform notes

| Platform | Tested | Notes |
|----------|--------|-------|
| Linux x86-64 | ✅ | Verified — `dist/primordial` 33.1 MB |
| Windows x86-64 | ❌ untested | Should work; `dist/primordial.exe` produced cross-platform build is untested |
| macOS | ❌ untested | `--noconsole` becomes `--windowed`; may need code signing |

## M4 analysis tools

The project includes offline M4 analysis tools for recording sampled history artifacts, generating seeded comparison reports, and inspecting artifacts from the command line.

Current tools:
- `tools/analysis_history.py`
- `tools/analysis_compare.py`
- `tools/inspect_history.py`

These are development and analysis tools, not an in-game dashboard or visual replay system.

### Quick start

Record a history artifact:

```bash
.venv/bin/python tools/analysis_history.py \
  --scenario energy_medium \
  --steps 180 \
  --sample-every 30 \
  --output build/milestones/M4/energy_history.json
Inspect the artifact:

.venv/bin/python tools/inspect_history.py \
  --history build/milestones/M4/energy_history.json

Generate a same-seed comparison report:

.venv/bin/python tools/analysis_compare.py \
  --scenario energy_medium \
  --seed 424242 \
  --steps 180 \
  --sample-every 30 \
  --output build/milestones/M4/energy_same_seed_compare.json

Recommended representative scenarios:

energy_medium

predator_prey_medium

boids_dense

Use these tools when you want to understand long-run behavior, inspect lineage and zone trends, or verify whether behavior changes are real rather than random variance.
