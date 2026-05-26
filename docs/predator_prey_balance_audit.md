# Predator-Prey Balance Audit

## Scope

This is an audit of current `main` behavior using committed defaults and the existing graphical predator-collapse diagnostics. No simulation behavior, tuning, defaults, or local user config values were changed for this report beyond the explicit reset to canonical defaults before running diagnostics.

## Exact Commit Tested

- Commit: `0999e40b44015f064eba48043ca4a5e964748bb0`
- Short hash: `0999e40`

## Exact Commands Run

```bash
.venv/bin/python tools/write_default_config.py --backup --force

.venv/bin/python tools/predator_collapse_diagnostics.py \
  --seeds 1373158607,239081664,53710185,1592467582,590620972 \
  --max-ticks 20000 \
  --output run_logs/balance_audit_5seed_report.md \
  --json run_logs/balance_audit_5seed.json
```

The 5-seed batch command exceeded the local command timeout in this environment because the tool runs full graphical mode. I completed the same committed scenario and defaults with equivalent per-seed commands:

```bash
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 1373158607 --max-ticks 20000 --output run_logs/balance_seed_1373158607_report.md --json run_logs/balance_seed_1373158607.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 239081664 --max-ticks 20000 --output run_logs/balance_seed_239081664_report.md --json run_logs/balance_seed_239081664.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 53710185 --max-ticks 20000 --output run_logs/balance_seed_53710185_report.md --json run_logs/balance_seed_53710185.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 1592467582 --max-ticks 20000 --output run_logs/balance_seed_1592467582_report.md --json run_logs/balance_seed_1592467582.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 590620972 --max-ticks 20000 --output run_logs/balance_seed_590620972_report.md --json run_logs/balance_seed_590620972.json
```

Runtime was reasonable once runs were split per seed, so I also audited the deterministic next five seeds from the tool's own `random.seed(42)` sequence:

```bash
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 525901257 --max-ticks 20000 --output run_logs/balance_seed_525901257_report.md --json run_logs/balance_seed_525901257.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 479341424 --max-ticks 20000 --output run_logs/balance_seed_479341424_report.md --json run_logs/balance_seed_479341424.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 299655413 --max-ticks 20000 --output run_logs/balance_seed_299655413_report.md --json run_logs/balance_seed_299655413.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 1581559893 --max-ticks 20000 --output run_logs/balance_seed_1581559893_report.md --json run_logs/balance_seed_1581559893.json
.venv/bin/python tools/predator_collapse_diagnostics.py --seeds 220106708 --max-ticks 20000 --output run_logs/balance_seed_220106708_report.md --json run_logs/balance_seed_220106708.json
```

## Seed Lists

- Requested 5-seed set: `1373158607, 239081664, 53710185, 1592467582, 590620972`
- Wider 10-seed set: `1373158607, 239081664, 53710185, 1592467582, 590620972, 525901257, 479341424, 299655413, 1581559893, 220106708`

## Limits Of Existing Diagnostics

Existing committed diagnostics are strong on predator life histories, hunt outcomes, near-contact behavior, and kill-energy transfer. They do not expose exact aggregate prey birth totals or exact aggregate non-predation prey death totals. For prey recovery, this audit therefore uses:

- final prey counts
- per-run minimum prey counts from species timelines
- predator kill totals
- whether prey counts recovered after their low point

## Requested 5-Seed Summary

| Seed | Final ticks | Collapse cause | Final predators | Final prey | Predator births | Predator deaths | Total kills |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1373158607 | 20000 | none | 7 | 26 | 44 | 77 | 90 |
| 239081664 | 16409 | Predators collapsed | 0 | 34 | 5 | 41 | 26 |
| 53710185 | 20000 | none | 1 | 33 | 12 | 54 | 31 |
| 1592467582 | 20000 | none | 0 | 25 | 6 | 40 | 21 |
| 590620972 | 20000 | none | 2 | 31 | 24 | 57 | 60 |

## Aggregate Summary

| Metric | 5 seeds | 10 seeds |
| --- | ---: | ---: |
| Runs ending with predators alive | 3/5 | 5/10 |
| Runs ending with zero predators | 2/5 | 5/10 |
| Runs hitting explicit predator-collapse game over | 1/5 | 3/10 |
| Runs hitting prey collapse | 0/5 | 0/10 |
| Mean final predators | 2.0 | 2.9 |
| Median final predators | 1.0 | 0.5 |
| Mean final prey | 29.8 | 29.6 |
| Median final prey | 31.0 | 30.0 |
| Predator births | 91 | 207 |
| Predator deaths | 269 | 553 |
| Predator births minus deaths | -178 | -346 |
| Completed predator lives with zero kills | 167/269 (62.1%) | 345/553 (62.4%) |
| Mean kills per completed predator life | 0.85 | 0.84 |
| Active-hunting deaths | 169 | 332 |
| Long-scarcity deaths | 68 | 143 |
| After-failed-pursuit deaths | 6 | 16 |
| Same-depth near-contact no-kill frames | 1049 | 1944 |
| Cross-depth near-contact no-kill frames | 535 | 1073 |
| Near-contact frames ending without kill | 88.2% | 87.7% |
| Kills cap-limited | 28.9% | 30.5% |
| Kills helped by biomass bonus | 78.9% | 77.0% |
| Kills crossing reproduction threshold | 18.4% | 19.5% |
| Runs where predators ever hit zero during the run | 4/5 | 8/10 |
| Median first predator-zero tick when it happened | 5160 | 5160 |

