# Predator-Prey

## Predator-Prey Overview

Predator-prey mode creates two roles:

- **Prey** search for food and flee predators.
- **Predators** hunt prey and may forage when they are not actively hunting.

The default run starts with a larger prey population and a smaller predator population. Predators start at 12% of the initial population. From there, the balance changes continuously as creatures eat, reproduce, starve, hunt, mutate, and die.

Predator-prey mode also adds an abstract vertical layer called **depth bands**. Creatures are drawn on a flat 2D screen, but internally they can occupy surface, mid, or deep water. Predators can only kill prey on contact when both are in the same band.

## How Predators Behave

A predator scans for the nearest prey within its sensing range. When it detects prey, it steers toward it and tries to match its depth band. Simple epistasis can bend that sensing and contact quality: large fast predators tend to handle contact better but pay more to move, while depth specialists sense best in-band and worse across bands.

**Kill on contact**: when the predator and prey are close enough and in the same depth band, the predator kills the prey. Kill energy gain is capped.

**Depth tracking**: predators probabilistically shift depth toward the band their target prey occupies. A predator can only kill prey in the same depth band. Reaching a prey in 2D but in the wrong band is a **cross-band miss**.

**Foraging**: when a predator is not actively hunting, it can forage for food with predator-specific efficiency and cost rules. However, predator reproduction requires recent animal energy, so kills remain essential for population growth.

**Satiety**: after a kill, the predator enters a brief satiety period with reduced hunting sense.

**Interference**: predators near other predators suffer reduced hunting effectiveness, preventing predator swarms from wiping out local prey instantly.

**Movement cost**: predators pay a metabolic premium on movement. When prey are scarce (below 15% of population), predators pay additional scarcity penalty energy costs.

## How Prey Behave

Prey search for nearby food within their current depth band. If food is unavailable in their band, they may shift toward another band where food is present. Small fast prey, asymmetric darters, and appendage-rich bodies can gain modest fleeing advantages, while specialized depth morphs tend to read their home band better than other bands.

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

**Movement costs**: energy cost scales with speed, size, longevity, and simple eco-morphological epistasis. Fast heavy bodies, ornate high-sense bodies, and draggy appendage-rich bodies all pay more than their raw traits alone would imply.

## What to Watch For

- **Swift-small prey** that react early and turn away quickly but are weak contact attackers.
- **Heavy hunters** that win contact more reliably but burn energy fast if they stay large and quick.
- **Sensory specialists** that read prey or food well but pay more upkeep.
- **Depth specialists** that dominate one band while missing more across bands.
- **Efficient gliders** with symmetric, low-drag bodies that save on movement cost.
- **Evasive darters** with small, asymmetric, burst-motion bodies that flee more effectively.

Use **Inspect Mode** (press `I`, then click a creature) to see any creature's **body plan** bucket and **key effect** phrase. Press `D` to toggle detail mode, which shows the full set of effective phenotype modifiers (speed, move cost, metabolism, sensing, food efficiency, reproduction threshold, contact quality, flee agility, depth transition, in-band/cross-band sensing). Predators show contact quality prominently; prey show flee agility. When epistasis is disabled, the card shows "Epistasis disabled" instead of modifier values.

## What Makes an Organism Predator or Prey

In predator_prey mode, species is a role determined by the `aggression` trait using hysteresis thresholds. A prey creature whose aggression reaches `prey_to_predator_aggression_threshold` (default 0.30) becomes a predator. A predator whose aggression drops below `predator_to_prey_aggression_threshold` (default 0.20) becomes prey. Unknown species fall back to 0.5.

An offspring can be born a different species than its parent if the mutation shifts aggression across the relevant hysteresis threshold. A cosmic ray mutation can also flip a living creature's species mid-life.

## Game Over and Adaptive Tuning

If predators or prey hit zero, predator_prey enters an extinction grace window. The simulation continues while zero ticks are counted. If the species recovers through mutation-driven species switching before the grace window expires, the run continues. If the zero state persists for `extinction_grace_ticks` (default 7200), the run freezes and shows a red **GAME OVER** overlay. The default hold is 10 seconds. Press `Space` to skip the countdown and restart immediately.

When predators hit zero, existing predator lineages are biologically gone. During the grace window, the remaining prey population continues to live, mutate, reproduce, and evolve. New predators can reappear if prey offspring or living prey cross the predator threshold through mutation or cosmic ray species flip. If `GAME OVER` occurs, the living world's biological history is reset on restart.

Adaptive tuning exists in the codebase but is disabled by the committed default config. When enabled, the system can compare bounded ecological dial changes across repeated runs.

The settings overlay includes **Reset Predator-Prey Dials** when predator-prey mode is active. It restores ecological dial values to their baseline, clears survival/tuning history, and starts a fresh predator-prey run.
