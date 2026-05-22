# Primordial Guide

This guide explains what Primordial is, how organisms work, what their genomes
control, what you can learn by looking at them, and what you cannot. It is
written for users, not for contributors reading the code.

## What Primordial Is

Primordial is a living screensaver: a dark ocean-like world filled with glowing
creatures that move, eat, reproduce, mutate, and die. Each creature has a small
genome. That genome affects how it moves, what it can sense, how efficiently it
uses energy, how long it lives, and how its glowing glyph looks.

The simulation is not a biological model of real ocean life. It is a compact
artificial ecosystem designed to make selection, drift, population cycles, and
lineage change visible enough to watch.

## What You See On Screen

The default ocean theme draws:

- **Creatures** as glowing procedural glyphs.
- **Food** as small cyan particles.
- **Trails** behind moving creatures.
- **Kin lines** between nearby related creatures, when enabled.
- **Territory shimmer** around dominant lineages, when enabled.
- **Environmental zones** as faint colored regions.
- **Attack lines** for predator kills.
- **Birth and death animations** when creatures appear or dissolve.
- **Cosmic ray rings** when a living creature receives a spontaneous mutation.

Predators have a warm species tint in predator-prey mode, while prey generally
read cooler. The `P` highlight key makes predators much easier to find in dense
scenes.

Some features are deliberately subtle. Depth bands, sensing range, energy cost,
and most trait values are not directly labeled on creatures.

## What an Organism Is

Each creature in Primordial is a single autonomous organism driven by an
inherited genome. It has a position, velocity, energy level, age, a species
role (in predator_prey mode), and a lineage identifier. It cannot learn, plan,
or store memories. Every decision it makes — where to move, when to flee, what
to eat — follows directly from its genome, its current state, and what it can
sense nearby.

An organism is born, lives for a bounded number of frames determined by its
`longevity` trait, and dies either when its energy reaches zero or when it
reaches old age. It leaves no corpse and passes nothing to its offspring
except a mutated copy of its genome.

There is no brain, no neural network, no learned behavior. The genome is the
entire behavioral program.

## What the Genome Controls

The genome is a frozen dataclass with 16 traits, each a float from 0.0 to
1.0. These traits fall into groups:

**Survival traits** affect how the organism behaves in the simulation:

| Trait | What it does |
|-------|-------------|
| `speed` | Maximum movement speed |
| `size` | Body radius (4–12 pixels); larger bodies have more collision area but cost more energy to move |
| `sense_radius` | How far the organism can detect food and threats (40–150 pixels); declines after 85% of max lifespan |
| `aggression` | Feeding strategy: below 0.4 = grazer, above 0.6 = hunter, between = opportunist. In predator_prey mode, this also determines species role |
| `efficiency` | How much energy the organism extracts from each food particle |
| `longevity` | Maximum lifespan (3000–10000 frames, roughly 50 seconds to 2.8 minutes at 60 fps). High longevity costs extra energy per frame |
| `conformity` | Tendency to align velocity with flockmates in boids mode. Inert in other modes, but still heritable and still mutates |
| `depth_preference` | Which depth band the organism gravitates toward in predator_prey mode (0 = surface, 0.5 = mid, 1 = deep) |
| `motion_style` | Movement pattern: glide (0–0.33), swim (0.34–0.66), dart (0.67–1.0) |

**Visual traits** affect what the organism looks like on screen:

| Trait | What it does visually |
|-------|----------------------|
| `hue` | Base color, mapped through the theme palette. Heritable. Large hue shifts trigger a new lineage |
| `saturation` | How vivid or greyed-out the color appears |
| `complexity` | Number of strokes in the glyph: 0 = 2 strokes, 1 = 7 strokes |
| `symmetry` | Glyph arrangement: below 0.33 = asymmetric, 0.33–0.66 = bilateral mirror, 0.66–0.83 = 3-fold radial, 0.83–1.0 = 4-fold radial |
| `stroke_scale` | Overall size and delicacy of glyph strokes (low = compact tight strokes, high = spread-out delicate strokes) |
| `appendages` | 0–4 extra limb strokes radiating outward from the glyph perimeter |
| `rotation_speed` | How fast the glyph spins: 0 = almost no rotation, 1 = steady continuous rotation |

All 16 traits are heritable. All 16 traits can mutate. There is no
distinction in the code between "functional" and "decorative" traits —
visual traits mutate, are inherited, and can drift under selection pressure
just like survival traits.

## How Reproduction Works

