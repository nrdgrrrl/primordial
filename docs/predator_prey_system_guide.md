# Primordial Predator-Prey Guide

This guide explains what Primordial is showing today, with a focus on
`predator_prey` mode. It is written for users, not for contributors reading the
code.

## What Primordial Is

Primordial is a living screensaver: a dark ocean-like world filled with glowing
creatures that move, eat, reproduce, mutate, and die. Each creature has a small
genome. That genome affects how it moves, what it can sense, how efficiently it
uses energy, how long it lives, and how its glowing glyph looks.

The simulation is not a biological model of real ocean life. It is a compact
artificial ecosystem designed to make selection, drift, population cycles, and
lineage change visible enough to watch.

## Predator-Prey Mode Overview

Predator-prey mode creates two roles:

- **Prey** search for food and flee predators.
- **Predators** hunt prey and may forage when they are not actively hunting.

The default predator-prey run starts with a larger prey population and a smaller
predator population. In the committed defaults, predators start at 12% of the
initial population. From there, the balance changes continuously as creatures
eat, reproduce, starve, hunt, mutate, and die.

Predator-prey mode also adds an abstract vertical layer called **depth bands**.
Creatures are still drawn on a flat 2D screen, but internally they can occupy
surface, mid, or deep water. Predators can only kill prey on contact when both
are in the same band.

## What You See On Screen

The default ocean theme draws:

- **Creatures** as glowing procedural glyphs.
- **Food** as small cyan particles.
- **Trails** behind moving creatures.
- **Kin lines** between nearby related creatures, when enabled.
- **Territory shimmer** around dominant lineages, when enabled.
- **Environmental zones** as faint colored regions.
- **Predator kill effects**: luminous strike tethers, a localized bloom, a soft ripple, and subtle predator feedback.
- **Birth and death animations** when creatures appear or dissolve.
- **Cosmic ray rings** when a living creature receives a spontaneous mutation.

Predators have a warm species tint in predator-prey mode, while prey generally
read cooler. The `P` highlight key makes predators much easier to find in dense
scenes.

Predation is now visually distinct from starvation and old age. A successful kill
briefly leaves a bioluminescent tether between predator and prey, a bloom and
ripple at the prey location, and a small predator pulse. This is presentation
only: same-depth contact, kill distance, energy transfer, and population
balance are unchanged. The pygame renderer uses cached bloom/ripple/pulse
surfaces, and the GPU renderer uses bounded line/radial sprites, so the effect
can stay visible without unbounded per-frame work.

Some features are deliberately subtle. Depth bands, sensing range, energy cost,
and most trait values are not directly labeled on creatures.

## Predators, Prey, and Food

Prey try to find nearby food in their current depth band. If there is no food
available in that band, they may shift toward another band where food is
available. Food spawns continuously, but the food cycle causes the amount of new
food to rise and fall over time.

Predators scan for prey. When they sense prey, they steer toward it and try to
match its depth band. A predator kills by contact if it is close enough and in
the same band. A kill transfers a capped amount of the prey's remaining energy
to the predator.

Hunting grounds now also act as modest **ambush habitat** for predators already
inside them. In the first pass, this bonus is habitat-only: predators do not
steer toward hunting grounds, do not spawn there, and do not preserve collapsed
predator lineages. The bonus is intentionally small, fades toward zone edges,
and shrinks when too many predators stack together locally.

Predators are not purely obligate hunters in the current implementation. When a
predator is not engaged with prey, it can forage for food with predator-specific
efficiency and cost rules. Predator reproduction still requires recent animal
energy, so kills remain important.

## Movement, Sensing, Fleeing, and Hunting

Creature movement is smooth steering, not grid movement. Genomes define a motion
style:

- **Glide**: slow, long, smooth movement with longer trails.
- **Swim**: moderate movement with a side-to-side oscillation.
- **Dart**: stillness broken by sharper bursts.

