# Reading Creatures

## The Meaning of Organism Appearance

Creature visuals are not hand-drawn sprites. Each creature's glyph is procedurally generated entirely from its genome. The same genome always produces the same glyph. Related creatures look related. Mutations produce similar but distinct offspring.

## What You Can Infer

| Visual feature | Determined by | What it tells you |
|---------------|---------------|-------------------|
| **Hue/color** | `hue`, plus predator species tint | Approximate lineage family |
| **Saturation/intensity** | `saturation` | Vividness; desaturation also signals aging |
| **Size** | `size` (4-12 px radius) | Body size; also affected by depth band |
| **Complexity** | `complexity` (2-7 strokes) | Stroke count in the glyph |
| **Symmetry type** | `symmetry` | Asymmetric / bilateral / 3-fold / 4-fold radial |
| **Stroke delicacy** | `stroke_scale` | Compact tight strokes vs. spread-out fine strokes |
| **Appendages** | `appendages` (0-4) | Extra limb-like strokes radiating outward |
| **Rotation** | `rotation_speed` | How fast the glyph body spins |
| **Motion style** | `motion_style` | Glide / swim / dart (visible in trail length and pattern) |
| **Aging** | Computed from age / max_lifespan | Grey overlay increases after 70% of max lifespan |
| **Kin lines** | Shared lineage_id | Faint threads between nearby same-lineage creatures |
| **Territory shimmer** | Top 3 dominant lineages | Soft pulsing glow at lineage centroids |

## What Is Hidden

| Mechanism | Why it is invisible |
|-----------|-------------------|
| **Energy level** | Not drawn on creatures. Use the HUD or Inspect Mode |
| **Sensing range** | Not drawn. A creature may be starving because it cannot sense nearby food |
| **Depth band** | Only hinted by subtle brightness/size differences |
| **Death cause** | Same dissolution animation for starvation, predation, and old age |
| **Reproductive readiness** | Not shown. A creature at 0.79 energy looks the same as one at 0.81 |
| **Gene flow between species** | Not signaled visually beyond the predator tint |

## Limits of Visual Inference

- Some important traits are not directly visible. A creature that looks healthy may be one frame from starvation.
- Visual traits may drift neutrally. Glyph complexity, symmetry, and appendage count are not under selection pressure. A lineage drifting toward more complex glyphs over 500 generations does not mean complexity is adaptive.
- Predator/prey color conventions can become less reliable over time. Species is assigned by aggression, not by hue.
- Not every visual change means adaptive advantage. Visual change is evidence of inheritance and mutation, not evidence of adaptation.

## How to Watch Evolution Happen

### Over seconds
Watch individual creatures move, eat, and avoid each other. Notice their motion styles: gliders leave long smooth trails, swimmers undulate, darters sit still and then burst. Notice the food cycle bar in the HUD. A white ring briefly expanding around a creature is a cosmic ray mutation.

### Over minutes (10-30 minutes)
Look for glyph family divergence. After 5-10 minutes, distinct visual clans emerge that share symmetry type, stroke style, and general glyph shape. In predator_prey mode, watch the population counts oscillate in the HUD. Watch territory shimmer centroids drift toward favorable zones.

### Over long runs (hours)
Population-level trait averages shift directionally. Lineages spread and disappear. Extinction events in predator_prey mode can reset the system, but not immediately. If a species hits zero, the simulation enters a grace window where recovery through mutation-driven species switching is still possible. Only if the zero state persists for the full grace window does the run end. In drift mode, all traits drift without direction — pure neutral evolution.

### Why the HUD helps
The simulation hides energy levels, sensing ranges, reproductive readiness, death causes, and trait distributions inside its internal state. The HUD exposes key aggregates. For understanding what is actually happening, the HUD is essential. The visual field is atmospheric and meaningful, but it is incomplete.