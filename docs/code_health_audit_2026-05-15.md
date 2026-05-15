# Code Health Audit

## Summary

The recent runtime/display/input/persistence split is directionally healthy: import smoke checks pass, tests pass, and no moved helper still imports from `primordial.main`. The remaining risk is concentrated in the still-large `primordial/main.py` event loop, especially the settings-overlay action block. That block now owns settings application, display/backend switching, snapshot load/save, browser help, predator-prey dial reset, runtime timing state, and simulation swapping in one nested branch.

The best next refactor target is the settings-overlay action handling, but it should start with tests for current behavior and two bug fixes rather than a broad loop rewrite.

## Validation Run

| Command | Status | Notes |
| --- | --- | --- |
| `make test` | PASS | `291 passed, 3 subtests passed in 16.97s` |
| `.venv/bin/python -m compileall primordial tools tests` | PASS | All packages/tools/tests compiled successfully. |
| runtime import smoke script | PASS | Printed `imports ok`; no circular import failure for the refactored modules. |
| `.venv/bin/python tools/headless_graphical_parity_audit.py --scenario predator_prey_medium --steps 1200 --output runs/code_health_audit_graphical_parity_audit.json` | PASS | Raw and RNG-isolated parity both passed for seed `161803`; output left under `runs/`. |
| `mkdir -p runs/code_health_audit_benchmarks && .venv/bin/python tools/benchmark.py --scenario energy_medium --seconds 5 --output runs/code_health_audit_benchmarks/energy_medium.json` | PASS | Wrote benchmark JSON; 297 frames, 299 sim steps, ~59.3 FPS overall. |
| `ruff` / `vulture` availability check | NOT RUN | Neither tool is installed/configured in the current venv/workspace. No dependencies were added. |

Generated files under `runs/` were left untracked, as requested.

## Findings by Severity

### High Risk / Should Fix Soon

- Settings overlay emits a `reset` action that `main.py` ignores.
  - Evidence: `SettingsOverlay.handle_event()` mutates and saves defaults, then returns `"reset"` at `primordial/rendering/settings_overlay.py:158-164`. The overlay action block in `primordial/main.py:263-393` handles `apply`, `discard`, `save_snapshot`, `load_snapshot`, `help`, and `reset_predator_prey_dials`, but not `reset`.
  - Why it matters: pressing `R` twice can change the live `Settings` object and save defaults without applying display/backend/theme/mode changes through the runtime path. The overlay remains visible, so runtime state can drift from settings.
  - Suggested fix: add an explicit reset action path before extracting the block. Either treat reset like apply plus sync, or change overlay reset to update pending values only until Enter.
  - Estimated risk: medium behavioral risk; fix is small but needs tests because reset affects display, mode, and persisted config.

- Loading a snapshot from the settings overlay swaps the `Simulation` without restoring run/milestone loggers.
  - Evidence: startup attaches loggers at `primordial/main.py:161-166`. Overlay load creates `loaded_simulation` and calls `_swap_loaded_simulation()` at `primordial/main.py:333-352`; `_swap_loaded_simulation()` only resizes/sets mode/resets renderer at `primordial/main.py:609-622`.
  - Why it matters: in sessions launched with `--log csv` or `--milestone-log`, loading a snapshot from the overlay can silently stop predator-prey run telemetry.
  - Suggested fix: after overlay load, reattach `csv_run_logger` and `milestone_logger`, and log a run/session transition if appropriate.
  - Estimated risk: low code risk, medium observability risk.

### Medium Risk / Good Cleanup

- The frame/debug payload construction is repeated in three runtime-like loops.
  - Evidence: `primordial/main.py:448-508`, `primordial/runtime/session.py:44-86`, and `primordial/graphical_benchmarking.py:567-613` all build nearly the same debug/timing payload around `advance_fixed_step_frame()`, `renderer.draw()`, `pygame.display.flip()`, and `build_frame_metrics()`.
  - Why it matters: future timing/debug additions can land in only one path, breaking parity between interactive, profile/benchmark, and graphical benchmark runs.
  - Suggested fix: add a small runtime helper that builds the external debug payload from timing deltas, renderer dimensions, and simulation dimensions. Do not merge the whole main loop yet.
  - Estimated risk: low if helper is pure and covered by existing fixed-step tests.