When a creature's energy reaches or exceeds the reproduction threshold, it
splits into two: the parent keeps half its energy, and the offspring receives
the other half. The offspring's genome is the parent's genome passed through
`mutate()`, which independently nudges each trait with a small Gaussian offset
(mean 0, standard deviation 0.08) at a per-trait probability set by the
`mutation_rate` config value (default ~6%).

Reproduction is asexual. There is no mating, no gene exchange between parents,
and no recombination. Each offspring has exactly one parent.

The offspring spawns at a small random offset from the parent's position. Its
glyph is generated fresh from its mutated genome, independently cached, and
never shared with the parent.

In predator_prey mode, reproduction has additional rules:

- Prey reproduce when their energy meets the prey-specific threshold.
- Predators reproduce when their energy meets the predator-specific threshold
  **and** they have recently gained energy from killing prey
  (`recent_animal_energy`).
- When predators exceed 60% of the population, their effective reproduction
  threshold increases by 20%, making it harder for predators to dominate.
- An offspring may change species from its parent if the mutation shifted its
  `aggression` across the 0.5 species boundary.

## How Mutation Works

There are two mutation sources:

1. **Reproduction mutation**: each of the 16 traits has an independent
   probability (`mutation_rate`, ~6% by default) of shifting by a Gaussian
   offset with standard deviation 0.08. Clamped to [0.0, 1.0].

2. **Cosmic ray mutation**: each creature has a small per-frame chance
   (`cosmic_ray_rate`, ~0.03% by default) of a spontaneous single-trait
   mutation with a larger standard deviation (0.15). The trait shifted is
   chosen uniformly at random.

Cosmic rays can hit any creature at any time, including between reproduction
events. In drift mode, the cosmic ray rate is doubled because mutation is the
primary driver of change.

A mutation that shifts `hue` by more than 0.15 from the parent's hue triggers a
**lineage branch**: the offspring gets a new lineage ID. This is the
mechanism for visual speciation events.

Mutations are small. A single mutation rarely produces a dramatic new
organism. Over tens of generations, however, small shifts accumulate and
produce visibly different lineages.

## How Selection Pressure Works

Selection pressure is the aggregate effect of the simulation's energy model
on which organisms survive long enough to reproduce. Primordial has several
interacting selection systems:

**Energetic selection**: Organisms that find food efficiently, avoid
unnecessary costs, and maintain positive energy balance reproduce more often.
Speed, efficiency, size, and sense radius are all directly under energetic
selection. Faster organisms find food sooner but pay higher movement costs.
Larger organisms have broader collision area but cost more to move. This is a
tradeoff, not a simple "higher is better."

**Predation selection** (energy mode): Hunters (aggression > 0.6) gain energy
by attacking nearby smaller creatures. Grazers (aggression < 0.4) gain a 20%
food-efficiency bonus. The relative profitability of hunting vs. grazing
depends on prey density: hunting is profitable when prey are plentiful and
unprofitable when prey are scarce. This is frequency-dependent selection.

**Predator-prey arms race** (predator_prey mode): Predators and prey are under
mutual selection pressure. Faster predators catch more prey, so prey are
selected for speed and awareness. Faster prey escape more often, so predators
are selected for speed and sensing. The traits on both sides co-evolve.

**Longevity-fecundity tradeoff**: High-longevity organisms live longer but
pay a continuous metabolic tax and reproduce less often per unit time.
Low-longevity organisms die sooner but reproduce more frequently. Which
strategy wins depends on the current ecological conditions: stable feast
periods favor longevity; crash periods favor fast reproduction.

**Zone selection**: Five environmental zones bias energy costs depending on
trait profiles. A high-efficiency organism in a warm vent pays less; a fast
aggressive organism in a hunting ground pays less. Over many generations,
organisms cluster toward zones that match their traits. This is spatially
structured selection.

**Overcrowding selection**: When population exceeds 50% of the cap, energy
costs increase quadratically. This punishes organisms in crowded areas and
creates boom-bust cycles that periodically reshape the population.

**Aging**: Speed declines after 70% of max lifespan; sense radius declines
after 85%. Old organisms are less competitive even before death. This creates
a hard ceiling on how long any individual can contribute to the gene pool.

## What Lineage Means

A lineage is a numeric identifier assigned at birth. Offspring normally
inherit their parent's lineage ID. When a mutation shifts `hue` by more than
0.15, the offspring gets a new lineage ID instead.

Lineages are not biological species. They are ancestry markers used for
kin-line rendering and territory shimmer. Two creatures with different lineage
IDs may still be genetically close if their lineages recently branched. Two
creatures with the same lineage ID may have drifted apart in traits other
than hue if many small mutations accumulated without triggering a hue branch.

