# Predator-prey adaptive dial tuning review

This note reviews the current predator-prey adaptive tuning loop and flags strengths, risks, and likely improvements.

## What the current loop does today (with concrete mechanics)

1. A run ends only when predator or prey count reaches zero.
2. The mode enters a red `GAME OVER` hold for **10 seconds**.
3. On collapse, the run's `survival_ticks` are finalized, compared to the rolling median from `run_history`, and logged.
4. If no trial is active and the run was below that rolling median, the mode starts a **one-dial multi-seed trial**.
5. Each dial trial generates a fixed seed set and runs both:
   - the candidate dial values on those seeds
   - the unchanged baseline dial values on those same seeds
6. The trial decision uses robust aggregates:
   - first compare `median(candidate_survivals)` vs `median(baseline_survivals)`
   - if the absolute survival-median gap is greater than `adaptive_survival_deadband`, decide by survival alone
   - if the gap is inside the deadband, compare `median(candidate_near_extinction_pressure)` vs `median(baseline_near_extinction_pressure)` and prefer the lower pressure
   - if both survival and pressure are tied, preserve the old keep-on-tie behavior when candidate survival meets baseline; otherwise revert
7. The sim restarts with those scheduled seeds while preserving rolling stability/tuning state.

Important detail: survival remains the primary objective. Near-extinction pressure is only a tie-breaker inside the deadband.

## Exactly which dials are tuned

The adaptive loop mutates only these six predator-prey mode params:

| Dial key | Min | Max | Default | Base step | Ecological meaning |
|---|---:|---:|---:|---:|---|
| `predator_contact_kill_distance_scale` | 0.80 | 1.20 | 1.00 | 0.03 | Effective predator contact distance for kills |
| `predator_kill_energy_gain_cap` | 0.35 | 0.65 | 0.50 | 0.02 | Max energy predator can gain from a kill |
| `predator_hunt_sense_multiplier` | 1.50 | 2.50 | 2.00 | 0.05 | Predator sensing boost while hunting |
| `prey_flee_sense_multiplier` | 1.00 | 1.60 | 1.20 | 0.05 | Prey threat sensing boost while fleeing |
| `predator_prey_scarcity_penalty_multiplier` | 1.40 | 2.60 | 2.00 | 0.10 | Extra predator cost when prey are scarce |
| `food_cycle_amplitude` | 0.40 | 1.00 | 1.00 | 0.05 | Feast/famine swing amount |

Every candidate change is clamped to `[min, max]`, so out-of-range moves are prevented.

## Rolling median, rollback, and step escalation (specific numbers)

### Rolling median

- `run_history` is a bounded deque.
- Default history window: **20 runs** (`stability_history_size = 20`).
- Rolling baseline used for comparisons is the median of the current deque.

So if your last 20 runs have a median survival of 3200 ticks, that becomes the baseline for triggering trials and for evaluating whether a normal (non-trial) run is "improving".

### Trial start trigger

A new trial starts only when all are true:

- no trial currently active,
- rolling median exists (`> 0`),
- just-finished run is below rolling median.

Then one random dial and one random direction (`-1` or `+1`) is attempted, skipping no-op moves caused by clamping.

### Rollback/keep decision

Default multi-seed evaluation config:

- `adaptive_trial_seed_count = 2`
- `adaptive_max_consecutive_retry_trials = 2`
- `adaptive_survival_deadband = 50`
- `adaptive_near_extinction_predator_floor = 5`
- `adaptive_near_extinction_prey_floor = 5`

For each selected seed:

- run the candidate dial values on that seed,
- run the unchanged baseline dial values on that same seed.

Then compute:

- `candidate_score = median(candidate_survivals)`
- `baseline_score = median(baseline_survivals)`
- `candidate_pressure = median(candidate_near_extinction_pressure)`
- `baseline_pressure = median(baseline_near_extinction_pressure)`

Decision rule:

- if `abs(candidate_score - baseline_score) > adaptive_survival_deadband`:
  - keep when `candidate_score >= baseline_score`
  - revert when `candidate_score < baseline_score`
- else if `candidate_pressure < baseline_pressure` → keep trial values
- else if `candidate_pressure > baseline_pressure` → revert to `previous_values`
- else keep when `candidate_score >= baseline_score`, otherwise revert

This is still a bounded one-dial A/B search, but it now uses same-seed median scoring instead of a single follow-up run.

### Failed-trial retry chaining

When a trial ends with `reverted`, the tuner immediately restores the last
accepted dial values. From that reverted incumbent state it may start a fresh
candidate/baseline trial immediately, without spending an extra ordinary run on
the unchanged incumbent first.

That immediate retry chain is bounded:

- `adaptive_max_consecutive_retry_trials` caps how many retry-launched trials
  may chain directly after failed trials.
- The counter increments only when a failed trial reverts and a new trial is
  launched immediately from the reverted incumbent.
- The counter resets when an ordinary non-trial run occurs, when a trial is
  kept, or when retry chaining otherwise ends.
- Once the cap is reached, the tuner blocks further immediate retries and
  requires at least one ordinary run before another trial can open.

CSV logging exposes this control flow with trial roles, trigger reasons
(`below_rolling_median`, `immediate_retry_after_revert`,
`blocked_by_retry_cap_then_waited_for_ordinary_run`), the current consecutive
retry count, the configured cap, and whether a launch was blocked by the cap.

