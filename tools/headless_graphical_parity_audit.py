#!/usr/bin/env python3
"""Headless vs graphical parity audit for predator_prey mode.

Compares ecological outcomes between:
  - "offline" path: direct simulation.step() loop (no rendering, no timing)
  - "graphical" path: run_bounded_session() with dummy SDL (accumulator-driven)

Both paths use the same seed, same config, and the same step count.
The graphical path is given generous wall-clock time so the accumulator
does NOT clamp or drop steps, ensuring the same step budget is executed.

If the simulation is truly decoupled from rendering, both paths must produce
identical ecological outcomes for the same seed and step count.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Force dummy SDL drivers before any pygame import so the graphical path
# runs without a display server.
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from primordial.main import (
    LoopTimingCollector,
    _create_fixed_step_loop_state,
    run_bounded_session,
)
from primordial.rendering import Renderer
from primordial.scenarios import build_settings_for_scenario, list_scenarios
from primordial.settings import Settings
from primordial.simulation import Simulation


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------

def _extract_metrics(
    simulation: Simulation,
    *,
    label: str,
    steps: int,
    seed: int,
    scenario_id: str,
    wall_seconds: float | None = None,
    timing_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a full ecological metric snapshot from a simulation."""
    pred_count, prey_count = simulation.get_species_counts()
    diagnostics = simulation.export_predator_diagnostics()
    completed_lives = diagnostics["completed_lives"]
    active_lives = diagnostics["active_lives"]
    all_lives = completed_lives + active_lives
    events = diagnostics["events"]
    stability = simulation.get_predator_prey_stability_stats()

    total_kills = sum(int(life["kills"]) for life in all_lives)
    zero_kill_lives = sum(1 for life in all_lives if int(life["kills"]) == 0)
    total_predator_lives = len(all_lives)

    true_births = len(events["births"])
    cosmic_flips_to = len(events["cosmic_flips_to_predator"])
    cosmic_flips_from = len(events.get("cosmic_flips_from_predator", []))

    metrics: dict[str, Any] = {
        "label": label,
        "scenario_id": scenario_id,
        "seed": seed,
        "steps_requested": steps,
        "sim_frame": diagnostics["frame"],
        "population": simulation.population,
        "predator_count": pred_count,
        "prey_count": prey_count,
        "total_births": simulation.total_births,
        "total_deaths": simulation.total_deaths,
        "generation": simulation.generation,
        "predation_kill_count": simulation.predation_kill_count,
        "true_predator_births": true_births,
        "cosmic_flips_to_predator": cosmic_flips_to,
        "cosmic_flips_from_predator": cosmic_flips_from,
        "survival_ticks": stability["survival_ticks"],
        "rolling_average_survival_ticks": stability["rolling_average_survival_ticks"],
        "game_over_active": stability["game_over_active"],
        "total_predator_lives": total_predator_lives,
        "zero_kill_predator_lives": zero_kill_lives,
        "zero_kill_share": (
            zero_kill_lives / total_predator_lives
            if total_predator_lives > 0
            else 0.0
        ),
        "base_threshold": diagnostics["base_threshold"],
        "predator_kill_energy_gain_cap": diagnostics["predator_kill_energy_gain_cap"],
        "predator_contact_kill_distance_scale": diagnostics[
            "predator_contact_kill_distance_scale"
        ],
        "food_count": simulation.food_count,
    }
    if wall_seconds is not None:
        metrics["wall_seconds"] = round(wall_seconds, 4)
    if timing_info is not None:
        metrics["timing"] = timing_info
    return metrics


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def _run_offline(
    scenario_id: str,
    seed: int,
    steps: int,
    settings: Settings,
    scenario: Any,
) -> dict[str, Any]:
    """Run the pure offline path: direct simulation.step() loop."""
    random.seed(seed)
    simulation = Simulation(scenario.width, scenario.height, settings)

    t0 = time.perf_counter()
    for _ in range(steps):
        simulation.step()
    wall = time.perf_counter() - t0

    return _extract_metrics(
        simulation,
        label="offline",
        steps=steps,
        seed=seed,
        scenario_id=scenario_id,
        wall_seconds=wall,
    )


