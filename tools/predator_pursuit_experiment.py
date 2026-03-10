#!/usr/bin/env python3
"""Run a bounded predator pursuit experiment matrix for predator_prey mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys
from statistics import mean
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from predator_repro_diagnostic import _build_report, _detect_window

from primordial.scenarios import build_settings_for_scenario, list_scenarios
from primordial.simulation import Simulation


BASELINE_EXPERIMENT = {"name": "baseline", "overrides": {}}
SINGLE_LEVER_EXPERIMENTS = (
    {
        "name": "sense_up",
        "overrides": {"predator_hunt_sense_multiplier": 2.3},
    },
    {
        "name": "speed_up",
        "overrides": {"predator_hunt_speed_multiplier": 1.15},
    },
    {
        "name": "contact_up",
        "overrides": {"predator_contact_kill_distance_scale": 1.2},
    },
)


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0.0:
        return None
    return float(numerator / denominator)


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0.0:
        return 0.0
    return float(numerator / denominator)


def _aggregate_reports(
    *,
    scenario_id: str,
    steps: int,
    seed_reports: list[dict[str, Any]],
    overrides: dict[str, float],
) -> dict[str, Any]:
    births = [int(report["continuity"]["predator_births"]) for report in seed_reports]
    rescues = [int(report["continuity"]["predator_rescues"]) for report in seed_reports]
    kills_per_life = [
        float(report["kills"]["mean_kills_per_life"] or 0.0)
        for report in seed_reports
    ]
    zero_kill_shares = []
    threshold_crossers = []
    threshold_crosser_shares = []
    highest_energies = []
    energy_before_kill = []
    energy_after_kill = []
    end_predators = []
    end_prey = []
    prey_mean_in_window = []
    prey_min_in_window = []
    window_starts = []
    total_lives = 0
    total_zero_kill_lives = 0
    total_crossers = 0
    total_births = sum(births)
    total_rescues = sum(rescues)

    for report in seed_reports:
        distribution = report["kills"]["distribution"]
        lives = int(report["kills"]["lives_started_in_window"])
        zero_kill = int(distribution["0"])
        crossers = int(report["energy"]["repro_check_reached_threshold_lives"])
        total_lives += lives
        total_zero_kill_lives += zero_kill
        total_crossers += crossers
        zero_kill_shares.append(_safe_divide(zero_kill, lives))
        threshold_crossers.append(crossers)
        threshold_crosser_shares.append(_safe_divide(crossers, lives))
        highest_energies.append(float(report["energy"]["mean_highest_energy_per_life"] or 0.0))
        energy_before_kill.append(float(report["energy"]["mean_energy_before_kill"] or 0.0))
        energy_after_kill.append(float(report["energy"]["mean_energy_after_kill"] or 0.0))
        end_predators.append(int(report["population"]["predators_end"]))
        end_prey.append(int(report["population"]["prey_end"]))
        prey_mean_in_window.append(float(report["population"]["prey_mean_in_window"] or 0.0))
        prey_min = report["population"]["minimum_prey_in_window"]
        prey_min_in_window.append(float(prey_min if prey_min is not None else 0.0))
        window_starts.append(int(report["window"]["start_step"]))

    return {
        "scenario": scenario_id,
        "steps": steps,
        "overrides": overrides,
        "window_starts": window_starts,
        "predator_births_total": total_births,
        "predator_rescues_total": total_rescues,
        "births_to_rescues_ratio": _safe_ratio(float(total_births), float(total_rescues)),
        "mean_births_per_run": _mean_or_none([float(value) for value in births]),
        "mean_rescues_per_run": _mean_or_none([float(value) for value in rescues]),
        "mean_kills_per_life": _mean_or_none(kills_per_life),
        "zero_kill_life_share": _safe_divide(total_zero_kill_lives, total_lives),
        "mean_zero_kill_share_per_run": _mean_or_none(zero_kill_shares),
        "mean_energy_before_kill": _mean_or_none(energy_before_kill),
        "mean_energy_after_kill": _mean_or_none(energy_after_kill),
        "mean_highest_energy_per_life": _mean_or_none(highest_energies),
        "repro_threshold_crossers": total_crossers,
        "repro_threshold_crosser_share": _safe_divide(total_crossers, total_lives),
        "mean_threshold_crosser_share_per_run": _mean_or_none(threshold_crosser_shares),
        "mean_end_predators": _mean_or_none([float(value) for value in end_predators]),
        "mean_end_prey": _mean_or_none([float(value) for value in end_prey]),
        "mean_prey_in_window": _mean_or_none(prey_mean_in_window),
        "mean_minimum_prey_in_window": _mean_or_none(prey_min_in_window),
        "total_lives_started_in_window": total_lives,
        "per_seed": seed_reports,
    }


def _ranking_tuple(aggregate: dict[str, Any]) -> tuple[float, float, float, float]:
    prey_stability = float(aggregate["mean_prey_in_window"] or 0.0)
    births_to_rescues = float(aggregate["births_to_rescues_ratio"] or 0.0)
    end_predators = float(aggregate["mean_end_predators"] or 0.0)
    zero_kill_share = float(aggregate["zero_kill_life_share"] or 1.0)
    return (
        births_to_rescues,
        end_predators,
        prey_stability,
        -zero_kill_share,
    )


def _run_one(
    *,
    scenario_id: str,
    steps: int,
    seed: int,
    sustain_steps: int,
    low_predator_threshold: int,
    overrides: dict[str, float],
) -> dict[str, Any]:
    scenario, settings = build_settings_for_scenario(scenario_id)
    if settings.sim_mode != "predator_prey":
        raise ValueError("predator pursuit experiment requires predator_prey mode")
    settings.mode_params["predator_prey"].update(overrides)

    random.seed(seed)
    simulation = Simulation(scenario.width, scenario.height, settings)

    predator_counts = []
    predator_count, prey_count = simulation.get_species_counts()
    predator_counts.append({"step": 0, "predators": predator_count, "prey": prey_count})
    for step in range(1, steps + 1):
        simulation.step()
        predator_count, prey_count = simulation.get_species_counts()
        predator_counts.append({"step": step, "predators": predator_count, "prey": prey_count})

    window = _detect_window(
        predator_counts,
        initial_predators=predator_counts[0]["predators"],
        low_predator_threshold=low_predator_threshold,
        sustain_steps=sustain_steps,
    )
    return _build_report(
        simulation=simulation,
        predator_counts=predator_counts,
        steps=steps,
        seed=seed,
        scenario_id=scenario.id,
        window=window,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        default="predator_prey_medium",
        choices=list_scenarios(),
        help="Seeded scenario identifier.",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=4800,
        help="Number of simulation steps to execute per seed.",
    )
    parser.add_argument(
        "--seed-start",
        type=int,
        default=161803,
        help="Starting seed for the bounded sweep.",
    )
    parser.add_argument(
        "--seed-count",
        type=int,
        default=5,
        help="How many consecutive seeds to run.",
    )
    parser.add_argument(
        "--low-predator-threshold",
        type=int,
        default=4,
        help="Explicit low-predator threshold for the post-collapse window.",
    )
    parser.add_argument(
        "--sustain-steps",
        type=int,
        default=45,
        help="Consecutive low-predator steps required to start the main window.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON experiment summary.",
    )
    args = parser.parse_args()

    seeds = [args.seed_start + offset for offset in range(args.seed_count)]
    experiments: list[dict[str, Any]] = [BASELINE_EXPERIMENT, *SINGLE_LEVER_EXPERIMENTS]
    aggregates: dict[str, dict[str, Any]] = {}

    for experiment in experiments:
        reports = [
            _run_one(
                scenario_id=args.scenario,
                steps=args.steps,
                seed=seed,
                sustain_steps=args.sustain_steps,
                low_predator_threshold=args.low_predator_threshold,
                overrides=experiment["overrides"],
            )
            for seed in seeds
        ]
        aggregates[experiment["name"]] = _aggregate_reports(
            scenario_id=args.scenario,
            steps=args.steps,
            seed_reports=reports,
            overrides=experiment["overrides"],
        )

    ranked_single_names = sorted(
        (experiment["name"] for experiment in SINGLE_LEVER_EXPERIMENTS),
        key=lambda name: _ranking_tuple(aggregates[name]),
        reverse=True,
    )
    combo_overrides: dict[str, float] = {}
    combo_name = None
    if len(ranked_single_names) >= 2:
        best_first = next(
            experiment for experiment in SINGLE_LEVER_EXPERIMENTS if experiment["name"] == ranked_single_names[0]
        )
        best_second = next(
            experiment for experiment in SINGLE_LEVER_EXPERIMENTS if experiment["name"] == ranked_single_names[1]
        )
        combo_overrides = dict(best_first["overrides"])
        combo_overrides.update(best_second["overrides"])
        combo_name = f"{ranked_single_names[0]}__{ranked_single_names[1]}"
        reports = [
            _run_one(
                scenario_id=args.scenario,
                steps=args.steps,
                seed=seed,
                sustain_steps=args.sustain_steps,
                low_predator_threshold=args.low_predator_threshold,
                overrides=combo_overrides,
            )
            for seed in seeds
        ]
        aggregates[combo_name] = _aggregate_reports(
            scenario_id=args.scenario,
            steps=args.steps,
            seed_reports=reports,
            overrides=combo_overrides,
        )

    payload = {
        "scenario": args.scenario,
        "steps": args.steps,
        "seeds": seeds,
        "window_rule": (
            f"first sustained low-predator regime: predators <= {args.low_predator_threshold} "
            f"for {args.sustain_steps} consecutive steps"
        ),
        "experiments": aggregates,
        "ranked_single_levers": ranked_single_names,
        "combo_experiment": combo_name,
    }

    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