## Prey Recovery Check

Prey did not collapse in any audited run.

Every audited run showed prey recovery after the local low point in the species-count timeline:

- 5-seed sample: prey low points ranged from `8` to `17`, and every run recovered by `+12` to `+22` prey by the end.
- 10-seed sample: prey low points ranged from `5` to `17`, and every run recovered by `+11` to `+31` prey by the end.

This is important because it argues against prey reproduction failure being the primary bottleneck on current `main`.

## Diagnosis

Primary bottleneck: `contact conversion remains the limiting factor`.

Why this is the best fit for the current data:

1. Predators are usually not failing to find prey first.
The percentage of predator lives with no prey sightings is very low across the audit, generally `0%` to `5%` per run. Long-scarcity deaths exist, but they are not the dominant signature.

2. Predators often see prey and still fail to secure kills.
Across 10 seeds, about `62%` of completed predator lives ended with zero kills, and the mean was only `0.84` kills per completed life.

3. Near-contact failure is common even after predators get close.
Across 10 seeds, `87.7%` of near-contact frames did not convert to kills. Same-depth near-contact no-kill frames (`1944`) were also much more common than pure cross-depth misses would need to be to explain the bottleneck by themselves.

4. Death context points to failed/expensive hunting more than famine.
Across 10 seeds, `332` predator deaths were tagged `active_hunting`, versus `143` `long_scarcity` deaths and `16` `after_failed_pursuit` deaths. Predators are dying while engaged, not primarily while isolated from prey for long stretches.

5. Reproduction is also tight, but it looks secondary to kill conversion.
Only `19.5%` of kills crossed the reproduction threshold after biomass, and predator births were far below predator deaths (`207` births vs `553` deaths`). That matters, but a reproduction-only explanation does not fit the high share of zero-kill lives and near-contact no-kill frames.

6. Prey are not the collapsed side of the ecosystem.
Prey survived all runs and recovered after dips, so the dominant failure mode is not "prey cannot recover after predation" and not "predators starve after prey depletion."

Working interpretation:

- Predators can usually locate prey.
- Predators too often fail to convert pursuit and close-range pressure into actual kills.
- Because kills per life stay low, reproduction-ready states are too infrequent to replace predator deaths.
- The visible ecological outcome is a persistent near-extinction predator floor, with prey recovering once predator pressure fades.

## Comparison To Intended Target

### Prey should not collapse quickly

Observed: met.

- No prey-collapse runs in either the 5-seed or 10-seed audit.
- Prey recovered after local lows in every run.

### Predators can stay lower than prey, but should not hover at permanent near-extinction

Observed: not met.

- Median final predators were `1` in the 5-seed sample and `0.5` in the 10-seed sample.
- Predators hit zero at some point in `8/10` runs.
- Half of the 10 audited runs ended with zero predators.

### Predator births should be frequent enough to replace deaths in at least some runs

Observed: not met.

- Predator births were below predator deaths in every audited run.
- Aggregate births-minus-deaths was strongly negative in both samples.

### Prey should recover after predation pressure

Observed: met.

- This happened in every audited run.

## Confidence Level

Moderate-high.

Reasons for confidence:

- The 10-seed extension preserved the same shape seen in the requested 5 seeds.
- The same conclusion is supported by multiple independent existing signals: zero-kill life share, near-contact no-kill share, death contexts, prey-sighting rates, and prey recovery.

Reasons this is not "high" confidence:

- Existing diagnostics do not provide exact aggregate prey birth/death totals.
- Existing diagnostics do not segment same-depth near-contact failures by detailed terminal outcome outside the predator life summaries already recorded.

## Recommended Next Change

Do not implement in this task.

Recommended next change: investigate and test a very small predator contact-conversion adjustment first, not a broad food or reproduction retune.

Reason:

- The strongest current bottleneck is between "predator got close enough to pressure prey" and "predator actually secured the kill."
- If that conversion improves modestly, predator reproduction may improve indirectly without needing to lower the reproduction threshold first.

If the team wants more certainty before changing mechanics, the safer follow-up is an outside-loop reporting pass focused on same-depth near-contact sequences and terminal outcomes, because current committed diagnostics are already very close to isolating that failure point.

## Rejected Changes And Why

- `Lower predator reproduction threshold first`
The data does show a reproduction bottleneck, but the upstream problem is larger: too many predator lives never get enough kills for threshold tuning to matter often enough.

- `Make the food cycle less famine-heavy`
Long-scarcity deaths are present but not dominant, prey survive all runs, and predators usually do see prey. This does not look primarily famine-driven.

- `Increase prey reproduction or recovery`
Prey already recover after pressure in every audited run. This would push the system in the wrong diagnostic direction unless later evidence shows prey availability is still the limiting factor.

- `Focus on cross-depth fixes first`
Cross-depth near-contact misses exist, but same-depth near-contact no-kill frames are larger in absolute count. The present bottleneck is not isolated to depth mismatch alone.

- `Reintroduce post-move contact logic`
That branch was already identified as unsafe. This audit does not need it, and the current data is sufficient to point at the bottleneck without reviving a risky mechanic.

- `Tune from local user config`
That would break reproducibility and violate the config-authority discipline for this project.
