# SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md

## Purpose

This spec defines the first implementation milestone for the simulation project.

Milestone 1 exists to protect simulation integrity before further performance work or ecological expansion begins. The main objective is to ensure that simulation progression is no longer coupled to rendering cadence, and to establish trustworthy instrumentation for measuring where frame time is actually going.

This milestone should be treated as architectural groundwork, not as a broad rewrite.

---

## Objective

Implement a fixed-step simulation loop with variable-rate rendering, and add core instrumentation that cleanly separates simulation time, render time, and frame pacing behavior.

The result should make it possible to answer questions like:
- Is the simulation advancing independently of rendering cost?
- How much time is spent in simulation versus rendering?
- What are the frame-time percentiles under representative workloads?
- Are visual spikes still capable of distorting simulation progression?

---

## Why This Milestone Exists

The project’s long-term goals depend on the ecosystem’s history being driven by simulation rules rather than by rendering pressure.

If heavy rendering slows the world itself, then ecological outcomes become entangled with graphics cost. That makes later evolution work much less trustworthy.

This milestone protects the world from the renderer and creates the measurement foundation for later headroom work.

---

## In-Scope Work

### 1. Main loop restructuring
- Introduce a fixed-step simulation accumulator model.
- Allow simulation to advance in stable increments regardless of render speed.
- Allow rendering to occur at a variable cadence based on available frame time.

### 2. Core timing instrumentation
Add clear timing instrumentation for at least:
- simulation step/update time
- render time
- total frame time
- frame pacing / effective FPS
- number of sim steps executed per rendered frame, where relevant

### 3. Benchmark-friendly measurement output
- Make the timing data accessible to the benchmark workflow.
- Ensure results can be captured in a comparable way across runs.
- Prefer simple structured output over premature dashboards.

### 4. Basic spike protection if required for stability
If there are one or two known catastrophic visual paths that make fixed-step validation hard, it is acceptable to add narrow caps or guards during this milestone, but only if they are needed to preserve loop stability.

Examples:
- extreme pairwise line drawing caps
- reduced update cadence for a specific expensive overlay

These must remain tightly bounded and should not turn into a generalized render optimization pass.

---

## Explicit Non-Goals

This milestone must not become any of the following:

- a renderer rewrite
- GPU rendering work
- ecology or behavior changes
- new species logic
- imperfect sensing
- save/resume
- full observability tooling
- speculative process-split architecture
- broad cleanup or refactoring unrelated to loop timing and measurement
- visual redesign or presentation polishing

If the work appears to require broader architectural changes than this spec allows, that should be reported explicitly instead of silently expanding scope.

---

## Required Invariants

The following must remain true after this milestone.

### Simulation integrity
- Simulation progression must no longer depend directly on render cadence.
- `Simulation.step()` must remain render-agnostic.
- Simulation logic must not begin reaching into renderer-owned state.

### Behavioral containment
- Existing modes should preserve their intended behavior unless a change is strictly required to support fixed-step progression.
- Event semantics must not be silently broken.
- Genome, lineage, and ecological state logic must remain functionally intact.

### Architectural containment
- Fullscreen/screensaver behavior must continue to work.
- Existing benchmark entry points or benchmark workflows must remain functional.
- Asset loading and deployment assumptions must not be casually disturbed.

### Measurement integrity
- Instrumentation must measure the actual loop behavior, not a guessed or synthetic approximation.
- Logging should be cheap enough that it does not meaningfully distort ordinary runs.

---

## Desired Implementation Shape

This section describes the preferred form of the solution without overconstraining internal code decisions.

### Main loop model
Preferred shape:
- accumulate elapsed real time
- execute zero or more fixed-size simulation steps per frame as needed
- render at most once per outer loop iteration
- optionally clamp runaway accumulation to avoid spiral-of-death failure modes

