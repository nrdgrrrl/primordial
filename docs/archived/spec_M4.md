# Milestone M4: Rich Observability and Analysis Tooling

## Summary

Status: Pass A contract drafted from code audit

Milestone M4 adds Tier 2 observability as a bounded, artifact-first analysis layer on
top of the existing simulation, benchmark, and persistence foundations. The goal is
to make long-run ecosystem histories inspectable and comparable without turning M4
into renderer replay, save-system redesign, or broad runtime UI work.

## Milestone Intent

M4 exists to answer higher-order ecology questions that Tier 1 observability could
not answer on its own:

- are lineages actually diverging over time
- are different seeded runs producing meaningfully different histories
- are zone-mediated pressures sustaining distinct occupancy patterns
- is the ecosystem collapsing into one dominant strategy or maintaining variety

The milestone should do that with bounded run artifacts and comparison reports,
not by redesigning the live runtime or persistence architecture.

## Current State

The repository already has three important M4 prerequisites in place.

### 1. Stable Tier 1 observability core already exists

[`primordial/simulation/simulation.py`](/home/victoria/projects/primordial/primordial/simulation/simulation.py)
exposes `build_observability_snapshot()` with a shared core:

- `population`
- `lineages`
- `strategies`
- `zone_occupancy`

Mode-gated optional sections already exist:

- `species` for `predator_prey`
- `flocks` for `boids`

That boundary is already exercised by
[`tests/test_benchmark_observability.py`](/home/victoria/projects/primordial/tests/test_benchmark_observability.py).

### 2. Representative seeded benchmark scenarios already exist

[`primordial/benchmarking.py`](/home/victoria/projects/primordial/primordial/benchmarking.py)
already defines representative scenarios with explicit seeds:

- `energy_medium`
- `predator_prey_medium`
- `boids_dense`

Those scenarios already produce machine-readable JSON output with stable scenario and
performance metadata plus the shared observability core.

### 3. Versioned world snapshots already exist, but only for resume

[`primordial/simulation/persistence.py`](/home/victoria/projects/primordial/primordial/simulation/persistence.py)
provides versioned world snapshots for save/load/resume and captures RNG state.
That boundary is intentionally authoritative-world persistence, not replay history.

M4 can reuse the fact that the project now has a disciplined machine-readable state
boundary, but it must not turn snapshot persistence into a replay database.

## Goals

- add a bounded run-history artifact format for seeded analysis runs
- add a seeded comparison harness that can generate machine-readable reports
- add lineage-history and zone-history summaries derived from sampled run history
- add the smallest useful artifact inspection surface needed to review M4 outputs
- preserve existing benchmark and snapshot behavior while reusing their proven seams

## Chosen Bounded Implementation Interpretation

M4 should be implemented as one milestone with four internal workstreams:

### M4-A: History / replay artifacts

Record sampled simulation-history artifacts from seeded offline runs. This is replay
of structured observability history, not replay of renderer frames or transient
visual state.

### M4-B: Seeded comparison harness and reports

Run the same bounded scenario with explicit seeds and emit comparison reports that
can answer whether two histories are identical, drifted, or diverged in specific
summary dimensions.

### M4-C: Lineage and zone-history analysis

Track history over time for:

- active lineage count
- leading lineage sizes or shares
- zone occupancy over sampled time
- strategy ratios over sampled time

Mode-specific sections may extend that history where they already exist in the live
 observability surface.

### M4-D: Minimal viewer / dashboard

Provide only a minimal artifact inspection surface, preferably offline and
machine-friendly. A small CLI summary or artifact-inspection command is acceptable.
A broad in-app dashboard or settings/HUD rewrite is not.

## Explicit In-Scope Work

- offline seeded analysis runs driven by repository-local commands
- JSON history artifacts with a stable core shape
- JSON comparison reports derived from two history artifacts or two seeded runs
- derived lineage-history and zone-history summaries
- deterministic or tightly bounded same-seed verification for the offline harness
- focused tests and milestone acceptance for artifact shape and comparison behavior

## Explicit Non-Goals

