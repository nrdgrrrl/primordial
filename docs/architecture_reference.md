# Primordial Architecture Reference

This document describes the current codebase for future maintainers and coding
agents. Treat the code as the source of truth; this file is a map of ownership,
boundaries, and invariants that should make changes safer.

For agent-specific rules, see `AGENTS.md`. For packaging and screensaver
details, see `docs/build_and_integration.md`.

## Project Shape

Top-level entry points:

- `main.py` parses screensaver/runtime arguments and delegates to
  `primordial.main.main`.
- `build.py`, `primordial.spec`, and `Makefile` support packaging and common
  development commands.

Runtime package:

- `primordial/main.py` owns pygame initialization, display mode selection,
  top-level event routing, fixed-step simulation advancement, renderer calls,
  and clean shutdown.
- `primordial/config/config.py` owns TOML load/save, canonical defaults,
  validation, coercion, clamping, and mode-parameter merging.
- `primordial/config/defaults.toml` is the committed source of user-meaningful
  default values.
- `primordial/runtime/` contains fixed-step timing, profiling, session helpers,
  and settings overlay action handling.
- `primordial/input/keyboard.py` handles normal runtime key bindings.
- `primordial/display/` contains display-mode, coordinate, and cursor helpers.
- `primordial/help/` contains the Markdown-backed help document model, parser,
  bundled guide path resolution, and simple section search.
- `primordial/tutorial/` contains declarative onboarding steps, tutorial
  runtime state, and first-launch tutorial user-state persistence.
- `primordial/simulation/` owns all simulation state and rules.
- `primordial/rendering/` owns pygame/GPU drawing, HUDs, inspect mode, glyphs,
  settings/help/tutorial UI rendering, transient action-bar UI, and renderer-side
  visual state.
- `primordial/persistence/` contains runtime sidecar paths, snapshot defaults,
  external help fallback integration, and predator-prey tuning-state
  persistence.

## Main Loop

`primordial/main.py` is intentionally mostly orchestration:

1. Parse screensaver mode and runtime flags.
2. Initialize pygame and load `Settings`.
3. Create the display, simulation, renderer, fixed-step state, and optional run
   loggers.
4. Route events:
   - screensaver mode quits on real user input after a short grace period;
   - preview mode ignores input except quit;
   - tutorial events are handled before help, settings, inspect, and normal
     simulation controls;
   - help browser events are handled before settings events;
   - settings overlay events are passed to
     `runtime/settings_actions.py`;
   - normal-mode mouse motion refreshes the transient bottom action bar;
   - inspect clicks use display window-to-world conversion;
   - normal keyboard input goes through `input/keyboard.py`.
5. Advance the simulation through `runtime/fixed_step.py` unless paused,
   in a transition, in game-over hold, or suppressed by inspect mode.
6. Ask the renderer to draw.
7. Persist predator-prey adaptive tuning state on shutdown and restore the OS
   cursor before leaving pygame.

Keep `main.py` thin. New runtime behavior usually belongs in an existing helper
module rather than in the loop body.

## Simulation Boundary

`primordial/simulation/simulation.py` owns the mutable world:

- creatures, food manager, zone manager, counters, mode-specific runtime state;
- event queues: `death_events`, `birth_events`, `cosmic_ray_events`,
  `active_attacks`;
- mode dispatch through `Simulation.step()`;
- reset, resize, snapshot rebuild, and observability snapshot helpers.

Important boundary: simulation code must not call pygame or mutate renderer
state. It may emit renderable event data, and the renderer may consume and clear
those event queues according to the existing contract.

Implemented modes:

- `energy`: food-seeking creatures with aggression tiers.
- `predator_prey`: explicit predator/prey roles, depth bands, collapse/game-over
  scoring, and optional adaptive ecological tuning.
- `boids`: flocking mode using neighbor caches and flock connected components.
- `drift`: low-pressure neutral drift mode.

Known visual stubs: `petri`, `geometric`, and `chaotic` themes are valid config
values but use `StubTheme` placeholder rendering and a "coming soon" renderer
overlay. The `ocean` theme is the implemented production theme.

## Core Simulation Objects