### Timing model
Preferred shape:
- use a consistent monotonic timer source
- measure sim/update, render, and total frame timing separately
- collect rolling stats during runtime
- allow benchmark runs to emit summarized results

### Output model
Preferred shape:
- lightweight in-process counters or summaries
- machine-readable structured output for benchmark capture
- optional simple human-readable console/log summary

Avoid building dashboards in this milestone.

---

## Risks and Failure Modes

### 1. Hidden coupling between simulation and rendering
There may be places where render assumptions are embedded in update flow, timing, event consumption, or animation handling.

### 2. Spiral of death
If rendering becomes too slow and the loop tries to catch up indefinitely, sim-step accumulation can become unstable. A clamp or max-step-per-frame rule may be necessary.

### 3. Instrumentation distortion
Too much logging or too-granular measurement can alter the performance profile of the thing being measured.

### 4. Event timing assumptions
Visual systems or effect queues may assume one update per rendered frame. Those assumptions may need to be surfaced and handled carefully.

### 5. Benchmark ambiguity
If benchmark tooling is not updated to distinguish sim from render cost, this milestone will not deliver its intended value.

---

## Affected Subsystems to Inspect

The agent should begin by auditing at least these categories of code before making loop changes:
- main application loop / game loop / screensaver loop
- simulation stepping entry points
- renderer frame entry points
- event queue ownership and consumption
- animation/effect managers
- benchmarking harness or benchmark runners
- timing/FPS utilities
- any config or mode-specific loop behavior

The audit should identify concrete files before implementation begins.

---

## Acceptance Criteria

Milestone 1 should only be considered complete if all of the following are true.

### Core behavior
- The simulation runs under a fixed-step model.
- Rendering cadence is no longer the direct clock for simulation progression.
- The system remains stable during ordinary interactive/fullscreen use.

### Timing visibility
- Sim time, render time, total frame time, and frame pacing are measurable.
- Benchmark or test runs can report the timing split clearly.
- Results are comparable across runs.

### Stability
- No obvious runaway catch-up behavior under temporary render stalls.
- No major regression in existing startup/fullscreen/saver behavior.
- No major corruption of event-driven visual behavior.

### Containment
- The milestone does not introduce unrelated ecological or rendering feature work.
- The change surface remains bounded and reviewable.

---

## Validation Plan

Validation should include both correctness-oriented checks and measurement-oriented checks.

### Correctness checks
- verify simulation continues progressing correctly when render load changes
- verify application remains stable in normal fullscreen or screensaver operation
- verify event-driven animations still appear and resolve correctly
- verify different simulation modes still run

### Measurement checks
- run representative benchmark scenarios
- capture sim/update time separately from render time
- compare behavior under lighter and heavier visual load
- record frame-time percentiles where practical
- verify that structured output is usable for later comparison

### Suggested comparison scenarios
- moderate population, normal mode
- higher population, visually dense mode
- boids-heavy or interaction-heavy scenario
- headless or minimal-render comparison, if available

The exact scenario list should be refined during the Pass A audit.

---

## Recommended AI Agent Execution Sequence

This milestone should be implemented in three passes.

### Pass A: Audit and Design
Deliverables:
- affected files list
- description of current loop/control flow
- hidden timing or ownership dependencies
- recommended fixed-step design shape
- instrumentation insertion points
- validation plan

No code changes yet.

### Pass B: Scaffolding
Deliverables:
- loop timing abstractions or counters
- config flags if needed
- benchmark output hooks
- minimal structural support for the fixed-step accumulator

Still not the full behavior.

### Pass C: Implementation
Deliverables:
- fixed-step sim loop integration
- variable-rate rendering
- timing summaries wired into benchmark/report path
- any minimal guards needed for stability

---

## Guidance for Task File Generation

Task files for this milestone should be produced from this spec, not from the high-level roadmap.

Recommended shape:
- one audit task
- one scaffolding task for loop restructuring support
- one instrumentation task
- one integration task for fixed-step loop behavior
- one validation and benchmark task