- full renderer-state replay
- save/load redesign
- replay persistence built on full world snapshots every frame
- broad HUD, settings overlay, or menu work
- richer fullscreen/window handling
- M5 depth-layer mechanics or rendering
- ecology retuning except for strictly necessary exposure of already-existing state
- general-purpose analytics platform work

## Sequencing Rationale

M4 comes after M3.5 because:

- Tier 1 observability is already in place from M2
- ecology signals are richer after M3
- persistence boundaries are now explicit after M3.5

That means M4 should capitalize on these seams, not reopen them:

- reuse existing observability summaries instead of redefining them
- reuse seeded scenario conventions instead of inventing unrelated scenario systems
- reuse the snapshot lesson that authoritative simulation state and transient
  renderer state must stay separate

## Invariants

- simulation stepping remains authoritative; M4 only observes or derives artifacts
- existing benchmark JSON shape remains valid for its current consumers
- snapshot save/load remains a resume boundary, not a replay/history store
- M4 artifacts must be producible through repository-local commands
- same-seed offline analysis runs must be deterministic or the milestone must stop
- mode-specific observability remains mode-gated rather than becoming a mixed schema
- M4 must not require renderer-owned state to understand sampled simulation history

## Affected Files / Subsystems To Inspect

- [`primordial/simulation/simulation.py`](/home/victoria/projects/primordial/primordial/simulation/simulation.py)
- [`primordial/benchmarking.py`](/home/victoria/projects/primordial/primordial/benchmarking.py)
- [`primordial/simulation/persistence.py`](/home/victoria/projects/primordial/primordial/simulation/persistence.py)
- [`tools/benchmark.py`](/home/victoria/projects/primordial/tools/benchmark.py)
- [`tools/persistence_check.py`](/home/victoria/projects/primordial/tools/persistence_check.py)
- [`tools/run_milestone.py`](/home/victoria/projects/primordial/tools/run_milestone.py)
- [`tests/test_benchmark_observability.py`](/home/victoria/projects/primordial/tests/test_benchmark_observability.py)
- new M4 analysis/report tools and focused tests

Runtime rendering surfaces are deliberately not primary M4 targets:

- [`primordial/main.py`](/home/victoria/projects/primordial/primordial/main.py)
- [`primordial/rendering/hud.py`](/home/victoria/projects/primordial/primordial/rendering/hud.py)
- [`primordial/rendering/settings_overlay.py`](/home/victoria/projects/primordial/primordial/rendering/settings_overlay.py)

If M4 starts depending materially on those runtime UI surfaces, scope has drifted.

## Audit Facts That Shape M4

### Existing observability boundary is present but shallow

The current observability snapshot is summary-only and present-focused. It does not
store history. M4 therefore needs sampled history capture, but it does not need
simulation ownership redesign to get it.

### Existing benchmark harness already has seeded, representative scenarios

The benchmark layer proves there is already a stable repository-local path for:

- applying scenario-specific settings
- seeding runs
- emitting machine-readable JSON

M4 should extend this pattern rather than introducing a separate orchestration model.

### Existing persistence boundary is useful but must not be repurposed

M3.5 snapshots prove that authoritative state can be serialized faithfully.
However, using snapshots as high-frequency replay frames would expand M3.5 into an
unbounded replay database. M4 should prefer slim sampled history artifacts instead.

### No existing analysis viewer or dashboard subsystem exists

The live code has a runtime HUD and settings overlay, but no analysis dashboard,
artifact browser, replay viewer, or report UI. A bounded M4 therefore favors an
offline inspector over in-app dashboard work.

### Seed plumbing appears trustworthy enough to validate, not assume

The simulation and persistence code use Python `random`, benchmarks seed it
explicitly, and M3.5 already relies on RNG-state continuity. That is enough to try a
deterministic seeded analysis harness, but M4 must verify same-seed repeatability in
tests instead of assuming it.

## Risks / Drift Traps

1. Treating replay as renderer replay would force M4 into visual-state persistence.
2. Using full world snapshots as the history format would silently redesign M3.5.
3. Building a runtime dashboard would broaden M4 into UI work with weak acceptance.
4. Adding many new observability dimensions would turn M4 into a generic analytics stack.
5. Assuming determinism without proving same-seed repeatability would make seeded comparison untrustworthy.
6. Reworking simulation ownership to expose history would be broader than M4 needs.
7. Mixing M5 concepts such as depth into history artifacts would distort milestone order.

