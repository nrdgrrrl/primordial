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

# Run the screensaver
python -m primordial.main
```

The screensaver will launch in fullscreen mode by default.

## Keyboard Controls

| Key | Action |
|-----|--------|
| `ESC` or `Q` | Quit the screensaver |
| `H` | Toggle HUD (heads-up display) |
| `Space` | Pause/unpause simulation |
| `F` | Toggle fullscreen/windowed mode |
| `R` | Reset simulation (new population) |
| `S` | Open in-app settings overlay (disabled in /s screensaver mode) |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

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
- Generation count tracks total reproductions; oldest creature tracked as % of max lifespan

## Simulation Modes

Primordial ships with four fully independent simulation modes selectable in the settings overlay (`S`) or via `config.toml`.

### Energy Mode (default)

The classic Primordial experience. Creatures forage for food, hunt each other, and evolve under Darwinian selection pressure. Features food cycles (feast/famine), environmental zones, hunter/grazer arms races, and kin territory shimmer.

**Best for:** watching genuine natural selection and glyph-family divergence over 10–30 minute runs.

HUD shows: population, generation count, hunter/grazer/opportunist ratio, dominant trait values, food cycle bar.

### Predator Prey Mode

A Lotka-Volterra ecosystem where creatures are born as either **predator** (30%) or **prey** (70%). Predators hunt prey on contact and drain energy proportional to prey size; prey flee from nearby predators. Populations oscillate in classic predator-prey cycles.

- Arms race evolution: predator aggression and prey speed evolve under mutual selection pressure.
- Cosmic ray hits can flip species identity when aggression crosses the 0.5 threshold.
- Automatic ecosystem rescue when either species nears extinction (inject a small cohort of the depleted species).
- Predators render in warm hues (high hue), prey in cool hues (low hue).

**Best for:** oscillating population dynamics — watch predator and prey counts chase each other in boom-bust waves.

HUD shows: predator count, prey count, avg predator speed vs. avg prey speed, dominant trait values.

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

Configuration is now TOML-backed and persistent across app updates.

- Press **`S`** in normal mode to open the in-app settings overlay.
- Config is also editable by hand in `config.toml`.
- File locations:
  - **Windows:** `~/AppData/Roaming/Primordial/config.toml`
  - **macOS:** `~/Library/Application Support/Primordial/config.toml`
  - **Linux:** `~/.config/primordial/config.toml`

### Settings Reference

| Section | Key | Type / Range | Description |
|---|---|---|---|
| simulation | mode | enum: energy/predator_prey/boids/drift | Active simulation mode |
| simulation | initial_population | int >= 0 | Initial creature count (requires reset) |
| simulation | max_population | int >= 1 | Soft population cap |
| simulation | food_spawn_rate | float >= 0 | Base food spawn rate |
| simulation | food_cycle_enabled | bool | Enables feast/famine cycle |
| simulation | food_cycle_period | int >= 1 | Frames per food cycle |
| simulation | mutation_rate | float 0..1 | Per-trait mutation chance |
| simulation | cosmic_ray_rate | float 0..1 | Per-frame spontaneous mutation chance |
| simulation | energy_to_reproduce | float 0.05..1 | Reproduction energy threshold |
| simulation | creature_speed_base | float > 0 | Global movement scale |
| simulation/evolution | zone_count | int >= 0 | Number of generated environmental zones |
| simulation/evolution | zone_strength | float 0..1 | Zone effect intensity |
| display | visual_theme | enum: ocean/petri/geometric/chaotic | Rendering theme |
| display | fullscreen | bool | Fullscreen/windowed mode |
| display | target_fps | int >= 1 | Frame limit |
| display | show_hud | bool | HUD visibility |

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
├── primordial/
│   ├── __init__.py
│   ├── main.py              # Entry point, game loop, controls
│   ├── config/              # TOML-backed Config class and path logic
│   ├── settings.py          # Compatibility alias to Config
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
3. Add mode-specific built-in defaults to `_MODE_DEFAULTS` dict.
4. Add mode name to `Config.VALID_SIM_MODES` and the settings overlay option list.
5. Add HUD lines in `hud.py` (`_lines_<name>()` + dispatch in `render()`).
6. Optionally add a `[modes.<name>]` TOML section in `Config.to_toml()`.

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
| Linux x86-64 | ✅ | Verified — `dist/primordial` 31.9 MB |
| Windows x86-64 | ❌ untested | Should work; `dist/primordial.exe` produced cross-platform build is untested |
| macOS | ❌ untested | `--noconsole` becomes `--windowed`; may need code signing |

## License

MIT License