Task files should remain small and independently reviewable.

Do not generate one giant “implement Milestone 1” task.

---

## Suggested Prompt for an AI Agent, Pass A

```text
We are implementing Milestone 1 from the attached spec: SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md.

Work only on Pass A: audit and design.
Do not write code yet.

Your job:
1. Identify the files and subsystems involved in the current loop, simulation stepping, rendering entry points, event consumption, and benchmark flow.
2. Explain the current control flow and where render cadence may currently influence simulation progression.
3. Identify hidden dependencies or risks.
4. Propose a bounded implementation shape for fixed-step simulation with variable-rate rendering.
5. Propose where instrumentation should be inserted.
6. Provide a validation plan.

Constraints:
- Stay within Milestone 1 only.
- Do not redesign later milestones.
- Do not mix in renderer rewrites or ecology changes.
- Preserve existing behavior unless change is required by the spec.
- If required changes seem broader than the spec allows, say so explicitly instead of improvising.
```

---

## Suggested Prompt for Generating Milestone 1 Task Files

```text
Using the attached roadmap, IMPLEMENTATION_PROGRAM.md, and SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md, generate bounded markdown task files for Milestone 1 only.

Requirements:
- Create small, reviewable tasks.
- Separate audit, scaffolding, instrumentation, implementation, and validation work where appropriate.
- Each task file must include: title, purpose, scope, affected files/subsystems, implementation notes, validation steps, and out-of-scope notes.
- Do not include work from later milestones.
- Do not collapse the milestone into one giant task.
- If a task depends on unresolved architectural uncertainty, flag it clearly.

Output:
1. Milestone decomposition summary.
2. Recommended task order.
3. One markdown task file per task.
```

---

## Final Note

This milestone is successful if it makes the simulation trustworthy enough to support everything that comes later.

It is not successful merely because the loop is different.

The point is to ensure that later ecological history belongs to the world itself, not to the renderer.

---

## Pass A Audit Findings

Date of audit: 2026-03-05

Scope of this audit:
- Milestone 1 only
- audit and design only
- no renderer rewrite
- no ecology changes
- no broad cleanup beyond what fixed-step sim and instrumentation strictly require

### 1. Short Summary of Milestone 1

Milestone 1 should decouple simulation advancement from render cadence without rewriting simulation behavior. In the current codebase, the bounded and code-aligned form of this is:
- keep simulation logic on a fixed 60 Hz step
- allow rendering to run at variable cadence
- measure event, sim, render, and pacing costs separately
- preserve current behavior unless the spec requires a change

This is an outer-loop control-flow change plus measurement work. It is not a simulation-internals rewrite.

### 2. Files and Subsystems Involved

Primary runtime entry points:
- `main.py`
- `primordial/main.py`

Simulation stepping and frame-native state:
- `primordial/simulation/simulation.py`
- `primordial/simulation/creature.py`
- `primordial/simulation/food.py`

Rendering and event consumption:
- `primordial/rendering/renderer.py`
- `primordial/rendering/animations.py`
- `primordial/rendering/hud.py`
- `primordial/rendering/settings_overlay.py`

Config and pacing inputs:
- `primordial/config/config.py`
- `config.toml`

Relevant subsystems:
- main application/game loop
- screensaver/preview/fullscreen loop behavior
- simulation stepping entry points
- renderer frame entry point
- simulation event queue ownership and consumption
- render-only animation systems
- timing/FPS utilities
- profile/benchmark-like runtime path

### 3. Current Control Flow

#### Launch flow

Root `main.py` parses screensaver args and runtime args, sets `SDL_WINDOWID` for preview mode before importing the pygame application package, then calls `primordial.main.main(scr_args, runtime_args)`.

#### Main runtime loop

