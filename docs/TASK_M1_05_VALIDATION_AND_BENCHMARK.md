# Task: M1.05 Validation and Benchmark Capture

## Title
Validate Fixed-Step Behavior and Capture Comparable Timing Results

## Purpose
Verify that Milestone 1 achieved simulation/render decoupling without destabilizing the app, and capture timing results that can be used as the baseline for later milestones.

## Scope
- Run correctness-oriented smoke tests across runtime modes affected by Milestone 1.
- Run representative timing captures using the new instrumentation output.
- Verify structured output from the profile path is usable for later comparison.
- Confirm clamp/drop behavior is bounded and observable under temporary render stress.

## Affected Files / Subsystems
- `primordial/main.py`
- `primordial/rendering/renderer.py`
- `primordial/simulation/simulation.py`
- any timing-summary artifact emitted by `--profile`

Subsystems:
- runtime loop stability
- profile output path
- event-driven render effects under multi-step frames
- timing comparison workflow

## Implementation Notes
- Use a small, repeatable scenario set:
  - moderate `energy` run
  - visually denser `energy` or `predator_prey` run
  - `boids` run
- Test multiple render caps such as 30, 60, and 120 FPS.
- Compare sim-step rate against effective render FPS to confirm decoupling.
- Include at least one pause/resume test and one mode-transition test.
- Include at least one temporary render-stall or stress scenario to verify anti-spiral containment.
- Record any known residual limitation, especially if attack visuals or render-frame-native animations remain intentionally approximate under stress.

## Validation Steps
- Run normal mode with `--debug` and verify timing lines are populated and stable.
- Run `--profile` and confirm:
  - `.pstats` output still exists
  - text profile output still exists
  - structured timing summary exists
- Verify reported metrics include:
  - sim time
  - render time
  - total frame time
  - effective FPS
  - sim steps per rendered frame
  - clamp/drop counts
- Verify death, birth, and cosmic-ray visuals still appear correctly under multi-step frames.
- Verify there is no obvious runaway catch-up after temporary stalls.

## Out Of Scope
- Long-term observability/dashboard work
- Performance optimization beyond narrow stability guards
- Ecology analysis
- Later milestone telemetry
