# Primordial Roadmap

Primordial is a fullscreen evolutionary screensaver: a beautiful ambient world
whose visuals are meant to be the visible trace of real simulation state.

The project is trying to become two things at once:

1. a mesmerizing bioluminescent display;
2. a richer artificial ecosystem where lineages, niches, and population
   histories matter.

The guiding principle remains:

**Protect simulation truth, spend rendering budget artistically.**

## Current Foundation

The project has moved beyond the original early roadmap. The current foundation
includes:

- decoupled simulation and rendering;
- fixed-step simulation timing;
- pygame and GPU renderer paths;
- spatial bucketing for food, creatures, and interaction queries;
- genome-driven creatures with heritable motion, ecology, visual, and depth
  traits;
- four implemented simulation modes: `energy`, `predator_prey`, `boids`, and
  `drift`;
- a production ocean theme plus placeholder/stub visual themes;
- predator-prey depth bands, food cycles, zones, collapse/game-over, optional
  adaptive tuning, and run logging;
- versioned world snapshots and predator-prey tuning-state persistence;
- HUDs, inspect mode, benchmark/probe tooling, and observability snapshots;
- a redesigned categorized settings overlay with mouse support, cursor handling,
  action buttons, and modular metadata/layout/navigation/runtime action code;
- refreshed current-state architecture and predator-prey user documentation.

This foundation enables the next phase: making the existing system easier for a
normal user to understand.

## Completed or Repositioned Roadmap Items

| Earlier Roadmap Item | Current Decision |
| --- | --- |
| Fixed-step simulation and timing instrumentation | Complete. Keep protecting this invariant. |
| Early render/headroom work | Mostly complete. Continue only with measurement-backed targeted work. |
| Lightweight observability | Partially complete. HUDs, logs, probes, and snapshots exist; richer visual interpretation remains future work. |
| Ecology deepening / imperfect sensing | Partially complete. Predator-prey already has imperfect sensing, zones, food cycles, role pressure, and dials. More strategy diversity remains valid. |
| Simulation persistence | Complete as first version. Future work should be schema evolution and UX around save/load, not initial design. |
| Constrained depth layer | Complete as first ecological version. Future work is readability and deeper depth-specialization, not introducing depth from scratch. |
| Settings overlay polish | Complete for current needs. Future settings work should extend the refactored modules rather than rewrite the overlay. |
| Current-state docs refresh | Complete. The human guide is now source material for in-app help. |

## Near-Term Roadmap

### 1. In-App Documentation / Help Browser

The next user-facing priority is to bring documentation into the app.

The current Guide action opens `docs/predator_prey_system_guide.md` in an
external browser. That works, but it interrupts the screensaver and leaves help
outside the simulation experience. The refreshed guide should become the source
for an in-app help browser.

Desired shape:

- load or parse documentation from docs files;
- organize content by Markdown headings or a simple section model;
- show section navigation, a readable content area, search, and scrolling;
- support mouse and keyboard;
- reuse the ocean/bioluminescent visual language of the settings overlay;
- remain separate from settings overlay internals;
- keep content out of renderer code;
- leave room for future mode-specific help sections.

First version should prioritize wrapped text, section navigation, scrolling, and
search. It should not attempt a full Markdown renderer unless the simpler model
proves inadequate.

### 2. In-Game Tutorial / Onboarding Flow

After the help browser, add a guided tutorial that introduces Primordial from
inside the running app.

The tutorial should run on first launch, be forceable from the command line for
developers/testers, and eventually be launchable from in-app help/settings.

It should explain:

- what Primordial is;
- basic controls;
- settings and help access;
- pause, fullscreen/windowed, HUD, and reset behavior;
- mouse and keyboard basics;
- predators, prey, food, glyphs, trails, births, deaths, lineages, zones, depth
  bands, food cycles, game over, adaptive tuning, and evolution at a user level;
- what is currently hard to see or hidden.

The first version should be linear and data-driven. Tutorial steps should define
title, text, highlight target, paused/running behavior, and optional action
requirements. Do not build complex missions or scoring in the first version.