Lineage IDs are monotonic. They are useful for visualizing how family groups
spread, cluster, and compete, but they do not define hard reproductive
boundaries.

## What Changes Across Generations

Traits that are under active selection pressure will shift in the population
average over time. For example:

- In energy mode, average aggression often rises as hunting becomes
  profitable, then may stabilize as prey (grazers) become scarce and hunting
  loses its advantage.
- In predator_prey mode, predator speed and prey speed may co-evolve upward
  in an arms race.
- In drift mode, all traits drift randomly with no direction because there
  is no selection pressure.

Traits that are not under selection may drift neutrally. Visual traits
(saturation, complexity, symmetry, stroke_scale, appendages, rotation_speed)
are not directly tied to survival in the current model, so mutations in these
traits are neutral by default. They change over time through random drift and
genetic hitchhiking (a neutral trait may spread if it is linked to a
beneficial mutation that happened to occur nearby in the same genome copy).

## What Counts as Evolution in This App

Evolution in Primordial means heritable change in trait distributions across
the population over successive generations. It is real Darwinian selection:
variation exists, it is heritable, and it affects reproductive success.

It is not open-ended evolution. The system cannot invent new traits, new
behaviors, new ecological roles, or new body plans beyond the 16-trait genome.
It cannot evolve reproductive isolation, new food sources, or new sensing
modalities. Evolution here is optimization within a bounded, designed trait
space.

## Biological Simulation Versus Visual Metaphor

The following are **real biological simulations** implemented in code:

- Heritable variation via genome mutation
- Selection pressure from resource competition, predation, and environmental costs
- Frequency-dependent selection (hunter/grazer balance)
- Arms-race coevolution (predator/prey speed)
- Longevity-fecundity tradeoff
- Spatially structured selection (zones)
- Neutral genetic drift (especially visible in drift mode)
- Speciation events (lineage branching on large hue mutations)
- Aging and senescence (declining speed and sensing)

The following are **visual metaphors, not biological models**:

- The glyph shape does not affect survival. A more complex glyph is not
  "more evolved" or "fitter." Glyph morphology is determined by neutral
  visual traits, including simple eco-morphological epistasis where body-plan
  traits change ecological performance.
- The glow and bioluminescent pulse are cosmetic. They do not signal mating
  readiness, territory, or fitness.
- Trail length reflects motion style, not intelligence or health.
- Kin lines represent shared ancestry, not social bonds or communication.
- Territory shimmer shows where a lineage is concentrated, not claimed territory
  in a behavioral sense.

## What the App Can and Cannot Currently Model

**Can model:**

- Directional selection on heritable traits
- Frequency-dependent selection (hunter vs. grazer, predator vs. prey)
- Tradeoffs between competing trait values (speed vs. cost, longevity vs.
  fecundity)
- Simple epistatic trait interactions where combinations of inherited traits
  alter effective speed, sensing, energy cost, reproduction, predation, and
  depth behavior
- Neutral drift of unconstrained traits
- Population dynamics driven by resource cycles and predation
- Spatial effects on evolution (zone adaptation, local density)

**Cannot model:**

- Novel traits or behaviors not in the 16-trait genome
- Sexual selection, mate choice, or recombination
- Reproductive isolation or true speciation
- Coevolution of organisms with their environment (the zones are static)
- Cultural transmission, learning, or behavioral plasticity
- Ecosystem engineering (organisms cannot change their environment)
- Full genetic regulatory networks or developmental programs

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

## Predators, Prey, and Food

Prey try to find nearby food in their current depth band. If there is no food
available in that band, they may shift toward another band where food is
available. Food spawns continuously, but the food cycle causes the amount of new
food to rise and fall over time.

Predators scan for prey. When they sense prey, they steer toward it and try to
match its depth band. A predator kills by contact if it is close enough and in
the same band. A kill transfers a capped amount of the prey's remaining energy
to the predator.

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
normal food seeking and may trigger a depth-band escape attempt. Predators track
prey by sensing, steering, and probabilistically shifting depth.

### How Predators Behave

A predator scans for the nearest prey within its sensing range (modified by
the predator hunt sense multiplier, predator interference, and hunt balance
factor). When it detects prey, it steers toward it and tries to match its
depth band.

