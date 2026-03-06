# M5 Spec, Constrained Depth-Layer Model

## Purpose

Introduce a bounded ecological depth axis that creates new forms of niche differentiation and predator-prey strategy without turning the project into a 3D engine or a rendering-led milestone.

This milestone is an ecological expansion first. Rendering support exists only to preserve legibility of the new ecological state.

## Goals

1. Add a bounded depth state or trait to the simulation.
2. Make at least one meaningful ecological pressure depth-dependent.
3. Make detection and predation interactions depth-aware.
4. Allow lineage-level specialization by depth preference or tolerance to emerge or at least become representable.
5. Preserve readability with simple rendering support for depth.

## Why this milestone exists now

The roadmap and implementation program place depth after fixed-step integrity, headroom and observability, imperfect sensing, persistence, and richer observability. M5 is the next major simulation expansion, not a cleanup pass and not a UI pass.

The intent is to add a new ecological axis for coexistence and strategy divergence while keeping the world visually legible and architecturally bounded.

## In-scope work

The first implementation of M5 should be intentionally narrow.

### Required scope

- Add a bounded depth representation for relevant world entities.
  - This may be a continuous bounded scalar or a small set of discrete bands.
  - The implementation should choose the simpler option that fits the existing code architecture with the least disruption.
- Add depth-aware ecological interaction rules for at least:
  - resource access or availability
  - predator-prey detection and or attack success
- Add a depth preference, tolerance, or comfort concept that can influence behavior and can be inherited or lineage-associated if the current genome model supports that without architectural breakage.
- Add simple readable rendering support so depth is visible enough for manual review.
  - Examples: band tinting, brightness scaling, silhouette size bias, or a compact overlay.
  - This must remain secondary to ecology.
- Extend persistence only as needed so the new depth state resumes correctly through the existing snapshot path.
- Extend observability only as needed to verify that depth is producing ecological differentiation.

### Preferred first-version ecological shape

Unless the repository audit strongly contradicts this, the coding agent should prefer the smallest coherent version below:

- creature depth as a bounded scalar or banded state
- food or hazard distribution varying by depth
- detection or attack success reduced by cross-depth separation
- inherited or mutating preferred depth band or tolerance
- minimal depth readout in existing observability artifacts

## Non-goals

This milestone must not turn into any of the following:

- full 3D movement or volumetric world simulation
- camera systems, parallax systems, or perspective-heavy presentation work
- renderer overhaul or major visual polish pass
- reopening M4 as a rich in-game analysis UI effort
- save/load UX redesign from the settings menu
- fullscreen/windowed mode fixes
- broad species-system redesign unless depth implementation is impossible without a tiny local adjustment
- broad retuning of all ecology knobs across every mode
- benchmark or performance optimization work beyond what is needed to keep M5 measurable and stable

## Invariants

- Simulation truth remains primary over visual flair.
- M5 must remain legible in a 2D presentation.
- Existing non-depth modes and behaviors should remain stable unless the spec explicitly says otherwise.
- New depth state must round-trip through existing persistence if the affected mode supports persistence.
- Any added observability should reuse existing observability and artifact patterns where practical.
- Acceptance must verify real ecological use of depth, not merely existence of a new field.

## Scope boundary decisions

Because the roadmap language allows multiple forms of depth, this spec chooses bounded simplicity first.

### Decision 1, depth model

Prefer discrete depth bands over continuous free-depth movement unless the repository already has a natural scalar state and using it is clearly lower risk.

Reason:
- easier persistence
- easier observability
- easier rendering legibility
- lower interaction-surface risk
- more bounded acceptance checks

### Decision 2, ecological pressure

Require at least one of these and prefer exactly one or two in the first version:
- resource layering by depth
- hazard or comfort band by depth
- predation or detection penalty across depth separation

Reason:
Depth should create ecological tension, not just another coordinate.

### Decision 3, inheritance

If the current genome and mutation model can absorb one bounded depth preference or tolerance trait locally, do that. If not, use a lighter lineage-associated or agent-local preference for the first version and stop rather than redesigning the genome system.

### Decision 4, rendering

Use the smallest existing render seam that can make depth readable. Do not introduce speculative presentation systems.

## Affected subsystems

Repository audit should confirm exact files, but M5 is expected to touch only a bounded subset of these areas:

- world state and entity state
- genome or trait model, if a local inheritable depth preference is feasible
- sensing and target selection logic
- predation or attack-resolution logic
- food, hazard, or zone logic
- persistence snapshot serialization and load paths
- observability or analysis artifact generation
- rendering presentation of creature or world depth
- tests, milestone runner wiring, and acceptance artifacts

## Hidden dependencies to audit before implementation

The coding agent must inspect these before Pass C:

1. Whether imperfect sensing already exists as a reusable seam that depth can modulate.
2. Whether zone state already provides a clean place to attach depth-dependent resources or comfort.
3. Whether persistence serializes creature-local and world-local trait extensions cleanly.
4. Whether observability artifacts already have a schema that can accept depth summaries without breaking prior assumptions.
5. Whether the renderer has a cheap existing hook for a small depth cue.
6. Whether active simulation modes share enough logic that M5 should target one mode first rather than all modes at once.

## Recommended targeting rule

If repository audit shows mode architectures differ materially, M5 should target the mode where predator-prey and resource ecology are already richest, almost certainly predator_prey, and avoid forcing depth into every sim mode in the first pass.

Only generalize across multiple modes if the existing architecture already makes it cheap and low risk.

## Acceptance shape

M5 acceptance should prove four things:

1. the new depth model exists in simulation state
2. it materially affects ecological interaction outcomes
3. it persists through save/load where applicable
4. it is observable enough to review for stratification or specialization

## Testing and measurement plan

Acceptance and tests should include:

- unit tests for depth bounds and update rules
- unit tests for depth-aware detection or predation logic
- unit tests for depth-layered resource or comfort logic
- snapshot round-trip tests for new depth state
- one bounded scenario run that emits a structured artifact proving depth summaries are present
- one comparison or invariant test showing same-seed runs are deterministic or tightly bounded under the existing project standard

## Review questions

These remain required at review even if automated checks pass:

1. Does depth create actual ecological tension, or merely carry a field with no meaningful behavioral consequence?
2. Is rendering support merely explanatory, or has it started to drive the milestone?
3. Did the implementation stay bounded to one clean ecological slice, or did it smuggle in broader biology redesign?
4. Does persistence resume depth state without hidden discontinuities?
5. Is depth legible enough to inspect without becoming a presentation side project?

## Rollback and containment notes

If M5 reveals broad architectural contradictions, stop after scaffold or spec refinement rather than improvising. In particular, halt if any of the following become necessary:

- broad world-coordinate refactor across the entire sim
- broad renderer architecture rewrite
- snapshot schema redesign beyond local field additions
- species-system redesign as a prerequisite for depth
- forced cross-mode generalization with duplicated logic and unclear ownership

## Milestone-specific stop conditions

Pass B or C must halt and report instead of improvising if:

- the only viable implementation appears to require full 3D coordinates or a major movement-model rewrite
- persistence cannot absorb depth without broad snapshot format redesign
- observability cannot show depth effects without reopening M4-level dashboard work
- predator-prey logic and resource logic are too fragmented to modify without a broad architecture merge
- mode coverage is genuinely contradictory and no single-mode bounded slice exists