Sensing is imperfect. Distance, environmental zones, depth-band separation, and
age can all affect what a creature can detect. Kelp forests and deep trenches
make sensing less clear. Open water and hunting grounds sharpen it.

Prey flee when they sense a nearby predator. Fleeing uses stronger steering than
normal food seeking and may trigger a depth-band escape attempt. Flee speed now
also respects prey condition directly: healthy young prey still flee at full
strength, but old prey inherit the same age frailty that slows general
movement, and low-energy prey can taper toward a configurable minimum flee-speed
multiplier when `prey_flee_low_energy_slowdown_enabled` is on. This is meant to
make tired or elderly prey easier to catch without changing predator spawning,
trait preservation, or reproduction thresholds. Predators track prey by
sensing, steering, and probabilistically shifting depth. Inside a hunting
ground, predators can get a small density-damped boost to hunt sensing, contact
range, and depth tracking, plus a slight reduction in hunting energy costs.
Sustained pursuit now also adds a conservative depth-fatigue layer: prey that
have been chased repeatedly, especially while low on energy, become less
perfect at repeated depth escapes, and predators that stay committed to the
same quarry long enough can make a bounded depth-follow step near contact. The
final kill still requires normal contact and same depth.

## Depth Bands and Cross-Band Misses

Predator-prey mode has three depth bands:

- **Surface**
- **Mid**
- **Deep**

Depth bands are an internal ecological dimension. They are not separate screen
layers. The only visual hints are subtle brightness, tint, scale, and food glow
differences. Surface creatures are slightly brighter/larger; deep creatures are
slightly dimmer/smaller.

Depth affects the simulation in three main ways:

- sensing is strongest in the same band and weaker across band separation;
- prey can escape by changing to a different band;
- predators can only kill prey in the same band.

When a predator reaches contact range but the prey is in another band, that is a
**cross-band miss**. The HUD reports recent cross-band misses so you can tell
whether depth is protecting prey.

Near-contact diagnostics now also record when predators repeatedly reach a
configurable band around contact range without converting the hunt. The
diagnostics separate:

- same-depth near-contact no-kill frames, which point to flee/contact
  oscillation or "dance" behavior;
- cross-depth near-contact no-kill frames, which point to depth mismatch;
- sustained same-target chases that still fail to end in kills;
- kills that land mainly on old or low-energy prey, which indicates prey
  frailty is doing work on the prey side rather than through predator rescue.

## Zones and Environmental Pressure

The world contains soft environmental zones. They are faint colored circles or
regions behind the creatures. Zones do not block movement. Instead, they change
energy costs and sensing conditions.

Current zone types:

| Zone | Favors | Penalizes |
| --- | --- | --- |
| Warm Vent | efficiency, size | speed |
| Open Water | speed, small size | aggression |
| Kelp Forest | sense radius, low aggression | speed |
| Hunting Ground | aggression, speed | longevity |
| Deep Trench | longevity, small size | efficiency |

A creature whose traits match a zone pays less energy there. A mismatched
creature pays more. Zone labels are easiest to see when the HUD is visible.

## Reproduction, Mutation, Lineages, and Evolution

Creatures reproduce when their energy reaches the current threshold for their
mode and role. Parent energy is split with the offspring. The offspring receives
a mutated copy of the parent's genome.

Mutation is usually small. Over many births, small changes can accumulate.
Cosmic rays add a second mutation source: a rare spontaneous mutation to one
trait on a living creature.

Lineages are identifiers used to show family structure. Kin lines and territory
shimmer use lineage data. A lineage branch can happen when a mutation shifts
visual/ecological traits enough, especially hue. Lineages are useful for
watching ancestry, but they are not biological species in the strict sense.

Evolution in Primordial means selection within a fixed trait space. Faster,
better-sensing, more efficient, or better-positioned creatures can reproduce
more often. The system does not invent new behaviors; it tunes existing traits.

## Food Cycle, Famine, and Collapse

The food cycle is a repeating feast/famine wave. During feast periods, food
appears more quickly. During famine periods, food becomes scarce and populations
come under stress.

