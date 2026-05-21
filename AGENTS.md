# AGENTS.md — Primordial Codebase Context

This document is for AI coding agents tasked with extending or modifying the Primordial codebase.

Detailed design/system reference: `docs/architecture_reference.md`
Build/integration details: `docs/build_and_integration.md`

## Agent instructions
Whenever you make code changes you MUST make a meaningful git commit
Whenever you make code changes you MUST update CHANGELOG.md with an explanation of the change.

## Project Summary

Primordial is a fullscreen Python screensaver featuring a cellular evolution simulation with bioluminescent visuals. Creatures with heritable genomes compete for food, reproduce with mutations, and evolve over time. The app is designed to run indefinitely on a monitor.

**Design philosophy:**
- Simulation and rendering are strictly decoupled
- All behavior is driven by the `Config` object — no hardcoded magic numbers
- Performance-sensitive code uses spatial bucketing (no O(n²) loops)
- Creatures are data-driven: the genome determines all behavior
- Visual themes are pluggable and don't affect simulation logic

## Architecture Map

```
primordial/                  ← project root
├── main.py                  # Top-level entry point for direct run and PyInstaller
│                            #   Parses screensaver args, sets SDL_WINDOWID if preview,
│                            #   parses runtime flags (--debug/--profile/--mode/--theme),
│                            #   then delegates to primordial.main.main(scr_args, runtime_args)
├── build.py                 # Cross-platform build script (produces dist/primordial[.exe/.scr])
├── Makefile                 # Dev shortcuts: run, debug, profile, build, clean
├── primordial.spec          # PyInstaller spec — commit this for reproducible builds
├── requirements.txt         # Runtime deps + pyinstaller under # build
└── primordial/              ← Python package
    ├── main.py              # Real entry point, pygame init, game loop, event handling
    │                        #   main(scr_args) branches on screensaver mode
    ├── config/
    │   ├── config.py        # Config class + persistent TOML load/save
    │   └── __init__.py
    ├── settings.py          # Compatibility alias to Config
    ├── utils/
    │   ├── paths.py         # get_base_path() — resolves paths in dev + frozen builds
    │   ├── screensaver.py   # ScreensaverArgs + parse_screensaver_args()
    │   └── cli.py           # RuntimeArgs + parse_runtime_args() for --debug/--profile/--mode/--theme
    ├── simulation/
    │   ├── genome.py        # Genome dataclass — heritable traits (13 traits)
    │   ├── creature.py      # Creature — position, velocity, energy, behavior, motion style
    │   ├── food.py          # Food particle and FoodManager with spatial bucketing
    │   ├── simulation.py    # Simulation — orchestrates creatures, food, evolution, events
    └── rendering/
        ├── glyphs.py        # Glyph rendering system — stroke vocabulary, deterministic assembly
        ├── animations.py    # AnimationManager — death/birth animations, decoupled from sim
        ├── themes.py        # Theme ABC and implementations (OceanTheme, StubTheme)
        ├── hud.py           # HUD overlay for simulation stats
        └── renderer.py      # Renderer — draws state, kin lines, territory shimmer, animations
```

## Sim Mode Contract

All four modes are implemented as `_step_<mode>()` private methods on the single
`Simulation` class. `step()` dispatches to the appropriate method based on
`settings.sim_mode`. A new mode must:

1. Add `_step_<mode>(self) -> None` to Simulation
2. Add `_spawn_initial_population_<mode>(self) -> None` and register it in
   `_spawn_initial_population()`
3. Add mode name to `Settings.VALID_SIM_MODES`
4. Add canonical defaults in `primordial/config/defaults.toml`
5. Update `Config` parsing/serialization for the new mode

**What a mode may override:**
- Food spawning (call or skip `_spawn_food()`)
- Energy model (regen, costs, thresholds)
- Movement behaviour (may call `wander()`, `steer_toward()`, or custom helpers)
- Death conditions (energy ≤ 0, age ≥ max_lifespan, or age-only for drift)
- Position update (may use `update_position()` or custom `_drift_update_position()`)

**What a mode must preserve:**
- Shared infrastructure: spatial bucket, zone manager, cosmic rays, aging
- Event queues: `death_events`, `birth_events`, `active_attacks`, `cosmic_ray_events`
- Creature fields: all modes use same Creature/Genome dataclasses
- Toroidal world wrapping

## Visual Theme Contract

A new theme must:

1. Inherit from `Theme` ABC
2. Implement all abstract methods including `render_creature(surface, creature, time, scale=1.0)`
3. Register in `get_theme()`
4. Add to `Settings.VALID_VISUAL_THEMES`

## Known Stubs

**Visual themes (not implemented):**
- `petri`, `geometric`, `chaotic`

All four simulation modes (`energy`, `predator_prey`, `boids`, `drift`) are now fully implemented.

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

## Config file and settings overlay

