# IMPLEMENTATION_PROGRAM.md

## Purpose

This document translates the roadmap into a development process that an AI coding agent can follow without quietly taking over the design.

The roadmap remains the strategic north star. It explains what matters, why the order matters, and what should not be done too early.

This implementation program exists to:

- turn roadmap direction into bounded milestones
- preserve milestone intent, not just milestone names
- define what each milestone is trying to accomplish
- define what each milestone must not accidentally turn into
- create a repeatable path from strategy to code changes
- support strong automated verification without pretending every important truth is fully automatable
- reduce the risk of broad speculative changes by AI coding agents

This project combines performance engineering, architecture work, simulation design, rendering richness, and long-horizon ecological goals. That makes sequencing important. A milestone can be implemented correctly in local code terms and still be strategically wrong if it breaks the roadmap order or smuggles in later concerns too early.

The intended workflow is:

**Roadmap -> Implementation Program -> Milestone Spec -> Acceptance File -> Runner -> Code Changes**

Do not skip the spec layer.
Do not treat passing checks as permission to ignore the roadmap.

---

## Core Position

The project is trying to protect two things at once:

1. visual spectacle
2. simulation integrity and future evolvability

The governing principle is:

**Protect simulation truth, spend rendering budget artistically.**

That means visual compromise is often acceptable if it protects simulation integrity. The reverse is much more dangerous.

---

## Development Principles

Every milestone and every task should respect these principles.

### 1. Protect simulation integrity first

Rendering pressure must not silently rewrite simulation history. If render load changes what survives, reproduces, or goes extinct, the system is lying about its own rules.

### 2. Prefer bounded change over broad rewrite

The project already has meaningful structure. Most milestones should be implemented as targeted, minimally invasive improvements rather than ambitious rewrites.

### 3. Separate architecture work from ecology work

Do not mix major loop or control-flow changes with ecological redesign in the same milestone unless the spec explicitly requires it.

### 4. Make success measurable

Every milestone must define how it will be validated. “Runs successfully” is not enough.

### 5. Keep future milestones flexible

Only the current milestone should be decomposed into implementation tasks. Later milestones should remain at roadmap or spec level until earlier work is complete and reality has been checked.

### 6. Avoid accidental side projects

An AI agent must not helpfully rewrite unrelated systems, rename broad surfaces, perform generic cleanup, or smuggle later-milestone work into the current milestone.

### 7. Use automation aggressively, but not naively

Automated checks are essential, but not every important design constraint is reducible to a simple pass or fail assertion. Specs and review gates must still encode sequencing, non-goals, and anti-drift rules.

### 8. Preserve long-horizon ecological intent

The aim is not raw complexity, raw agent count, or more knobs. The aim is a richer living system with more durable branching, niche differentiation, and strategy-level divergence.

---

## Milestone Artifact Structure

Each milestone should have its own spec and acceptance file before implementation begins.

Recommended repository paths:

- `docs/spec_M<N>.md`
- `docs/acceptance_M<N>.yaml`
- `tools/run_milestone.py`

Recommended milestone names:

- `M1` Fixed-step simulation and core instrumentation
- `M2` Headroom and lightweight observability
- `M3` Ecology deepening and imperfect sensing
- `M3_5` Simulation persistence, save, and resume
- `M4` Rich observability and analysis tooling
- `M5` Constrained depth-layer model

Each spec should define:

- purpose
- goals
- in-scope work
- non-goals
- invariants
- affected subsystems
- risks and hidden dependencies
- implementation boundaries
- acceptance shape
- testing and measurement plan
- rollback or containment notes
- milestone-specific review questions

Each acceptance file should define a machine-readable completion contract using a small JSON-compatible YAML subset.

It should include:

- milestone metadata
- checks
- commands
- required files
- JSON assertions
- thresholds and invariants where relevant

---

## Acceptance Check Model

The runner should stay deliberately small.

Preferred check styles:

- `command`
  Run a repository-local command and verify exit status and optional output.

- `file_exists`
  Require that a path exists.

- `json_assert`
  Load a JSON artifact and verify required fields, thresholds, or invariants.

Prefer expressing milestone verification through repository-local commands before extending the runner. Extend the runner only when a new check type clearly improves reuse and clarity.

Good acceptance checks are:

- fast enough to run regularly
- specific enough to fail usefully
- stable enough to avoid flaky milestone state
- close to milestone-facing outcomes

Avoid checks that are:

- vague
- purely stylistic
- overly broad and hard to diagnose
- dependent on manual interpretation as the primary completion signal

For performance milestones, prefer:

- bounded benchmark scripts
- structured JSON summaries
- explicit thresholds such as mean frame time, p95 frame time, clamp counts, event counts, or output completeness

For correctness milestones, prefer:

- focused unit and integration tests
- invariant checks on structured output
- deterministic or tightly bounded comparisons

---

## What the Runner Can and Cannot Decide

The runner is the source of truth for milestone status, but not the sole source of truth for project wisdom.

