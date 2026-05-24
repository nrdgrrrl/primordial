# AGENTS.md — Primordial Codebase Context

This document is for AI coding agents tasked with extending or modifying the Primordial codebase.

Detailed design/system reference: `docs/architecture_reference.md`
Build/integration details: `docs/build_and_integration.md`
In-app help documents: `docs/help_*.md` (quick_start, organisms, reading_creatures, predator_prey, controls_settings)
Standalone biology reference: `docs/organism_biology.md`

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
- Glyph morphology is the organism's phenotype — visual traits are heritable and meaningful, not decorative

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
    │   ├── genome.py        # Genome dataclass — 16 heritable traits
    │   ├── creature.py      # Creature — position, velocity, energy, behavior, motion style
    │   ├── food.py          # Food particle and FoodManager with spatial bucketing
    │   ├── phenotype.py     # EffectivePhenotype, strategy buckets, epistasis, describe/format helpers
    │   ├── simulation.py    # Simulation — orchestrates creatures, food, evolution, events
    ├── help/
    │   └── document_model.py # HelpDocEntry registry, document loading, markdown parsing
    └── rendering/
        ├── glyphs.py        # Glyph rendering system — stroke vocabulary, deterministic assembly
        ├── animations.py    # AnimationManager — death/birth animations, decoupled from sim
        ├── themes.py        # Theme ABC and implementations (OceanTheme, StubTheme)
        ├── hud.py           # HUD overlay for simulation stats
        ├── inspect_mode.py  # Inspect Mode — creature card with phenotype observability
        ├── help_overlay.py  # In-app help browser with section nav, search
        ├── help_layout.py   # Layout geometry for help overlay
        ├── help_navigation.py # Section selection, search, scroll state
        ├── help_mouse.py    # Mouse hit regions for help overlay
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
11. **Glyph morphology is semantically meaningful** — creature visual traits (complexity, symmetry, stroke_scale, appendages, rotation_speed) are heritable genome traits that mutate, drift, and mark ancestry. Glyph appearance is the organism's phenotype. Do not treat glyph rendering as purely decorative or decoupled from simulation meaning. Changes to glyph generation must preserve determinism and recognizability of lineage resemblance. Visual changes that would make related organisms look unrelated, or that would add cosmetic effects not traceable to genome traits, break the visual-evolution contract.
12. **Raw genome vs effective phenotype stays separate** — inherited values remain the authoritative genome. Ecological consequences from trait interactions must flow through the phenotype translation layer (`primordial/simulation/phenotype.py`), not by mutating genome values or smearing ad hoc epistasis math across the simulation loop. Inspect Mode must show both raw genome and effective phenotype; the `describe_phenotype_effect()` and `format_phenotype_modifiers()` helpers in `phenotype.py` are the canonical observability surface for UI code.

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
- The settings Help action opens a renderer-owned in-app help browser above settings. The help browser shows registered help documents (`HELP_DOCUMENTS` in `primordial/help/document_model.py`) with tab switching (Tab/Shift+Tab), section navigation, search, and keyboard navigation (Up/Down, PageUp/PageDown, / search, Esc close). Pressing `H` from normal playback opens the help browser directly. Help rendering/layout/navigation/mouse logic lives in `primordial/rendering/help_overlay.py`, `help_layout.py`, `help_navigation.py`, and `help_mouse.py`.
- When adding a new help document, update all of: `HELP_DOCUMENTS` in `primordial/help/document_model.py`, the `__init__.py` exports, `build.py` (PyInstaller `--add-data`), and `primordial.spec` (datas list). Add a test guard that the new document loads and has sections.
- The tutorial is a peer renderer-owned overlay, not part of settings/help internals. Tutorial content/state/persistence live in `primordial/tutorial/steps.py`, `state.py`, and `persistence.py`; tutorial rendering/layout/mouse hit regions live in `primordial/rendering/tutorial_overlay.py`, `tutorial_layout.py`, and `tutorial_mouse.py`. First-launch completion is stored in `tutorial_state.json` next to `config.toml`; it is not a snapshot or adaptive tuning file.
- The runtime mouse-activated bottom action bar lives in `primordial/rendering/action_bar.py`. Keep its displayed shortcut metadata aligned with the real handlers in `primordial/input/keyboard.py` and the small `K_p` hold path in `primordial/main.py`.
- Settings overlay geometry lives in `primordial/rendering/settings_layout.py`; keep future modal/sidebar/list/details/footer sizing there instead of adding one-off rectangle math in the renderer.
- Runtime cursor behavior lives in `primordial/display/cursor.py`: normal simulation playback hides the OS cursor, interactive UI states such as tutorial/settings/help/inspect show it, and clean shutdown restores it.
- Predator kill visibility is renderer-owned. Simulation may attach render-only predation metadata (for example predator position/color on a `death_event`) so the renderer can build bounded kill effects, but simulation must not own visual timers, surfaces, or pygame state. Current rendering keys are `predation_kill_effects_enabled`, `predation_kill_effect_intensity`, and `predation_kill_effect_max_active`.
- Settings that require reset are marked in the overlay; simulation reset is only triggered by explicit `R`.
- Eco-morphological epistasis is controlled by `simulation.epistasis_enabled` and `simulation.epistasis_strength`. Keep the raw genome separate from effective phenotype values so future mate choice, recombination, and reproductive compatibility work can reuse the same translation layer.

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
Predator/prey extinction uses a grace window: when a species hits zero,
`predator_zero_ticks` or `prey_zero_ticks` starts counting. The simulation
continues during the grace window. If the zero-count species recovers through
mutation-driven species switching before `extinction_grace_ticks` (default 7200)
expires, the run continues. If the zero state persists for the full grace window,
the run enters a frozen red `GAME OVER` state, then an automatic restart after
10 seconds. Pressing `Space` during that screen skips the hold and restarts
immediately.
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
Predator ambush-habitat tuning is separate from those adaptive dials. The first
pass is hardcoded to `hunting_ground` and only applies modest predator-only
bonuses when predators are already inside that zone. It must remain
density-damped and must not attract predators, spawn predators, preserve
collapsed predator traits, or act as a predator-respawn system. Current
mode-scoped keys are `predator_refuge_enabled`,
`predator_refuge_hunt_sense_bonus`, `predator_refuge_contact_bonus`,
`predator_refuge_depth_transition_bonus`,
`predator_refuge_movement_cost_reduction`,
`predator_refuge_density_radius`, `predator_refuge_density_soft_cap`, and
`predator_refuge_density_hard_cap`.
Prey flee base chase speed in predator_prey is mode-scoped via `prey_flee_speed_multiplier` (default 1.30), replacing the previous hardcoded `1.5` flee factor.
Prey flee frailty is a prey-only movement condition layer in `_prey_flee()`.
`prey_flee_age_slowdown_enabled` applies `Creature.get_age_speed_mult()`
directly to flee max speed, and the optional low-energy taper uses
`prey_flee_low_energy_slowdown_enabled`,
`prey_flee_low_energy_threshold`, and `prey_flee_low_energy_min_mult`. This is
not predator spawning, not predator rescue, not extinct-trait preservation,
and not a direct reproduction-threshold change.
Predator near-contact diagnostics are observational only. The current config
keys are `predator_near_contact_diagnostic_scale` and
`predator_sustained_chase_min_frames`. They exist to measure same-depth
contact/flee oscillation, cross-depth near misses, sustained chase without
kill, and whether kills are skewing toward old or low-energy prey.
Snapshots must round-trip the adaptive tuning state, current seed, `sim_ticks`,
and `survival_ticks`.
The adaptive predator_prey tuning state is also persisted on app exit and
reloaded on the next launch without requiring a world snapshot.
These live in TOML mode params today. The in-app overlay edits only fields
declared explicitly in `primordial/rendering/settings_metadata.py`; other
mode-param tuning remains TOML-only unless overlay metadata is added.

Predator rarity advantage is predator-only, living-population-only tuning gated by low predator count plus healthy prey count. It does not create predators, preserve extinct predator traits, alter prey behaviour, or directly lower predator reproduction thresholds.

Predator quarry memory is a short attention/last-known-position aid only: it never grants magical sensing or memory-only kills, and all kills still require normal same-depth contact rules.

Predator target switching diagnostics are strict: first acquisition and same-target reacquisition do not count as switches.
