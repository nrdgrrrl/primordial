# Milestone M3.5: Simulation Persistence, Save, and Resume

## Summary

Status: implemented for bounded review

Milestone M3.5 adds a first-version world snapshot system for the authoritative simulation state. The implementation is intentionally narrow: save the world, load it back, rebuild transient state, and resume normal simulation stepping without introducing replay, renderer persistence, or broad state redesign.

## Current State

The current repository has one coherent world owner: [`primordial/simulation/simulation.py`](/home/victoria/projects/primordial/primordial/simulation/simulation.py). `Simulation` owns the mutable world state that affects future evolution:

- living creatures
- food particles
- zones and their strengths
- generation and birth/death counters
- the food-cycle frame counter
- lineage allocator state
- mode-specific continuity state such as boid flock derivation inputs and creature motion internals

The renderer reads simulation state but also stores its own transient state in rendering-only structures. Some renderer-facing fields also exist on simulation objects:

- `Creature.trail`
- `Creature.rotation_angle`
- `Creature.glyph_surface`
- `Creature._glyph_phase`
- `Food.twinkle_phase`
- simulation event queues such as `death_events`, `birth_events`, `cosmic_ray_events`, and `active_attacks`

Those fields are reconstructible or purely visual and must not define the save boundary for M3.5.

## Chosen Bounded Implementation Interpretation

M3.5 is implemented as:

1. a single JSON world snapshot format with explicit `version`
2. a dedicated simulation persistence module
3. save to disk and load from disk
4. explicit load-time rebuilding of derived/transient state
5. startup/bootstrap support for `new world` vs `load world`
6. save-on-exit CLI plumbing without renderer-state persistence

This remains snapshot persistence, not replay.

## M3.5 Scope / Non-Goals

### In scope

- authoritative world snapshot persistence
- versioned save format
- save/load entry points
- resume through the normal `Simulation.step()` flow
- restoration of continuity-critical counters and RNG state
- rebuilding derived boid flock state and other transient caches on load

### Out of scope

- replay or history systems
- renderer/HUD/window/fullscreen persistence
- animation/trail/particle persistence
- depth-layer work
- ecology retuning unrelated to persistence correctness
- migration machinery beyond explicit version rejection

## Audit Facts

### Authoritative state confirmed in code

- `Simulation.width` / `Simulation.height`
- `Simulation.creatures`
- `Simulation.food_manager.particles`
- `Simulation.zone_manager.global_strength` and `Simulation.zone_manager.zones`
- `Simulation.generation`
- `Simulation.total_births`
- `Simulation.total_deaths`
- `Simulation._frame`
- `Simulation._next_lineage_id`
- global RNG state from Python `random`
- per-creature motion internals:
  - `_swim_phase`
  - `_dart_burst_remaining`
  - `_dart_cooldown`
- per-creature biological/ecological state:
  - position
  - velocity
  - energy
  - age
  - lineage ID
  - species
  - genome

### Derived or transient state rebuilt on load

- food spatial buckets
- boids flock assignments and `_flock_sizes` / `_flock_count`
- creature trails
- cached glyph surfaces
- glyph pulse phase
- rotation angle
- simulation event queues
- render-only food twinkle phase

### State audited and deliberately not persisted

- `Simulation.paused`
  Reason: runtime control state, not world continuity
- `Simulation._old_age_lifespans`
  Reason: historical HUD metric, not future simulation behavior
- renderer animation manager state, HUD state, ambient particles, screen state

### Existing serialization patterns reused

- JSON is already the project’s machine-readable format for benchmark output and milestone acceptance.
- `tools/run_milestone.py` already supports JSON-compatible YAML acceptance payloads.

### Startup / bootstrap seam

The application bootstrap lives in [`primordial/main.py`](/home/victoria/projects/primordial/primordial/main.py). M3.5 adds the new-world vs load-world decision there, before the runtime loop begins.

## Affected Files / Subsystems

- [`primordial/simulation/simulation.py`](/home/victoria/projects/primordial/primordial/simulation/simulation.py)
- [`primordial/simulation/food.py`](/home/victoria/projects/primordial/primordial/simulation/food.py)
- [`primordial/simulation/persistence.py`](/home/victoria/projects/primordial/primordial/simulation/persistence.py)
- [`primordial/simulation/__init__.py`](/home/victoria/projects/primordial/primordial/simulation/__init__.py)
- [`primordial/main.py`](/home/victoria/projects/primordial/primordial/main.py)
- [`primordial/utils/cli.py`](/home/victoria/projects/primordial/primordial/utils/cli.py)
- [`tests/test_simulation_persistence.py`](/home/victoria/projects/primordial/tests/test_simulation_persistence.py)
- [`tools/persistence_check.py`](/home/victoria/projects/primordial/tools/persistence_check.py)