`primordial/main.py` currently runs one outer loop with this shape:
1. poll pygame events once
2. handle screensaver exit, preview behavior, keyboard input, and settings overlay actions
3. update mode-transition fade state
4. call `simulation.step()` exactly once
5. call `renderer.draw(simulation)` exactly once
6. overlay the transition fade
7. call `pygame.display.flip()`
8. call `clock.tick(target_fps)`

Important consequence:
- simulation advancement is directly tied to the outer render loop
- `target_fps` currently acts as both render cap and effective simulation-speed cap

Preview mode halves the target frame cap:
- `target_fps = settings.target_fps // 2 if scr_args.mode == "preview" else settings.target_fps`

#### Simulation stepping flow

`Simulation.step()` dispatches by mode:
- `energy`
- `predator_prey`
- `boids`
- `drift`

Each mode currently:
- increments `self._frame` once per step
- performs one full simulation advance
- clears `active_attacks` at the start of the step
- appends `birth_events`, `death_events`, and `cosmic_ray_events` during the step

Simulation internals are frame-native, not wall-clock-native. Examples:
- food cycle rate depends on `self._frame`
- age increments by `1` per step
- lifespan is expressed in frames
- drift and boids updates assume one frame-sized step
- HUD lifespan-in-seconds conversion divides by `60.0`

#### Rendering flow

`Renderer.draw(simulation)` currently:
1. updates render-FPS tracking from wall-clock time
2. ingests sim death/birth events into `AnimationManager`
3. turns cosmic ray events into render animations
4. clears the sim event queues after ingestion
5. draws background, ambient particles, zones, shimmer, food, links, trails, creatures, attacks, animation effects, HUD, and settings overlay
6. in debug mode, stores render timing breakdown and draws debug graphs

Render timing is partially instrumented already inside `Renderer.draw()`:
- clear
- ambient
- zones
- territory
- food
- links
- trails
- creatures
- attacks
- animations
- HUD
- settings
- total draw time

However:
- this breakdown is currently mainly debug-oriented
- total frame timing and sim-step cadence are not tracked as first-class loop metrics

#### Event consumption flow

Current ownership model:
- simulation produces `death_events`, `birth_events`, `cosmic_ray_events`, and `active_attacks`
- renderer consumes and clears `death_events`, `birth_events`, and `cosmic_ray_events`
- simulation clears `active_attacks` at the start of each step

This matters for fixed-step integration:
- if multiple sim steps run before one render, `death_events`, `birth_events`, and `cosmic_ray_events` will accumulate and still be visible to the renderer
- `active_attacks` will not accumulate, because each sim step clears it before render ever sees the earlier step's values

#### Benchmark/profile flow

There is no dedicated checked-in benchmark harness module in the repo.

The current benchmark-adjacent flow is `--profile` in `primordial/main.py`:
- runs for 60 seconds under `cProfile`
- loops as `simulation.step() -> renderer.draw() -> pygame.display.flip() -> clock.tick(target_fps)`
- writes `.pstats` and a text profile report

This path is still coupled in the same way as the normal loop. It does not currently emit structured timing summaries separating sim from render.

### 4. Where Render Cadence May Currently Affect Simulation Progression

The direct coupling is in the main loop:
- one call to `simulation.step()` per rendered frame

That means simulation slows down in wall-clock time when any of these get slower:
- event handling
- renderer work
- `pygame.display.flip()`
- frame cap pacing through `clock.tick()`

Specific effects already present:
- lowering `target_fps` slows the simulation
- preview mode slows the simulation because it halves the frame cap
- expensive visual paths reduce effective sim advancement per second
- temporary render stalls change ecological history because the world advances less often in real time

This is exactly the Milestone 1 problem described by the roadmap and spec.

### 5. Hidden Dependencies, Risks, and Edge Cases

#### A. The simulation is already authored as fixed-size frame logic

This is the most important constraint.

The current simulation is not variable-dt based. It already assumes:
- one discrete step = one simulation frame
- ages measured in frames
- food cycle period measured in frames
- motion updates tuned for `dt=1.0`
- multiple random processes tuned per frame

