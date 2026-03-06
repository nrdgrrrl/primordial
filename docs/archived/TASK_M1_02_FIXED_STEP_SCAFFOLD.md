# Task: M1.02 Fixed-Step Loop Scaffold

## Title
Add Fixed-Step Loop Scaffolding and Shared Runtime State

## Purpose
Add the minimal structural support required for Milestone 1 so fixed-step behavior can be integrated cleanly in Pass C without rewriting the simulation or renderer. This task should establish loop-state abstractions and shared runtime scaffolding only.

## Scope
- Add a bounded fixed-step loop state model for the outer runtime loop.
- Add a shared runtime helper or driver surface that can be used by both the interactive loop and the `--profile` loop.
- Add configuration/constants for:
  - fixed simulation timestep
  - accumulator state
  - max sim steps per outer frame
  - runaway clamp/drop behavior
- Add explicit pause/transition handling hooks so elapsed time does not accumulate into catch-up debt during suppressed simulation periods.
- Add a narrow seam for future render-safe event preservation where multi-step frames need it.

## Affected Files / Subsystems
- `primordial/main.py`
- `primordial/simulation/simulation.py`
- `primordial/config/config.py` if a new internal-facing runtime setting is strictly necessary

Subsystems:
- main runtime loop control flow
- profile loop control flow
- pause and transition gating
- fixed-step accumulator state

## Implementation Notes
- Keep the scaffold local to Milestone 1. Do not redesign application architecture.
- Prefer a small dataclass or helper object over broad refactoring.
- `Simulation.step()` must remain the unit of fixed simulation advancement.
- `target_fps` remains the render pacing control. Do not use this task to change HUD wording or user-facing config semantics beyond what fixed-step scaffolding requires.
- The interactive loop and `--profile` loop should share the same scaffolding shape to avoid divergence.
- If a new helper is introduced, keep it narrowly focused on loop timing/state rather than generic engine abstractions.
- If event preservation requires a seam for `active_attacks`, keep it narrowly bounded and do not redesign all simulation event ownership in this task.

## Validation Steps
- Confirm the new scaffold can be instantiated without changing visible runtime behavior yet.
- Confirm pause and mode-transition paths have explicit accumulator reset/freeze handling points.
- Confirm the same scaffold is usable from both the normal loop and `--profile`.
- Confirm no simulation mode behavior changes occur in this task.

## Out Of Scope
- Executing multiple simulation steps per frame
- Changing renderer timing behavior
- Adding final benchmark output
- Reworking simulation internals to variable `dt`
- Render optimization or UI cleanup
