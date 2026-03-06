# IMPLEMENTATION_PROGRAM.md

## Purpose

This document translates the long-range roadmap into an execution structure that an AI coding agent can work from safely.

The roadmap is the strategic north star. It explains what matters, what order matters, and what the project should avoid doing too early.

This implementation program is different. It exists to:
- break the roadmap into bounded milestones
- define what each milestone is trying to accomplish
- define what each milestone must not accidentally turn into
- create a repeatable path from strategy to spec to task files
- reduce the risk of an AI agent making broad speculative changes

This project combines performance engineering, architecture work, simulation design, and long-horizon ecological goals. That makes it especially important not to jump straight from vision to implementation tickets.

The intended workflow is:

**Roadmap -> Implementation Program -> Milestone Spec -> Task Files -> Code Changes**

Do not skip the spec layer.

---

## Development Principles

Every milestone and every task should respect these principles.

### 1. Protect simulation integrity first
Rendering load must not change the history of the simulation. The world must advance according to simulation rules, not according to frame pacing pressure.

### 2. Prefer bounded change over ambitious rewrite
This project already has meaningful structure and working behavior. Most milestones should be implemented as targeted, minimally invasive improvements.

### 3. Separate architecture work from ecology work
Do not mix major loop/control-flow changes with ecological design changes in the same task set unless there is a compelling reason.

### 4. Make success measurable
Every milestone should define how it will be validated. “Runs successfully” is not enough.

### 5. Keep future milestones flexible
Only the next milestone should be fully decomposed into task files. Later milestones should remain at program/spec level until earlier work is complete.

### 6. Avoid accidental side projects
An AI agent should not be allowed to “helpfully” rewrite unrelated systems, rename broad surfaces, or perform cleanup that is not required by the current spec.

---

## Milestone Structure

Each milestone should have its own detailed spec file before task files are generated.

Recommended naming convention:
- `SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md`
- `SPEC_M2_HEADROOM_AND_LIGHT_OBSERVABILITY.md`
- `SPEC_M3_ECOLOGY_DEEPENING_AND_IMPERFECT_SENSING.md`
- `SPEC_M3_5_SIMULATION_PERSISTENCE.md`
- `SPEC_M4_RICH_OBSERVABILITY_AND_ANALYSIS.md`
- `SPEC_M5_DEPTH_LAYER_MODEL.md`

Each spec should define:
- objective
- non-goals
- invariants
- affected subsystems
- risks
- implementation boundaries
- acceptance criteria
- testing and measurement plan
- rollback or containment notes

---

## Program Overview

## Milestone 1: Fixed-Step Simulation and Core Instrumentation

### Goal
Decouple simulation cadence from render cadence and establish measurement of where time is actually being spent.

### Why it comes first
If rendering load changes the simulation’s effective history, then long-run ecological behavior cannot be trusted.

### Expected outputs
- fixed-step simulation loop
- variable-rate rendering
- clean sim/update/render timing instrumentation
- initial frame pacing telemetry
- hard caps or guardrails for worst visual spikes if needed for stability

### Must not turn into
- a renderer rewrite
- ecology changes
- speculative multithreading
- broad UI cleanup

### Success looks like
- simulation progression no longer depends on render cadence
- timing breakdown is available and trustworthy
- benchmark runs can distinguish sim cost from render cost

---

## Milestone 2: Headroom and Lightweight Observability

### Goal
Buy near-term performance headroom and introduce lightweight ecology telemetry before tradeoff-heavy ecology work begins.

### Expected outputs
- early render-cost governance
- possibly GPU-assisted or more efficient render paths for high-cost visual systems
- possibly one targeted compiled/native simulation hotspot if measurement supports it
- Tier 1 ecological telemetry

### Tier 1 telemetry should include
- lineage divergence summaries
- phenotype cluster summaries
- strategy ratio logging
- simple zone occupancy summaries
- comparable machine-readable logs per run

### Must not turn into
- full dashboard work
- full replay tooling
- open-ended optimization without measurement

### Success looks like
- more headroom is available for future ecological work
- ecological changes in later milestones can be measured rather than guessed

---

## Milestone 3: Ecology Deepening and Imperfect Sensing

### Goal
Increase the system’s capacity for durable branching, niche differentiation, and strategy-level divergence.

### Expected outputs
- stronger ecological tradeoffs
- sharper niche structure
- temporal environmental variation where appropriate
- improved species or lineage differentiation logic
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

---

## Milestone 3.5: Simulation Persistence, Save and Resume

### Goal
Allow the world to persist across sessions as simulation history accumulates.

### Expected outputs
- versioned save format
- simulation-state serialization and loading
- resume capability
- deliberate omission of transient renderer-state persistence in the first version

### Must not turn into
- full replay system
- renderer-state snapshotting
- aggressive schema complexity before first save format exists

### Success looks like
- a world can be resumed without breaking ecological continuity
- save format is explicit and versioned

---

## Milestone 4: Rich Observability and Analysis Tooling

### Goal
Add deeper tooling for interpretation, comparison, and long-run understanding of the ecosystem.