**Kill on contact**: when the predator and prey are close enough (sum of
radii, scaled by `predator_contact_kill_distance_scale`) and in the same
depth band, the predator kills the prey. Kill energy gain is capped by
`predator_kill_energy_gain_cap`. Multiple predators cannot farm the same prey
in one frame: the first predator to reach it drains its energy, setting it
to zero.

**Depth tracking**: predators probabilistically shift depth toward the band
their target prey occupies. A predator can only kill prey in the same depth
band. Reaching a prey in 2D but in the wrong band is a **cross-band miss**.

**Foraging**: when a predator is not actively hunting (no prey sensed, or
recently sated), it can forage for food with predator-specific efficiency
and cost rules. However, predator reproduction requires recent animal energy,
so kills remain essential for population growth.

**Satiety**: after a kill, the predator enters a brief satiety period during
which its hunting sense is reduced, causing it to search at close range only.

**Interference**: predators near other predators suffer reduced hunting
effectiveness. This natural interference prevents predator swarms from
wiping out local prey instantly.

**Movement cost**: predators pay a metabolic premium on movement (up to 1.4x
base cost, reduced toward 1.0x when broad omnivory/foraging is strong). When
prey are scarce (< 15% of population), predators pay additional scarcity
penalty energy costs.

### How Prey Behave

Prey search for nearby food within their current depth band. If food is
unavailable in their band, they may shift toward another band where food is
present.

**Fleeing**: when a prey senses a nearby predator (sensing range modified by
`prey_flee_sense_multiplier`), it steers directly away and may attempt to
shift to a different depth band to escape. Fleeing takes priority over food
seeking: if the prey is actively fleeing, it does not look for food.

**Cost model**: prey pay standard movement cost, longevity metabolic cost,
sensing upkeep, overcrowding penalty, and zone modifiers. They do not pay
the predator metabolic premium.

### Why Predators Cannot Simply Dominate Forever

Several mechanisms prevent permanent predator dominance:

- **Reproduction gate**: predators must have recent animal energy (from kills)
  to reproduce. Without kills, predator reproduction stalls.
- **Predator dominance penalty**: when predators exceed 60% of the population,
  their reproduction threshold increases by 20%.
- **Prey scarcity penalty**: when prey drop below 15% of the population,
  predators pay extra energy costs on top of the base predator metabolic
  premium.
- **Predator interference**: predators in close proximity reduce each other's
  hunting effectiveness, diluting the advantage of swarming.
- **Cross-band misses**: prey that escape into a different depth band survive
  even at close 2D range.

These mechanisms create a negative feedback loop: predator success reduces
prey density, which makes predation harder and costlier, which reduces
predator reproduction, which allows prey to recover.

### Why Prey Can Boom, Crash, or Stabilize

Prey population dynamics emerge from the interaction of food availability,
predation pressure, and reproduction rate:

- **Boom**: when food is abundant (feast phase of the food cycle) and
  predation is light (few predators or high cross-band miss rate), prey
  reproduce rapidly and population grows.
- **Crash**: when predators are numerous and food cycles enter famine, prey
  face simultaneous predation and starvation. Both pressures remove prey
  faster than they can reproduce.
- **Stabilize**: when predator and prey populations are balanced, prey
  losses to predation approximately equal prey births from feeding. This
  equilibrium is dynamic and can shift with any change in trait distributions
  or ecological conditions.

### How Predator/Prey Oscillations Emerge

Lotka-Volterra-style oscillations emerge naturally from the predator-prey
interaction loop:

1. Many prey → predators find targets easily → predator population grows.
2. Growing predator population → more prey killed → prey population drops.
3. Fewer prey → predators struggle to find food → predator population drops.
4. Fewer predators → prey recover and reproduce → prey population rises.
5. Cycle repeats.

The food cycle (feast/famine oscillation) modulates these dynamics. During
feast, prey reproduction accelerates. During famine, both species struggle
but prey suffer more because they depend on food directly while predators can
survive on remaining prey.

The depth-band system adds further modulation: prey concentrated in one band
are easier for same-band predators to find, but prey distributed across bands
impose more cross-band misses and reduce predator hunting efficiency.

### How Scarcity, Food Cycles, Depth Bands, Zones, and Movement Costs Shape Survival

**Scarcity**: when prey are scarce, predators pay extra energy costs. This
creates a hard selection pressure against predator overpopulation.

**Food cycles**: the sinusoidal food cycle alternates feast and famine phases
(approximately 30 seconds per cycle at default settings). Feast phases
allow rapid prey reproduction. Famine phases stress both species but tend
to remove weaker organisms first — those with low efficiency, high metabolic
costs, or poor food-seeking.