A milestone should not be declared complete unless:

1. `python tools/run_milestone.py` reports all checks passing
2. the work still respects the roadmap order and milestone non-goals
3. no material design drift has been introduced under the cover of passing checks

Important implication:

If the spec says something matters and the runner cannot detect it, either:

- tighten the milestone definition and add a better automated check, or
- record that it remains a required human review gate for that milestone

Do not pretend a subtle design constraint is unimportant merely because it is inconvenient to automate.

---

## Standard Agent Workflow

The default workflow for non-trivial milestones is a three-pass process. This is a recommended default, not empty ceremony.

### Pass A: Audit and Design

The agent reads the relevant code and produces:

- affected files and subsystems
- current control flow
- hidden dependencies
- risks and edge cases
- recommended implementation shape
- testing and measurement plan
- a list of things the milestone must not accidentally turn into

No code changes in this pass.

### Pass B: Scaffolding

The agent adds only structural changes needed to support the milestone.

Examples:

- interfaces
- config flags
- instrumentation hooks
- adapters
- helper extraction for testability
- benchmark or test harness support
- acceptance-file plumbing

Still not the full feature.

### Pass C: Implementation

The agent implements the actual behavior inside the approved scaffold.

This structure exists to reduce the chance of large speculative changes before the shape of the work is understood.

For very small and well-bounded milestones, Pass A and Pass B may be compressed, but only if the spec is already unusually clear and the surface area is genuinely small.

---

## Agent Execution Rules

When working a milestone, an agent should:

1. Read the roadmap, current spec, and acceptance file first.
2. Treat the acceptance file as the completion contract, but not as permission to ignore non-goals.
3. Implement the smallest coherent change that satisfies the milestone.
4. Add or update automated tests as part of the milestone, not afterward.
5. Run `python tools/run_milestone.py` before declaring completion.
6. Make meaningful, reviewable git commits as coherent chunks of progress land.
7. Avoid unrelated cleanup and speculative refactors.
8. Stop and report if the work appears to require broader architectural change than the current spec allows.

Agents should not invent unrelated task hierarchies or broad new workflows unless the repository deliberately chooses to reintroduce them.

---

## How to Create a New Milestone

When starting a new milestone:

1. Choose the next milestone identifier.
2. Create the spec at `docs/spec_M<N>.md`.
3. Create the acceptance file at `docs/acceptance_M<N>.yaml`.
4. Define the milestone in terms of verifiable outcomes.
5. Include explicit non-goals and anti-drift constraints.
6. Include milestone-specific review questions for anything not fully reducible to automated checks.
7. Implement code and tests until the runner passes.
8. Perform the milestone review gate before moving on.

---

## Review Gate Before Starting the Next Milestone

Before moving to the next milestone, confirm:

- acceptance criteria for the current milestone were actually met
- validation results were captured
- any temporary flags or experimental code were either removed or deliberately retained
- profiler or benchmark outputs still make sense for the milestone just completed
- the next milestone spec still matches reality after the changes made
- no new assumptions were introduced that would distort later milestones

If the previous milestone changed assumptions materially, update the implementation program and milestone specs before creating more implementation work.

---

## Program Overview

## Milestone 1: Fixed-Step Simulation and Core Instrumentation

### Goal

Decouple simulation cadence from render cadence and establish trustworthy measurement of where time is actually being spent.

### Why it comes first

If rendering load changes the simulation’s effective history, then long-run ecological behavior cannot be trusted.

### Expected outputs

- fixed-step simulation loop
- variable-rate rendering
- clean simulation, update, render, and pacing instrumentation
- initial frame pacing telemetry
- hard caps or guardrails for catastrophic visual spikes if needed for stability

### Must not turn into

- a renderer rewrite
- ecology changes
- speculative multithreading
- broad UI cleanup

### Success looks like

- simulation progression no longer depends on render cadence
- timing breakdown is available and trustworthy
- benchmark and profile runs can distinguish simulation cost from render cost

---

## Milestone 2: Headroom and Lightweight Observability

### Goal

Buy near-term performance headroom and introduce lightweight ecology telemetry before tradeoff-heavy ecology work begins.

### Why it comes next

If headroom is not created early, future ecology will be shaped by current bottlenecks rather than by design goals. At the same time, ecology changes should not land blind.

### Expected outputs

- early render-cost governance
- rendering acceleration for the highest-value hotspots where measurement supports it
- possibly one targeted compiled or native simulation hotspot if measurement supports it
- Tier 1 ecological telemetry
- run-to-run comparable machine-readable output

### Priority order inside the milestone

1. rendering acceleration first
2. targeted simulation acceleration second, only if measurement still justifies it
3. Tier 1 observability early enough that later ecology work is measurable

### Tier 1 telemetry should include

- lineage divergence summaries or metrics
- phenotype cluster summaries
- strategy ratio logging
- simple zone occupancy summaries
- comparable CSV or JSON logs per run

### Must not turn into