Because of that, a broad simulation rewrite to arbitrary variable dt would exceed Milestone 1 scope. The codebase-aligned approach is to keep the simulation step itself fixed and only decouple the outer loop.

#### B. `target_fps` currently influences more than rendering

Today `target_fps` affects:
- render pacing
- simulation progression rate
- preview mode behavior
- apparent lifespan timing shown in HUD

After fixed-step integration, `target_fps` should become a render pacing control only. That is a real behavior change, but it is required by the spec.

#### C. Event semantics are not uniform across event types

`death_events`, `birth_events`, and `cosmic_ray_events` can safely accumulate across multiple sim steps before render.

`active_attacks` cannot, because it is cleared inside every sim step. Under multi-step-per-render execution, only the last sim step's attacks survive. This is a hidden dependency between render cadence and a visual event path.

This is likely the narrowest event-semantics adjustment needed inside Milestone 1.

#### D. Pause and transition behavior should not retroactively catch up

Current behavior:
- opening the settings overlay pauses simulation
- mode transitions can temporarily suppress stepping

If a fixed-step accumulator continues accumulating while paused or during a transition hold, the sim could "catch up" afterward and violate current behavior. Accumulator behavior must explicitly freeze or discard elapsed sim time in these states.

#### E. Render-only animation systems are frame-based

These systems advance on rendered frames, not simulation steps:
- `AnimationManager` birth/death/cosmic-ray animation progression
- settings overlay fade
- some shimmer fade multipliers use frame-derived increments

This does not block Milestone 1, because the spec is about protecting simulation truth first. But it means render visuals may still appear slower or choppier under render stress even after sim decoupling. That is acceptable unless the spec explicitly requires more.

#### F. Existing profile path duplicates the main-loop structure

If fixed-step logic is added only to the main interactive loop but not to `--profile`, benchmark/profile numbers will remain misleading. The loop control path likely needs a shared driver or parallel update in both places.

This is still within Milestone 1. A larger runtime architecture rewrite is not required.

#### G. Headless step-only runs are not cleanly supported today

Past docs mention headless benchmark numbers, but the checked-in code does not expose a dedicated harness. A pure step-only benchmark would currently leak event queues unless it explicitly drains or suppresses them, because renderer owns queue consumption by contract.

So:
- benchmark-friendly output is in scope
- inventing a large standalone benchmark framework is broader than the current code requires for M1

### 6. Recommended Bounded Implementation Shape

Preferred Milestone 1 shape for this codebase:

#### Main loop model

Use a monotonic fixed-step accumulator in `primordial/main.py`:
- choose a fixed simulation timestep of `1 / 60`
- accumulate elapsed real time from a monotonic timer
- execute zero or more simulation steps while accumulator >= fixed step
- render at most once per outer loop iteration
- flip once per outer loop iteration
- optionally sleep or cap render cadence after rendering

Important boundary:
- do not rewrite simulation internals to arbitrary variable dt
- keep `Simulation.step()` as one fixed simulation tick

#### Catch-up protection

Add a bounded anti-spiral mechanism:
- either clamp maximum accumulated time
- or cap sim steps per outer loop iteration
- or both

If the clamp is hit:
- drop excess accumulated time
- record that event in instrumentation
- do not try to catch up forever

#### Pause and transition handling

When simulation should not advance:
- do not accumulate catch-up debt
- do not replay paused time later

This should apply at minimum to:
- paused state
- transition phases where stepping is intentionally suppressed

#### Render cadence

`target_fps` should become a render pacing target only.

That implies:
- normal mode render cap still works
- preview mode can still render at half rate if desired
- but preview mode should no longer slow simulation progression unless the spec explicitly wants that, and the spec does not

#### Event handling shape

Keep current ownership where possible:
- simulation still owns event production
- renderer still owns event ingestion for birth/death/cosmic-ray visuals