**Depth bands**: three abstract vertical layers (surface, mid, deep) add a
spatial dimension that is not visible on the 2D screen. Depth creates refuges:
prey in a different band from a predator cannot be killed, even at close
range. Depth distribution therefore affects kill rates and oscillation
dampening.

**Zones**: five environmental zone types provide energy cost modifiers based
on trait profiles. A predator in a hunting ground (favors aggression and
speed, penalizes longevity) pays less energy there. A prey organism in a
warm vent (favors efficiency and size, penalizes speed) pays less. Over
time, trait distributions shift toward the zones organisms occupy.

**Movement costs**: energy cost scales with speed, size, and longevity.
Faster, larger, or longer-lived organisms must eat more to stay alive.
Movement cost is the main constraint that prevents any one trait from
increasing without limit.

### How Predator/Prey Traits Are Inherited and Selected Over Time

Both species inherit full 16-trait genomes from their parents with mutation.
Key traits under selection in each role:

**Predators**: speed (catch prey faster), sense_radius (find prey at greater
range), aggression (already above 0.5 by definition, but higher aggression
affects hunt priority), depth_preference (matching prey depth bands improves
kill rate).

**Prey**: speed (escape predators faster), sense_radius (detect predators
earlier), efficiency (extract more energy from limited food), depth_preference
(occupying different depth bands from average predators reduces kill risk),
longevity (surviving through famine periods may be more valuable than
reproducing quickly).

Because species assignment depends on the `aggression` trait boundary, there
is gene flow between the roles when mutations cross the 0.5 threshold. A
high-speed prey organism can give birth to a predator offspring if the
aggression mutation is large enough. This means predator and prey gene pools
are not fully isolated.

### What Makes an Organism Predator or Prey

In predator_prey mode, species is a role assigned at birth based on the
`aggression` trait. If aggression is above 0.5, the creature is born a
predator. If below 0.5, it is born prey. This means species is not a
separate property — it is an emergent consequence of a single genome trait.

An offspring can be born a different species than its parent if the mutation
shifts aggression across the 0.5 boundary. A cosmic ray mutation can also
flip a living creature's species mid-life when aggression crosses 0.5.

Predators receive a warm color tint layered over their genome hue. Prey
render directly from their genome color palette. This tint is cosmetic, not
mechanical: it helps the viewer distinguish roles visually.

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

## Food Cycle, Famine, and Collapse

The food cycle is a repeating feast/famine wave. During feast periods, food
appears more quickly. During famine periods, food becomes scarce and populations
come under stress.

Collapse can happen in several ways:

- prey run out of food or cannot escape predation;
- predators overtake the ecosystem and then starve when prey become scarce;
- one role hits zero and stays there beyond the configured grace window;
- overcrowding raises costs when populations are high.

The HUD shows the food-cycle bar, predator/prey counts, and danger status when a
role has reached zero but is still inside the extinction grace window.

## Game Over and Adaptive Tuning

Predator-prey mode has a clear failure state. If predators or prey remain at
zero long enough to exceed the configured extinction grace window, the run
freezes and shows a red **GAME OVER** overlay.

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

## The Meaning of Organism Appearance

Creature visuals are **not hand-drawn sprites**. Each creature's glyph is
procedurally generated entirely from its genome. The same genome always
produces the same glyph. Related creatures look related. Mutations produce
similar but distinct offspring.

### What You Can Infer from Appearance