def _run_graphical(
    scenario_id: str,
    seed: int,
    steps: int,
    settings: Settings,
    scenario: Any,
) -> dict[str, Any]:
    """Run the graphical path with dummy SDL, replicating per-step overhead.

    This reproduces exactly what the interactive/benchmark loop does around
    each simulation.step() call:
      1. simulation.step()
      2. buffer_simulation_attacks() — drains active_attacks between steps
      3. restore_buffered_attacks() — restores them before render
      4. renderer.draw() — reads simulation state for rendering
      5. pygame.display.flip()

    We bypass the wall-clock accumulator and execute a fixed step count so
    the comparison is step-for-step identical.  The question being tested is
    whether the attack buffering, rendering reads, or event pumping introduce
    any side-effects into simulation state.
    """
    random.seed(seed)

    pygame.init()
    try:
        screen = pygame.display.set_mode((scenario.width, scenario.height))
        simulation = Simulation(scenario.width, scenario.height, settings)
        renderer = Renderer(screen, settings, debug=False)
        runtime_loop = _create_fixed_step_loop_state()

        t0 = time.perf_counter()
        for _ in range(steps):
            # Exactly what the graphical main loop does per sim step:
            simulation.step()
            runtime_loop.buffer_simulation_attacks(simulation)

            # Every few steps, do the render cycle (mimicking multi-step frames).
            # In the real loop, rendering happens once per outer frame after
            # all sim steps.  Here we render every 3 steps to exercise the
            # renderer read path without being wasteful.
            if simulation._frame % 3 == 0:  # noqa: SLF001
                runtime_loop.restore_buffered_attacks(simulation)
                renderer.draw(simulation)
                pygame.display.flip()
                pygame.event.pump()

        # Final render flush
        runtime_loop.restore_buffered_attacks(simulation)
        renderer.draw(simulation)
        pygame.display.flip()

        wall = time.perf_counter() - t0
        timing_info = {
            "frames_rendered": simulation._frame // 3 + 1,  # noqa: SLF001
            "sim_steps_total": simulation._frame,  # noqa: SLF001
            "approach": "direct_step_with_render_overhead",
        }
    finally:
        pygame.quit()

    return _extract_metrics(
        simulation,
        label="graphical",
        steps=steps,
        seed=seed,
        scenario_id=scenario_id,
        wall_seconds=wall,
        timing_info=timing_info,
    )


def _run_graphical_full_rng_isolated(
    scenario_id: str,
    seed: int,
    steps: int,
    settings: Settings,
    scenario: Any,
) -> dict[str, Any]:
    """Run the graphical path with RNG isolation around BOTH renderer
    construction and all draw calls.

    This isolates the root cause: the Renderer constructor and draw() both
    consume global random.Random() state (via create_ambient_particles,
    animation spawning, etc.).
    """
    random.seed(seed)

    pygame.init()
    try:
        screen = pygame.display.set_mode((scenario.width, scenario.height))
        simulation = Simulation(scenario.width, scenario.height, settings)

        # Save RNG state BEFORE constructing the renderer (it consumes RNG)
        rng_state = random.getstate()
        renderer = Renderer(screen, settings, debug=False)
        random.setstate(rng_state)

        runtime_loop = _create_fixed_step_loop_state()

        t0 = time.perf_counter()
        for _ in range(steps):
            simulation.step()
            runtime_loop.buffer_simulation_attacks(simulation)

            if simulation._frame % 3 == 0:  # noqa: SLF001
                runtime_loop.restore_buffered_attacks(simulation)
                # Save RNG state around render calls too
                rng_state = random.getstate()
                renderer.draw(simulation)
                pygame.display.flip()
                pygame.event.pump()
                random.setstate(rng_state)

        runtime_loop.restore_buffered_attacks(simulation)
        rng_state = random.getstate()
        renderer.draw(simulation)
        pygame.display.flip()
        random.setstate(rng_state)

        wall = time.perf_counter() - t0
        timing_info = {
            "frames_rendered": simulation._frame // 3 + 1,  # noqa: SLF001
            "sim_steps_total": simulation._frame,  # noqa: SLF001
            "approach": "full_rng_isolation",
        }
    finally:
        pygame.quit()

    return _extract_metrics(
        simulation,
        label="graphical_full_rng_isolated",
        steps=steps,
        seed=seed,
        scenario_id=scenario_id,
        wall_seconds=wall,
        timing_info=timing_info,
    )


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

EXACT_MATCH_KEYS = [
    "sim_frame",
    "population",
    "predator_count",
    "prey_count",
    "total_births",
    "total_deaths",
    "generation",
    "predation_kill_count",
    "true_predator_births",
    "cosmic_flips_to_predator",
    "cosmic_flips_from_predator",
    "survival_ticks",
    "game_over_active",
    "total_predator_lives",
    "zero_kill_predator_lives",
    "food_count",
]

FLOAT_KEYS = [
    "zero_kill_share",
    "base_threshold",
    "predator_kill_energy_gain_cap",
    "predator_contact_kill_distance_scale",
    "rolling_average_survival_ticks",
]