Collapse can happen in several ways:

- prey run out of food or cannot escape predation;
- predators overtake the ecosystem and then starve when prey become scarce;
- one role hits zero and stays there beyond the configured grace window
  (default 7200 ticks at 30 Hz, roughly 4 minutes);
- overcrowding raises costs when populations are high.

If a species hits zero, the simulation enters an extinction grace window. The
run is not immediately over: the remaining species continues to live, mutate,
reproduce, and evolve. If the zero-count species recovers through mutation-driven
species switching before the grace window expires, the run continues normally.
When predators hit zero, the existing predator lineages are biologically gone,
but new predators can reappear from surviving prey via species flip during the
grace window. If the zero state persists for the full grace window, the run
enters GAME OVER.

The HUD shows the food-cycle bar, predator/prey counts, and a danger/grace line
when a role has reached zero, indicating which role is at zero and how many
grace ticks remain.

## Game Over and Adaptive Tuning

Predator-prey mode has a clear failure state, but extinction is not immediate.
If predators or prey hit zero, the simulation enters an extinction grace window
(configured by `extinction_grace_ticks`, default 7200). During the grace window,
the remaining species continues to live, mutate, reproduce, and evolve. Recovery
is possible if the zero-count species reappears through mutation-driven species
switching before the grace window expires.

If the zero state persists for the full grace window, the run freezes and shows
a red **GAME OVER** overlay.

The game-over overlay shows the collapse cause, seed, predator/prey counts,
survival ticks, rolling survival history, adaptive dial values, and a restart
countdown. The default hold is 10 seconds. Press `Space` to skip the countdown
and start the next run immediately.

Adaptive tuning exists in the current codebase, but it is disabled by the
committed default config (`adaptive_tuning_enabled = false`). When enabled in
config, the system can compare bounded ecological dial changes across repeated
runs and keep or revert candidates based on survival and near-extinction
pressure. Normal default runs do not automatically change those dials.

The settings overlay includes **Reset Predator-Prey Dials** when predator-prey
mode is active. It restores the ecological dial values to their baseline,
clears survival/tuning history, persists that reset state, and starts a fresh
predator-prey run.

## HUD Guide

Press `U` to show or hide the HUD. In predator-prey mode, it shows:

- predator and prey counts;
- average actual speed for each role;
- recent kills and cross-band misses over a rolling 3-second window;
- simulation ticks and current run seed;
- current survival ticks, rolling median, and recent best survival;
- danger/grace status if a role has hit zero;
- adaptive trial status if tuning is enabled and active;
- dominant zone;
- mode, theme, FPS, and food-cycle bar.

The HUD is the best way to understand what is happening mechanically. The
screensaver view is intentionally quieter and more atmospheric.

## Settings Guide

Press `S` in normal mode to open the settings overlay. The simulation pauses and
the mouse cursor appears while settings are open. Closing the overlay hides the
cursor again unless another interactive mode is active.

Settings are grouped into categories:

- **Simulation**: mode, population, food spawn, global speed.
- **Display**: backend, fullscreen, target FPS, HUD.
- **Evolution**: mutation, cosmic rays, epistasis, food cycle, zones.
- **Ecology / Predator-Prey**: predator-prey-specific starting mix and dials.
- **Rendering**: kin-line visuals, predator kill visibility effects, and related presentation options.
- **Actions**: snapshots, guide, reset actions.

The selected setting has a description panel explaining what it does, its range
or choices, and whether it applies on save or requires a reset. Reset-required
settings are marked with a compact badge.

Predator-prey exposes additional ecology-only tuning for this pass:

- `prey_flee_age_slowdown_enabled`
- `prey_flee_low_energy_slowdown_enabled`
- `prey_flee_low_energy_threshold`
- `prey_flee_low_energy_min_mult`
- `prey_depth_fatigue_enabled`
- `prey_depth_fatigue_min_chase_ticks`
- `prey_depth_fatigue_energy_threshold`
- `prey_depth_fatigue_escape_urgency_mult`
- `prey_depth_fatigue_decay_ticks`
- `prey_depth_fatigue_max`
- `predator_near_contact_diagnostic_scale`
- `predator_sustained_chase_min_frames`
- `predator_committed_depth_tracking_enabled`
- `predator_committed_depth_tracking_min_chase_ticks`
- `predator_committed_depth_tracking_near_contact_scale`
- `predator_committed_depth_tracking_cooldown_ticks`

The prey flee settings change only prey escape speed under age/energy frailty.
The depth-fatigue and committed-tracking settings are conservative depth-band
behavior rules: they do not increase global kill distance and do not allow
cross-depth kills. The near-contact settings remain diagnostics-only and do not
add a lunge/strike mechanic.

Actions in the footer and Actions category use the same behavior as their
keyboard shortcuts. Destructive reset actions require confirmation.

## Controls

Normal runtime controls:

Move the mouse during normal playback to reveal a temporary top action bar
with the current runtime shortcuts. It stays fully visible for 5 seconds after
movement stops, then fades out over 10 seconds. The cursor still stays hidden
unless an interactive overlay or Inspect Mode is active.

| Control | Action |
| --- | --- |
| `Esc` / `Q` | Quit |
| `H` | Open in-app Help |
| `U` | Toggle HUD |

Settings overlay controls:

| Control | Action |
| --- | --- |
| mouse click | Click categories, rows, steppers, and buttons |
| mouse wheel | Scroll the active settings list |
| `Up` / `Down` | Move selection |
| `Left` / `Right` | Change selected value |
| `Tab` / `Shift+Tab` | Change category |
| `Enter` | Apply and save settings |
| `Esc` / `S` | Discard pending changes and close |
| `Space` | Run selected action in the Actions category |
| `V` | Save snapshot |
| `L` | Load snapshot |
| `H` | Open this guide in the in-app help browser |
| `T` | Start the onboarding tutorial from the Actions category |
| `R R` | Confirm reset settings defaults |
| `D D` | Confirm predator-prey dial reset, when available |

The **Guide** action opens this document inside Primordial. The help browser has
section navigation on the left, readable guide content on the right, search,
mouse scrolling, and keyboard navigation. Press `Esc` or click **Close** to
return to settings.

## Tutorial

Primordial includes a guided onboarding tutorial for new users. It runs on a
fresh normal-mode launch, can be replayed with `python main.py --tutorial`, and
can be started from the settings **Actions** category. The tutorial explains app
controls first, then walks through creatures, food, predators and prey, births
and deaths, lineages, zones, depth bands, collapse, and evolution. The tutorial
keeps the simulation paused until you finish, skip, or close it, then resumes
normal playback. It is a quick tour; this guide is the deeper reference.

## Save, Load, and Persistent Tuning State

The settings overlay can save and load a world snapshot. A snapshot stores the
world dimensions, simulation settings, creatures, food, zones, RNG state, and
predator-prey runtime state when applicable.

Predator-prey adaptive tuning state is also persisted separately on app exit,
next to the user config. That sidecar file is not a world snapshot; it exists so
adaptive dial history can carry between launches when tuning is enabled.

## Other Modes

Primordial also includes:

- **Energy**: the default mode. Creatures forage for food and aggression creates
  hunter/grazer/opportunist behavior.
- **Boids**: flocking behavior. Creatures gain energy from being in useful flock
  sizes instead of eating food.
- **Drift**: a calmer neutral-drift mode with passive energy regeneration and
  old-age deaths.

The predator-prey guide focuses on predator-prey mode, but many visual systems,
such as glyphs, trails, zones, aging, cosmic rays, and the HUD, are shared.

## What Is Currently Hard To See

Some real mechanics are not obvious from the screen:

- **Depth bands** are only hinted visually.
- **Sensing range** is not drawn.
- **Energy level** is not shown on each creature.
- **Death cause** is not visible in the death animation.
- **Trait distributions** are not graphed over time.
- **Zone cost modifiers** are not shown per creature.
- **Evolutionary adaptation** is indirect; you infer it from population changes,
  movement, lineage visuals, and long-term trends rather than from charts.

These are current observability limits, not hidden controls.

## Current Limitations

Primordial evolves creatures inside a fixed set of traits and behaviors. It can
select for different speeds, sizes, sensing ranges, efficiencies, depth
preferences, and visual glyph traits. It cannot currently evolve entirely new
behaviors, new body plans, new food sources, or reproductive isolation.

The simulation is built for a beautiful, readable screensaver experience. It is
not a complete artificial-life research environment.

## Glossary

**Adaptive tuning**: Optional predator-prey system that tests bounded ecological
dial changes across runs. Implemented, but disabled by default.

**Cosmic ray**: Rare spontaneous mutation to one trait on a living creature.

**Cross-band miss**: A predator reaches prey in 2D space but cannot kill because
they are in different depth bands.

**Depth band**: Abstract predator-prey layer: surface, mid, or deep.

**Food cycle**: Repeating resource wave between famine and feast.

**Game over**: Predator-prey collapse state after a role remains at zero for the
full extinction grace window. Temporary zero-count extinction can recover through
mutation-driven species switching during the grace window.

**Genome**: The inherited trait set that determines creature behavior and
appearance.

**Glyph**: The procedural glowing symbol used as a creature body.

**Kin line**: A visual connection between nearby creatures with the same
lineage.

**Lineage**: An ancestry identifier used for visual family structure.

**Predator-prey dials**: Configured ecological parameters that affect hunting,
fleeing, scarcity pressure, kill distance, kill energy, and food-cycle amplitude.

**Zone**: Soft environmental region that changes energy and sensing pressure.

## Related Guides

For a deeper explanation of what organisms are, how their genomes determine
both behavior and appearance, what you can learn by looking at them, and how to
watch evolution happen over time, switch to the **Organism Biology** tab in the
help browser.


### Predator rarity advantage
Predator-prey mode now supports a modest, capped rarity advantage for living predators when predator count is low and prey are abundant. It does not spawn predators, preserve extinct predator lineages, alter prey behavior, or directly change reproduction thresholds. It blends conservatively with refuge bonuses.

### 2026-05 chase balance + sighting semantics update

- Predator prey-sighting diagnostics now count **usable** sightings only: a prey candidate must pass final depth-adjusted `_sense_target_position()` before `frames_with_prey_sighted` or sustained same-target chase can increment.
- Sensing remains finite-radius circular (pixel-distance bounded), omnidirectional (no facing cone), and modifier-driven (genome base sense + hunt multiplier + depth/phenotype/zone/rarity/refuge factors).
- Chase balance defaults are now `predator_hunt_speed_multiplier=1.15` and `prey_flee_speed_multiplier=1.30` (configurable), replacing the old hardcoded prey flee `1.5` term.
- This is a chase-balance correction only; it does not introduce predator spawning, trait preservation, reproduction-threshold changes, kill-cap changes, or direct prey suppression logic.

Predators now choose among final sensed usable prey targets; a nearby prey that fails depth-adjusted sensing no longer blocks pursuit of another usable target.

Predators now keep short quarry memory (target id, last-known position/depth, last-seen frame) and can briefly pursue last known position when live sensing drops out. Memory pursuit is weaker than live sensing, does not increment usable sighting metrics, and does not bypass normal same-depth contact kill rules.

Quarry-memory diagnostics now distinguish strict target switches from same-target reacquisitions, and `kills_after_memory_chase` reports memory-assisted same-target kills after memory chase episodes.

- HUD/Inspect observability now includes average age, lineage age, and compact evolution drift direction (run-baseline trait-average deltas). These are descriptive observability metrics, not adaptation proof.

- Snapshot compatibility note: older snapshots missing observability baseline metadata now capture a stable load-time baseline so evolution drift remains descriptive and does not use a moving fallback.
