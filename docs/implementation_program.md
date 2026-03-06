# IMPLEMENTATION_PROGRAM.md

## Purpose

This document defines the development process for the project.

The roadmap explains long-term direction. This implementation program explains how work is planned, executed, and verified milestone by milestone.

The process is intentionally small:
- minimal documents
- explicit milestone state
- automated verification
- simple instructions that AI coding agents can follow without improvising a separate workflow

## Core Workflow

Every milestone uses exactly three core artifacts:

1. `spec.md`
   Human-readable milestone definition.
   It explains goals, scope, non-goals, invariants, and implementation boundaries.

2. `acceptance.yaml`
   Machine-readable completion contract.
   It defines the checks that must pass before the milestone is considered complete.

3. `tools/run_milestone.py`
   Milestone runner.
   It executes the checks, reports pass/fail status, and identifies missing work.

Milestone state is therefore not tracked in scattered notes or task files. A milestone is complete when:

```bash
python tools/run_milestone.py
```

reports that all checks pass.

## Development Principles

### 1. Protect simulation integrity first

Rendering pressure must not silently rewrite simulation history.

### 2. Prefer bounded change over broad rewrite

Milestones should stay small enough to review, test, and revert if needed.

### 3. Make success machine-verifiable

If completion cannot be checked by the runner, the milestone is underspecified.

### 4. Keep milestone scope narrow

Do not mix architecture work, ecology redesign, rendering experiments, and observability expansion in one milestone unless the spec explicitly requires it.

### 5. Prefer repository-local automation

Acceptance checks should use commands and outputs that can run inside this repository without a large external framework.

### 6. Make meaningful git commits as work progresses

Agents should not accumulate the entire milestone into one unstructured working tree change.

Use meaningful, reviewable commits for coherent chunks of progress, such as:
- benchmark harness added
- observability summary output added
- hotspot optimization implemented
- acceptance checks updated

Commits should reflect real milestones within the work, not noise like formatting-only snapshots unless formatting is the actual change being made.

## Milestone Artifact Structure

Use these repository paths:

- `docs/spec_M<N>.md`
- `docs/acceptance_M<N>.yaml`
- `tools/run_milestone.py`

The acceptance files use a small JSON-compatible YAML subset so the runner can remain stdlib-only and easy to operate.

Each spec should include:
- purpose
- goals
- in-scope work
- non-goals
- acceptance shape
- implementation guidance
- exit criteria

Each acceptance file should include:
- milestone metadata
- check list
- commands
- required files
- JSON assertions
- thresholds and invariants where relevant

## Acceptance Check Model

The current runner supports a deliberately small set of check types:

- `command`
  Run a shell command and verify exit code and optional stdout content.

- `file_exists`
  Require that a path exists.

- `json_assert`
  Load a JSON file and assert required fields and thresholds.

Keep acceptance definitions simple. If a milestone needs a new kind of verification, prefer expressing it through a repository-local command first. Extend the runner only when the new check type clearly improves reuse.

## Agent Execution Rules

When working a milestone, an agent should:

1. Read the current spec and acceptance file first.
2. Treat the acceptance file as the completion contract.
3. Implement the smallest coherent change that moves checks toward green.
4. Add or update automated tests as part of the milestone, not afterward.
5. Run `python tools/run_milestone.py` before declaring completion.
6. Make meaningful git commits as coherent chunks of work land.
7. Avoid unrelated cleanup and speculative refactors.

The agent should not invent task files, pass structures, or prompt workflows unless the repository explicitly reintroduces them later.

## How to Create a New Milestone

When starting a new milestone:

1. Choose the next milestone identifier.
   Example: `M3`

2. Create the spec.
   Path: `docs/spec_M3.md`

3. Create the acceptance file.
   Path: `docs/acceptance_M3.yaml`

4. Define the milestone in terms of verifiable outcomes.
   Good checks:
   - unit or integration tests
   - benchmark commands
   - required artifact generation
   - JSON field assertions
   - numeric thresholds with explicit bounds

5. Prefer checks that can run unattended.
   Avoid milestone definitions that depend on manual observation as the primary completion signal.

6. Implement the code and tests until the runner passes.

7. Update this implementation program only if the workflow itself has changed.

## How to Choose Good Acceptance Checks

Good acceptance checks are:
- fast enough to run regularly
- specific enough to fail usefully
- stable enough to avoid flaky milestone state
- close to user-facing or milestone-facing outcomes

Avoid checks that are:
- vague
- purely stylistic
- dependent on manual interpretation
- too broad to diagnose when they fail

For performance milestones, prefer:
- bounded benchmark scripts
- structured JSON summaries
- explicit thresholds such as mean frame time, p95 frame time, clamp counts, or event counts

For correctness milestones, prefer:
- focused unit/integration tests
- invariant checks on structured output
- deterministic or tightly bounded comparisons

## Current Milestone Sequence

### Milestone 1

Fixed-step simulation and core timing instrumentation.

### Milestone 2

Performance headroom and lightweight observability.

### Milestone 3

Ecology deepening and imperfect sensing.

### Milestone 3.5

Simulation persistence, save, and resume.

### Milestone 4

Richer observability and analysis tooling.

### Milestone 5

Constrained depth-layer ecological model.

This sequence is directional, not rigid. If completed work changes the right order, update the specs and acceptance files to reflect reality.

## Final Rule

The milestone runner is the source of truth for milestone status.

If the spec says something is important but `python tools/run_milestone.py` cannot detect whether it is done, the milestone definition is incomplete and should be tightened before more implementation work begins.