### Step escalation

Default escalation config:

- `adaptive_step_escalation_runs = 5`
- `adaptive_step_escalation_percent = 25.0`

Step multiplier formula:

`multiplier = 1.0 + floor(non_improving_run_streak / escalation_runs) * (escalation_percent / 100)`

With defaults:

- streak 0-4 → `1.00x`
- streak 5-9 → `1.25x`
- streak 10-14 → `1.50x`
- streak 15-19 → `1.75x`

Example: `predator_contact_kill_distance_scale` base step is `0.03`; at streak 10 the effective step is `0.03 * 1.50 = 0.045`.

## Strengths

- Safe bounded search space: every dial has min/max and clamp behavior.
- Conservative edits: one dial at a time makes causal attribution easier.
- Explicit rollback: harmful edits are reverted instead of accumulating blindly.
- Built-in anti-stagnation: step escalation increases exploratory radius after streaks of non-improvement.
- Good observability hooks: HUD stats, GAME OVER summary, and optional CSV logs provide post-run diagnostics.

## Risks and blind spots

- High-variance objective: run survival can still vary significantly by seed and stochastic interactions, even though same-seed median scoring reduces one-run noise.
- Delayed coupling effects: one dial may help immediately but harm after several runs due to ecological feedback loops.
- Scalar objective only: optimizing survival ticks alone can drift toward brittle or degenerate ecologies.
- Myopic search: random one-dial perturbation ignores interactions among dials (cross terms).
- Rolling baseline drift: comparison target moves with recent history, which can produce oscillation around local plateaus.
- Extinction-only endpoint: non-collapsing but unhealthy states are not explicitly penalized unless they collapse soon.

## More detailed upgrades for your stated goal

### 1) Multi-seed trial evaluation (implemented)

This is now in place.

Current policy:

- keep your current candidate-generation logic (one dial, one signed step),
- evaluate candidate on **k = 2** fixed seeds by default,
- compute robust aggregate score with `median`,
- compare against baseline aggregate on same seed set,
- use near-extinction pressure only when survival medians are within the deadband,
- preserve the old keep-on-tie behavior only after the tie-breaker is exhausted.

Config:

- `adaptive_trial_seed_count` controls `k`
- minimum allowed value is `1`

Why this helps:

- controls RNG noise,
- reduces false keeps/reverts,
- makes tuning progress less streaky.

### 2) Low-risk ecological health tie-breaker (implemented)

The live loop still optimizes `survival_ticks` first. The only ecological health term now used in the accept/revert decision is a bounded tie-breaker:

- `near_extinction_pressure = predator_low_ticks + prey_low_ticks`
- `predator_low_ticks` counts run ticks with predator count below `adaptive_near_extinction_predator_floor`
- `prey_low_ticks` counts run ticks with prey count below `adaptive_near_extinction_prey_floor`
- this pressure is only consulted when survival medians are inside `adaptive_survival_deadband`

### 3) Confirmation before permanent keep

Even with single-run trialing, add one confirmation:

- tentative keep after first pass,
- if confirmation run also meets threshold, finalize keep,
- otherwise revert.

This is often the best complexity/performance trade-off.

### 4) Occasionally test multi-dial moves (to capture interactions)

Right now the search is strictly one-dial-at-a-time. That is great for simplicity,
but it misses cross-effects where two individually neutral changes are beneficial
together (or vice versa).

Suggested low-risk extension:

- keep **most** trials as single-dial (e.g., 80-90%),
- reserve a small fraction (10-20%) for **two-dial trials**,
- use smaller per-dial steps for multi-dial trials (e.g., 0.5x normal step),
- evaluate with the same multi-seed/confirmation criteria,
- if accepted, attribute credit to the dial pair as a combo in logs.

Practical pair candidates worth testing first:

- `predator_hunt_sense_multiplier` + `prey_flee_sense_multiplier`
- `predator_kill_energy_gain_cap` + `predator_prey_scarcity_penalty_multiplier`
- `food_cycle_amplitude` + either sensing dial (to adapt to feast/famine pressure)

Guardrails:

- avoid proposing pairs when either dial is already at/near clamp boundaries,
- limit consecutive multi-dial trials (e.g., max 1 in any 5 trials),
- revert the whole pair if aggregate score fails threshold.

This gives you interaction awareness without fully jumping to expensive global
optimizers.

## Is this “multi-dimensional gradient descent”?

Not strictly.

- It is **multi-dimensional parameter tuning** (because there are multiple dials).
- But it is **not gradient descent** in the formal sense:
  - no gradient estimate,
  - no vector step across all dimensions,
  - no differentiable objective assumption,
  - accept/revert by run outcome rather than descent on gradient direction.

Better labels:

- "stochastic coordinate hill-climbing"
- "one-factor-at-a-time adaptive search"
- "bounded random coordinate search with rollback"

## Bottom line

Your current approach is reasonable and safer than naive auto-tuning. With rolling-median comparisons and multi-seed acceptance now in place, the highest-leverage remaining upgrades are:

1. occasional interaction-aware multi-dial trials,
2. richer offline analysis of the new pressure-aware decision logs,
3. optional smarter dial selection from historical lift once enough logs accumulate.
