# Predator-prey adaptive dial tuning review

This note reviews the current "small adjustment + rerun" loop used in predator-prey mode and flags strengths, risks, and likely improvements.

## What the current loop actually does

- A run ends only on species extinction (predator, prey, or both), then enters GAME OVER.
- At run end, survival is compared to the rolling average over recent runs (`run_history`).
- If the run is below the rolling average and no trial is currently active, the sim starts a one-dial trial for the next run.
- Trial logic changes one bounded dial by one signed step (with optional escalation after repeated non-improving runs).
- The next completed run decides the trial:
  - keep the change if survival is `>=` trial baseline average,
  - revert otherwise.

This is a single-parameter, noisy hill-climb with accept/revert, not a full multivariate optimizer.

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

## Practical improvements (low complexity)

1. **Multi-seed trial evaluation**
   - Evaluate each candidate dial change on `k` short seeds (or 2-3 full runs) and use mean/median survival.
   - Keep/revert based on aggregate score, not one sample.

2. **Use a robust decision threshold**
   - Require improvement margin (e.g., `trial >= baseline + epsilon`) to keep.
   - Consider median of history instead of mean for heavy-tail robustness.

3. **Add secondary health metrics**
   - Include predator/prey balance stability, population volatility, or minimum viable population floor.
   - Optimize a composite score, not only time-to-extinction.

4. **Guardrails against boundary lock**
   - Track boundary hit counts per dial; deprioritize dials repeatedly clamped at min/max.

5. **Smarter dial selection**
   - Use CSV history to bias selection toward dials with better historical lift, while still exploring occasionally.

6. **Trial confirmation**
   - When a trial looks successful, run one confirmation trial before permanently accepting.

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

Your approach is sensible for a noisy simulation and is already safer than naive auto-tuning. It is good as a first-order controller, but it will likely plateau and occasionally chase noise. For the goal of "longer and longer runs without intervention," the biggest win is usually **multi-seed/confirmation-based acceptance** plus **a slightly richer objective than survival ticks alone**.
