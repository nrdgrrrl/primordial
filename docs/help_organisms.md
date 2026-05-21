# Organisms

## What an Organism Is

Each creature in Primordial is a single autonomous organism driven by an inherited genome. It has a position, velocity, energy level, age, a species role (in predator_prey mode), and a lineage identifier. It cannot learn, plan, or store memories. Every decision it makes follows directly from its genome, its current state, and what it can sense nearby.

An organism is born, lives for a bounded number of frames determined by its `longevity` trait, and dies either when its energy reaches zero or when it reaches old age. It leaves no corpse and passes nothing to its offspring except a mutated copy of its genome.

There is no brain, no neural network, no learned behavior. The genome is the entire behavioral program.

## What the Genome Controls

The genome is a frozen dataclass with 16 traits, each a float from 0.0 to 1.0.

**Survival traits** affect how the organism behaves:

| Trait | What it does |
|-------|-------------|
| `speed` | Maximum movement speed |
| `size` | Body radius (4-12 pixels); larger bodies cost more energy to move |
| `sense_radius` | How far the organism can detect food and threats (40-150 pixels); declines after 85% of max lifespan |
| `aggression` | Feeding strategy: below 0.4 = grazer, above 0.6 = hunter, between = opportunist. In predator_prey mode, this determines species role |
| `efficiency` | How much energy the organism extracts from each food particle |
| `longevity` | Maximum lifespan (3000-10000 frames). High longevity costs extra energy per frame |
| `conformity` | Tendency to align velocity with flockmates in boids mode |
| `depth_preference` | Which depth band the organism gravitates toward in predator_prey mode |
| `motion_style` | Movement pattern: glide (0-0.33), swim (0.34-0.66), dart (0.67-1.0) |

**Visual traits** affect what the organism looks like:

| Trait | What it does visually |
|-------|----------------------|
| `hue` | Base color, mapped through the theme palette. Large hue shifts trigger a new lineage |
| `saturation` | How vivid or greyed-out the color appears |
| `complexity` | Number of strokes in the glyph: 0 = 2 strokes, 1 = 7 strokes |
| `symmetry` | Glyph arrangement: below 0.33 = asymmetric, 0.33-0.66 = bilateral mirror, 0.66-0.83 = 3-fold radial, 0.83-1.0 = 4-fold radial |
| `stroke_scale` | Overall size and delicacy of glyph strokes |
| `appendages` | 0-4 extra limb strokes radiating outward |
| `rotation_speed` | How fast the glyph spins |

All 16 traits are heritable. All 16 traits can mutate. Visual traits mutate, are inherited, and can drift under selection pressure just like survival traits.

## Reproduction and Mutation

When a creature's energy reaches the reproduction threshold, it splits into two: the parent keeps half its energy, and the offspring receives the other half with a mutated genome. Reproduction is asexual with no mating, gene exchange, or recombination.

**Reproduction mutation**: each of the 16 traits has an independent probability (default ~6%) of shifting by a Gaussian offset with standard deviation 0.08. Clamped to [0.0, 1.0].

**Cosmic ray mutation**: each creature has a small per-frame chance (default ~0.03%) of a spontaneous single-trait mutation with a larger standard deviation (0.15). The trait shifted is chosen uniformly at random.

A mutation that shifts `hue` by more than 0.15 from the parent's hue triggers a **lineage branch**: the offspring gets a new lineage ID. This is the mechanism for visual speciation events.

In predator_prey mode, predators must have recent animal energy from kills to reproduce. When predators exceed 60% of the population, their effective reproduction threshold increases by 20%.

## Lineages

A lineage is a numeric identifier assigned at birth. Offspring normally inherit their parent's lineage ID. When a mutation shifts `hue` by more than 0.15, the offspring gets a new lineage ID instead.

Lineages are ancestry markers used for kin-line rendering and territory shimmer. They are not biological species and do not define hard reproductive boundaries.

## What Counts as Evolution

Evolution in Primordial means heritable change in trait distributions across the population over successive generations. It is real Darwinian selection: variation exists, it is heritable, and it affects reproductive success.

It is not open-ended evolution. The system cannot invent new traits, new behaviors, new ecological roles, or new body plans beyond the 16-trait genome. Evolution here is optimization within a bounded, designed trait space.

## What the App Can and Cannot Model

**Can model**: directional selection, frequency-dependent selection, trait tradeoffs, neutral drift, population dynamics, spatial effects on evolution.

**Cannot model**: novel traits or behaviors, sexual selection or recombination, reproductive isolation or true speciation, coevolution with environment, cultural transmission, ecosystem engineering, epistasis.