- Display setup logic is still repeated across app, probes, and graphical benchmarks.
  - Evidence: initial setup in `primordial/main.py:107-133`, transition setup in `primordial/display/mode.py:67-160`, probe setup in `primordial/graphics_probe.py:68-78`, and graphical benchmark setup in `primordial/graphical_benchmarking.py:1720-1734`.
  - Why it matters: fullscreen/windowed/GPU flag fixes can miss one path.
  - Suggested fix: after overlay action tests exist, introduce one display creation helper that supports normal/screensaver/preview/load-snapshot sizing. Keep tool-specific wrappers where they intentionally avoid app coupling.
  - Estimated risk: medium because screensaver preview and loaded snapshot sizing have special rules.

- Benchmark module mutates SDL video environment at import time.
  - Evidence: `primordial/benchmarking.py:14-16` sets `SDL_VIDEODRIVER=dummy` before importing pygame.
  - Why it matters: importing `primordial.benchmarking` in a long-lived process can force later graphical execution down the dummy path.
  - Suggested fix: move dummy SDL setup into the CLI/benchmark entrypoint or an explicit `configure_headless_benchmark_environment()` helper called before pygame import.
  - Estimated risk: medium; tests may depend on current import side effect.

- Refactor helper modules export and import underscore-prefixed helpers across package boundaries.
  - Evidence: `primordial/display/__init__.py:3-35` exports many `_...` helpers; `primordial/main.py`, `primordial/graphics_probe.py`, and tests import them.
  - Why it matters: these helpers are now package APIs in practice, but their names signal private implementation. That makes future moves riskier and obscures intended seams.
  - Suggested fix: promote stable helpers to public names where they are intended cross-module APIs; leave truly private helpers module-local.
  - Estimated risk: low mechanical risk, medium churn.

- Runtime helper modules import broad concrete types mostly for annotations.
  - Evidence: `primordial/persistence/runtime_state.py` imports `Renderer`, `Simulation`, `Settings`, and `RuntimeArgs`; most uses are annotations or duck-typed attribute access.
  - Why it matters: import smoke currently passes, but this keeps display/persistence/rendering/simulation more coupled than necessary and increases future circular import risk.
  - Suggested fix: move annotation-only imports under `TYPE_CHECKING` and quote annotations where practical.
  - Estimated risk: low.

### Low Risk / Optional

- Small stale imports remain.
  - Evidence from ad hoc AST/`rg` scan:
    - `primordial/graphical_benchmarking.py:7,12,18`: `field`, `math`, `shlex`
    - `primordial/milestone_logging.py:14-15`: `math`, `time`
    - `primordial/rendering/animations.py:24`: `field`
    - `primordial/rendering/hud.py:5`: `math`
    - `tools/run_milestone.py:14`: `sys`
    - `tests/test_inspect_mode.py:5,38-39`: `math`, `LifeStage`, `AttentionTarget`
  - Why it matters: low runtime risk; mostly noise for future linting.
  - Suggested fix: remove in a tiny cleanup commit with compile/test validation.
  - Estimated risk: very low.

- Renderer backend debug/overlay methods are near-duplicates.
  - Evidence: `_draw_inspect_overlay()`, `_build_debug_lines()`, and `_update_fps()` exist in both `primordial/rendering/renderer.py` and `primordial/rendering/gpu_renderer.py`.
  - Why it matters: backend UI behavior can drift.
  - Suggested fix: only extract pure formatting helpers first, not renderer backend structure.
  - Estimated risk: low for pure helpers, medium for renderer class changes.

## Duplicate / Near-Duplicate Code

