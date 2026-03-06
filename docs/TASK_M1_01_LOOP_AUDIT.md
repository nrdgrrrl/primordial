# Task: M1.01 Loop Audit Baseline

## Title
Milestone 1 Audit Baseline for Fixed-Step Simulation and Instrumentation

## Purpose
Capture the Pass A audit/design findings for Milestone 1 in a bounded task file so later implementation tasks have a fixed reference point. This task exists to prevent speculative loop changes and to document the concrete runtime surfaces involved before Pass B and Pass C work begins.

## Status
Audit baseline captured against the checked-in code on 2026-03-05.

## Short Summary
The current runtime is still a one-step-per-render loop. In normal, preview, screensaver, and `--profile` flows, the application polls events once, runs at most one `simulation.step()`, runs one `renderer.draw(simulation)`, flips once, and then yields through `clock.tick(...)`. Because of that shape, render cadence still acts as the simulation clock. Milestone 1 must change the outer loop, not rewrite simulation internals to variable `dt`.

## Scope
- Confirm the current loop structure in normal, preview, screensaver, and `--profile` flows.
- Confirm where simulation cadence is currently coupled to rendering cadence.
- Confirm event ownership and render-side queue draining behavior.
- Confirm timing surfaces already present in the renderer and debug HUD.
- Record hidden dependencies that must constrain later Milestone 1 tasks.

## Affected Files / Subsystems
- `main.py`
- `primordial/main.py`
- `primordial/simulation/simulation.py`
- `primordial/rendering/renderer.py`
- `primordial/rendering/animations.py`
- `primordial/rendering/hud.py`
- `primordial/config/config.py`
- `config.toml`

Subsystems:
- main application loop
- profile/runtime loop
- simulation stepping entry point
- renderer entry point
- event queue production and consumption
- FPS/debug timing surfaces

## Audit Findings

### Launch And Mode Entry
- Root `main.py` parses screensaver/runtime args, sets `SDL_WINDOWID` for preview mode before pygame initialization, and then calls `primordial.main.main(...)`.
- `primordial/main.py` has distinct display setup for normal, preview, screensaver, and config modes, but only config mode skips simulation startup entirely.
- `--profile` is only honored in normal mode and swaps into a separate 60-second profile loop.

### Current Main Loop Shape
- The interactive loop in `primordial/main.py` currently does this once per outer iteration:
  - poll pygame events once
  - handle screensaver exit rules, preview no-op input, keyboard controls, and settings overlay actions
  - update mode-transition fade state
  - run exactly one `simulation.step()` unless the transition is holding at full fade-out
  - pass `event_ms` and `sim_ms` into the renderer debug metrics
  - run exactly one `renderer.draw(simulation)`
  - apply the transition fade overlay
  - call `pygame.display.flip()`
  - call `clock.tick(target_fps)`
- Preview mode halves the render cap with `settings.target_fps // 2`.
- Current pause behavior is not accumulator-based. Opening the settings overlay pauses the simulation directly through `simulation.paused`.

### Current Profile Loop Shape
- `_run_profile_session(...)` duplicates the coupled runtime pattern:
  - poll events once
  - run exactly one `simulation.step()`
  - run exactly one `renderer.draw(simulation)`
  - flip once
  - call `clock.tick(max(1, settings.target_fps))`
- This means the profile path is coupled in the same way as the interactive loop and must be updated alongside it in later M1 tasks.

### Where Simulation Cadence Is Coupled To Rendering
- The direct coupling point is the one-call-per-frame `simulation.step()` in both the interactive loop and the profile loop.
- `target_fps` currently acts as both:
  - the render pacing cap
  - the effective simulation-speed cap in wall-clock time
- Consequences already present in the checked-in code:
  - lowering `target_fps` slows simulation progression
  - preview mode slows simulation progression because it halves the cap
  - renderer work, event handling, `pygame.display.flip()`, and `clock.tick(...)` all affect how often the world advances

### Simulation Step Baseline
- `Simulation.step()` is a mode dispatcher only. It does not accept `dt` and should remain one fixed simulation tick for Milestone 1.
- Each mode-specific step currently assumes frame-sized advancement:
  - `_frame` increments once per step
  - food cycle logic is frame-based
  - age and lifespan are frame-based
  - movement calls use fixed `dt=1.0`
  - per-frame random processes are tuned around one discrete step
- This constrains later M1 work: fixed-step integration belongs in the outer loop, not in a variable-`dt` rewrite of simulation internals.

### Event Ownership And Queue Draining
- Simulation produces:
  - `death_events`
  - `birth_events`
  - `cosmic_ray_events`
  - `active_attacks`
- Renderer consumes and clears:
  - `death_events`
  - `birth_events`
  - `cosmic_ray_events`
- Simulation clears `active_attacks` at the start of every mode-specific step.
- Hidden dependency:
  - `death_events`, `birth_events`, and `cosmic_ray_events` can accumulate across multiple sim steps before one render
  - `active_attacks` cannot, because earlier-step attacks are discarded by the next sim step before render sees them
- This is the key event-semantics constraint for later fixed-step work.

### Existing Timing Surfaces
- `primordial/main.py` already measures:
  - event handling time as `event_ms`
  - single-step simulation time as `sim_ms`
- `Renderer.draw(...)` already measures internal render breakdown timings for:
  - event ingestion
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
  - settings overlay
  - total draw time
- The HUD/debug path already shows:
  - rolling FPS
  - target FPS line
  - population history
  - compact debug timing lines using the external `event_ms` and `sim_ms` metrics plus renderer timings
- What is still missing for later M1 tasks:
  - first-class total frame timing
  - frame pacing / sleep timing
  - sim steps per rendered frame
  - clamp/drop visibility for catch-up protection
  - non-debug structured summary output for benchmark/profile use

### Hidden Dependencies And Constraints
- `target_fps` currently affects simulation speed, so later M1 tasks will intentionally change that behavior by making it render-only.
- Pause and transition states currently suppress stepping directly. Any future fixed-step accumulator must not build up catch-up debt while paused or during transition holds.
- Render-only animation systems remain render-frame-driven today. That is acceptable for M1 as long as simulation truth is decoupled first.
- There is no dedicated checked-in benchmark harness. The bounded benchmark-friendly path for M1 remains the existing `--profile` flow rather than a new framework.

## Implementation Notes
- This is a documentation-only task. Do not change runtime code here.
- Use the existing Pass A findings in `docs/spec_m_1_fixed_step_and_instrumentation.md` as the source of truth unless the code materially changes.
- Keep the key Milestone 1 constraint explicit: `Simulation.step()` remains one fixed simulation tick, not arbitrary variable `dt`.
- Keep the key hidden dependency explicit: `active_attacks` currently clears per sim step and does not naturally preserve visuals across multi-step render frames.

## Validation Steps
- Re-read the current code paths in `primordial/main.py`, `primordial/simulation/simulation.py`, and `primordial/rendering/renderer.py`.
- Confirm the audit findings still match the checked-in code before starting M1.02.
- Confirm the task file does not prescribe work from Milestone 2 or later.

## Out Of Scope
- Writing or changing loop code
- Adding instrumentation
- Implementing fixed-step behavior
- Benchmark framework expansion
- Renderer optimization work
- Ecology or behavior changes