`simulation/genome.py` defines immutable `Genome` values with 16 traits:

- ecological/motion traits: `speed`, `size`, `sense_radius`, `aggression`,
  `efficiency`, `motion_style`, `longevity`, `conformity`,
  `depth_preference`;
- visual traits: `hue`, `saturation`, `complexity`, `symmetry`,
  `stroke_scale`, `appendages`, `rotation_speed`.

`Genome.mutate()` returns a new genome with per-trait Gaussian mutation.
`Genome.mutate_one()` is used by cosmic rays.

`simulation/creature.py` defines mutable creatures: position, velocity, energy,
age, lineage, species, depth band, flock id, trails, motion-state fields, and
renderer-owned glyph cache fields. Creatures wrap in a toroidal world, keep
energy within bounds through simulation logic, and cap trail length through
`Creature.get_trail_length()`.

`simulation/food.py` provides food particles and a spatially bucketed
`FoodManager`. `simulation/zones.py` provides soft environmental zones.
`simulation/depth.py` defines the bounded predator-prey depth-band helpers.

## Rendering

`rendering/renderer.py` is the pygame renderer. `rendering/gpu_renderer.py` is
the GPU-backed renderer used when available and requested. `rendering/backend.py`
selects backend behavior.

Renderer responsibilities include:

- drawing background, food, zones, creatures, trails, kin lines, territory
  shimmer, attack lines, HUD, game-over overlay, inspect UI, and settings UI;
- consuming simulation render events through `AnimationManager`;
- maintaining renderer-side caches and visual-only state;
- resizing surfaces and renderer dimensions after display changes.

`rendering/themes.py` owns theme color/rendering behavior. `OceanTheme` is the
implemented visual theme. `rendering/glyphs.py` builds deterministic creature
glyphs from genomes. `rendering/animations.py` owns birth, death, and cosmic-ray
visual animations.

Renderer code may read simulation state but should not change simulation rules.
The permitted exception is consuming and clearing render event queues after they
have been turned into animations.

## HUD, Inspect Mode, and Help

`rendering/hud.py` builds mode-specific text panels. Predator-prey HUD lines
currently include predator/prey counts, actual speeds, recent kills,
cross-band misses, ticks/seed, survival statistics, danger/grace status, trial
status, dominant zone, mode, theme, FPS, and a food-cycle bar.

`rendering/inspect_mode.py` owns inspect-mode selection and card state. Normal
runtime mouse clicks are transformed to world coordinates only for inspect mode.
Settings overlay hit testing uses raw pygame UI coordinates and must not reuse
world-coordinate transforms.

The settings overlay action labeled `Guide` now opens an in-app documentation
browser above the settings overlay. Help events are routed before settings
events in `primordial/main.py`, so normal simulation controls do not fire while
the browser is open. Closing help returns to the settings overlay if it is still
open; otherwise it returns to normal playback.

Help content is loaded from `docs/predator_prey_system_guide.md` through
`primordial/help/document_model.py`. That module resolves the bundled path with
`get_base_path()`, parses Markdown headings into flat sections, simplifies body
Markdown into readable text, and performs simple case-insensitive title/body
search. It does not implement a full Markdown renderer.

Help UI ownership mirrors the settings split without sharing internals:

- `rendering/help_overlay.py`: drawing, keyboard/mouse event interpretation,
  search box editing, content wrapping, and hit-region registration.
- `rendering/help_layout.py`: modal, search, nav, content, footer, and close
  button rectangles.
- `rendering/help_navigation.py`: selected section, search query/results, and
  nav/content scroll state.
- `rendering/help_mouse.py`: hit-region dataclass.

The old external browser helper
`persistence/runtime_state.py::_open_predator_prey_help` still exists as tested
fallback infrastructure, but it is no longer the primary Guide action path.

## Action Bar

`rendering/action_bar.py` owns the mouse-activated bottom action bar shown
during normal playback. It contains:

- declarative shortcut display metadata;
- monotonic-timer visibility and fade state;
- context filtering for normal, inspect, predator-prey, and game-over states;
- bottom-bar layout and drawing.

