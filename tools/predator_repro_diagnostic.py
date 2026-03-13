#!/usr/bin/env python3
"""Run a focused predator reproduction diagnostic for predator_prey mode."""

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

from primordial.scenarios import build_settings_for_scenario, list_scenarios
from primordial.simulation import Simulation


def _detect_window(
    counts: list[dict[str, int]],
    *,
    initial_predators: int,
    low_predator_threshold: int | None,
    sustain_steps: int,
) -> dict[str, Any]:
    threshold = (
        low_predator_threshold
        if low_predator_threshold is not None
        else max(2, int(round(initial_predators * 0.12)))
    )
    threshold = min(max(1, threshold), max(1, initial_predators))

    for start in range(len(counts)):
        end = start + sustain_steps
        if end > len(counts):
            break
        if all(sample["predators"] <= threshold for sample in counts[start:end]):
            return {
                "start_step": counts[start]["step"],
                "low_predator_threshold": threshold,
                "sustain_steps": sustain_steps,
                "reason": (
                    f"first sustained low-predator regime: "
                    f"predators <= {threshold} for {sustain_steps} consecutive steps"
                ),
                "fallback": False,
            }

    minimum = min(sample["predators"] for sample in counts)
    for sample in counts:
        if sample["predators"] == minimum:
            return {
                "start_step": sample["step"],
                "low_predator_threshold": threshold,
                "sustain_steps": sustain_steps,
                "reason": (
                    "fallback window: no sustained low regime found; using first minimum "
                    f"predator count ({minimum})"
                ),
                "fallback": True,
            }
    raise RuntimeError("window detection failed")


def _flatten(values: list[list[float]]) -> list[float]:
    flattened: list[float] = []
    for bucket in values:
        flattened.extend(bucket)
    return flattened


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _kill_distribution(lives: list[dict[str, Any]]) -> dict[str, int]:
    distribution = {"0": 0, "1": 0, "2": 0, "3+": 0}
    for life in lives:
        kills = int(life["kills"])
        if kills >= 3:
            distribution["3+"] += 1
        else:
            distribution[str(kills)] += 1
    return distribution