| Visual feature | Determined by | What it tells you |
|---------------|---------------|-------------------|
| **Hue/color** | `hue`, plus predator species tint | Approximate lineage family. Predators biased warm; prey reflect genome hue. Over time, hue drift can blur this distinction |
| **Saturation/intensity** | `saturation` | How vivid the organism looks. Desaturation also signals aging (after 70% of max lifespan, grey overlays increase) |
| **Size** | `size` (4–12 px radius) | Body size. Also affected by depth band (surface = slightly larger/brighter, deep = slightly smaller/dimmer) |
| **Complexity** | `complexity` (2–7 strokes) | How many strokes make up the glyph. Simple glyphs are 2 strokes; complex ones have up to 7 |
| **Symmetry type** | `symmetry` | Asymmetric / bilateral / 3-fold radial / 4-fold radial. Related organisms share symmetry type |
| **Stroke delicacy** | `stroke_scale` | Compact tight strokes (low) vs. spread-out fine strokes (high). Affects glyph "feel" more than overall creature radius |
| **Appendages** | `appendages` (0–4) | Extra limb-like strokes radiating outward. More appendages look more "limbed" |
| **Rotation** | `rotation_speed` | How fast the glyph body spins. Gliders barely rotate; some organisms spin steadily |
| **Motion style** | `motion_style` | Glide: smooth long trails, 14 positions. Swim: side-to-side oscillation, 10 positions. Dart: stillness with periodic bursts, 5 positions |
| **Aging/desaturation** | Computed from `age / max_lifespan` | Grey overlay increases after 70% of max lifespan. Ancient organisms are visibly washed out |
| **Pulsing glow** | `_glyph_phase` (derived from `hue`) | Bioluminescent pulse amplitude. In boids mode, flock members synchronize pulse phase |
| **Kin lines** | Shared `lineage_id` | Faint filament threads between nearby same-lineage creatures. Show family clusters, not social bonds |
| **Territory shimmer** | Top 3 dominant lineages | Soft pulsing elliptical glow at lineage centroids. Shows which families are most numerous in an area |
| **Birth budding** | Reproduction event | New creatures appear at 0.2x scale and ease out to full size over 30 frames |
| **Death dissolution** | Death event | Dying creatures flash white, shrink, and fade over 40 frames with scattered particles |
| **Cosmic ray ring** | Spontaneous mutation event | Faint white ring briefly expands around a creature that received a cosmic ray mutation |
| **Attack lines** | Predator kill event | Thin colored thread briefly connects predator and prey during a kill |
| **Zone backgrounds** | Static zone layout | Subtle radial tints marking environmental zones. Not visible on every display at default alpha |
| **Depth cues** | `depth_band` | Surface creatures are slightly brighter and larger; deep creatures are slightly dimmer and smaller |

### What Is Not Directly Visible

These important mechanics are real but cannot be read from a creature's
appearance:

| Mechanism | Why it is invisible |
|-----------|-------------------|
| **Energy level** | Not drawn on creatures. Must use the HUD or Inspect Mode |
| **Sensing range** | Not drawn. A creature may be starving because it cannot sense nearby food |
| **Depth band** | Only hinted by subtle brightness/size differences. Not labeled |
| **Death cause** | Death animations are the same regardless of cause (starvation, predation, old age) |
| **Reproductive readiness** | Not shown. A creature at 0.79 energy looks the same as one at 0.81 |
| **Species role** | In energy mode, aggression tiers are not marked. In predator_prey mode, the warm tint is the primary cue but can become less reliable after many generations of hue mutation |
| **Trait distributions over time** | No historical trait graphs. The HUD shows current snapshots; Inspect Mode shows one creature at a time |
| **Zone cost modifiers** | Not per-creature. Only visible as aggregate zone backgrounds |
| **Predator recent animal energy** | Not visible. Predators must have recent kills to reproduce, but this state is internal |
| **Gene flow between species** | When a prey offspring is born a predator (or vice versa) due to an aggression mutation, this is not signaled visually beyond the tint |

### Limits of Visual Inference

- **Some important traits are not directly visible**. A creature that looks
  healthy may be one frame from starvation. A creature that looks fast may
  have declining sense radius due to age.

- **Visual traits may drift neutrally**. Glyph complexity, symmetry, and
  appendage count are not under selection pressure. If a lineage drifts
  toward more complex glyphs over 500 generations, that does not mean
  complexity is adaptive. It may be genetic hitchhiking or neutral drift.

- **Predator/prey color conventions can become less reliable over time**.
  Species is assigned by aggression, not by hue. If a prey lineage mutates
  toward warm hues over many generations, it may look predator-like despite
  being prey. The warm tint overlay on predators still distinguishes them
  from most prey, but it is not a permanent guarantee.

- **Not every visual change means adaptive advantage.** A creature that
  looks different from its parent may have gained a beneficial mutation, a
  harmful mutation, or a neutral mutation that does not affect its survival.
  Visual change is evidence of inheritance and mutation, not evidence of
  adaptation.

## How to Watch Evolution Happen

### Over a few seconds

- Watch individual creatures move, eat, and avoid each other. Notice their
  motion styles: gliders leave long smooth trails, swimmers undulate side to
  side, darters sit still and then burst.
- Notice the food cycle bar in the HUD. When it swings right (feast), food
  particles appear more often and populations tend to grow. When it swings
  left (famine), food becomes scarce.
- If you see a white ring briefly expand around a creature, that is a cosmic
  ray mutation happening in real time.

### Over several minutes (10–30 minutes)