But inspect `active_attacks` carefully:
- either allow accumulation across all sim steps until render
- or explicitly define it as "last-step only" and accept the changed visibility

The first option is more consistent with preserving current visual semantics during multi-step frames.

#### Benchmark/profile shape

Do not invent a large new benchmark subsystem.

Bounded M1 shape:
- keep existing `--profile` entry point
- make it use the same fixed-step loop behavior
- emit lightweight structured timing summary at the end

If this appears to require a much broader benchmark framework, that would be beyond the spec and should be reported, not improvised.

### 7. Instrumentation Insertion Points

#### Outer-loop instrumentation in `primordial/main.py`

Add cheap counters/timers around:
- event polling/handling time
- sim batch time for all fixed steps executed this outer frame
- render time (`renderer.draw`)
- present/flip time
- total outer frame time
- pacing/sleep time if measured
- number of sim steps executed this rendered frame
- accumulator clamp/drop occurrences

This is the primary place to answer the Milestone 1 questions.

#### Renderer timing in `primordial/rendering/renderer.py`

Reuse the existing per-draw timing breakdown:
- keep current sub-phase timings
- expose total render time in a non-debug-only summary path
- avoid high-volume per-frame logging

#### Optional simulation-side counters in `primordial/simulation/simulation.py`

Minimal counters only, if needed:
- total sim steps executed
- possibly current `_frame`

Avoid deep instrumentation inside hot loops unless measurement shows it is necessary.

#### Benchmark/profile output path in `primordial/main.py`

The current `--profile` path is the natural insertion point for:
- summarized sim timing
- summarized render timing
- total frame timing
- effective FPS
- sim-steps-per-render-frame statistics
- clamp/drop counts
- machine-readable summary output

Prefer a lightweight structured file format such as JSON.

### 8. Validation Plan

#### Correctness checks

1. Verify simulation progression is stable across render caps.
   - run with `target_fps` values such as 30, 60, and 120
   - confirm sim step rate remains approximately fixed while render FPS changes

2. Verify preview mode no longer changes sim progression merely by rendering less often.

3. Verify pause and overlay behavior.
   - open settings overlay
   - hold for several seconds
   - close overlay
   - confirm no sim catch-up burst occurs

4. Verify mode transition behavior.
   - change mode through settings overlay
   - confirm fade/reset/fade still works
   - confirm accumulator state does not cause unexpected multi-step bursts after reset

5. Verify fullscreen/screensaver behavior still works.
   - normal fullscreen
   - preview mode
   - screensaver mode input-to-exit

#### Event and visual containment checks

6. Verify death, birth, and cosmic-ray visuals still appear correctly under multi-step frames.

7. Verify attack-line behavior under heavy load.
   - this is the main event semantic risk area
   - confirm whether current behavior is preserved or intentionally minimally adjusted

#### Stability checks

8. Introduce temporary render stress or a synthetic stall.
   - confirm the loop does not enter runaway catch-up
   - confirm clamp/drop behavior is bounded and observable

9. Run a dense boids or dense energy scenario long enough to ensure no obvious loop instability.

#### Measurement checks

10. Capture comparable timing summaries for at least:
- moderate energy-mode run
- visually dense energy or predator/prey run
- boids-heavy run

11. Validate reported metrics include at least:
- sim time
- render time
- total frame time
- effective FPS
- sim steps per rendered frame

12. If a minimal-render or headless comparison is added, confirm event queues are still drained safely and that the path is explicitly defined rather than inferred.

### 9. Explicit Containment Notes

The following would be broader than this spec and should not be improvised during Milestone 1:
- converting the whole simulation to arbitrary variable-dt behavior
- rewriting the renderer around interpolation or GPU paths
- redesigning ecological systems or trait dynamics
- building a large standalone benchmarking framework
- broad cleanup unrelated to loop timing, event semantics, or measurement

The current codebase supports a bounded Milestone 1 implementation without those expansions.
