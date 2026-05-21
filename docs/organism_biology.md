# Organism Biology and Visual Morphology

This document explains what the organisms in Primordial are, how their genomes
determine both behavior and appearance, what you can learn by looking at them,
and what you cannot. It is written for a curious user, not for contributors
reading the code.

For the predator-prey system guide, switch to the **Predator-Prey Guide**
tab in the help browser, or see
[predator_prey_system_guide.md](predator_prey_system_guide.md).
For architecture and implementation notes, see
[architecture_reference.md](architecture_reference.md).

---

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

---

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

---

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

---

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

---

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

---

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

---

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

---

## What Counts as Evolution in This App

Evolution in Primordial means heritable change in trait distributions across
the population over successive generations. It is real Darwinian selection:
variation exists, it is heritable, and it affects reproductive success.

It is not open-ended evolution. The system cannot invent new traits, new
behaviors, new ecological roles, or new body plans beyond the 16-trait genome.
It cannot evolve reproductive isolation, new food sources, or new sensing
modalities. Evolution here is optimization within a bounded, designed trait
space.

---

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
  visual traits.
- The glow and bioluminescent pulse are cosmetic. They do not signal mating
  readiness, territory, or fitness.
- Trail length reflects motion style, not intelligence or health.
- Kin lines represent shared ancestry, not social bonds or communication.
- Territory shimmer shows where a lineage is concentrated, not claimed territory
  in a behavioral sense.

---

## What the App Can and Cannot Currently Model

**Can model:**

- Directional selection on heritable traits
- Frequency-dependent selection (hunter vs. grazer, predator vs. prey)
- Tradeoffs between competing trait values (speed vs. cost, longevity vs.
  fecundity)
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
- Epistasis (trait interactions are additive, not synergistic or antagonistic)

---

## Predator and Prey Biology

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

---

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

---

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
- Neutral drift of visual traits (complexity, symmetry, appendages)
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