## Risks / Drift Traps

1. Forgetting hidden motion state such as swim or dart timers would make resume visually plausible but behaviorally wrong.
2. Omitting RNG state would break continuity after load because simulation uses Python `random` heavily.
3. Persisting renderer queues or cached glyphs would expand the boundary incorrectly.
4. Letting load silently accept mismatched world dimensions would produce an invalid resume path.
5. Reworking the simulation core to isolate RNG further would drift beyond M3.5.

## Proposed Acceptance Shape

Acceptance should verify:

- `docs/spec_M3_5.md` exists
- `docs/acceptance_M3_5.yaml` exists
- focused persistence tests pass
- a repository-local persistence probe can:
  - create a world
  - save it
  - load it
  - confirm round-trip equality
  - confirm resumed stepping equality
- the saved JSON has explicit `version`
- the saved JSON contains authoritative sections for settings, counters, creatures, food, zones, and RNG
- the probe confirms renderer/transient fields are omitted

## Recommended Pass A / B / C Plan

### Pass A

- verify the persistence boundary and hidden state
- confirm the bootstrap seam in `primordial/main.py`
- define acceptance around real saved payloads and deterministic resume checks

### Pass B

- add a dedicated persistence module
- add empty-world construction and derived-state rebuild hooks
- add load/save CLI plumbing and milestone probe tooling

### Pass C

- serialize authoritative world state
- restore counters, allocators, world geometry, and RNG
- rebuild derived/transient state on load
- add focused tests and milestone acceptance
- verify end to end

## Milestone Shape

M3.5 should remain one milestone.

Internal execution can still be understood as two bounded workstreams:

- save/load format and bootstrap plumbing
- continuity-critical state coverage and resume verification

## Rejected Alternative Interpretations

### Full replay/history system

Deferred to later observability work. M3.5 persists world state, not event history.

### Persist all visual state

Deferred because trails, particles, HUD state, cached glyphs, and window state are reconstructible or cosmetic.

### Migration framework beyond version 1

Deferred because explicit version tagging plus clear rejection is sufficient for the first real format.

### Persistence plus ecology redesign

Deferred because persistence correctness can be satisfied without retuning M3 behavior.

## Exact Stop Conditions For Pass B/C

Halt instead of improvising if any of the following becomes true:

1. faithful resume requires renderer-owned state
2. more hidden mutable simulation state appears that cannot be enumerated confidently
3. load requires replay/event-log reconstruction instead of snapshot restoration
4. bootstrap support requires major loop or renderer redesign
5. version 1 support unexpectedly requires migration machinery
6. acceptance can only prove file load, not resumed simulation equivalence
7. the work begins touching M4/M5 surfaces
8. roadmap/program assumptions are contradicted by the live codebase

## Concrete Repo Facts For `docs/acceptance_M3_5.yaml`

- persistence tests live at [`tests/test_simulation_persistence.py`](/home/victoria/projects/primordial/tests/test_simulation_persistence.py)
- the acceptance runner supports `command`, `file_exists`, and `json_assert`
- a repo-local probe script can emit:
  - `build/milestones/M3_5/world_snapshot.json`
  - `build/milestones/M3_5/persistence_check.json`
- the save artifact top-level shape is:
  - `version`
  - `metadata.kind`
  - `world`
- continuity-critical JSON sections are:
  - `world.settings`
  - `world.counters`
  - `world.creatures`
  - `world.food`
  - `world.zones`
  - `world.rng_state`

# M3.5 Closeout

  Status: Closed

  Basis:

  - automated acceptance and regression verification passed for the bounded save/load/resume implementation
  - manual review confirmed the milestone intent is present: versioned world-snapshot persistence for authoritative simulation state, load-time rebuild of transient state, and resume
    through normal simulation flow
  - remaining issues are deferred follow-up items outside M3.5 scope, not blockers to closing the milestone

  What was verified automatically:

  - the M3.5 acceptance file passed, including snapshot artifact shape checks and the repo-local save/load/resume probe
  - the automated test suite passed, including focused persistence tests and added direct save/load/resume coverage for predator_prey
  - explicit snapshot error handling was verified for both normal load and early snapshot dimension inspection paths

  What was verified manually:

  - the implementation remained within M3.5 scope and did not expand into replay/history, renderer-state persistence, migration machinery, or unrelated simulation redesign
  - the persisted boundary matches milestone intent: authoritative simulation state is saved, while transient and derived state is rebuilt on load
  - practical in-app save/load from the settings menu was not verified as complete for M3.5 and is not part of this closeout

  Deferred follow-up items:

  - practical in-app save/load from the settings menu remains a separate post-M3.5 usability task
  - the known fullscreen/windowed-mode bug remains open and is not part of M3.5 closure
  - compatibility work beyond the first explicit snapshot version remains deferred beyond M3.5
