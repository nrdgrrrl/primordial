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
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

## How It Works

### The Genome System

Each creature has a **genome** — a set of 13 heritable traits that determine its characteristics. All traits are floats in the range 0.0–1.0 and can mutate slightly each generation.

#### Survival Traits

| Trait | Range | Effect |
|-------|-------|--------|
| **speed** | 0–1 | Maximum movement speed multiplier |
| **size** | 0–1 | Body radius (4–12 pixels); larger = more collision area but higher energy cost |
| **sense_radius** | 0–1 | Food detection range (40–150 pixels) |
| **aggression** | 0–1 | Reserved for predator-prey mode |
| **hue** | 0–1 | Base color hue (heritable; hue drift > 0.15 triggers speciation) |
| **saturation** | 0–1 | Color saturation |
| **efficiency** | 0–1 | Energy extraction rate from food |

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

### Evolution

1. **Food Seeking**: Creatures sense nearby food particles and steer toward them
2. **Eating**: Touching food gains energy scaled by efficiency
3. **Energy Cost**: Movement costs energy proportional to speed × size
4. **Reproduction**: At energy ≥ 0.8, split into parent + offspring (halved energy each); the offspring genome is mutated
5. **Mutation**: Each of 13 traits has a 5% chance of shifting (gaussian, std 0.08), clamped to 0–1
6. **Speciation**: If hue mutates more than 0.15 in one step, the offspring starts a new lineage
7. **Death**: Energy depleted → 40-frame dissolution animation, then removed
8. **Natural Selection**: Traits that find food efficiently and survive spread

### Population Dynamics

- Population is soft-capped at `max_population` (default 300)
- When population exceeds 50% of max, energy costs increase quadratically
- Boom-bust cycles emerge naturally; generation count tracks total reproductions

## Settings

All settings are configured in `primordial/settings.py`:

```python
# Simulation
sim_mode: str = "energy"          # "energy" implemented; others coming soon
visual_theme: str = "ocean"       # "ocean" implemented; others coming soon
initial_population: int = 80
max_population: int = 300
food_spawn_rate: float = 0.4      # food particles per frame
mutation_rate: float = 0.05       # chance of mutation per trait
energy_to_reproduce: float = 0.8
creature_speed_base: float = 1.5

# Display
fullscreen: bool = True
target_fps: int = 60
show_hud: bool = True

# Glyph rendering
glyph_size_base: int = 48         # base glyph canvas size in pixels

# Kin connection lines
kin_line_max_distance: float = 120.0  # max px between kin for a line
kin_line_min_group: int = 3           # min lineage size before drawing lines

# Territory shimmer
territory_top_n: int = 3              # dominant lineages to show shimmer
territory_shimmer_lerp: float = 0.05  # centroid drift speed (0=snap)
territory_fade_seconds: float = 2.0   # fade-out when lineage leaves top-N

# Animations
death_animation_frames: int = 40
birth_animation_frames: int = 30
death_particle_count: int = 5
```

## Project Structure

```
primordial/
├── primordial/
│   ├── __init__.py
│   ├── main.py              # Entry point, game loop, controls
│   ├── settings.py          # Configuration dataclass
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── creature.py      # Creature class with motion styles
│   │   ├── food.py          # Food and FoodManager
│   │   ├── genome.py        # Genome — 13 heritable traits
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

1. Create a class in `primordial/simulation/` with `__init__(width, height, settings)`, `step()`, `reset()`, and all required properties (see AGENT.md for full contract)
2. The class must also expose `death_events: list[dict]` and `birth_events: list[Creature]` for the AnimationManager
3. Add mode name to `Settings.VALID_SIM_MODES`
4. Update `main.py` to instantiate based on `settings.sim_mode`

### Adding a New Visual Theme

1. Create a class in `themes.py` inheriting from `Theme`
2. Implement all abstract methods including `render_creature(surface, creature, time, scale=1.0)`
3. Register in `get_theme()`
4. Add name to `Settings.VALID_VISUAL_THEMES`

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