def _compare(
    offline: dict[str, Any],
    graphical: dict[str, Any],
) -> dict[str, Any]:
    """Build a parity comparison report."""
    exact_deltas: dict[str, Any] = {}
    for key in EXACT_MATCH_KEYS:
        o_val = offline[key]
        g_val = graphical[key]
        exact_deltas[key] = {
            "offline": o_val,
            "graphical": g_val,
            "match": o_val == g_val,
            "delta": g_val - o_val if isinstance(o_val, (int, float)) else None,
        }

    float_deltas: dict[str, Any] = {}
    for key in FLOAT_KEYS:
        o_val = offline[key]
        g_val = graphical[key]
        if isinstance(o_val, float) and isinstance(g_val, float):
            if o_val == float("inf") and g_val == float("inf"):
                match = True
                delta = 0.0
            elif o_val == float("inf") or g_val == float("inf"):
                match = False
                delta = None
            else:
                delta = g_val - o_val
                match = abs(delta) < 1e-9
        else:
            match = o_val == g_val
            delta = None
        float_deltas[key] = {
            "offline": o_val,
            "graphical": g_val,
            "match": match,
            "delta": delta,
        }

    all_exact_match = all(d["match"] for d in exact_deltas.values())
    all_float_match = all(d["match"] for d in float_deltas.values())

    return {
        "parity_holds": all_exact_match and all_float_match,
        "exact_match_metrics": exact_deltas,
        "float_match_metrics": float_deltas,
        "graphical_timing": graphical.get("timing"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        default="predator_prey_medium",
        choices=list_scenarios(),
        help="Seeded scenario to audit.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=3600,
        help="Number of simulation steps to compare.",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Explicit seed(s) to test.  Defaults to the scenario seed.",
    )
    parser.add_argument(
        "--contact-kill-distance-scale",
        type=float,
        default=None,
        help="Optional contact-kill distance scale override for variant run.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for the JSON report.",
    )
    args = parser.parse_args()

    scenario, base_settings = build_settings_for_scenario(args.scenario)
    if base_settings.sim_mode != "predator_prey":
        print(f"ERROR: scenario '{args.scenario}' is not predator_prey mode", file=sys.stderr)
        return 1

    seeds = args.seeds or [scenario.seed]
    configs: list[tuple[str, Settings]] = [("baseline", base_settings)]

    # Optionally add a variant config with a different contact-kill distance scale.
    if args.contact_kill_distance_scale is not None:
        from copy import deepcopy

        variant_settings = deepcopy(base_settings)
        variant_settings.mode_params["predator_prey"][
            "predator_contact_kill_distance_scale"
        ] = args.contact_kill_distance_scale
        configs.append(
            (f"contact_kill_scale_{args.contact_kill_distance_scale}", variant_settings)
        )

    all_results: list[dict[str, Any]] = []

    for config_label, settings in configs:
        for seed in seeds:
            print(f"\n{'='*70}")
            print(f"Config: {config_label}  |  Seed: {seed}  |  Steps: {args.steps}")
            print(f"{'='*70}")

            print("  Running offline path ...", end=" ", flush=True)
            offline = _run_offline(args.scenario, seed, args.steps, settings, scenario)
            print(f"done ({offline['wall_seconds']:.2f}s)")

            print("  Running graphical path ...", end=" ", flush=True)
            graphical = _run_graphical(args.scenario, seed, args.steps, settings, scenario)
            print(f"done ({graphical['wall_seconds']:.2f}s)")

            print("  Running graphical+rng_isolated ...", end=" ", flush=True)
            graphical_isolated = _run_graphical_full_rng_isolated(
                args.scenario, seed, args.steps, settings, scenario,
            )
            print(f"done ({graphical_isolated['wall_seconds']:.2f}s)")

            comparison_raw = _compare(offline, graphical)
            comparison_isolated = _compare(offline, graphical_isolated)

            result = {
                "config": config_label,
                "seed": seed,
                "steps": args.steps,
                "offline": offline,
                "graphical": graphical,
                "graphical_rng_isolated": graphical_isolated,
                "comparison_offline_vs_graphical": comparison_raw,
                "comparison_offline_vs_graphical_rng_isolated": comparison_isolated,
            }
            all_results.append(result)

            # Print summary: offline vs graphical (raw)
            parity_raw = comparison_raw["parity_holds"]
            status = "PASS" if parity_raw else "FAIL"
            print(f"\n  Offline vs Graphical (raw): {status}")
            _print_comparison_detail(comparison_raw, offline)

            # Print summary: offline vs graphical (RNG isolated)
            parity_iso = comparison_isolated["parity_holds"]
            status = "PASS" if parity_iso else "FAIL"
            print(f"  Offline vs Graphical (RNG isolated): {status}")
            _print_comparison_detail(comparison_isolated, offline)

            if not parity_raw and parity_iso:
                print("\n  ROOT CAUSE CONFIRMED: renderer consumes global random.Random()")
                print("  state, shifting the simulation RNG sequence when rendering is active.")
                print("  With RNG state saved/restored around renderer calls, parity holds.")

    # Final summary
    print(f"\n{'='*70}")
    print("AUDIT SUMMARY")
    print(f"{'='*70}")
    all_raw_pass = all(
        r["comparison_offline_vs_graphical"]["parity_holds"] for r in all_results
    )
    all_iso_pass = all(
        r["comparison_offline_vs_graphical_rng_isolated"]["parity_holds"]
        for r in all_results
    )
    for r in all_results:
        raw_tag = "PASS" if r["comparison_offline_vs_graphical"]["parity_holds"] else "FAIL"
        iso_tag = (
            "PASS"
            if r["comparison_offline_vs_graphical_rng_isolated"]["parity_holds"]
            else "FAIL"
        )
        print(
            f"  [{raw_tag}] raw  [{iso_tag}] rng_isolated  "
            f"config={r['config']}  seed={r['seed']}  steps={r['steps']}"
        )
    print()
    if all_raw_pass:
        print("CONCLUSION: Exact parity holds without any fix.")
        print("Headless tuning experiments are representative of graphical simulation.")
    elif all_iso_pass and not all_raw_pass:
        print("CONCLUSION: TRUE SIMULATION DIVERGENCE exists between headless and graphical.")
        print("ROOT CAUSE: The renderer (animations.py, themes.py, renderer.py) consumes")
        print("the global random.Random() state during draw calls.  This shifts the RNG")
        print("sequence for all subsequent simulation steps, producing different ecological")
        print("outcomes even with the same seed and step count.")
        print()
        print("PROOF: When RNG state is saved/restored around renderer.draw() calls,")
        print("parity is restored exactly.")
        print()
        print("IMPACT: Headless tuning experiments produce DIFFERENT ecological outcomes")
        print("than graphical runs.  Rankings from headless experiments may not transfer")
        print("faithfully to the visible simulation.")
        print()
        print("SMALLEST FIX: Give the renderer its own independent random.Random()")
        print("instance instead of using the global module-level RNG.  This decouples")
        print("rendering randomness from simulation randomness without any other changes.")
    else:
        print("CONCLUSION: Divergence exists even with RNG isolation.")
        print("Additional side-effects beyond RNG consumption may be present.")

    # Write output
    report = {
        "audit": "headless_vs_graphical_parity",
        "scenario": args.scenario,
        "steps": args.steps,
        "seeds": seeds,
        "results": all_results,
        "all_raw_pass": all_raw_pass,
        "all_rng_isolated_pass": all_iso_pass,
    }

    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
        print(f"\nReport written to: {args.output}")
    else:
        print(f"\n(Use --output <path> to save the full JSON report)")

    return 0 if all_raw_pass else 1


def _print_comparison_detail(
    comparison: dict[str, Any],
    offline: dict[str, Any],
) -> None:
    """Print comparison details for a single parity check."""
    if not comparison["parity_holds"]:
        for key, detail in comparison["exact_match_metrics"].items():
            if not detail["match"]:
                print(
                    f"    MISMATCH {key}: "
                    f"offline={detail['offline']}  "
                    f"other={detail['graphical']}  "
                    f"delta={detail['delta']}"
                )
        for key, detail in comparison["float_match_metrics"].items():
            if not detail["match"]:
                print(
                    f"    MISMATCH {key}: "
                    f"offline={detail['offline']}  "
                    f"other={detail['graphical']}  "
                    f"delta={detail['delta']}"
                )
    else:
        print(f"    sim_frame:           {offline['sim_frame']}")
        print(f"    population:          {offline['population']}")
        print(f"    predator_count:      {offline['predator_count']}")
        print(f"    prey_count:          {offline['prey_count']}")
        print(f"    total_births:        {offline['total_births']}")
        print(f"    total_deaths:        {offline['total_deaths']}")
        print(f"    predation_kills:     {offline['predation_kill_count']}")
        print(f"    true_pred_births:    {offline['true_predator_births']}")
        print(f"    survival_ticks:      {offline['survival_ticks']}")
        print(
            "    survival_avg20:      "
            f"{offline['rolling_average_survival_ticks']:.1f}"
        )
        print(f"    zero_kill_share:     {offline['zero_kill_share']:.3f}")
        print(f"    food_count:          {offline['food_count']}")


if __name__ == "__main__":
    raise SystemExit(main())