| Area | Files | Description | Recommendation |
| --- | --- | --- | --- |
| Display setup | `primordial/main.py`, `primordial/display/mode.py`, `primordial/graphics_probe.py`, `primordial/graphical_benchmarking.py` | Similar fullscreen/windowed size, display flags, mouse visibility, and renderer resize flow. | Consolidate after overlay tests; preserve preview and snapshot sizing branches explicitly. |
| Bounded session loop | `primordial/main.py`, `primordial/runtime/session.py`, `primordial/graphical_benchmarking.py`, `primordial/graphics_probe.py` | Similar fixed-step/render/flip/timing/debug-payload sequence. | Extract pure payload/timing helpers first; do not move the whole main loop yet. |
| Debug timing payload | `primordial/main.py:454-467`, `primordial/runtime/session.py:49-62`, `primordial/graphical_benchmarking.py:574-589`, `primordial/graphics_probe.py:192-203` | Repeated scalar payload keys for HUD/debug metrics. | Add `build_external_debug_payload(...)` in `primordial/runtime/timing.py`. |
| Resize/checkpoint instrumentation | `primordial/graphics_probe.py`, `primordial/graphical_benchmarking.py` | Similar monkey-patched resize logging and checkpoint capture. | Optional shared tool helper; acceptable duplication if keeping probe lightweight. |
| Renderer UI helpers | `primordial/rendering/renderer.py`, `primordial/rendering/gpu_renderer.py` | Duplicate inspect overlay, FPS, debug line formatting, and public renderer API surface. | Share pure formatting/overlay functions only; avoid backend unification for now. |
| Parity comparison scripts | `tools/headless_graphical_parity_audit.py`, `tools/check_predator_prey_backend_parity.py` | Similar digest/compare/report structure but different questions. | Keep separate unless a third parity script appears. |
| Tool math helpers | `tools/predator_pursuit_experiment.py`, `tools/predator_repro_diagnostic.py` | Duplicate `_mean_or_none`/safe math helpers. | Optional; tool-local duplication is fine to avoid coupling. |

## Unused / Stale Code

| Symbol/File | Evidence | Recommendation |
| --- | --- | --- |
| `field` in `primordial/graphical_benchmarking.py` | Imported at line 7; no `field` use. | Remove. |
| `math` in `primordial/graphical_benchmarking.py` | Imported at line 12; no use. | Remove. |
| `shlex` in `primordial/graphical_benchmarking.py` | Imported at line 18; no use. | Remove. |
| `math`, `time` in `primordial/milestone_logging.py` | Imported at lines 14-15; no use. | Remove. |
| `field` in `primordial/rendering/animations.py` | Imported at line 24; no `field(...)` use. | Remove. |
| `math` in `primordial/rendering/hud.py` | Imported at line 5; no use. | Remove. |
| `sys` in `tools/run_milestone.py` | Imported at line 14; no use. | Remove. |
| `math`, `LifeStage`, `AttentionTarget` in `tests/test_inspect_mode.py` | Imported but not referenced. | Remove in test cleanup. |
| `primordial.benchmarking` re-exports `SCENARIOS` / `list_scenarios` by import | Not used internally, but used by `tools/benchmark.py` and tests. | Keep for now or add explicit `__all__` to make the compatibility API intentional. |

## Potential Bugs

| Area | Risk | Evidence | Suggested test/fix |
| --- | --- | --- | --- |
| Settings overlay reset | Defaults are saved and live settings mutate, but runtime does not apply reset. | `settings_overlay.py:158-164`; no `action == "reset"` branch in `main.py:263-393`. | Add an integration-style unit test for double-R reset while fullscreen/backend/mode differ; implement reset handling. |
| Overlay snapshot load | Loaded simulation loses run/milestone loggers. | Startup attaches loggers at `main.py:161-166`; overlay load swaps at `main.py:333-352` without reattach. | Test with fake loggers and snapshot load; reattach after `_swap_loaded_simulation()`. |
| Help while fullscreen | Helper forces windowed mode while overlay is open; discard does not restore fullscreen. | `_open_predator_prey_help()` calls `_force_windowed_mode()` at `runtime_state.py:138-139`; main updates pending fullscreen at `main.py:373`. | Decide intended behavior; add test for help action followed by Esc/discard. |
| Benchmark import side effect | Importing benchmark helpers forces dummy video for the whole process. | `benchmarking.py:14-16`. | Move env setup to benchmark CLI or document as intentional; add import smoke asserting graphical modules do not set dummy video. |
| Snapshot path precedence | Overlay active path uses `runtime_args.load or runtime_args.save`. | `main.py:169-172`. | Add CLI bootstrap test for `--load A --save B`; decide whether overlay save should target loaded path or save path. |
| Graphical parity coverage | Current parity audit passed, but it does not drive the actual `main.py` event loop, settings overlay, GPU backend, or screensaver modes. | Tool directly steps simulation/render path. | Keep parity audit, add smaller app-level smoke tests around imports/actions rather than relying on parity for UI behavior. |
| Circular import drift | Import smoke passes today, but persistence/display/input modules import concrete rendering/simulation types. | `runtime_state.py` and `display.mode.py` runtime imports. | Move annotation-only imports under `TYPE_CHECKING`; keep a runtime import smoke test. |

