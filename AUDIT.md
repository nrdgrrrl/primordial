# Primordial Audit (2026-03-05)

Status legend: **FIXED**, **DEFERRED**, **WONTFIX**.

## main.py (root)
- **Screensaver-specific / preview HWND validation** — **FIXED**: preview mode now only activates for positive HWND values via parser hardening.

## primordial/main.py
- **Screensaver-specific / input grace** — **WONTFIX**: grace-period quit logic already checks grace timestamp before all quit-on-input branches.
- **Configuration UX** — **FIXED**: config dialog and runtime now point to user `config.toml`, not `settings.py`.
- **Interactive settings pass** — **FIXED**: `S` opens renderer overlay in normal mode only; overlay pauses simulation and supports apply/discard/reset semantics.

## primordial/config/config.py (new)
- **Correctness / corruption handling** — **FIXED**: parse failures back up bad TOML to `.bak`, then regenerate defaults.
- **Correctness / value bounds** — **FIXED**: clamps applied for range-constrained fields and nonzero divisors.
- **Persistence** — **FIXED**: first run writes default config for user discoverability.
- **Comments preservation** — **DEFERRED**: exact user comment round-tripping is not implemented; file is regenerated from typed attributes.

## primordial/settings.py
- **Architecture migration** — **FIXED**: replaced dataclass implementation with compatibility alias to new `Config` class.

## primordial/simulation/simulation.py
- **Correctness / food-cycle non-negative rate** — **FIXED**: explicit non-negative clamp in `_get_food_rate()`.
- **Correctness / divide-by-zero edge cases** — **FIXED**: guarded `max_population` and `food_cycle_period` divisors.
- **Reproduction cardinality** — **WONTFIX**: existing logic already yields at most one offspring per parent frame-check.
- **Lineage ID uniqueness** — **WONTFIX**: existing monotonic allocator already prevents duplicates.

## primordial/rendering/renderer.py
- **Interactive settings pass** — **FIXED**: renderer now owns and draws settings overlay with fade animation.
- **Performance / surface allocations** — **DEFERRED**: overlay currently allocates a full-screen shade surface each draw; low-impact but could be cached per resolution.

## primordial/rendering/settings_overlay.py (new)
- **Feature implementation** — **FIXED**: sectioned widget list, keyboard control mapping, reset confirmation, apply/discard behavior.
- **Performance** — **DEFERRED**: value text is rerendered each frame while open; acceptable for current panel size and fps budget.

## primordial/utils/screensaver.py
- **Screensaver-specific / invalid preview handle** — **FIXED**: `/p` with invalid or non-positive HWND falls back to normal mode.

## primordial/simulation/creature.py
- **Correctness checks** — **WONTFIX**: trail cap, toroidal wrapping, and trait clamping paths already satisfy audit requirements.

## primordial/simulation/food.py
- **Memory bounds** — **WONTFIX**: particle list is bounded by `max_particles`; no unbounded growth found.

## primordial/rendering/animations.py
- **Memory/perf** — **WONTFIX**: completed animations are already pruned each frame by manager tick.

## primordial/rendering/glyphs.py
- **Performance / cache invalidation timing** — **WONTFIX**: glyph cache usage remains stable; age effects are applied at render/blit layer, not glyph regeneration layer.

## primordial/rendering/hud.py
- **Code quality** — **WONTFIX**: HUD reads simulation query properties only; sim/render decoupling remains intact.

## primordial/simulation/zones.py
- **Performance** — **WONTFIX**: per-creature zone modifier is computed once in simulation loop; renderer does not recompute zone effects.

## primordial/rendering/themes.py
- **Performance / trails and glyphs** — **WONTFIX**: trail and glyph effects remain batched/cached as designed.

## primordial/__init__.py, primordial/simulation/__init__.py, primordial/rendering/__init__.py, primordial/utils/__init__.py, primordial/utils/paths.py, primordial/spec/build tooling
- **Code quality** — **WONTFIX**: no correctness/performance/memory regressions found in this pass.
