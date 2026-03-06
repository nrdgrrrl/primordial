# Milestone 3: Ecology Deepening and Imperfect Sensing

## Purpose

Milestone 3 deepens the existing ecology by making local information imperfect and by making existing zones matter more behaviorally. The milestone is intentionally narrow.

The goal is not to add more traits or more simulation surface area. The goal is to create stronger ecological tension so the current world has a better chance of producing durable branching, niche differentiation, and strategy-level divergence.

This milestone uses the M2 benchmark and observability baseline as its measurement base. It does not replace that baseline.

## Goals

- Add one shared imperfect-sensing model for `energy` and `predator_prey` decision paths.
- Make existing zones affect sensing quality so niches become more behaviorally meaningful.
- Add one modest differentiation improvement so lineage branching is less purely hue-driven.
- Preserve the fixed-step loop, the current benchmark scenarios, and the M2 shared observability core.

## Chosen Bounded Interpretation

This milestone is implemented as:

1. shared imperfect sensing for food seeking, predator pursuit, and prey fleeing
2. zone-mediated sensing quality using existing zone types
3. a small sensing tradeoff using the existing `sense_radius` trait
4. a modest lineage-branching improvement using existing ecological traits

This milestone is explicitly bounded to `energy` and `predator_prey` behavior changes. `boids` remains a regression-check scenario, not a redesign target.

## In Scope

### 1. Shared imperfect sensing

Add one shared sensing helper used by the main `energy` and `predator_prey` target-acquisition paths.

The helper should introduce:

- distance-based sensing reliability decay
- noisy target estimates instead of perfect target positions

The helper should be used for:

- food seeking
- predator hunting prey
- prey detecting predators
- energy-mode creature hunting

### 2. Zone-mediated niche effects

Reuse the existing zones as sensing environments rather than adding new world layers.

The intended ecological effect is:

- clearer open hunting in `open_water` and `hunting_ground`
- more refuge and misdetection in `kelp_forest` and `deep_trench`

This should remain a bounded modifier on sensing quality, not a geometry-heavy visibility system.

### 3. Stronger tradeoff using existing traits

Use the existing `sense_radius` trait to impose a modest sensing upkeep cost in the modes affected by M3.

This exists to prevent stronger sensing from becoming a universal winner.

### 4. Modest differentiation improvement

Improve lineage splitting so it can reflect meaningful ecological-trait divergence in addition to hue divergence.

This should remain small and use existing traits such as:

- `speed`
- `sense_radius`
- `aggression`
- `efficiency`
- `longevity`

This is not a full species system.

## Non-Goals

- adding several new heritable traits
- a full species or taxonomy system
- depth-layer or line-of-sight geometry work
- persistence, save, load, or resume work
- rich dashboards, new observability platforms, or replay tooling
- broad boids redesign
- large ecology rewrites or multi-milestone redesign
- knob proliferation without clear ecological rationale

## Invariants

- fixed-step simulation behavior must remain intact
- rendering still occurs once per outer frame
- the M2 benchmark scenarios remain representative:
  - `energy_medium`
  - `predator_prey_medium`
  - `boids_dense`
- the M2 shared observability core remains present:
  - `population`
  - `lineages`
  - `strategies`
  - `zone_occupancy`
- mode-gated optional observability remains intact:
  - `species` only for `predator_prey`
  - `flocks` only for `boids`

## Anti-Drift Constraints

- Do not add a new benchmark framework.
- Do not replace or widen M2 observability unless a minimal additive field is strictly necessary.
- Do not add more than one new behavioral abstraction layer if existing code can support the change.
- Do not redesign `boids` to match the new sensing model.
- Do not turn zone effects into cover geometry, ray-casting, or proto-depth logic.
- Do not treat lineage count alone as proof of ecological branching.

## Affected Subsystems

- `primordial/simulation/simulation.py`
- `primordial/simulation/creature.py`
- `primordial/simulation/zones.py`
- `primordial/benchmarking.py`
- `tests/test_benchmark_observability.py`
- new focused ecology/sensing tests

## Acceptance Shape

Milestone 3 is complete when:

```bash
python tools/run_milestone.py docs/acceptance_M3.yaml
```

passes and the human review items below are satisfied.

The acceptance file should verify:

- existing regressions still pass
- focused ecology/sensing tests exist and pass
- `energy_medium` and `predator_prey_medium` still run and emit the M2 shared observability core
- `boids_dense` still runs as a regression scenario
- mode-gated optional observability sections remain properly bounded

It should not try to prove long-run ecological success through flaky numeric thresholds.

## Testing and Measurement Plan

- Add deterministic unit or integration tests for sensing reliability, sensing noise, and zone sensing modifiers.
- Add deterministic tests for lineage branching from ecological-trait divergence.
- Keep M2 benchmark shape tests intact.
- Re-run the bounded benchmark scenarios after implementation.

## Required Human Review Items

These remain mandatory because they are important but not safely reducible to a fast automated gate:

- In seeded runs, do obscuring zones visibly create more refuge or missed pursuit than open zones?
- Does imperfect sensing create believable missed detections or wasted pursuit rather than random chaos?
- Does the lineage branching change appear less purely cosmetic than hue-only branching?
- Did the implementation remain bounded to sensing, niche effects, and modest differentiation rather than expanding into later-milestone work?

## Stop Conditions

Pass B or Pass C must halt and report instead of improvising if:

- implementation pressure requires more than one new genome trait
- the work requires changing fixed-step loop semantics or render cadence behavior
- the change requires rich new observability or dashboard work to validate success
- the change requires persistence, replay, or save-state work
- zone effects start requiring geometry-heavy visibility logic or depth-like behavior
- the sensing change cannot be shared across the targeted `energy` and `predator_prey` paths without a larger architecture rewrite
- benchmark verification appears to require flaky ecological outcome thresholds rather than bounded correctness and regression checks
- `boids` would need comparable redesign to remain coherent

## M3 Closeout
Status: closed

Reason:
- bounded M3 implementation is complete
- automated acceptance passes
- manual review confirms zone-mediated behavior differences are present and good enough for this milestone
- remaining work is tuning / future observability, not required for M3 completion

Deferred:
- further ecology tuning
- richer HUD / observability
- fullscreen toggle bug
- boids performance investigation