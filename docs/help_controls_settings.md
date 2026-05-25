# Controls and Settings

## Runtime Controls

Move the mouse during normal playback to reveal a temporary bottom action bar with the current runtime shortcuts. It stays fully visible for 5 seconds after movement stops, then fades out over 10 seconds.

| Key | Action |
| --- | --- |
| `Esc` / `Q` | Quit |
| `H` | Open in-app Help |
| `U` | Toggle HUD |
| `S` | Open or close Settings |
| `Space` | Pause/unpause, or skip predator-prey game-over countdown |
| `F` | Toggle fullscreen/windowed |
| `R` | Reset the current simulation run |
| `I` | Toggle Inspect Mode (see body plan, key effect, and effective phenotype) |
| `M` | In Inspect Mode, switch between pause and slow motion |
| `N` | In Inspect Mode, switch to normal-speed follow |
| `D` | In Inspect Mode, toggle compact/detailed card (detail shows effective phenotype modifiers) |
| mouse click | In Inspect Mode, select a creature |
| hold `P` | Highlight predators |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

## Settings Guide

Press `S` in normal mode to open the settings overlay. The simulation pauses and the mouse cursor appears while settings are open.

Settings are grouped into categories:

- **Simulation**: mode, population, food spawn, global speed.
- **Display**: backend, fullscreen, target FPS, HUD.
- **Evolution**: mutation, cosmic rays, epistasis, food cycle, zones.
- **Ecology / Predator-Prey**: predator-prey-specific starting mix and dials.
- **Rendering**: kin-line visuals and related rendering options.
- **Actions**: snapshots, help, reset actions.

The selected setting has a description panel explaining what it does, its range or choices, and whether it applies on save or requires a reset.

Settings overlay controls:

| Control | Action |
| --- | --- |
| `Up` / `Down` | Move selection |
| `Left` / `Right` | Change selected value |
| `Tab` / `Shift+Tab` | Change category |
| `Enter` | Apply and save settings |
| `Esc` / `S` | Discard pending changes and close |
| `Space` | Run selected action in the Actions category |
| `V` | Save snapshot |
| `L` | Load snapshot |
| `H` | Open the in-app help browser |
| `T` | Start the onboarding tutorial from the Actions category |
| `R R` | Confirm reset settings defaults |
| `D D` | Confirm predator-prey dial reset, when available |

## Tutorial

Primordial includes a guided onboarding tutorial for new users. It runs on a fresh normal-mode launch, can be replayed with `python main.py --tutorial`, and can be started from the settings Actions category. The tutorial explains app controls first, then walks through creatures, food, predators and prey, births and deaths, lineages, zones, depth bands, collapse, and evolution.

## Save and Load

The settings overlay can save and load a world snapshot. A snapshot stores the world dimensions, simulation settings, creatures, food, zones, RNG state, and predator-prey runtime state when applicable.

Predator-prey adaptive tuning state is also persisted separately on app exit, next to the user config.

## Other Modes

Primordial also includes:

- **Energy**: the default mode. Creatures forage for food and aggression creates hunter/grazer/opportunist behavior.
- **Boids**: flocking behavior. Creatures gain energy from being in useful flock sizes instead of eating food.
- **Drift**: a calmer neutral-drift mode with passive energy regeneration and old-age deaths.

Many visual systems, such as glyphs, trails, zones, aging, cosmic rays, and the HUD, are shared across all modes.

## Glossary

**Adaptive tuning**: Optional predator-prey system that tests bounded ecological dial changes across runs. Implemented, but disabled by default.

**Arms race**: Coevolution where predators and prey each evolve traits that counter the other's advantage.

**Body plan**: A strategy bucket classifying a creature's eco-morphological role: swift-small, heavy-hunter, sensory-specialist, efficient-glider, evasive-darter, depth-specialist, or generalist. Shown in Inspect Mode.

**Cosmic ray**: Rare spontaneous mutation to one trait on a living creature.

**Cross-band miss**: A predator reaches prey in 2D space but cannot kill because they are in different depth bands.

**Depth band**: Abstract predator-prey layer: surface, mid, or deep.

**Effective phenotype**: The ecological modifiers derived from interacting genome traits through epistasis. Includes speed, movement cost, metabolic cost, sensing, food efficiency, reproduction threshold, predation contact, flee agility, depth transition, and depth sensing. When epistasis is disabled, all modifiers are ×1.00. Shown in Inspect Mode detail view.

**Food cycle**: Repeating resource wave between famine and feast.

**Frequency-dependent selection**: Selection where the fitness of a strategy depends on how common it is.

**Game over**: Predator-prey collapse state after a role remains at zero for the full extinction grace window. Temporary zero-count extinction can recover through mutation-driven species switching during the grace window.

**Gene flow**: Exchange of genetic material between populations. In predator_prey mode, mutations that shift aggression across the hysteresis thresholds (prey → predator at 0.30, predator → prey at 0.20) transfer a creature between species.

**Genome**: The inherited trait set that determines creature behavior and appearance. A frozen dataclass with 16 float traits.

**Glyph**: The procedural glowing symbol used as a creature body. Generated deterministically from the genome.

**Kin line**: A visual connection between nearby creatures with the same lineage.

**Lineage**: An ancestry identifier used for visual family structure. Branches when a hue mutation exceeds 0.15.

**Lineage branch**: A speciation event where an offspring gets a new lineage ID because its hue mutation was large enough to trigger a branch.

**Inspect graphs**: The translucent graph strip shown in Inspect Mode. It keeps the selected organism's moment-to-moment state separate from lineage population and lineage trait drift so the UI does not imply that a single organism evolves over time.

**Longevity-fecundity tradeoff**: The evolutionary tension between living a long time and reproducing quickly.

**Neutral drift**: Change in trait values caused by random mutations that do not affect survival.

**Predator-prey dials**: Configured ecological parameters that affect hunting, fleeing, scarcity pressure, kill distance, kill energy, and food-cycle amplitude.

**Zone**: Soft environmental region that changes energy and sensing pressure. With the HUD visible, environmental zones are also labeled on screen.
