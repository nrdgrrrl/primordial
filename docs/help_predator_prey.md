# Predator-Prey

## Predator-Prey Overview

Predator-prey mode creates two roles:

- **Prey** search for food and flee predators.
- **Predators** hunt prey and may forage when they are not actively hunting.

The default run starts with a larger prey population and a smaller predator population. Predators start at 12% of the initial population. From there, the balance changes continuously as creatures eat, reproduce, starve, hunt, mutate, and die.

Predator-prey mode also adds an abstract vertical layer called **depth bands**. Creatures are drawn on a flat 2D screen, but internally they can occupy surface, mid, or deep water. Predators can only kill prey on contact when both are in the same band.

## How Predators Behave

A predator scans for the nearest prey within its sensing range. When it detects prey, it steers toward it and tries to match its depth band.

**Kill on contact**: when the predator and prey are close enough and in the same depth band, the predator kills the prey. Kill energy gain is capped.

**Depth tracking**: predators probabilistically shift depth toward the band their target prey occupies. A predator can only kill prey in the same depth band. Reaching a prey in 2D but in the wrong band is a **cross-band miss**.

**Foraging**: when a predator is not actively hunting, it can forage for food with predator-specific efficiency and cost rules. However, predator reproduction requires recent animal energy, so kills remain essential for population growth.

**Satiety**: after a kill, the predator enters a brief satiety period with reduced hunting sense.

**Interference**: predators near other predators suffer reduced hunting effectiveness, preventing predator swarms from wiping out local prey instantly.

**Movement cost**: predators pay a metabolic premium on movement. When prey are scarce (below 15% of population), predators pay additional scarcity penalty energy costs.

## How Prey Behave

Prey search for nearby food within their current depth band. If food is unavailable in their band, they may shift toward another band where food is present.

**Fleeing**: when a prey senses a nearby predator, it steers directly away and may attempt to shift to a different depth band to escape. Fleeing takes priority over food seeking.

**Cost model**: prey pay standard movement cost, longevity metabolic cost, sensing upkeep, overcrowding penalty, and zone modifiers. They do not pay the predator metabolic premium.

## Why Predators Cannot Dominate Forever

Several mechanisms prevent permanent predator dominance:

- **Reproduction gate**: predators must have recent animal energy (from kills) to reproduce.
- **Predator dominance penalty**: when predators exceed 60% of the population, their reproduction threshold increases by 20%.
- **Prey scarcity penalty**: when prey drop below 15% of the population, predators pay extra energy costs.
- **Predator interference**: predators in close proximity reduce each other's hunting effectiveness.
- **Cross-band misses**: prey that escape into a different depth band survive even at close 2D range.

These create a negative feedback loop: predator success reduces prey density, which makes predation harder and costlier, which reduces predator reproduction, which allows prey to recover.

## Why Prey Can Boom, Crash, or Stabilize

- **Boom**: when food is abundant and predation is light, prey reproduce rapidly and population grows.
- **Crash**: when predators are numerous and food cycles enter famine, prey face simultaneous predation and starvation.
- **Stabilize**: when predator and prey populations are balanced, prey losses to predation approximately equal prey births.

## Depth Bands and Cross-Band Misses

Predator-prey mode has three depth bands: **Surface**, **Mid**, and **Deep**.

Depth bands are an internal ecological dimension, not separate screen layers. The only visual hints are subtle brightness, tint, scale, and food glow differences.

When a predator reaches contact range but the prey is in another band, that is a **cross-band miss**. The HUD reports recent cross-band misses so you can tell whether depth is protecting prey.

## Scarcity, Food Cycles, and Zones

**Scarcity**: when prey are scarce, predators pay extra energy costs, creating hard selection pressure against predator overpopulation.

**Food cycles**: the sinusoidal food cycle alternates feast and famine phases. Feast phases allow rapid prey reproduction. Famine phases stress both species but tend to remove weaker organisms first.

**Zones**: five environmental zone types provide energy cost modifiers based on trait profiles. A predator in a hunting ground pays less energy there. A prey organism in a warm vent pays less.

**Movement costs**: energy cost scales with speed, size, and longevity. Movement cost is the main constraint that prevents any one trait from increasing without limit.

## What Makes an Organism Predator or Prey

In predator_prey mode, species is a role assigned at birth based on the `aggression` trait. If aggression is above 0.5, the creature is born a predator. If below 0.5, it is born prey.

An offspring can be born a different species than its parent if the mutation shifts aggression across the 0.5 boundary. A cosmic ray mutation can also flip a living creature's species mid-life.

## Game Over and Adaptive Tuning

If predators or prey remain at zero long enough to exceed the configured extinction grace window, the run freezes and shows a red **GAME OVER** overlay. The default hold is 10 seconds. Press `Space` to skip the countdown and restart immediately.

Adaptive tuning exists in the codebase but is disabled by the committed default config. When enabled, the system can compare bounded ecological dial changes across repeated runs.

The settings overlay includes **Reset Predator-Prey Dials** when predator-prey mode is active. It restores ecological dial values to their baseline, clears survival/tuning history, and starts a fresh predator-prey run.