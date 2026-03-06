# Task: M1.04 Main Loop Fixed-Step Integration

## Title
Integrate Fixed-Step Simulation into the Main and Profile Loops

## Purpose
Wire the Milestone 1 scaffolding into the actual runtime so simulation advances on a fixed step while rendering remains variable-rate and capped independently. This is the behavioral integration task for Milestone 1.

## Scope
- Replace one-step-per-render behavior in the interactive loop with a fixed-step accumulator model.
- Apply the same fixed-step model to the `--profile` loop.
- Render at most once per outer loop iteration.
- Add bounded anti-spiral behavior through clamp and/or max-steps-per-frame handling.
- Ensure pause, overlay, reset, and transition states do not accumulate catch-up debt.
- Preserve existing event-driven visuals as closely as possible within Milestone 1 scope.

## Affected Files / Subsystems
- `primordial/main.py`
- `primordial/simulation/simulation.py`
- `primordial/rendering/renderer.py`
- `primordial/rendering/animations.py` only if a narrow event-ingestion adjustment is required

Subsystems:
- interactive runtime loop
- profile runtime loop
- sim-to-render event handoff
- pause/transition/reset gating

## Implementation Notes
- Use the fixed-step scaffold from M1.02 rather than inventing a second loop model.
- Keep `Simulation.step()` as the discrete sim tick.
- Render cadence should remain capped by `target_fps`, including preview-specific render pacing if retained.
- Clamp or cap runaway catch-up so temporary stalls do not create infinite recovery behavior.
- Keep changes narrowly centered on loop control flow and event semantics required by multi-step frames.
- Preserve renderer ownership of death/birth/cosmic-ray queue draining unless a narrow Milestone 1 adjustment is unavoidable.

## Validation Steps
- Verify simulation progression no longer slows when render cap changes from 30 to 60 to 120 FPS.
- Verify preview mode no longer changes sim speed merely by rendering at a different cadence.
- Verify pause and settings overlay do not produce a burst of catch-up sim steps on resume.
- Verify mode transitions still fade, reset, and resume cleanly.
- Verify fullscreen, preview, and screensaver paths still behave correctly.

## Out Of Scope
- Renderer interpolation
- GPU or rendering optimization work
- Ecology rule changes
- Save/resume
- Benchmark framework expansion beyond the existing profile path

## Uncertainty Flag
This task depends on one unresolved Milestone 1 detail:

- `active_attacks` currently clears inside each simulation step. Under multi-step-per-render execution, earlier-step attack visuals may be lost unless a narrow preservation rule is added.

Resolve this uncertainty before implementation by choosing one bounded behavior:
- preserve attacks across all sim steps until the next render, or
- explicitly accept last-step-only attack visuals and document that containment decision

If preserving attack visuals requires a broader event-system redesign, stop and report it instead of expanding scope.