### 3. Richer Observability and Evolution Readability

Once users can access help and onboarding, return to the visibility gaps called
out by the guide:

- evolution is hard to see;
- depth bands are subtle;
- kills are easy to miss;
- death cause is not visible;
- zone pressure is real but hidden;
- trait trends are not visible in-app.

This phase should add observability that answers concrete questions. Examples:

- Are prey becoming faster?
- Are predators improving hunting efficiency?
- Which lineages are growing or collapsing?
- Which deaths are starvation, predation, or old age?
- Are depth bands actually protecting prey?

Avoid vague dashboard work. Each visualization should justify itself by making a
currently hidden mechanic understandable.

## Mid-Term Roadmap

### Deeper Ecology and Strategy Diversity

The older ecology goals still matter, but they should come after help/tutorial
and clearer observability.

Useful directions:

- stronger tradeoffs so one trait bundle does not dominate everywhere;
- sharper niches around zones, food availability, depth, and role pressure;
- better species or lineage concepts based on sustained functional divergence;
- temporal environmental variation that changes pressure without making the
  world unreadable;
- sensing variations that create meaningful strategy differences.

The goal is not more knobs. The goal is more durable ways to live.

### Depth Readability and Specialization

Depth already exists. Future depth work should focus on making it legible and
ecologically meaningful:

- clearer but still subtle depth cues;
- better explanation in help/tutorial;
- observability for cross-band misses and depth occupancy;
- stronger specialization around depth preferences only if measurements show it
  improves coexistence or strategy diversity.

### Persistence and Long-Run Experience

Snapshots and tuning-state persistence exist. Future work can improve the user
experience around them:

- clearer save/load UI;
- snapshot status and path clarity;
- compatibility handling for future schema versions;
- optional startup resume behavior if it fits screensaver expectations.

Do not turn this into replay tooling unless that becomes a separate milestone.

## Long-Term Roadmap

### Rich Analysis and Replay

Longer-term observability can grow into seeded comparisons, replay-like
inspection, richer reports, and lineage history views. This should wait until
the user-facing help/tutorial layer and simpler in-app observability are in
place.

Questions this work should answer:

- Are lineages diverging in meaningful ways?
- Do niches persist or collapse?
- Which ecological pressures changed a run's outcome?
- Are adaptive tuning decisions improving stability or only shifting failure
  modes?

### More Expressive Evolution

If the current trait space becomes too narrow, future work may add more
expressive phenotype or behavior systems. That should be driven by observed
limitations, not by a desire to add complexity.

Possible long-term directions:

- strategy-level behavior variation;
- reproductive isolation or richer species concepts;
- more structured resource ecology;
- new modes or themes that preserve the simulation/render boundary.

### Larger Architecture Changes

Major process separation, native simulation kernels, or larger renderer
unification should remain measurement-driven. Do not start with threads as a
generic performance fix. Prefer targeted acceleration of proven hotspots and
clear state boundaries.

## What Future Agents Should Avoid

- Do not undo the recent modular settings overlay structure.
- Do not put help-browser or tutorial logic into `settings_overlay.py`.
- Do not hardcode large documentation strings into rendering code.
- Do not make `main.py` own detailed overlay behavior.
- Do not use world-coordinate transforms for UI hit testing.
- Do not show the OS cursor during normal simulation playback unless an
  interactive UI is active.
- Do not break keyboard support while adding mouse support.
- Do not treat future help/tutorial work as a reason to build a broad UI
  framework.
- Do not add ecology knobs without a clear selective pressure and validation
  story.

## Current Priority Order

1. Build an in-app documentation/help browser from the refreshed guide.
2. Build a simple first-launch tutorial/onboarding flow.
3. Add focused observability that makes hidden evolution/ecology legible.
4. Revisit deeper ecology and strategy diversity.
5. Consider richer analysis/replay and larger architecture changes only when
   measurement and user needs justify them.

The project is most compelling when the beauty on screen corresponds to a real
world underneath. The next step is making that world understandable without
leaving the app.