- Look for **glyph family divergence**. At startup, all glyphs look somewhat
  similar because they descend from a common ancestor with random variation.
  After 5–10 minutes, distinct visual clans emerge: groups of organisms that
  share symmetry type, stroke style, and general glyph shape. Kin lines
  help trace which families are expanding.
- In energy mode, watch the **hunter/grazer ratio** in the HUD. During feast
  periods, grazers can outpace hunters. During famines, hunters profit from
  preying on weakened grazers. The ratio can flip back and forth.
- In predator_prey mode, watch the **population counts** in the HUD. You may
  see predator and prey counts oscillate: predators rise, then prey drop,
  then predators drop, then prey recover. This is the classic Lotka-Volterra
  cycle emerging from the rules.
- Watch **territory shimmer**. The top 3 lineages get a soft pulsing glow at
  their centroid. If that centroid drifts toward a particular zone, organisms
  in that lineage may be adapting to that zone's trait profile.
- Notice **aging**: ancient organisms become visibly desaturated and slower.
  Watch long-lived organisms persist while shorter-lived contemporaries come
  and go.

### Over long runs (hours)

- Population-level trait averages shift. Average speed, efficiency, or
  aggression may change directionally over many generations. These shifts
  are real selection, but they are subtle and best read from the HUD or
  Inspect Mode rather than from individual creature appearance.
- **Lineages spread and disappear.** A dominant lineage may occupy much of
  the screen, then lose ground to a newer lineage with a trait advantage
  (or just lucky positioning during a famine). Old kin lines fade as
  lineages die out and new ones take their place.
- **Extinction events** in predator_prey mode can reset the system. When
  one species collapses, the run ends and restarts. Over many runs, you may
  observe which ecological configurations (speed distributions, depth
  distributions, food cycle parameters) tend to produce longer survival.
- In drift mode, all traits drift without direction. Watch glyph shapes
  slowly wander through the trait space over very long runs. No trait
  "improves" — it just changes. This is pure neutral evolution.

### How family resemblance appears visually

Because glyphs are deterministic functions of the genome, parent and offspring
glyphs differ only by the specific traits that mutated. If only `speed`
mutated, the offspring's glyph will look identical to its parent (speed does
not affect glyph appearance). If `complexity` or `symmetry` mutated, the
offspring's glyph will look noticeably different but still recognizably
related — same stroke vocabulary, similar appendages, similar scale.

Over several generations within a lineage, small mutations accumulate. You
may notice a lineage gradually shifting from simple 2-stroke asymmetric glyphs
to 4-stroke bilateral glyphs. The shift is gradual enough that adjacent
generations look similar, but distant generations look distinct.

### Why some evolution is real but subtle

Selection pressure in Primordial is real but modest. The mutation rate is low
(6% per trait per birth), the Gaussian offset is small (std 0.08), and the
energy model creates tradeoffs that prevent any one trait from dominating
without cost. This means trait distributions change directionally but slowly.

The most visible evolutionary changes tend to be:
- Lineage branching (sudden new kin-line group appearing)
- Population shifts during famine (lineage replacements as weaker organisms
  die first)
- Predator/prey oscillations (cyclical population changes visible in the HUD)

The least visible evolutionary changes tend to be:
- Gradual shifts in average trait values within a stable lineage
- Neutral drift still occurs in visual traits, but some morphology traits now
  also matter ecologically through simple epistasis
- Shifts in depth preference distributions

### Why the HUD helps interpret what the eye cannot see

The simulation hides energy levels, sensing ranges, reproductive readiness,
death causes, and trait distributions inside its internal state. The HUD
exposes key aggregates: population counts, species ratios, survival ticks,
average speeds, and the food cycle phase.

For understanding what is actually happening — whether a lineage is expanding
because it is fit or just lucky, whether a population crash is due to famine
or predation, whether predators are near the dominance threshold that triggers
the reproduction penalty — the HUD is essential. The visual field is
atmospheric and meaningful, but it is incomplete.

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
- **Rendering**: kin-line visuals and related rendering options.
- **Actions**: snapshots, guide, reset actions.

The selected setting has a description panel explaining what it does, its range
or choices, and whether it applies on save or requires a reset. Reset-required
settings are marked with a compact badge.

Actions in the footer and Actions category use the same behavior as their
keyboard shortcuts. Destructive reset actions require confirmation.

## Controls

Normal runtime controls:

Move the mouse during normal playback to reveal a temporary bottom action bar
with the current runtime shortcuts. It stays fully visible for 5 seconds after
movement stops, then fades out over 10 seconds. The cursor still stays hidden
unless an interactive overlay or Inspect Mode is active.