The action bar is informational only. Actual keyboard behavior still lives in
`input/keyboard.py` plus the small `K_p` hold path in `primordial/main.py`.
Keep those handlers and the displayed metadata aligned instead of scattering
shortcut labels through renderer code or docs.

## Tutorial Overlay

The tutorial is a renderer-owned peer to settings and help, not part of either
overlay:

- `tutorial/steps.py`: declarative linear content with phase, title, body,
  highlight target, and per-step pause preference.
- `tutorial/state.py`: current step, active/completed/skipped state, hover
  action, text scroll bounds, and previous pause state.
- `tutorial/persistence.py`: `tutorial_state.json` sidecar next to
  `config.toml`; stores versioned seen/skipped state and is not part of
  snapshots or predator-prey adaptive tuning.
- `rendering/tutorial_layout.py`: modal, button, and highlight rectangles.
- `rendering/tutorial_mouse.py`: hit-region dataclass.
- `rendering/tutorial_overlay.py`: drawing, keyboard/mouse event handling, text
  wrapping, and button registration.

Fresh normal-mode launches auto-start the tutorial only when `config.toml` did
not exist before startup and the tutorial sidecar has not marked the current
version seen/skipped. `--tutorial` and `--show-tutorial` force it for the current
run. Finish and Skip/Escape both mark the current tutorial version handled.

The tutorial keeps the simulation paused for the full onboarding flow. The main
loop resumes normal playback on Finish, Skip, or Escape instead of restoring a
saved paused state. Conceptual steps should not manufacture fake highlight
rectangles; highlight boxes are only appropriate for stable, actually visible
targets.

## Configuration

`Config` is exposed as `Settings` through `primordial/settings.py` for backward
compatibility.

Load order:

1. committed canonical defaults from `primordial/config/defaults.toml`;
2. platform user `config.toml` overrides.

User config path:

- Windows: `~/AppData/Roaming/Primordial/config.toml`
- macOS: `~/Library/Application Support/Primordial/config.toml`
- Linux: `~/.config/primordial/config.toml`

If the user config is missing, it is created from canonical defaults. If parsing
fails, the invalid file is backed up to `config.toml.bak` and defaults are
restored. Unknown keys are ignored with warnings. Invalid values are coerced or
clamped by config-layer rules and written back in normalized form.

Mode parameters live under `[modes.<mode>]` and are merged into
`settings.mode_params`. Simulation code reads them through `_get_mode_param`.
Do not duplicate validation or defaulting rules in rendering code.

## Settings Overlay Architecture

The in-app settings overlay is renderer-owned but split across focused modules:

- `rendering/settings_metadata.py`: categories, labels, descriptions, ranges,
  options, reset-required flags, mode-specific visibility, and action metadata.
- `rendering/settings_navigation.py`: active category and selected row state.
- `rendering/settings_layout.py`: modal/sidebar/list/details/footer rectangle
  calculation and long-label layout sizing.
- `rendering/settings_mouse.py`: hit-region dataclass.
- `rendering/settings_overlay.py`: drawing, local pending values, keyboard and
  mouse event interpretation, value formatting, hover state, and hit-region
  registration from the same rectangles that are drawn.
- `rendering/action_bar.py`: runtime shortcut metadata, transient visibility
  timing, context filtering, and bottom-bar drawing.
- `runtime/settings_actions.py`: applies overlay actions to the live runtime:
  apply/save, discard, reset defaults, save/load snapshot, in-app guide launch,
  display and backend changes, and predator-prey dial reset.

The overlay supports keyboard and mouse:

- `S` opens/closes settings in normal mode.
- `Enter` applies and saves.
- `Esc` or `S` discards and closes.
- arrows change selection and values.
- `Tab` / `Shift+Tab` change categories.
- double `R` confirms settings reset.
- action shortcuts include `V` save snapshot, `L` load snapshot, `H` in-app
  guide, `T` tutorial, and double `D` reset predator-prey dials when available.
- mouse clicks switch categories, select rows, use value steppers, press footer
  buttons, and run action buttons; mouse wheel scrolls the active list.

The overlay should remain a practical pygame UI, not a general UI framework.
Keep metadata, layout, navigation, hit testing, runtime actions, and config
validation separated.