- Canonical user-meaningful defaults live in committed `primordial/config/defaults.toml`.
- `Config` loads/saves the platform user `config.toml` under the user profile path:
  - Windows: `~/AppData/Roaming/Primordial/config.toml`
  - macOS: `~/Library/Application Support/Primordial/config.toml`
  - Linux: `~/.config/primordial/config.toml`
- Load order is canonical defaults first, then the user `config.toml` as overrides.
- On first run, a user `config.toml` populated from canonical defaults is written automatically.
- If parse fails, config is backed up to `config.toml.bak` and defaults are restored.
- Unknown config keys are ignored with warning logs (not fatal).
- Type mismatches are coerced safely; invalid values fall back to defaults and are clamped on save.
- In normal mode, `S` opens an in-app renderer-owned settings overlay.
- Overlay behavior: Arrow keys navigate/adjust, Enter applies+saves, Esc/S discards, R twice resets defaults. Mouse support is renderer-owned: click categories, rows, value controls, and footer/action buttons; wheel scrolls the active category list.
- The settings Guide action opens a renderer-owned in-app help browser above settings. Help content is loaded from `docs/predator_prey_system_guide.md` through `primordial/help/document_model.py`; help rendering/layout/navigation/mouse logic lives in `primordial/rendering/help_overlay.py`, `help_layout.py`, `help_navigation.py`, and `help_mouse.py`.
- The tutorial is a peer renderer-owned overlay, not part of settings/help internals. Tutorial content/state/persistence live in `primordial/tutorial/steps.py`, `state.py`, and `persistence.py`; tutorial rendering/layout/mouse hit regions live in `primordial/rendering/tutorial_overlay.py`, `tutorial_layout.py`, and `tutorial_mouse.py`. First-launch completion is stored in `tutorial_state.json` next to `config.toml`; it is not a snapshot or adaptive tuning file.
- The runtime mouse-activated bottom action bar lives in `primordial/rendering/action_bar.py`. Keep its displayed shortcut metadata aligned with the real handlers in `primordial/input/keyboard.py` and the small `K_p` hold path in `primordial/main.py`.
- Settings overlay geometry lives in `primordial/rendering/settings_layout.py`; keep future modal/sidebar/list/details/footer sizing there instead of adding one-off rectangle math in the renderer.
- Runtime cursor behavior lives in `primordial/display/cursor.py`: normal simulation playback hides the OS cursor, interactive UI states such as tutorial/settings/help/inspect show it, and clean shutdown restores it.
- Settings that require reset are marked in the overlay; simulation reset is only triggered by explicit `R`.

When adding a new setting, update all of:
1. Canonical defaults file (`primordial/config/defaults.toml`)
2. Config parsing/validation/serialization (`primordial/config/config.py`)
3. Settings overlay metadata (`primordial/rendering/settings_metadata.py`)
4. AGENTS.md (this file) — settings reference notes
5. README.md when user-facing config behavior or locations change

Rule: any newly introduced user-meaningful config or tuning value must be added
to `primordial/config/defaults.toml` in the same change. Do not hide new
user-facing defaults as unexplained Python literals.

Predator/prey reproduction thresholds are mode-scoped config authority:
`[modes.predator_prey].prey_energy_to_reproduce` and
`[modes.predator_prey].predator_energy_to_reproduce` override reproduction
thresholds by species only in `predator_prey`; if absent, resolution falls back
to the shared `energy_to_reproduce`.
When predators exceed 60% of the live population, predator reproduction becomes
harder by increasing the resolved predator threshold by 20%.
Predator/prey extinction is no longer rescued in normal operation: either
species hitting zero triggers a frozen red `GAME OVER` state, then an automatic
restart after 10 seconds with a new seed. Pressing `Space` during that screen
skips the hold and restarts immediately.
That `GAME OVER` overlay also shows the run's dial values, highlights the dial
changed for that run with its signed delta, and marks the highest survival tick
record when the just-ended run sets a new best.
The settings overlay exposes a predator-prey-only reset action that restores
adaptive dials to their baseline values, clears the max survival tick record,
and starts a fresh predator_prey run.
Adaptive predator_prey dials are intentionally small and ecological only:
`predator_contact_kill_distance_scale`, `predator_kill_energy_gain_cap`,
`predator_hunt_sense_multiplier`, `prey_flee_sense_multiplier`,
`predator_prey_scarcity_penalty_multiplier`, and `food_cycle_amplitude`.
Snapshots must round-trip the adaptive tuning state, current seed, `sim_ticks`,
and `survival_ticks`.
The adaptive predator_prey tuning state is also persisted on app exit and
reloaded on the next launch without requiring a world snapshot.
These live in TOML mode params today. The in-app overlay edits only fields
declared explicitly in `primordial/rendering/settings_metadata.py`; other
mode-param tuning remains TOML-only unless overlay metadata is added.
