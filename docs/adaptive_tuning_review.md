# Predator-prey adaptive dial tuning review

This note reviews the current "small adjustment + rerun" loop used in predator-prey mode and flags strengths, risks, and likely improvements.

## What the current loop does today (with concrete mechanics)

1. A run ends only when predator or prey count reaches zero.
2. The mode enters a red `GAME OVER` hold for **10 seconds**.
3. On collapse, the run's `survival_ticks` are finalized, compared to the rolling average from `run_history`, and logged.
4. If no trial is active and the run was below the rolling average, the next run starts a **one-dial trial**.
5. The next completed run decides the trial:
   - **keep** if `survival_ticks >= trial_baseline_average`
   - **revert** if `survival_ticks < trial_baseline_average`
6. The sim restarts with a new seed while preserving rolling stability/tuning state.

Important detail: ties are treated as success (`>=`), so "equal to baseline" keeps the change.

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

## Rolling average, rollback, and step escalation (specific numbers)

### Rolling average

- `run_history` is a bounded deque.
- Default history window: **20 runs** (`stability_history_size = 20`).
- Rolling baseline used for comparisons is the arithmetic mean of the current deque.

So if your last 20 runs averaged 3200 ticks, that becomes the baseline for triggering trials and for evaluating whether a normal (non-trial) run is "improving".

### Trial start trigger

A new trial starts only when all are true:

- no trial currently active,
- rolling average exists (`> 0`),
- just-finished run is below rolling average.

Then one random dial and one random direction (`-1` or `+1`) is attempted, skipping no-op moves caused by clamping.

### Rollback/keep decision

When the trial run ends:

- if `trial_survival < trial_baseline_average` → revert to `previous_values`
- else (equal or better) → keep trial values

This is a strict one-step A/B with immediate rollback capability.

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

- High-variance objective: run survival can vary significantly by seed and stochastic interactions; one-run accept/revert can overfit noise.
- Delayed coupling effects: one dial may help immediately but harm after several runs due to ecological feedback loops.
- Scalar objective only: optimizing survival ticks alone can drift toward brittle or degenerate ecologies.
- Myopic search: random one-dial perturbation ignores interactions among dials (cross terms).
- Rolling baseline drift: comparison target moves with recent history, which can produce oscillation around local plateaus.
- Extinction-only endpoint: non-collapsing but unhealthy states are not explicitly penalized unless they collapse soon.

## More detailed upgrades for your stated goal

### 1) Multi-seed trial evaluation (recommended first)

Instead of deciding from a single trial run, evaluate each candidate on a small seed set.

Suggested practical policy:

- keep your current candidate-generation logic (one dial, one signed step),
- evaluate candidate on **k = 3 to 5** fixed seeds,
- compute robust aggregate score (`median` preferred; mean also fine),
- compare against baseline aggregate on same seed set,
- keep only if improvement clears a margin.

Decision rule example:

- `candidate_score = median(survival_ticks over k seeds)`
- `baseline_score = median(current config over same k seeds)`
- keep if `candidate_score >= baseline_score + max(50, 0.02 * baseline_score)`

Why this helps:

- controls RNG noise,
- reduces false keeps/reverts,
- makes tuning progress less streaky.

Low-cost variant if full k-run trials are expensive:

- run `k=2` quickly,
- only if candidate looks better, run a 3rd confirmation seed.

### 2) Add ecological health to the objective (not just survival)

You want long, self-sustaining runs without intervention. Time-to-collapse alone can hide fragile states. Add a composite objective with survival + ecology quality.

Suggested additional metrics:

- **Species balance stability**: fraction of time predator/prey ratio stays inside a healthy band (e.g., 20/80 to 80/20).
- **Population volatility**: rolling stddev of total population (lower is usually healthier than boom-bust spikes).
- **Near-extinction pressure**: count of ticks where either species is below a floor (e.g., `< 5` individuals).
- **Food stress proxy**: average famine-severity exposure (or very low-food dwell time).
- **Collapse-side bias**: whether failures are mostly predator-collapse or prey-collapse (prevents one-sided "successes").

Example normalized score:

`score = 0.55 * survival_norm + 0.20 * balance_norm + 0.15 * (1 - volatility_norm) + 0.10 * (1 - near_extinction_norm)`

Use this score for keep/revert (with margin), while still reporting raw `survival_ticks` in HUD/logs.

### 3) Confirmation before permanent keep

Even with single-run trialing, add one confirmation:

- tentative keep after first pass,
- if confirmation run also meets threshold, finalize keep,
- otherwise revert.

This is often the best complexity/performance trade-off.

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

Your current approach is reasonable and safer than naive auto-tuning. For your goal (longer and longer hands-off stability), the highest-leverage upgrades are:

1. multi-seed/confirmation acceptance,
2. a composite health-aware objective,
3. optional smarter dial selection from historical lift once enough logs accumulate.
