# Primordial

A beautiful cellular evolution screensaver simulation with bioluminescent visuals. Watch glowing creatures evolve, compete for food, and adapt to their environment in an endless cycle of life and death.

Primordial is designed to run indefinitely on a monitor as a living screensaver, featuring smooth animations, emergent behavior, and visually stunning deep-sea aesthetics.

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

Each creature has a **genome** — a set of heritable traits that determine its characteristics:

| Trait | Range | Effect |
|-------|-------|--------|
| **speed** | 0.0–1.0 | Maximum movement speed multiplier |
| **size** | 0.0–1.0 | Body radius (4–12 pixels); larger = more collision area but higher energy cost |
| **sense_radius** | 0.0–1.0 | Detection range for food (40–150 pixels) |
| **aggression** | 0.0–1.0 | Reserved for predator-prey mode |
| **hue** | 0.0–1.0 | Base color hue (purely visual, but heritable) |
| **saturation** | 0.0–1.0 | Color saturation |
| **efficiency** | 0.0–1.0 | Energy extraction rate from food |

### Evolution

1. **Food Seeking**: Creatures sense nearby food particles and steer toward them using smooth steering behavior
2. **Eating**: When a creature touches food, it gains energy scaled by its efficiency trait
3. **Energy Cost**: Movement costs energy proportional to speed × size
4. **Reproduction**: When a creature's energy reaches the reproduction threshold (default 0.8), it splits into two — parent and offspring each get half the energy
5. **Mutation**: The offspring's genome is copied from the parent, but each trait has a chance (default 5%) to mutate by a small random amount (gaussian, std 0.08)
6. **Death**: When energy drops to zero, the creature dies
7. **Natural Selection**: Over generations, traits that help creatures find food efficiently and survive become more common in the population

### Population Dynamics

- Population is soft-capped at `max_population` (default 300)
- When population exceeds 50% of max, energy costs increase quadratically
- This creates boom-bust cycles as the population approaches carrying capacity
- Generation count increments with each reproduction event

## Settings

All settings are configured in `primordial/settings.py`. You can modify these values directly:

```python
@dataclass
class Settings:
    # Simulation mode: "energy" is fully implemented
    # "predator_prey", "boids", "drift" are coming soon
    sim_mode: str = "energy"

    # Visual theme: "ocean" is fully implemented
    # "petri", "geometric", "chaotic" are coming soon
    visual_theme: str = "ocean"

    # Population settings
    initial_population: int = 80      # Starting creatures
    max_population: int = 300         # Soft population cap

    # Food settings
    food_spawn_rate: float = 0.4      # Food particles per frame

    # Evolution settings
    mutation_rate: float = 0.05       # Chance of mutation per trait
    energy_to_reproduce: float = 0.8  # Energy threshold for reproduction

    # Creature settings
    creature_speed_base: float = 1.5  # Base movement speed multiplier

    # Display settings
    fullscreen: bool = True           # Start in fullscreen mode
    target_fps: int = 60              # Target frame rate
    show_hud: bool = True             # Show HUD on startup
```

## Extending Primordial

### Adding a New Simulation Mode

1. Create a new simulation class in `primordial/simulation/` (e.g., `boids_simulation.py`)

2. Your class should match the interface of `Simulation`:
   - `__init__(self, width, height, settings)` — initialize the simulation
   - `step(self)` — advance simulation by one frame
   - `reset(self)` — reset to initial state
   - Properties: `population`, `generation`, `oldest_age`, `food_count`, `creatures`, `food_manager`, `paused`, `settings`

3. Update `primordial/simulation/__init__.py` to export your class

4. Modify `main.py` to instantiate your simulation class based on `settings.sim_mode`

5. Add validation for your mode name in `Settings.VALID_SIM_MODES`

### Adding a New Visual Theme

1. Create a new theme class in `primordial/rendering/themes.py`

2. Inherit from `Theme` and implement all abstract methods:
   ```python
   class MyTheme(Theme):
       @property
       def name(self) -> str:
           return "mytheme"

       @property
       def background_color(self) -> tuple[int, int, int]:
           return (r, g, b)

       def render_creature(self, surface, creature, time) -> None:
           # Draw creature to surface
           pass

       def render_food(self, surface, food, time) -> None:
           # Draw food particle to surface
           pass

       def render_ambient(self, surface, particles, time) -> None:
           # Draw background ambient particles
           pass

       def create_ambient_particles(self, width, height, count) -> list[AmbientParticle]:
           # Create and return ambient particle list
           pass
   ```

3. Update `get_theme()` function in `themes.py` to return your theme for its name

4. Add your theme name to `Settings.VALID_VISUAL_THEMES`

## Project Structure

```
primordial/
├── primordial/
│   ├── __init__.py
│   ├── main.py              # Entry point, game loop, controls
│   ├── settings.py          # Configuration dataclass
│   ├── simulation/
│   │   ├── __init__.py
│   │   ├── creature.py      # Creature class
│   │   ├── food.py          # Food and FoodManager
│   │   ├── genome.py        # Genome traits
│   │   └── simulation.py    # Main simulation logic
│   └── rendering/
│       ├── __init__.py
│       ├── hud.py           # Heads-up display
│       ├── renderer.py      # Main renderer
│       └── themes.py        # Visual themes
├── requirements.txt
├── README.md
├── AGENT.md
├── CHANGELOG.md
└── .gitignore
```

## License

MIT License
