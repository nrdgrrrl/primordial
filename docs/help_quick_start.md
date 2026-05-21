# Quick Start

Primordial is a living screensaver: a dark ocean-like world filled with glowing creatures that move, eat, reproduce, mutate, and die. Each creature has a small genome that affects how it moves, what it can sense, how efficiently it uses energy, how long it lives, and how its glowing glyph looks.

The simulation is not a biological model of real ocean life. It is a compact artificial ecosystem designed to make selection, drift, population cycles, and lineage change visible enough to watch.

## What You See On Screen

The default ocean theme draws:

- **Creatures** as glowing procedural glyphs
- **Food** as small cyan particles
- **Trails** behind moving creatures
- **Kin lines** between nearby related creatures, when enabled
- **Territory shimmer** around dominant lineages, when enabled
- **Environmental zones** as faint colored regions
- **Attack lines** for predator kills
- **Birth and death animations** when creatures appear or dissolve
- **Cosmic ray rings** when a living creature receives a spontaneous mutation

Predators have a warm species tint in predator-prey mode, while prey generally read cooler. The `P` highlight key makes predators much easier to find in dense scenes.

## Basic Controls

| Key | Action |
| --- | --- |
| `Esc` / `Q` | Quit |
| `H` | Open in-app Help |
| `U` | Toggle HUD (heads-up display) |
| `S` | Open or close Settings |
| `Space` | Pause/unpause, or skip predator-prey game-over countdown |
| `F` | Toggle fullscreen/windowed |
| `R` | Reset the current simulation run |
| `I` | Toggle Inspect Mode |
| `M` | In Inspect Mode, switch between pause and slow motion |
| `D` | In Inspect Mode, toggle compact/detailed card |
| mouse click | In Inspect Mode, select a creature |
| hold `P` | Highlight predators |
| `+` / `=` | Increase food spawn rate |
| `-` / `_` | Decrease food spawn rate |

Move the mouse during normal playback to reveal a temporary bottom action bar with the current runtime shortcuts.

## How to Read the HUD

Press `U` to show or hide the HUD. In predator-prey mode, it shows:

- predator and prey counts
- average actual speed for each role
- recent kills and cross-band misses
- simulation ticks and current run seed
- current survival ticks, rolling median, and recent best survival
- danger/grace status if a role has hit zero
- dominant zone
- mode, theme, FPS, and food-cycle bar

The HUD is the best way to understand what is happening mechanically. The screensaver view is intentionally quieter and more atmospheric.