| Control | Action |
| --- | --- |
| `Esc` / `Q` | Quit |
| `H` | Open in-app help |
| `U` | Toggle HUD |
| `Space` | Pause/unpause, or skip predator-prey game-over countdown |
| `F` | Toggle fullscreen/windowed |
| `R` | Reset the current simulation run |
| `S` | Open or close settings |
| `I` | Toggle Inspect Mode |
| `M` | In Inspect Mode, switch between pause and slow motion |
| `D` | In Inspect Mode, toggle compact/detailed card |
| mouse click | In Inspect Mode, select a creature |
| hold `P` | Highlight predators |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

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
| `H` | Open the in-app help browser |
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

Many visual systems, such as glyphs, trails, zones, aging, cosmic rays, and the
HUD, are shared across all modes.

## What Is Currently Hard To See

Some real mechanics are not obvious from the screen:

- **Energy level** is not shown on each creature. A creature that looks healthy
  may be one frame from starvation.
- **Sensing range** is not drawn. A creature may be starving because it cannot
  sense nearby food.
- **Depth bands** are only hinted by subtle brightness and size differences.
- **Death cause** is not visible in the death animation. Starvation, predation,
  and old age all produce the same dissolution effect.
- **Reproductive readiness** is not shown. A creature at 0.79 energy looks the
  same as one at 0.81.
- **Trait distributions over time** are not graphed. The HUD shows current
  snapshots; Inspect Mode shows one creature at a time.
- **Zone cost modifiers** are not per-creature. Only visible as aggregate zone
  backgrounds.
- **Evolutionary adaptation** is indirect; you infer it from population changes,
  movement, lineage visuals, and long-term trends rather than from charts.

These are current observability limits, not hidden controls.

## Current Limitations

Primordial evolves creatures inside a fixed set of traits and behaviors. It can
select for different speeds, sizes, sensing ranges, efficiencies, depth
preferences, and visual glyph traits. It cannot currently evolve entirely new
behaviors, new body plans, new food sources, or reproductive isolation.

The simulation cannot model sexual selection, mate choice, recombination,
coevolution of organisms with their environment (the zones are static), cultural
transmission, learning, behavioral plasticity, ecosystem engineering, or full
genetic regulatory networks. It can now model simple epistatic trait
interactions, but not developmental gene regulation.

The simulation is built for a beautiful, readable screensaver experience. It is
not a complete artificial-life research environment.

## Glossary

**Adaptive tuning**: Optional predator-prey system that tests bounded ecological
dial changes across runs. Implemented, but disabled by default.

**Arms race**: Coevolution where predators and prey each evolve traits that
counter the other's advantage, potentially driving both sides to higher speed
or sensing over time.

**Cosmic ray**: Rare spontaneous mutation to one trait on a living creature.

**Cross-band miss**: A predator reaches prey in 2D space but cannot kill because
they are in different depth bands.

**Depth band**: Abstract predator-prey layer: surface, mid, or deep.

**Food cycle**: Repeating resource wave between famine and feast.

**Frequency-dependent selection**: Selection where the fitness of a strategy
depends on how common it is. Hunting is profitable when prey are common and
unprofitable when prey are scarce.

**Game over**: Predator-prey collapse state after a role remains at zero beyond
the configured grace window.

**Gene flow**: Exchange of genetic material between populations. In
predator_prey mode, mutations that shift aggression across 0.5 transfer a
creature between species, creating gene flow between predator and prey gene
pools.

**Genome**: The inherited trait set that determines creature behavior and
appearance. A frozen dataclass with 16 float traits.

**Glyph**: The procedural glowing symbol used as a creature body. Generated
deterministically from the genome.

**Kin line**: A visual connection between nearby creatures with the same
lineage.

**Lineage**: An ancestry identifier used for visual family structure. Branches
when a hue mutation exceeds 0.15.

**Lineage branch**: A speciation event where an offspring gets a new lineage ID
because its hue mutation was large enough to trigger a branch.

**Longevity-fecundity tradeoff**: The evolutionary tension between living a long
time (high longevity, high metabolic cost) and reproducing quickly (low longevity,
lower cost, more births per unit time).

**Neutral drift**: Change in trait values caused by random mutations that do not
affect survival. Especially visible in visual traits and in drift mode.

**Predator-prey dials**: Configured ecological parameters that affect hunting,
fleeing, scarcity pressure, kill distance, kill energy, and food-cycle amplitude.

**Zone**: Soft environmental region that changes energy and sensing pressure.