def _build_report(
    *,
    simulation: Simulation,
    predator_counts: list[dict[str, int]],
    steps: int,
    seed: int,
    scenario_id: str,
    window: dict[str, Any],
) -> dict[str, Any]:
    diagnostics = simulation.export_predator_diagnostics()
    completed_lives = diagnostics["completed_lives"]
    active_lives = diagnostics["active_lives"]
    all_lives = completed_lives + active_lives
    window_start = int(window["start_step"])

    carryover_lives = [
        life
        for life in all_lives
        if life["start_frame"] < window_start
        and (life["end_frame"] is None or life["end_frame"] >= window_start)
    ]
    post_window_started_lives = [
        life for life in all_lives if int(life["start_frame"]) >= window_start
    ]
    post_window_completed_lives = [
        life
        for life in completed_lives
        if life["end_frame"] is not None and int(life["end_frame"]) >= window_start
    ]

    events = diagnostics["events"]
    births = [event for event in events["births"] if int(event["frame"]) >= window_start]
    flips_to_predator = [
        event
        for event in events["cosmic_flips_to_predator"]
        if int(event["frame"]) >= window_start
    ]

    pre_kill_energies = _flatten([life["kill_pre_energies"] for life in post_window_started_lives])
    post_kill_energies = _flatten([life["kill_post_energies"] for life in post_window_started_lives])
    peak_energies = [float(life["highest_energy"]) for life in post_window_started_lives]
    closest_repro_gaps = [
        float(life["closest_repro_check_gap"])
        for life in post_window_completed_lives
        if life["closest_repro_check_gap"] is not None
        and not life["repro_check_reached_threshold"]
    ]

    predator_counts_in_window = [
        sample["predators"]
        for sample in predator_counts
        if int(sample["step"]) >= window_start
    ]
    prey_counts_in_window = [
        sample["prey"]
        for sample in predator_counts
        if int(sample["step"]) >= window_start
    ]

    recovery_sources: list[str] = []
    if births:
        recovery_sources.append("true births")
    if flips_to_predator:
        recovery_sources.append("cosmic flip")
    if not recovery_sources:
        recovery_sources.append("neither")

    if len(births) > len(flips_to_predator) and len(births) > 0:
        continuity_mode = "mostly birth-driven"
    elif len(flips_to_predator) > len(births) and len(flips_to_predator) > 0:
        continuity_mode = "mostly cosmic-flip-driven"
    elif len(births) == len(flips_to_predator) == 0:
        continuity_mode = "neither births nor cosmic flips restored predators"
    else:
        continuity_mode = "mixed birth/flip continuity"

    return {
        "scenario": scenario_id,
        "seed": seed,
        "steps": steps,
        "window": window,
        "population": {
            "initial_predators": predator_counts[0]["predators"],
            "initial_prey": predator_counts[0]["prey"],
            "minimum_predators": min(sample["predators"] for sample in predator_counts),
            "minimum_prey": min(sample["prey"] for sample in predator_counts),
            "predators_at_window_start": next(
                sample["predators"]
                for sample in predator_counts
                if int(sample["step"]) == window_start
            ),
            "predators_end": predator_counts[-1]["predators"],
            "prey_end": predator_counts[-1]["prey"],
            "predator_mean_in_window": _mean_or_none(predator_counts_in_window),
            "prey_mean_in_window": _mean_or_none(prey_counts_in_window),
            "minimum_prey_in_window": min(prey_counts_in_window) if prey_counts_in_window else None,
        },
        "continuity": {
            "mode": continuity_mode,
            "recovery_sources": recovery_sources,
            "carryover_lives_at_window_start": len(carryover_lives),
            "predator_births": len(births),
            "predator_cosmic_flips_to_predator": len(flips_to_predator),
            "active_end_origins": _count_by(active_lives, "origin"),
        },
        "kills": {
            "lives_started_in_window": len(post_window_started_lives),
            "distribution": _kill_distribution(post_window_started_lives),
            "mean_kills_per_life": _mean_or_none(
                [float(life["kills"]) for life in post_window_started_lives]
            ),
            "mean_cross_band_contact_misses_per_life": _mean_or_none(
                [float(life["cross_band_contact_misses"]) for life in post_window_started_lives]
            ),
        },
        "energy": {
            "mean_energy_before_kill": _mean_or_none(pre_kill_energies),
            "mean_energy_after_kill": _mean_or_none(post_kill_energies),
            "mean_highest_energy_per_life": _mean_or_none(peak_energies),
            "max_highest_energy_per_life": max(peak_energies) if peak_energies else None,
            "peak_reached_threshold_lives": sum(
                1 for life in post_window_started_lives if life["peak_reached_threshold"]
            ),
            "repro_check_reached_threshold_lives": sum(
                1
                for life in post_window_started_lives
                if life["repro_check_reached_threshold"]
            ),
            "near_miss_lives_within_0_02": sum(gap <= 0.02 for gap in closest_repro_gaps),
            "near_miss_lives_within_0_05": sum(gap <= 0.05 for gap in closest_repro_gaps),
            "mean_closest_repro_gap_for_non_crossers": _mean_or_none(closest_repro_gaps),
        },
        "threshold": {
            "base_threshold": diagnostics["base_threshold"],
            "lives_with_dynamic_threshold_discount": sum(
                1
                for life in post_window_started_lives
                if life["threshold_min"] is not None
                and life["threshold_max"] is not None
                and float(life["threshold_min"]) < float(life["threshold_max"])
            ),
            "threshold_min_seen": min(
                (float(life["threshold_min"]) for life in post_window_started_lives if life["threshold_min"] is not None),
                default=None,
            ),
            "threshold_max_seen": max(
                (float(life["threshold_max"]) for life in post_window_started_lives if life["threshold_max"] is not None),
                default=None,
            ),
        },
        "kill_reward": {
            "predator_kill_energy_gain_cap": diagnostics["predator_kill_energy_gain_cap"],
        },
        "pursuit": {
            "predator_hunt_sense_multiplier": diagnostics["predator_hunt_sense_multiplier"],
            "predator_hunt_speed_multiplier": diagnostics["predator_hunt_speed_multiplier"],
            "predator_contact_kill_distance_scale": (
                diagnostics["predator_contact_kill_distance_scale"]
            ),
        },
        "deaths": {
            "causes": _count_by(post_window_completed_lives, "death_cause"),
            "contexts": _count_by(post_window_completed_lives, "death_context"),
            "mean_prey_scarce_frames_per_life": _mean_or_none(
                [float(life["prey_scarce_frames"]) for life in post_window_completed_lives]
            ),
        },
    }


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
        default=3600,
        help="Number of simulation steps to execute.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="Optional explicit seed override for the scenario.",
    )
    parser.add_argument(
        "--low-predator-threshold",
        type=int,
        help="Optional explicit low-predator threshold for the diagnostic window.",
    )
    parser.add_argument(
        "--sustain-steps",
        type=int,
        default=45,
        help="Consecutive low-predator steps required to start the main window.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    parser.add_argument(
        "--predator-kill-energy-gain-cap",
        type=float,
        help="Optional override for predator kill energy gain cap.",
    )
    parser.add_argument(
        "--predator-hunt-sense-multiplier",
        type=float,
        help="Optional override for predator hunt sensing multiplier.",
    )
    parser.add_argument(
        "--predator-hunt-speed-multiplier",
        type=float,
        help="Optional override for predator hunt steering speed multiplier.",
    )
    parser.add_argument(
        "--predator-contact-kill-distance-scale",
        type=float,
        help="Optional override for predator contact-kill distance scale.",
    )
    args = parser.parse_args()

    scenario, settings = build_settings_for_scenario(args.scenario)
    if settings.sim_mode != "predator_prey":
        raise ValueError("predator reproduction diagnostic requires predator_prey mode")
    if args.predator_kill_energy_gain_cap is not None:
        settings.mode_params["predator_prey"]["predator_kill_energy_gain_cap"] = (
            args.predator_kill_energy_gain_cap
        )
    if args.predator_hunt_sense_multiplier is not None:
        settings.mode_params["predator_prey"]["predator_hunt_sense_multiplier"] = (
            args.predator_hunt_sense_multiplier
        )
    if args.predator_hunt_speed_multiplier is not None:
        settings.mode_params["predator_prey"]["predator_hunt_speed_multiplier"] = (
            args.predator_hunt_speed_multiplier
        )
    if args.predator_contact_kill_distance_scale is not None:
        settings.mode_params["predator_prey"]["predator_contact_kill_distance_scale"] = (
            args.predator_contact_kill_distance_scale
        )

    resolved_seed = scenario.seed if args.seed is None else args.seed
    random.seed(resolved_seed)
    simulation = Simulation(scenario.width, scenario.height, settings)

    predator_counts = []
    predator_count, prey_count = simulation.get_species_counts()
    predator_counts.append({"step": 0, "predators": predator_count, "prey": prey_count})
    for step in range(1, args.steps + 1):
        simulation.step()
        predator_count, prey_count = simulation.get_species_counts()
        predator_counts.append({"step": step, "predators": predator_count, "prey": prey_count})

    window = _detect_window(
        predator_counts,
        initial_predators=predator_counts[0]["predators"],
        low_predator_threshold=args.low_predator_threshold,
        sustain_steps=args.sustain_steps,
    )
    report = _build_report(
        simulation=simulation,
        predator_counts=predator_counts,
        steps=args.steps,
        seed=resolved_seed,
        scenario_id=scenario.id,
        window=window,
    )

    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