## Rejected Alternative Interpretations

### Full visual replay system

Rejected for M4 because the current codebase has no renderer-state replay seam and
the roadmap explicitly separated M3.5 snapshot persistence from replay/history.

### Snapshot-per-frame replay archive

Rejected because it would expand save/load into a de facto replay database and
increase storage, schema, and acceptance complexity without being required to answer
the milestone’s ecology questions.

### Broad in-app dashboards

Rejected because there is no existing dashboard framework and building one would
shift effort from analysis correctness into UI surface area.

### Generic analytics platform

Rejected because M4 only needs bounded history capture, comparison, and inspection
for current sim modes.

## Acceptance Shape

Acceptance should verify:

- `docs/spec_M4.md` exists
- `docs/acceptance_M4.yaml` exists
- focused M4 analysis tests pass
- a repo-local history tool can emit at least one seeded history artifact
- a repo-local comparison tool can emit at least one comparison report
- history artifacts have a stable shared core shape
- comparison reports prove same-seed repeatability for the bounded harness
- manual review confirms the implementation stayed artifact-first and did not drift
  into renderer replay, save-system redesign, or broad UI work

## Review Gates / Manual Review Questions

- Does the implementation answer M4 questions through bounded history artifacts and reports?
- Did any part of the work start depending on renderer-owned state?
- Did the milestone remain usable across the major active sim modes without inventing mode-specific contracts everywhere?
- Is the minimal inspection surface sufficient to review artifacts without becoming a UI side project?

## Recommended Pass A / B / C Plan

### Pass A

- confirm the artifact boundary and same-seed trust assumptions
- define the stable shared history and comparison-report shapes
- define explicit anti-drift boundaries around replay, persistence, and UI

### Pass B

- add the analysis-run and comparison scaffolding
- add stable artifact builders and focused tests for output shape
- add acceptance commands and JSON assertions

### Pass C

- implement sampled history capture
- implement lineage and zone-history summaries
- implement seeded comparison reporting
- implement the minimal artifact inspection surface
- run focused tests and milestone acceptance

## Milestone Shape

M4 should remain one milestone.

The four internal workstreams above are execution structure only. They are not
permission to split the roadmap into extra milestones or to advance later roadmap
items early.

## Exact Stop Conditions For Pass B/C

Halt instead of improvising if any of the following becomes true:

1. there is no stable offline run-artifact boundary and creating one requires major simulation-loop restructuring
2. useful replay requires renderer-state capture or full visual-state persistence
3. seeded comparison is not trustworthy because same-seed repeatability cannot be demonstrated
4. lineage history or zone history cannot be extracted without redesigning core state ownership
5. the only viable implementation path expands save/load into a de facto replay database
6. the minimal artifact inspector turns into a broad UI rewrite
7. observability output cannot support a stable cross-mode history contract
8. the work starts depending on M5 concepts
9. acceptance cannot be expressed mostly through repo-local commands plus explicit manual review gates
10. roadmap or implementation-program intent is contradicted by the live codebase

# Milestone 4 Closeout

Status: Closed

Basis:
- automated acceptance and tests pass
- manual review confirms the milestone intent is present and good enough for this milestone
- remaining concerns are deferred items, not blockers to milestone completion

What was verified automatically:
- M4 spec and acceptance artifacts were created and accepted by the milestone runner
- offline history artifacts were generated successfully for energy_medium, predator_prey_medium, and boids_dense
- same-seed comparison reporting and minimal artifact inspection passed automated tests and milestone acceptance

What was verified manually:
- M4 remained artifact-first Tier 2 observability and did not become renderer replay
- M4 did not expand the M3.5 snapshot boundary into replay storage or save-system redesign
- M4 did not drift into broad runtime dashboard/UI work or M5 depth-related scope

Deferred follow-up items:
- richer in-app dashboards or visual replay tooling, if still desired later
- any broader analysis/reporting UX beyond the bounded CLI inspector
- future Tier 2 or Tier 3 observability extensions that may be justified by later milestones