## Cursor Visibility

Runtime cursor behavior lives in `primordial/display/cursor.py`:

- `hide_runtime_cursor()` hides the OS cursor during normal simulation playback,
  screensaver mode, preview mode, display recreates, and app startup.
- `show_interactive_cursor()` shows it while interactive UI is open, including
  tutorial, settings, the help browser, and inspect mode.
- `restore_system_cursor()` restores visibility on clean shutdown.

Main-loop and input helpers coordinate these calls. Do not scatter raw
`pygame.mouse.set_visible(...)` calls through unrelated modules.

## Persistence and Snapshots

World snapshots are JSON files handled by `simulation/persistence.py`.
`SAVE_FORMAT_VERSION` is currently `2`; version `1` is still accepted. Snapshots
store:

- world dimensions;
- simulation settings fields and mode params;
- counters and RNG state;
- creatures, food, zones, and motion/depth/species runtime fields;
- predator-prey runtime state when applicable.

The default in-app snapshot path is next to the user config as
`world_snapshot.json`. Load rejects invalid kind/version or incompatible shapes
with `SnapshotError`.

Predator-prey adaptive tuning state is also persisted separately on app exit in
`predator_prey_tuning_state.json` next to the user config. This is not a world
snapshot; it carries cross-run tuning state so a later session can resume dial
history.

## Predator-Prey State

Predator-prey mode adds:

- predator/prey species roles;
- three abstract depth bands (`surface`, `mid`, `deep`);
- depth-aware food access and sensing;
- contact kills only when predator and prey are in the same depth band;
- recent kill and cross-band miss counters;
- near-extinction and zero-count tracking;
- a game-over hold and automatic restart after sustained collapse;
- run history, highest survival ticks, and optional adaptive tuning trials.

The committed default has `adaptive_tuning_enabled = false`. The adaptive
tuning machinery is implemented and can be enabled through config, but normal
default runs do not automatically change dials. The settings overlay still
exposes a predator-prey dial reset action; it restores baseline dial values,
clears survival history/max ticks, persists the reset sidecar state, and starts
a fresh predator-prey run.

## Tests and Smoke Checks

Useful commands:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_help_browser.py -q
.venv/bin/python -m pytest tests/test_tutorial.py -q
.venv/bin/python -m pytest tests/test_settings_overlay.py -q
.venv/bin/python -m pytest tests/test_settings_actions.py tests/test_fixed_step_loop.py -q
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy timeout 5 .venv/bin/python main.py --mode energy
```

Run targeted tests for the area being changed, then the full suite when
practical. UI/layout changes should also get a headless draw or graphical probe
when possible so hit rectangles, footer layout, and cursor behavior are checked.

## Agent Safety Notes

- Keep simulation and rendering decoupled; never import pygame into simulation
  rules.
- Keep config parsing, defaults, validation, and clamping inside
  `config/config.py` plus `defaults.toml`.
- Do not duplicate config rules in renderer or settings UI code.
- Use `settings_metadata.py` for user-facing settings labels/descriptions and
  `settings_layout.py` for overlay geometry.
- Do not bypass `settings_navigation.py` when changing category/row behavior.
- Keep tutorial content/state/persistence in `primordial/tutorial/`; do not
  fold it into settings/help overlays or simulation state.
- Keep `runtime/settings_actions.py` as the home for applying overlay actions to
  live simulation/display/runtime objects.
- Preserve keyboard support when adding mouse features.
- Keep action-bar shortcut labels in sync with the real handlers in
  `input/keyboard.py` and `main.py`; do not invent docs-only or UI-only keys.
- UI hit testing must use pygame event screen/window coordinates and the same
  rectangles used for drawing; do not apply world-coordinate transforms to UI
  clicks.
- Display/backend changes must resize both simulation and renderer and reset
  fixed-step timing debt.
- Do not regress screensaver mode: cursor hidden, preview behavior preserved,
  and user input exits only after the startup grace period.
- Snapshot changes must remain versioned and reject invalid payloads safely.
- When changing predator-prey collapse, tuning, or snapshots, update persistence
  tests and sidecar-state expectations.