### Expected outputs
- replay tooling
- seeded comparison harnesses and reports
- richer dashboards and ecology visualizations
- lineage history and zone occupancy analysis

### Must not turn into
- premature analysis tooling before the ecosystem is interesting enough to study

### Success looks like
- the system supports structured comparison and interpretation of ecological histories

---

## Milestone 5: Constrained Depth Layer Model

### Goal
Introduce a bounded ecological depth axis to create new forms of niche differentiation and predator/prey strategy without leaping to full 3D.

### Expected outputs
- bounded depth state or trait
- depth-dependent resources, hazards, or comfort ranges
- depth-aware detection and predation interactions
- lineage specialization by depth preference or tolerance
- simple readable rendering support for depth

### Must not turn into
- full 3D engine work
- 2.5D visual polish as the primary goal
- speculative camera or rendering overhauls before ecological value is proven

### Success looks like
- depth creates real new ecological structure rather than just extra coordinates

---

## Standard AI Agent Workflow

For each milestone, use a three-pass process.

### Pass A: Audit and Design
The agent reads the relevant code and produces:
- affected files
- current control flow
- hidden dependencies
- risks and edge cases
- recommended implementation shape
- test and measurement plan

No code changes in this pass.

### Pass B: Scaffolding
The agent adds only the structural changes needed to support the milestone.
Examples:
- interfaces
- config flags
- instrumentation hooks
- adapters
- abstractions
- test harness support

Still not the full feature.

### Pass C: Implementation
The agent implements the actual behavior inside the approved scaffold.

This keeps the agent from making large speculative changes before the structure is understood.

---

## How to Ask ChatGPT for Later Steps

When a future milestone is ready, do not ask for “the next tasks” in the abstract.

Instead, use this sequence:

1. Provide the current roadmap and implementation program.
2. Provide the milestone spec that is now in focus.
3. Ask ChatGPT to produce one of the following, explicitly:
   - an audit/design brief
   - a scaffolding plan
   - task files for implementation
4. Tell ChatGPT which pass you are on: A, B, or C.
5. Tell ChatGPT to stay within the current milestone only.

### Suggested prompt template for later milestones

```text
We are working from these project documents:
- roadmap
- IMPLEMENTATION_PROGRAM.md
- [current milestone spec]

We are currently on Pass [A/B/C] for [milestone name].

Your job is to work only within that milestone.
Do not redesign later milestones.
Do not mix unrelated refactors into this work.
Preserve existing behavior unless the spec explicitly allows change.
Prefer minimal invasive changes.

Deliver:
1. A short summary of the milestone objective.
2. A list of affected files/subsystems.
3. Risks and hidden dependencies.
4. A bounded plan for this pass only.
5. Validation steps and measurements.

If the work appears to require broader architectural change than the spec allows, stop and say so instead of improvising.
```

---

## How to Ask an AI Agent to Create Task Files

Task files should be created from a milestone spec, not directly from the roadmap.

### Rules for task file generation
- generate task files only for the current milestone
- tasks must be small and reviewable
- each task must touch a narrow surface area
- each task must have explicit validation steps
- do not create mega-tasks like “implement phase 2”
- separate scaffolding tasks from behavior tasks
- include rollback or containment notes where appropriate

### Suggested prompt for task-file generation

```text
Use the attached project documents and create implementation task files for the current milestone only.

Inputs:
- roadmap
- IMPLEMENTATION_PROGRAM.md
- [current milestone spec]

Requirements:
- Create small, bounded task files.
- Each task file must have: title, purpose, scope, files/subsystems affected, implementation notes, validation steps, and out-of-scope notes.
- Separate audit/scaffolding/implementation work where appropriate.
- Do not include tasks for later milestones.
- Do not collapse the milestone into one giant task.
- Prefer tasks that can be implemented and reviewed independently.
- If a task would require broad uncertain redesign, flag it instead of pretending it is straightforward.

Output format:
- First, provide a milestone decomposition summary.
- Then provide a recommended task order.
- Then produce one markdown task file per task.
```

### Recommended task file naming convention
- `TASK_M1_01_LOOP_AUDIT.md`
- `TASK_M1_02_FIXED_STEP_SCAFFOLD.md`
- `TASK_M1_03_TIMING_INSTRUMENTATION.md`
- `TASK_M1_04_MAIN_LOOP_INTEGRATION.md`
- `TASK_M1_05_VALIDATION_AND_BENCHMARK.md`

Adjust naming to match the actual milestone.

---

## Review Gate Before Starting the Next Milestone

Before moving to the next milestone, confirm:
- acceptance criteria for the current milestone were actually met
- validation results were captured
- any temporary flags or experimental code were either removed or deliberately retained
- the next milestone spec still matches reality after the changes made

If the previous milestone changed assumptions materially, update the implementation program and milestone specs before creating more task files.

---

## Final Guidance

This project should be developed as a guided sequence of bounded architectural and ecological steps, not as a single open-ended optimization campaign.

The implementation program exists to keep AI agents useful without letting them quietly take over the design.

Use the roadmap for direction.
Use the implementation program for sequencing.
Use milestone specs for constraints.
Use task files for execution.