## Main.py Next Refactor Recommendation

Yes: settings-overlay action handling should be the next refactor target.

Safest extraction seam: extract only the `if renderer.settings_overlay.visible:` action handling from `primordial/main.py:261-393`, not the whole event loop. Use a small context/result shape so the helper can return updated references:

- inputs/context: `settings`, `simulation`, `renderer`, `runtime_loop`, `active_snapshot_path`, `previous_mode`, `debug`, `csv_run_logger`, `milestone_logger`
- returned state: updated `simulation`, `renderer`, `active_snapshot_path`, updated/unchanged previous mode, and a flag/callback request for mode transition
- keep `_begin_mode_transition()` in `main.py` initially; let the extracted helper return `begin_mode_transition=True`

Tests needed before extraction:

- overlay reset action applies or intentionally stages defaults
- apply action handles backend change, display change, theme/mode change, and timing debt reset
- discard resumes simulation only when fade is closing
- save/load snapshot status success/failure paths
- load snapshot reattaches run/milestone loggers
- help action fullscreen behavior is specified
- predator-prey dial reset saves tuning state and resets renderer/runtime state

## Suggested Task List

1. Fix and test settings overlay reset handling
   - scope: clarify double-R behavior and implement matching `main.py` action handling
   - files likely touched: `primordial/main.py`, `primordial/rendering/settings_overlay.py`, `tests/test_settings_overlay.py` or new runtime action test
   - validation required: `make test`, import smoke
   - risk level: medium

2. Preserve loggers when overlay loads a snapshot
   - scope: reattach CSV/milestone loggers after `_swap_loaded_simulation()`
   - files likely touched: `primordial/main.py`, tests around overlay load helper/action
   - validation required: targeted test, `make test`
   - risk level: low

3. Extract settings-overlay action handling
   - scope: move the action block into a small runtime/input helper with explicit context/result
   - files likely touched: `primordial/main.py`, new `primordial/runtime/settings_actions.py` or similar, tests
   - validation required: `make test`, compileall, import smoke
   - risk level: medium

4. Consolidate debug payload construction
   - scope: pure helper for external HUD/debug metrics used by main, bounded session, graphical benchmark, and probe
   - files likely touched: `primordial/runtime/timing.py`, `primordial/main.py`, `primordial/runtime/session.py`, `primordial/graphical_benchmarking.py`, `primordial/graphics_probe.py`
   - validation required: fixed-step tests, benchmark smoke
   - risk level: low

5. Clean stale imports
   - scope: remove the small unused imports listed above
   - files likely touched: `primordial/graphical_benchmarking.py`, `primordial/milestone_logging.py`, `primordial/rendering/animations.py`, `primordial/rendering/hud.py`, `tools/run_milestone.py`, `tests/test_inspect_mode.py`
   - validation required: compileall, `make test`
   - risk level: very low

6. Reduce import coupling and private helper API ambiguity
   - scope: move annotation-only imports to `TYPE_CHECKING`; promote intended cross-module helpers to public names
   - files likely touched: `primordial/persistence/runtime_state.py`, `primordial/display/__init__.py`, imports in `main.py`/tools/tests
   - validation required: import smoke, `make test`
   - risk level: low to medium

7. Decide benchmark import environment policy
   - scope: move or document dummy SDL setup in `primordial/benchmarking.py`
   - files likely touched: `primordial/benchmarking.py`, `tools/benchmark.py`, tests importing benchmark helpers
   - validation required: benchmark smoke, graphical benchmark test, import smoke
   - risk level: medium

## Do Not Do Yet

- Do not extract or rewrite the whole `main.py` loop before the overlay action tests exist.
- Do not merge app runtime, graphical benchmark, and probe loops into one abstraction in a single pass.
- Do not unify pygame and GPU renderer classes broadly; extract only pure shared formatting/helpers first.
- Do not change simulation behavior while doing runtime cleanup.
- Do not couple lightweight diagnostic tools to app runtime internals unless the duplication is causing real drift.
- Do not change screensaver `/s`, `/p`, or `/c` behavior without dedicated smoke tests.
