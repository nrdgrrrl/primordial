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

# Replay the in-game onboarding tutorial
python main.py --tutorial

# Run a 60-second cProfile capture and exit
python main.py --profile

# Append predator_prey run telemetry rows to run_logs/predator_prey_runs.csv
python main.py --log=csv

# Resume a saved world, then save the updated snapshot on exit
python main.py --load build/world.json --save build/world.json
```

Predator-prey snapshots also persist the current seed, `sim_ticks`,
`survival_ticks`, rolling survival history, and adaptive dial trial state.
Separately, the adaptive predator-prey tuning state is saved on app exit and
reloaded on the next launch, so dial progress survives without a world
snapshot.

The screensaver will launch in fullscreen mode by default.

### Runtime CLI Flags

| Flag | Effect |
|---|---|
| `-h`, `--help` | Print command-line help and exit before pygame startup |
| `--debug` | Enables debug HUD timing lines, FPS/population graph overlay, and verbose console logging |
| `--profile` | Runs for 60 seconds, writes `.pstats` + text profile report to config directory, then exits |
| `--mode <name>` | Launch override: `energy`, `predator_prey`, `boids`, `drift` |
| `--theme <name>` | Launch override: `ocean`, `petri`, `geometric`, `chaotic` |
| `--load <path>` | Load a saved simulation world snapshot instead of creating a new world |
| `--save <path>` | Save the current world snapshot to the given path on exit |
| `--log=csv` | Append predator-prey run and dial-reset telemetry rows to `run_logs/predator_prey_runs.csv` |
| `--tutorial`, `--show-tutorial` | Open the in-game onboarding tutorial for this run without changing seen state |

Windows screensaver hosting still uses separate startup arguments: `/s` for
fullscreen screensaver mode, `/p <HWND>` for preview embedding, and `/c` for
config mode.

### Make Targets

```bash
make run       # python main.py
make debug     # python main.py --debug
make profile   # python main.py --profile
make build     # python build.py
make clean     # remove build/dist and __pycache__ dirs
```

## Keyboard Controls

Move the mouse during normal playback to reveal a transient bottom action bar
with the current runtime commands. It stays fully visible for 5 seconds after
the last meaningful movement, then fades out over 10 seconds. The cursor still
remains hidden during normal simulation playback.

| Key | Action |
|-----|--------|
| `ESC` or `Q` | Quit the screensaver |
| `H` | Open in-app Help browser |
| `U` | Toggle HUD (heads-up display) |
| `Space` | Pause/unpause simulation, or skip the predator_prey `GAME OVER` wait and restart immediately |
| `F` | Toggle fullscreen/windowed mode |
| `R` | Reset simulation (new population) |
| `S` | Open in-app settings overlay (disabled in /s screensaver mode) |
| `T` | In the settings overlay Actions category, start the tutorial |
| `D` | While in Inspect Mode, toggle the creature card between compact/detail; in the settings overlay, reset predator-prey adaptive dials to baseline and clear the max tick record |
| Hold `P` | Add a stronger locator highlight to predators while held in `predator_prey` mode |
| `I` | Toggle Inspect Mode (read-only creature observability; see below) |
| `M` | While in Inspect Mode, toggle between pause and slow-motion (2 Hz) sub-modes |
| Mouse click | While in Inspect Mode, select a creature; while settings are open, click categories, rows, value controls, and action buttons |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

### Inspect Mode

Press **I** to toggle Inspect Mode, a read-only observability overlay that does not alter simulation determinism. While active:

- **Pause sub-mode** (default): simulation is frozen; you can click creatures at leisure.
- **Slow sub-mode** (press **M** to switch): simulation advances at 2 ticks/second so you can watch behaviour unfold slowly.
- **Mouse click**: selects the nearest creature and displays a polished top-right microscope card with the creature title, a short behavior summary, state, focus, and temperament.
- **Detail toggle** (press **D**): switches the inspect card between compact and detailed layouts. Detail mode adds raw genome values, exact age, position, and predator-only satiety / recent prey energy.
- Exiting Inspect Mode (press **I** again) restores the prior paused/running state.

### Tutorial

On a fresh normal-mode launch, Primordial opens a short in-game tutorial.
Existing installs are not forced into it after upgrades. The tutorial explains
app controls first, then the main simulation concepts, with broad highlights and
mouse/keyboard Next, Back, Skip, and Finish controls. The tutorial keeps the
simulation paused while it is open and resumes normal playback when you finish,
skip, or close it. Replay it with `python main.py --tutorial` or from the
settings Actions category.

## Performance

Recent profile-driven optimization (2026-03-05) improved headless benchmark performance significantly:

- Energy mode step @ pop 150: `4.082ms → 2.005ms`
- Energy mode full frame @ pop 150: `25.445ms → 13.425ms`
- Boids mode step @ pop 150: `16.829ms → 11.887ms`

At 1920×1080 this keeps typical runs within the 60fps target envelope in normal mode, with heavy boids scenes still the most expensive.

## Design & Behavior Documentation

- **[docs/organism_biology.md](docs/organism_biology.md)** — organism biology, visual morphology, predator/prey ecology, and how to watch evolution happen.
- **[docs/predator_prey_system_guide.md](docs/predator_prey_system_guide.md)** — predator_prey mode mechanics, HUD/settings, controls, observability limits, and terminology.

## What You Are Watching

Primordial is a living artificial ecosystem. The glowing creatures on screen are **genome-driven organisms**, not decorative particles. Each one carries an inherited genome that determines how it behaves, how it moves, how long it lives, and — crucially — what it looks like.

Their bodies are **procedurally generated glyphs**: symbolic shapes assembled from the genome's visual traits. Related organisms look related because their genomes are similar. When a mutation changes a visual trait, the offspring's glyph changes too, producing a visible but recognizable variant. Glyph morphology is not decoration — it is the phenotype of inherited visual traits, and several morphology traits now also feed back into ecology through simple epistasis.

The simulation implements real selection pressure: organisms that find food efficiently, avoid predators, and manage energy well reproduce more often. Over generations, trait distributions in the population shift. This is Darwinian evolution in a compact, bounded trait space. It is not open-ended — the system cannot invent new behaviors or new body plans — but the selection, drift, and trait change you see are real.

For the full explanation, see [docs/organism_biology.md](docs/organism_biology.md).

## How It Works

### The Genome System

Each creature has a **genome** — a set of 16 heritable traits that determine its characteristics. All traits are floats in the range 0.0–1.0 and can mutate slightly each generation.

#### Survival Traits

| Trait | Range | Effect |
|-------|-------|--------|
| **speed** | 0–1 | Maximum movement speed multiplier |
| **size** | 0–1 | Body radius (4–12 pixels); larger = more collision area but higher energy cost |
| **sense_radius** | 0–1 | Food detection range (40–150 pixels); declines after 85% of max lifespan |
| **aggression** | 0–1 | Feeding strategy: <0.4 = grazer (+20% food efficiency, ignores prey), >0.6 = hunter (seeks and drains nearby creatures), 0.4–0.6 = opportunist |
| **efficiency** | 0–1 | Energy extraction rate from food |
| **longevity** | 0–1 | Maximum lifespan: 0 = ~3000 frames (~50s), 1 = ~10000 frames (~2.8min); high longevity costs energy each frame |
| **hue** | 0–1 | Base color hue (heritable; hue drift > 0.15 triggers speciation; predator rendering may add a species tint) |
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

- **Kin connection lines**: faint thin lines connect creatures of the same lineage when enough kin are nearby. In GPU predator/prey mode they are restored by default with conservative spacing, remain controlled by `kin_line_max_distance` and `kin_line_min_group`, and can be disabled by explicitly setting `kin_line_max_distance = 0.0`.
- **Territory shimmer**: the top 3 most populous lineages get a soft pulsing elliptical glow at their centroid. This "presence" shifts as lineages grow and shrink. It pulses on a 4–6 second sine wave.
- **Birth budding**: new creatures pop into existence at 0.2× scale and ease out to full size over 30 frames — a smooth "budding" effect.
- **Death dissolution**: dying creatures flash white, then shrink and fade over 40 frames, scattering 4–6 dim particles outward.
- **Glyph rotation**: each creature's glyph rotates at a rate set by `rotation_speed` — gliders barely turn, some creatures spin continuously.
- **Population cycles**: the overcrowding energy penalty creates boom-bust cycles. Watch population rise, crash, and re-stabilize.
- **Speciation events**: when a creature's offspring inherits a hue mutation > 0.15, it gets a new lineage ID. Kin lines for the old lineage gradually fade as the old line dies out and new lines emerge.
- **Aging**: creatures past 70% of their max lifespan gradually grey out. Ancient creatures become visibly desaturated and slower — a soft visual indicator of senescence.
- **Cosmic rays**: a faint white ring briefly expands around a creature struck by a spontaneous single-trait mutation. Watch for these in slow periods — they can seed sudden new lineage directions.
- **Attack lines**: when a hunter drains a nearby creature, a thin colored thread briefly connects them.
- **Zone backgrounds**: subtle radial tints mark the 5 environmental zones (warm vent, open water, kelp forest, hunting ground, deep trench). When the HUD is visible, those zones are also labeled on-screen at their centers. Creatures that evolve for their zone gain an energy advantage.

### Biology of the Organisms

Every organism has a genome that determines both behavior and appearance. Reproduction is asexual: a parent splits, passing a mutated genome copy to its offspring. Small mutations accumulate over generations, producing visible lineage divergence — not because visual traits are decorative, but because they are heritable traits that mutate like any other.

**Selection pressure** is real: organisms that feed efficiently, avoid predation, and manage energy costs reproduce more often. Traits under selection (speed, efficiency, aggression, longevity, sense radius) shift in the population average over time. Visual traits remain heritable lineage markers, but some of them now also have simple ecological consequences through the phenotype layer: complexity can make high-sense organisms metabolically expensive, symmetry can reward efficient gliders, and appendages can trade handling or evasion for drag.

**Lineage** is tracked by a numeric ID, branched when a hue mutation exceeds 0.15. Kin lines and territory shimmer use lineage data. A lineage is an ancestry marker, not a biological species — there is no reproductive isolation.

Evolution here is **bounded**: the system selects within a fixed 16-trait space. It cannot invent new behaviors, new body plans, or new ecological niches. What changes is the distribution of existing trait values in the population, driven by real selection pressure, neutral drift, and simple epistatic interactions between existing traits.

### Simple Epistasis

Primordial now includes a small **effective phenotype** layer between the raw genome and live ecology. The inherited genome stays unchanged; the phenotype layer translates trait combinations into effective modifiers for speed, movement cost, sensing, food extraction, reproduction burden, predation contact, flee agility, and depth behavior.

Current interactions are intentionally modest:

- **Speed x size**: large fast bodies are costly; small fast bodies flee well but make worse contact hunters.
- **Sense radius x complexity**: high-sense ornate bodies detect a bit better, but cost more to maintain.
- **Symmetry x motion style**: symmetric gliders/swimmers waste less movement energy; asymmetric darters evade a bit better.
- **Appendages x role**: appendages help prey turn away and help predators handle contact, but they add drag.
- **Longevity x reproduction**: long-lived bodies pay a higher effective reproduction threshold.
- **Depth preference x sensing**: specialists sense best in-band and worse across bands; generalists switch bands more easily.
- **Efficiency x speed**: high efficiency offsets some upkeep, but not the full cost of fast, expensive bodies.

This is **simple epistasis**, not a gene regulatory network. There is no recombination, developmental program, or sexual selection yet.

Tune it with `simulation.epistasis_strength`, or disable it entirely with
`simulation.epistasis_enabled = false`. In `predator_prey`, watch for
recognizable body plans such as swift-small prey, heavy-hunter predators,
efficient gliders, sensory specialists, and depth specialists.

For the full explanation, see [docs/organism_biology.md](docs/organism_biology.md).

### Reading the Creatures

Because glyphs are generated from the genome, you can learn to read organism traits visually:

- **Color** ≈ lineage and species (predators tinted warm; prey reflect genome hue)
- **Saturation** ≈ age (desaturation increases after 70% of max lifespan)
- **Size** ≈ body radius (4–12 px), also the `size` trait
- **Complexity** ≈ stroke count (2–7 strokes in the glyph)
- **Symmetry** ≈ arrangement type (asymmetric, bilateral, 3-fold, 4-fold)
- **Stroke delicacy** ≈ `stroke_scale` (tight/compact vs. spread/fine)
- **Appendages** ≈ 0–4 limb-like protrusions
- **Rotation** ≈ `rotation_speed` (near-still to steady spin)
- **Motion style** ≈ `motion_style` (glide/swim/dart; visible in trail length and movement pattern)
- **Kin lines** ≈ shared ancestry (nearby same-lineage creatures)
- **Territory shimmer** ≈ dominant lineages (top 3 get a pulsing glow)

Some critical traits are invisible: energy level, sensing range, depth band, reproductive readiness, and death cause cannot be read from creature appearance alone. The HUD and Inspect Mode expose what the eye cannot see.

Not every visual change is adaptive. Neutral drift can shift glyph traits over generations without any survival advantage. Predator/prey color cues can become less reliable after many generations of hue mutation. Visual change is evidence of heredity and mutation, not evidence of adaptation.

### Predator-Prey Biology

In predator_prey mode, species is determined by the `aggression` trait using hysteresis thresholds: prey with aggression ≥ `prey_to_predator_aggression_threshold` (default 0.30) become predators, and predators with aggression < `predator_to_prey_aggression_threshold` (default 0.20) become prey. Unknown species fall back to 0.5. This means species is an emergent role, not a separate property. Offspring can change species from their parent if a mutation crosses the relevant threshold.

**Predators** hunt prey on contact (same depth band required), gain capped energy per kill, and can forage for food when not actively hunting — but reproduction requires recent animal energy from kills. Predators also suffer interference (reduced effectiveness near other predators), a metabolic premium on movement, and a scarcity penalty when prey are below 15% of the population. Hunting grounds now act as modest ambush habitat for predators already inside them: the bonus is small, fades near the edge, and is density-damped so refuges do not become predator hotels. Predators do not seek those zones and no predator spawning or trait preservation was added.

**Prey** seek food and flee nearby predators. Fleeing takes priority over feeding. Prey can escape into a different depth band (cross-band miss) or flee beyond the predator's sensing range. Healthy young prey still flee at full strength, but prey flee max speed now also respects age frailty directly and can taper downward for low-energy prey when the low-energy slowdown is enabled.

Several mechanisms prevent permanent predator dominance: the reproduction gate (recent kills required), the 60% dominance penalty (+20% reproduction threshold), prey scarcity costs, predator interference, and cross-band misses. These create negative feedback: predator success reduces prey density, which makes predation harder, which reduces predator reproduction, which allows prey to recover.

Predator-collapse diagnostics also track near-contact "dance" behavior: same-depth close passes without kills, cross-depth near misses, sustained same-target chases, and whether successful kills skew toward old or low-energy prey. These diagnostics are observational only; they do not change kill distance or add a lunge/strike mechanic.
Predator kills now also get a renderer-only visibility pass: a brighter bioluminescent strike tether, a localized bloom at the prey position, a soft ripple, and a subtle predator pulse. This presentation layer does not alter same-depth contact rules, kill distance, predator/prey speed, kill energy, spawning, mutation, or adaptive tuning. On the pygame path the effect uses cached bloom/ripple/pulse surfaces; on the GPU path it uses bounded radial and line sprites so the extra visual work stays capped.

For the full predator-prey ecology explanation, see [docs/organism_biology.md](docs/organism_biology.md) and [docs/predator_prey_system_guide.md](docs/predator_prey_system_guide.md).

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
8. **Mutation**: Each of 16 traits has a ~6% chance of shifting (gaussian, std 0.08), clamped to 0–1
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

A Lotka-Volterra-inspired ecosystem where creatures are born as either **predator** or **prey**. The committed default starts at 12% predators and 88% prey. Predators hunt prey on contact and may forage when not actively hunting; prey search for food and flee nearby predators. The success metric is **stability**: how many simulation ticks the run survives before either species remains collapsed past the extinction grace window.

- Arms race evolution: predator aggression and prey speed evolve under mutual selection pressure.
- Cosmic ray hits can flip species identity when aggression crosses the hysteresis threshold (prey → predator at 0.30, predator → prey at 0.20).
- When predators exceed 60% of the population, predator reproduction becomes harder: their reproduction threshold increases by 20%.
- Hunting grounds provide a small density-damped ambush habitat bonus for predators already inside them, improving hunting conversion modestly without attracting predators or spawning new ones.
- Prey flee speed now respects prey frailty directly: age slowdown can apply to
  flee max speed, and low-energy prey can taper toward a configurable minimum
  flee multiplier. This is a prey-side ecological change, not predator
  spawning, extinct-trait preservation, or a direct reproduction-threshold
  change.
- Predator-collapse diagnostics now separate same-depth contact/flee
  oscillation, cross-depth near misses, sustained same-target chases, and
  kills of old or low-energy prey.
- If predators or prey hit zero, predator_prey enters an extinction grace window. The simulation continues while zero ticks are counted. If the species recovers (through mutation-driven species switching) before the grace window expires, the run continues. If the zero state persists for `extinction_grace_ticks` (default 7200 at 30 Hz, ~4 minutes), the run enters a red `GAME OVER` overlay, holds for 10 seconds, then restarts with a new seed. Predator lineages are biologically gone when predators hit zero, but new predators can reappear from surviving prey via species flip.
- Pressing `Space` during that `GAME OVER` screen skips the wait and starts the next seeded run immediately.
- The `GAME OVER` overlay also shows the rolling median that the run had to beat, highlights the current survival ticks when they beat that rolling median, shows the current adaptive step modifier, lists the current run's adaptive dial values, highlights the dial changed for that run with its up/down delta, and still notes when a run sets a new highest survival record.
- That dial highlight means "this run was the trial run that used this dial change," not "the dial change succeeded." A failed trial still highlights the changed dial, because that is the dial the run actually tested.
- The settings overlay exposes a predator-prey-only dial reset action that restores adaptive dials to baseline values and clears the max survival tick record before starting a fresh run.
- The settings overlay also exposes **Reset all settings to defaults** (`R` then `R`): it restores built-in app and mode defaults and saves them to `config.toml`, but does **not** delete saved worlds, logs, screenshots, or diagnostics. Some runtime changes may require a simulation reset to fully apply.
- The HUD shows `sim_ticks`, current seed, current `survival_ticks`, the rolling median survival over the configured history window (`stability_history_size`, 20 by default), and the best recent survival from that same window.
- Adaptive tuning is implemented but disabled by the committed default (`adaptive_tuning_enabled = false`). When enabled in config, it tweaks one bounded ecological dial at a time after below-median collapses. That comparison is against the rolling median, not the all-time high. Each candidate is then evaluated against the unchanged baseline on the same seed set, using the median survival from those runs. The seed-pair count defaults to `2` and can be overridden with `adaptive_trial_seed_count`. Survival remains the primary objective. If the candidate and baseline survival medians are within `adaptive_survival_deadband` ticks (`50` by default), the decision falls back to lower near-extinction pressure, defined as `predator_low_ticks + prey_low_ticks` over the run. Exact ties revert the candidate.
- If runs keep failing to beat the rolling median for `adaptive_step_escalation_runs` completed runs in a row (5 by default), the next dial trial increases its step size by `adaptive_step_escalation_percent` (25% by default) for each full streak block.
- If you launch with `--log=csv`, predator-prey appends one `run_complete` row per completed run and one `trial_decision` row per completed adaptive trial to `run_logs/predator_prey_runs.csv`. The rows include seed, `sim_ticks`, `survival_ticks`, `predator_low_ticks`, `prey_low_ticks`, `near_extinction_pressure`, trial role (`candidate` or `baseline`), verification seed, trial id, survival deadband, decision basis, keep/revert outcome, and the dial values used for that run. Manual dial resets still append a `dial_reset` marker row so later analysis can segment the data.
- Predators keep a persistent warm predator tint layered over their genome color, so they stay legible even after hue drift. Prey continue to render directly from their genome palette.

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
- The overlay is grouped by category, with one category visible at a time and a
  details panel explaining the selected setting, range, internal key, and reset
  behavior.
- The mouse cursor is hidden during normal simulation playback and appears while
  the settings overlay is open. Click categories to switch sections, click rows
  to select them, use value steppers to edit fields, use the mouse wheel to
  scroll long categories, and use footer buttons for Apply, Discard, Save, Load,
  Guide, and reset actions.
- Press **`H`** while the settings overlay is open, or click **Guide**, to open
  the in-app documentation browser. It loads the in-app help documents,
  supports section navigation, search, scrolling, mouse input, and keyboard
  input, and closes with `Esc` or the Close button.
- Click **Start Tutorial** in the Actions category, or press **`T`** there, to
  replay the guided onboarding overlay.
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
| simulation | epistasis_enabled | bool | Enables simple eco-morphological phenotype interactions |
| simulation | epistasis_strength | float 0..1.5 | Scales how strongly trait combinations bend effective ecology |
| simulation | zone_count | int >= 0 | Number of generated environmental zones |
| simulation | zone_strength | float 0..1 | Zone effect intensity |
| display | visual_theme | enum: ocean/petri/geometric/chaotic | Rendering theme |
| display | fullscreen | bool | Fullscreen/windowed mode |
| display | target_fps | int >= 1 | Frame limit |
| display | show_hud | bool | HUD visibility |
| rendering | glyph_size_base, kin/shimmer/animation fields | validated numeric ranges | Renderer tuning knobs (advanced) |
| rendering | predation_kill_effects_enabled | bool | Enable the richer predator-prey strike/bloom/ripple visibility pass |
| rendering | predation_kill_effect_intensity | float 0.1..2.5 | Scale the brightness and spread of predator kill effects |
| rendering | predation_kill_effect_max_active | int 1..256 | Cap live predator kill effect objects to bound worst-case render work |

Mode-specific tuning keys:

| Section | Key | Type / Range | Description |
|---|---|---|---|
| modes.predator_prey | prey_energy_to_reproduce | float 0.05..1 | Prey-only reproduction threshold in `predator_prey`; falls back to shared `simulation.energy_to_reproduce` if absent |
| modes.predator_prey | predator_energy_to_reproduce | float 0.05..1 | Predator-only reproduction threshold in `predator_prey`; falls back to shared `simulation.energy_to_reproduce` if absent |
| modes.predator_prey | predator_refuge_enabled | bool | Enable predator ambush-habitat bonuses in hunting grounds |
| modes.predator_prey | predator_refuge_hunt_sense_bonus | float 0..0.25 | Maximum extra predator hunt-sense bonus available in ambush habitat |
| modes.predator_prey | predator_refuge_contact_bonus | float 0..0.25 | Maximum extra predator contact-kill distance bonus available in ambush habitat |
| modes.predator_prey | predator_refuge_depth_transition_bonus | float 0..0.30 | Maximum extra predator depth-tracking urgency available in ambush habitat |
| modes.predator_prey | predator_refuge_movement_cost_reduction | float 0..0.20 | Maximum hunting-cost reduction available to predators in ambush habitat |
| modes.predator_prey | predator_refuge_density_radius | float >= 0 | Radius used to count nearby predators for refuge density damping |
| modes.predator_prey | predator_refuge_density_soft_cap | int >= 0 | Nearby-predator count that still allows the full refuge bonus |
| modes.predator_prey | predator_refuge_density_hard_cap | int >= 1 | Nearby-predator count where the refuge bonus fully fades out |
| modes.predator_prey | prey_flee_sense_multiplier | float 0.1..5 | Multiplier applied to prey threat sensing while fleeing |
| modes.predator_prey | prey_flee_speed_multiplier | float 0.75..2 | Multiplier applied to prey flee movement speed (replaces hardcoded 1.5) |
| modes.predator_prey | prey_flee_age_slowdown_enabled | bool | Apply age frailty directly to prey flee max speed |
| modes.predator_prey | prey_flee_low_energy_slowdown_enabled | bool | Allow low-energy prey to lose flee speed below the configured threshold |
| modes.predator_prey | prey_flee_low_energy_threshold | float 0.01..1 | Energy threshold where low-energy prey flee slowdown begins |
| modes.predator_prey | prey_flee_low_energy_min_mult | float 0.4..1 | Minimum flee-speed multiplier for the most energy-depleted prey |
| modes.predator_prey | predator_prey_scarcity_penalty_multiplier | float 0.1..5 | Extra predator energy-cost multiplier when prey fall below 15% of population |
| modes.predator_prey | food_cycle_amplitude | float 0..1 | Blend between constant food rate (`0`) and the full feast/famine swing (`1`) |
| modes.predator_prey | predator_near_contact_diagnostic_scale | float 1..5 | Diagnostic-only multiple of contact distance used to count predator near-contact frames |
| modes.predator_prey | predator_sustained_chase_min_frames | int >= 1 | Diagnostic-only same-target chase length required before a chase counts as sustained |
| modes.predator_prey | stability_history_size | int >= 1 | Rolling run-history window used for `MedN` / `BestN` survival stats and below-median comparisons |
| modes.predator_prey | adaptive_step_escalation_runs | int >= 1 | Number of consecutive completed runs that fail to beat the rolling median before dial step sizes scale up |
| modes.predator_prey | adaptive_step_escalation_percent | float >= 0 | Additional dial-step percentage applied for each full escalation streak block |
| modes.predator_prey | adaptive_trial_seed_count | int >= 1 | Number of same-seed baseline/candidate seed pairs used to evaluate each adaptive dial trial |
| modes.predator_prey | adaptive_survival_deadband | int >= 0 | Tick deadband for treating candidate vs baseline survival medians as a near tie before using the near-extinction tie-breaker |
| modes.predator_prey | adaptive_near_extinction_predator_floor | int >= 0 | Predator-count floor used when counting `predator_low_ticks` during a run |
| modes.predator_prey | adaptive_near_extinction_prey_floor | int >= 0 | Prey-count floor used when counting `prey_low_ticks` during a run |

Settings overlay labels, categories, descriptions, ranges, and action help live
in [`primordial/rendering/settings_metadata.py`](/home/victoria/projects/primordial/primordial/rendering/settings_metadata.py).
The overlay's modal, sidebar, list, details, and footer rectangles are sized by
[`primordial/rendering/settings_layout.py`](/home/victoria/projects/primordial/primordial/rendering/settings_layout.py)
so long labels wrap within their panels without shrinking the readable UI fonts.
Mouse hit regions are produced by the overlay draw pass with the small
`primordial/rendering/settings_mouse.py` hit-region type so visible controls and
click targets stay aligned.
In-app help content is loaded from docs files through
[`primordial/help/document_model.py`](/home/victoria/projects/primordial/primordial/help/document_model.py).
The help browser lives in dedicated rendering modules:
`help_overlay.py`, `help_layout.py`, `help_navigation.py`, and `help_mouse.py`.
The tutorial similarly lives outside settings/help internals:
`primordial/tutorial/steps.py`, `state.py`, `persistence.py`, plus
`rendering/tutorial_overlay.py`, `tutorial_layout.py`, and `tutorial_mouse.py`.
The overlay can edit selected mode-scoped values where a field explicitly points
at a `[modes.<name>]` key; other mode-table tuning remains TOML-only.

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
│   │   ├── genome.py        # Genome — 16 heritable traits
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
├── AGENTS.md
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

See AGENTS.md for the full Sim Mode Contract.

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

- Added predator rarity advantage (living predators only) in predator-prey mode; no spawning, trait preservation, or prey behavior changes.

Predators now choose among **final sensed usable prey targets**; a nearby prey that fails depth-adjusted sensing no longer blocks pursuit of a slightly farther usable target.

- Predators now keep a short quarry memory (last seen prey position/depth) for conservative pursuit when live sensing briefly fails; this memory steering is weaker than live sensing and does not count as a usable prey sighting.

- Quarry-memory diagnostics now separate strict target switches from same-target reacquisitions and report memory-assisted same-target kills via `kills_after_memory_chase`.