- full dashboard work
- full replay tooling
- open-ended optimization without measurement
- a premature thread-based sim and render split

### Success looks like

- more headroom is available for future ecological work
- ecology changes in later milestones can be measured rather than guessed
- the milestone leaves behind clearer evidence about whether rendering or simulation is the next true bottleneck

---

## Milestone 3: Ecology Deepening and Imperfect Sensing

### Goal

Increase the system’s capacity for durable branching, niche differentiation, and strategy-level divergence.

### Why it comes here

Once simulation truth is protected, there is more headroom, and Tier 1 observability exists, ecology can be deepened with less guesswork and less risk of tuning blind.

### Expected outputs

- stronger ecological tradeoffs
- sharper niche structure
- temporal environmental variation where appropriate
- improved lineage or species differentiation logic
- imperfect sensing mechanisms

### Imperfect sensing directions

- distance-based uncertainty
- directional blind spots
- noisy target estimation
- delayed information refresh
- differentiated sensing quality for food, prey, and predators
- heritable sensing reliability or acuity

### Must not turn into

- a pile of extra knobs with no ecological rationale
- a bundled depth-layer implementation
- rich visualization work unrelated to ecology behavior

### Success looks like

- more stable coexistence of multiple viable strategies
- measurable branching and niche differentiation using Tier 1 telemetry
- changes that create new ecological tension rather than just more parameters

---

## Milestone 3.5: Simulation Persistence, Save and Resume

### Goal

Allow the world to persist across sessions as simulation history accumulates.

### Why it is its own milestone

Persistence has real architectural implications and should not be smuggled in as a side effect of ecology work.

### Expected outputs

- versioned save format
- simulation-state serialization and loading
- resume capability
- deliberate omission of transient renderer-state persistence in the first version

### Likely saved state includes

- creature state and genomes
- lineage and ID allocator state
- food state
- world or zone state that materially affects future evolution
- cycle phases and environmental state
- RNG state if continuity quality matters

### Must not turn into

- full replay system
- renderer-state snapshotting
- aggressive schema complexity before the first save format exists

### Success looks like

- a world can be resumed without breaking ecological continuity
- save format is explicit and versioned

---

## Milestone 4: Rich Observability and Analysis Tooling

### Goal

Add deeper tooling for interpretation, comparison, and long-run understanding of the ecosystem.

### Why it waits until here

Tier 1 observability belongs earlier to support tuning. Richer observability should wait until the ecosystem is mature enough to justify deeper interpretation and comparison tooling.

### Expected outputs

- replay tooling
- seeded comparison harnesses and reports
- richer dashboards and ecology visualizations
- lineage history and zone occupancy analysis

### Must not turn into

- premature analysis tooling before the ecosystem is interesting enough to study

### Success looks like

- the system supports structured comparison and interpretation of ecological histories
- observability answers whether lineages are diverging, niches are persisting, or the ecosystem is collapsing into one dominant strategy

---

## Milestone 5: Constrained Depth-Layer Model

### Goal

Introduce a bounded ecological depth axis that creates new forms of niche differentiation and predator-prey strategy without leaping to full 3D.

### Why it comes after imperfect sensing

Imperfect sensing should be understood on its own first. Depth can then add a new ecological axis without multiplying ambiguity too early.

### Expected outputs

- bounded depth state or trait
- depth-dependent resources, hazards, or comfort ranges
- depth-aware detection and predation interactions
- lineage specialization by depth preference or tolerance
- simple readable rendering support for depth

### Must not turn into

- full 3D engine work
- 2.5D presentation polish as the primary goal
- speculative camera or rendering overhauls before ecological value is proven

### Success looks like

- depth creates real new ecological structure rather than just extra coordinates
- the project gains a new axis for coexistence and strategy divergence without sacrificing legibility

---

## Suggested Prompt Pattern for Future Milestones

```text
We are working from these project documents:
- roadmap.md
- IMPLEMENTATION_PROGRAM.md
- [current milestone spec]
- [current acceptance file]

We are currently on Pass [A/B/C] for [milestone name].

Your job is to work only within that milestone.
Do not redesign later milestones.
Do not mix unrelated refactors into this work.
Preserve existing behavior unless the spec explicitly allows change.
Prefer minimal invasive changes.

Deliver:
1. A short summary of the milestone objective.
2. A list of affected files and subsystems.
3. Risks, hidden dependencies, and edge cases.
4. A bounded plan for this pass only.
5. Validation steps and measurements.
6. Anything the milestone must not accidentally turn into.

If the work appears to require broader architectural change than the spec allows, stop and say so instead of improvising.
```

---

## Final Guidance

This project should be developed as a guided sequence of bounded architectural and ecological steps, not as a single open-ended optimization campaign.

Use the roadmap for direction.
Use the implementation program for sequencing and anti-drift rules.
Use milestone specs for constraints.
Use acceptance files and the runner for verification.
Use human review gates where the project’s deeper intent cannot yet be reduced safely to automation.

