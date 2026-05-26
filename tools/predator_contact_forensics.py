#!/usr/bin/env python3
"""External predator contact forensics for predator_prey mode.

This tool observes simulation state from outside the simulation loop and tries
to explain why close predator/prey encounters fail to convert into kills.

Important limits:
- It does not inspect private target-selection state.
- It infers the likely prey of interest as the nearest prey to each predator.
- Near-contact follow-up kill windows are based on total predation kill-count
  increases, so they are an approximation rather than a target-identity proof.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primordial.settings import Settings
from primordial.simulation.creature import Creature

_DEFAULT_MAX_TICKS = 20000
_DEFAULT_SCENARIO = "predator_prey_medium"
_PREDATOR_PREY_MODE = "predator_prey"
_FOLLOW_WINDOWS = (1, 3, 5, 10)


@dataclass(slots=True)
class PendingNearContactEvent:
    frame: int
    counted_1f: bool = False
    counted_3f: bool = False
    counted_5f: bool = False
    counted_10f: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run external predator contact forensics for predator_prey mode.",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        required=True,
        help="Comma-separated list of seeds.",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=_DEFAULT_MAX_TICKS,
        help=f"Maximum simulation ticks per run (default: {_DEFAULT_MAX_TICKS})",
    )
    parser.add_argument(
        "--output",
        default="run_logs/predator_contact_forensics.md",
        help="Path for the Markdown report.",
    )
    parser.add_argument(
        "--json",
        default="run_logs/predator_contact_forensics.json",
        help="Path for the JSON report.",
    )
    parser.add_argument(
        "--scenario",
        default=_DEFAULT_SCENARIO,
        help=f"Scenario ID to use (default: {_DEFAULT_SCENARIO})",
    )
    return parser


def parse_seed_list(value: str) -> list[int]:
    seeds = [part.strip() for part in value.split(",") if part.strip()]
    if not seeds:
        raise ValueError("at least one seed is required")
    return [int(seed) for seed in seeds]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.seeds = parse_seed_list(args.seeds)
    return args


def _mode_param(settings: Settings, key: str, default: float) -> float:
    params = settings.mode_params.get(_PREDATOR_PREY_MODE, {})
    return float(params.get(key, default))


def _toroidal_delta(a: float, b: float, world_size: int) -> float:
    delta = b - a
    half = world_size / 2.0
    if delta > half:
        delta -= world_size
    elif delta < -half:
        delta += world_size
    return delta


def toroidal_distance(
    ax: float,
    ay: float,
    bx: float,
    by: float,
    world_width: int,
    world_height: int,
) -> float:
    dx = _toroidal_delta(ax, bx, world_width)
    dy = _toroidal_delta(ay, by, world_height)
    return math.sqrt(dx * dx + dy * dy)


def relative_radial_speed(
    predator: Creature,
    prey: Creature,
    world_width: int,
    world_height: int,
) -> float:
    dx = _toroidal_delta(predator.x, prey.x, world_width)
    dy = _toroidal_delta(predator.y, prey.y, world_height)
    distance = math.sqrt(dx * dx + dy * dy)
    if distance <= 1e-9:
        return 0.0
    unit_x = dx / distance
    unit_y = dy / distance
    rel_vx = prey.vx - predator.vx
    rel_vy = prey.vy - predator.vy
    return (rel_vx * unit_x) + (rel_vy * unit_y)


def estimate_contact_radius(predator: Creature, prey: Creature, settings: Settings) -> float:
    contact_scale = _mode_param(settings, "predator_contact_kill_distance_scale", 1.0)
    return (predator.get_radius() + prey.get_radius()) * contact_scale


def estimate_near_contact_radius(predator: Creature, prey: Creature, settings: Settings) -> float:
    near_scale = _mode_param(settings, "predator_near_contact_diagnostic_scale", 1.25)
    return estimate_contact_radius(predator, prey, settings) * near_scale


def _nearest_prey(
    predator: Creature,
    prey_creatures: Iterable[Creature],
    *,
    world_width: int,
    world_height: int,
) -> tuple[Creature | None, float | None]:
    nearest: Creature | None = None
    nearest_dist: float | None = None
    for prey in prey_creatures:
        distance = toroidal_distance(
            predator.x,
            predator.y,
            prey.x,
            prey.y,
            world_width,
            world_height,
        )
        if nearest_dist is None or distance < nearest_dist:
            nearest = prey
            nearest_dist = distance
    return nearest, nearest_dist


def observe_predator_proximity(
    predator: Creature,
    prey_creatures: Sequence[Creature],
    *,
    settings: Settings,
    world_width: int,
    world_height: int,
) -> dict[str, Any]:
    same_depth = [prey for prey in prey_creatures if prey.depth_band == predator.depth_band]
    cross_depth = [prey for prey in prey_creatures if prey.depth_band != predator.depth_band]

    nearest_any, nearest_any_dist = _nearest_prey(
        predator,
        prey_creatures,
        world_width=world_width,
        world_height=world_height,
    )
    nearest_same, nearest_same_dist = _nearest_prey(
        predator,
        same_depth,
        world_width=world_width,
        world_height=world_height,
    )
    nearest_cross, nearest_cross_dist = _nearest_prey(
        predator,
        cross_depth,
        world_width=world_width,
        world_height=world_height,
    )

    same_depth_contact = False
    same_depth_near = False
    same_depth_contact_radius: float | None = None
    if nearest_same is not None and nearest_same_dist is not None:
        same_depth_contact_radius = estimate_contact_radius(predator, nearest_same, settings)
        same_depth_near_radius = estimate_near_contact_radius(predator, nearest_same, settings)
        same_depth_contact = nearest_same_dist <= same_depth_contact_radius
        same_depth_near = nearest_same_dist <= same_depth_near_radius

    cross_depth_contact = False
    cross_depth_near = False
    cross_depth_contact_radius: float | None = None
    if nearest_cross is not None and nearest_cross_dist is not None:
        cross_depth_contact_radius = estimate_contact_radius(predator, nearest_cross, settings)
        cross_depth_near_radius = estimate_near_contact_radius(predator, nearest_cross, settings)
        cross_depth_contact = nearest_cross_dist <= cross_depth_contact_radius
        cross_depth_near = nearest_cross_dist <= cross_depth_near_radius

    nearest_any_contact_radius: float | None = None
    nearest_any_contact_ratio: float | None = None
    if nearest_any is not None and nearest_any_dist is not None:
        nearest_any_contact_radius = estimate_contact_radius(predator, nearest_any, settings)
        if nearest_any_contact_radius > 0.0:
            nearest_any_contact_ratio = nearest_any_dist / nearest_any_contact_radius

    return {
        "nearest_any": nearest_any,
        "nearest_any_id": id(nearest_any) if nearest_any is not None else None,
        "nearest_any_dist": nearest_any_dist,
        "nearest_any_contact_ratio": nearest_any_contact_ratio,
        "nearest_same": nearest_same,
        "nearest_same_dist": nearest_same_dist,
        "nearest_same_contact": same_depth_contact,
        "nearest_same_near": same_depth_near,
        "nearest_same_contact_radius": same_depth_contact_radius,
        "nearest_cross": nearest_cross,
        "nearest_cross_dist": nearest_cross_dist,
        "nearest_cross_contact": cross_depth_contact,
        "nearest_cross_near": cross_depth_near,
        "nearest_cross_contact_radius": cross_depth_contact_radius,
        "near_contact": same_depth_near or cross_depth_near,
    }


def make_empty_aggregate() -> dict[str, Any]:
    return {
        "total_ticks": 0,
        "total_kills": 0,
        "near_contact_events": 0,
        "same_depth_near_contact_events": 0,
        "cross_depth_near_contact_events": 0,
        "same_depth_contact_radius_events": 0,
        "cross_depth_contact_radius_events": 0,
        "near_contact_followed_by_kill_1f": 0,
        "near_contact_followed_by_kill_3f": 0,
        "near_contact_followed_by_kill_5f": 0,
        "near_contact_followed_by_kill_10f": 0,
        "predator_zero_runs": 0,
        "prey_zero_runs": 0,
        "final_predator_counts": [],
        "final_prey_counts": [],
        "predator_frames_observed": 0,
        "predator_frames_with_prey": 0,
        "nearest_prey_changed_events": 0,
        "near_contact_target_switch_events": 0,
        "near_contact_moving_away_events": 0,
        "same_depth_just_outside_contact_events": 0,
        "sum_nearest_any_dist": 0.0,
        "count_nearest_any_dist": 0,
        "sum_nearest_same_dist": 0.0,
        "count_nearest_same_dist": 0,
        "sum_nearest_cross_dist": 0.0,
        "count_nearest_cross_dist": 0,
        "sum_nearest_any_contact_ratio": 0.0,
        "count_nearest_any_contact_ratio": 0,
        "predator_zero_ever_runs": 0,
        "prey_zero_ever_runs": 0,
    }


def _increment_follow_counts(
    aggregate: dict[str, Any],
    pending_events: list[PendingNearContactEvent],
    *,
    current_frame: int,
    kill_delta: int,
) -> None:
    if kill_delta <= 0:
        pending_events[:] = [
            event for event in pending_events if (current_frame - event.frame) <= _FOLLOW_WINDOWS[-1]
        ]
        return

    for event in pending_events:
        age = current_frame - event.frame
        if age < 0:
            continue
        if age <= 1 and not event.counted_1f:
            aggregate["near_contact_followed_by_kill_1f"] += 1
            event.counted_1f = True
        if age <= 3 and not event.counted_3f:
            aggregate["near_contact_followed_by_kill_3f"] += 1
            event.counted_3f = True
        if age <= 5 and not event.counted_5f:
            aggregate["near_contact_followed_by_kill_5f"] += 1
            event.counted_5f = True
        if age <= 10 and not event.counted_10f:
            aggregate["near_contact_followed_by_kill_10f"] += 1
            event.counted_10f = True

    pending_events[:] = [
        event for event in pending_events if (current_frame - event.frame) <= _FOLLOW_WINDOWS[-1]
    ]


def _safe_mean(total: float, count: int) -> float | None:
    if count <= 0:
        return None
    return total / count


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator)


def _make_summary_metrics(aggregate: dict[str, Any]) -> dict[str, Any]:
    near_contact = aggregate["near_contact_events"]
    same_depth_near = aggregate["same_depth_near_contact_events"]
    cross_depth_near = aggregate["cross_depth_near_contact_events"]
    same_depth_contact = aggregate["same_depth_contact_radius_events"]
    cross_depth_contact = aggregate["cross_depth_contact_radius_events"]
    return {
        "mean_nearest_any_distance": _safe_mean(
            aggregate["sum_nearest_any_dist"],
            aggregate["count_nearest_any_dist"],
        ),
        "mean_nearest_same_depth_distance": _safe_mean(
            aggregate["sum_nearest_same_dist"],
            aggregate["count_nearest_same_dist"],
        ),
        "mean_nearest_cross_depth_distance": _safe_mean(
            aggregate["sum_nearest_cross_dist"],
            aggregate["count_nearest_cross_dist"],
        ),
        "mean_nearest_contact_ratio": _safe_mean(
            aggregate["sum_nearest_any_contact_ratio"],
            aggregate["count_nearest_any_contact_ratio"],
        ),
        "share_near_contact_followed_by_kill_1f": _safe_ratio(
            aggregate["near_contact_followed_by_kill_1f"],
            near_contact,
        ),
        "share_near_contact_followed_by_kill_3f": _safe_ratio(
            aggregate["near_contact_followed_by_kill_3f"],
            near_contact,
        ),
        "share_near_contact_followed_by_kill_5f": _safe_ratio(
            aggregate["near_contact_followed_by_kill_5f"],
            near_contact,
        ),
        "share_near_contact_followed_by_kill_10f": _safe_ratio(
            aggregate["near_contact_followed_by_kill_10f"],
            near_contact,
        ),
        "share_same_depth_near_contact": _safe_ratio(same_depth_near, near_contact),
        "share_cross_depth_near_contact": _safe_ratio(cross_depth_near, near_contact),
        "share_same_depth_near_inside_contact_radius": _safe_ratio(
            same_depth_contact,
            same_depth_near,
        ),
        "share_cross_depth_near_inside_contact_radius": _safe_ratio(
            cross_depth_contact,
            cross_depth_near,
        ),
        "share_same_depth_just_outside_contact": _safe_ratio(
            aggregate["same_depth_just_outside_contact_events"],
            same_depth_near,
        ),
        "share_near_contact_with_target_switch": _safe_ratio(
            aggregate["near_contact_target_switch_events"],
            near_contact,
        ),
        "share_near_contact_with_moving_away": _safe_ratio(
            aggregate["near_contact_moving_away_events"],
            near_contact,
        ),
    }


def diagnose_bottleneck(aggregate: dict[str, Any]) -> dict[str, str]:
    summary = _make_summary_metrics(aggregate)
    depth_share = summary["share_cross_depth_near_contact"]
    same_depth_inside = summary["share_same_depth_near_inside_contact_radius"]
    just_outside = summary["share_same_depth_just_outside_contact"]
    switch_share = summary["share_near_contact_with_target_switch"]
    kill_3f = summary["share_near_contact_followed_by_kill_3f"]
    kill_10f = summary["share_near_contact_followed_by_kill_10f"]

    if depth_share >= 0.55:
        return {
            "primary_bottleneck": "depth mismatch",
            "recommended_next_change": "Investigate a conservative depth-alignment or same-depth contact opportunity change before touching reproduction or food.",
        }
    if same_depth_inside < 0.35 and just_outside >= 0.45:
        return {
            "primary_bottleneck": "radius/timing gap",
            "recommended_next_change": "Investigate a very small same-depth contact-conversion adjustment before retuning reproduction or scarcity.",
        }
    if switch_share >= 0.30:
        return {
            "primary_bottleneck": "target switching",
            "recommended_next_change": "Investigate whether predators are repeatedly dropping or swapping close prey targets before changing reproduction or food balance.",
        }
    if kill_3f >= 0.45 and kill_10f >= 0.60:
        return {
            "primary_bottleneck": "reproduction after kills",
            "recommended_next_change": "Investigate predator post-kill energy-to-reproduction conversion before changing contact or prey availability.",
        }
    return {
        "primary_bottleneck": "radius/timing gap",
        "recommended_next_change": "Investigate a very small same-depth contact-conversion adjustment first; near-contact frames are common but only a minority convert into kills quickly.",
    }


def aggregate_runs(runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    aggregate = make_empty_aggregate()
    for run in runs:
        run_agg = run["aggregate"]
        for key in (
            "total_ticks",
            "total_kills",
            "near_contact_events",
            "same_depth_near_contact_events",
            "cross_depth_near_contact_events",
            "same_depth_contact_radius_events",
            "cross_depth_contact_radius_events",
            "near_contact_followed_by_kill_1f",
            "near_contact_followed_by_kill_3f",
            "near_contact_followed_by_kill_5f",
            "near_contact_followed_by_kill_10f",
            "predator_frames_observed",
            "predator_frames_with_prey",
            "nearest_prey_changed_events",
            "near_contact_target_switch_events",
            "near_contact_moving_away_events",
            "same_depth_just_outside_contact_events",
            "sum_nearest_any_dist",
            "count_nearest_any_dist",
            "sum_nearest_same_dist",
            "count_nearest_same_dist",
            "sum_nearest_cross_dist",
            "count_nearest_cross_dist",
            "sum_nearest_any_contact_ratio",
            "count_nearest_any_contact_ratio",
        ):
            aggregate[key] += run_agg[key]
        aggregate["predator_zero_runs"] += int(run["final_predator_count"] == 0)
        aggregate["prey_zero_runs"] += int(run["final_prey_count"] == 0)
        aggregate["predator_zero_ever_runs"] += int(run["predator_zero_ever"])
        aggregate["prey_zero_ever_runs"] += int(run["prey_zero_ever"])
        aggregate["final_predator_counts"].append(run["final_predator_count"])
        aggregate["final_prey_counts"].append(run["final_prey_count"])

    summary = _make_summary_metrics(aggregate)
    diagnosis = diagnose_bottleneck(aggregate)
    return {
        **aggregate,
        **summary,
        **diagnosis,
    }


def build_markdown_report(
    *,
    seeds: Sequence[int],
    scenario_id: str,
    max_ticks: int,
    runs: Sequence[dict[str, Any]],
    aggregate: dict[str, Any],
) -> str:
    mean_nearest_contact_ratio = aggregate["mean_nearest_contact_ratio"]
    mean_nearest_contact_ratio_text = (
        f"{mean_nearest_contact_ratio:.2f}"
        if mean_nearest_contact_ratio is not None
        else "n/a"
    )
    lines: list[str] = []
    lines.append("# Predator Contact Forensics")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append(
        "This report observes predator/prey state from outside the simulation loop. "
        "It does not modify `Simulation`, predator/prey behavior, defaults, or runtime tuning."
    )
    lines.append("")
    lines.append("## Approximation Notes")
    lines.append("")
    lines.append(
        "- Likely prey targets are inferred as the nearest prey to each predator on that frame."
    )
    lines.append(
        "- Contact and near-contact thresholds use public creature radii plus committed mode params, without private per-frame hunt modifiers."
    )
    lines.append(
        "- Kill follow-up windows are based on total `predation_kill_count` increases within 1, 3, 5, and 10 subsequent frames."
    )
    lines.append("")
    lines.append("## Run Config")
    lines.append("")
    lines.append(f"- Scenario: `{scenario_id}`")
    lines.append(f"- Seeds: `{', '.join(str(seed) for seed in seeds)}`")
    lines.append(f"- Max ticks per run: `{max_ticks}`")
    lines.append("")
    lines.append("## Aggregate Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Total ticks observed | {aggregate['total_ticks']} |")
    lines.append(f"| Total kills | {aggregate['total_kills']} |")
    lines.append(f"| Near-contact predator-frames | {aggregate['near_contact_events']} |")
    lines.append(f"| Same-depth near-contact predator-frames | {aggregate['same_depth_near_contact_events']} |")
    lines.append(f"| Cross-depth near-contact predator-frames | {aggregate['cross_depth_near_contact_events']} |")
    lines.append(f"| Same-depth inside estimated contact radius | {aggregate['same_depth_contact_radius_events']} |")
    lines.append(f"| Cross-depth inside estimated contact radius | {aggregate['cross_depth_contact_radius_events']} |")
    lines.append(f"| Near-contact followed by kill within 1f | {aggregate['near_contact_followed_by_kill_1f']} ({aggregate['share_near_contact_followed_by_kill_1f']:.1%}) |")
    lines.append(f"| Near-contact followed by kill within 3f | {aggregate['near_contact_followed_by_kill_3f']} ({aggregate['share_near_contact_followed_by_kill_3f']:.1%}) |")
    lines.append(f"| Near-contact followed by kill within 5f | {aggregate['near_contact_followed_by_kill_5f']} ({aggregate['share_near_contact_followed_by_kill_5f']:.1%}) |")
    lines.append(f"| Near-contact followed by kill within 10f | {aggregate['near_contact_followed_by_kill_10f']} ({aggregate['share_near_contact_followed_by_kill_10f']:.1%}) |")
    lines.append(f"| Near-contact with inferred target switch | {aggregate['near_contact_target_switch_events']} ({aggregate['share_near_contact_with_target_switch']:.1%}) |")
    lines.append(f"| Near-contact with prey moving away | {aggregate['near_contact_moving_away_events']} ({aggregate['share_near_contact_with_moving_away']:.1%}) |")
    lines.append(f"| Same-depth near-contact just outside contact radius | {aggregate['same_depth_just_outside_contact_events']} ({aggregate['share_same_depth_just_outside_contact']:.1%} of same-depth near-contact) |")
    lines.append(f"| Mean nearest-prey/contact-radius ratio | {mean_nearest_contact_ratio_text} |")
    lines.append(f"| Runs ending with zero predators | {aggregate['predator_zero_runs']}/{len(runs)} |")
    lines.append(f"| Runs ever hitting zero predators | {aggregate['predator_zero_ever_runs']}/{len(runs)} |")
    lines.append(f"| Runs ending with zero prey | {aggregate['prey_zero_runs']}/{len(runs)} |")
    lines.append(f"| Final predator counts | {aggregate['final_predator_counts']} |")
    lines.append(f"| Final prey counts | {aggregate['final_prey_counts']} |")
    lines.append("")
    lines.append("## Per-Run Summary")
    lines.append("")
    lines.append("| Seed | Final ticks | Final predators | Final prey | Kills | Near-contact | Same-depth near | Cross-depth near | Kill within 3f | Zero predators ever |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for run in runs:
        run_agg = run["aggregate"]
        kill_3f_share = _safe_ratio(
            run_agg["near_contact_followed_by_kill_3f"],
            run_agg["near_contact_events"],
        )
        lines.append(
            f"| {run['seed']} | {run['final_sim_ticks']} | {run['final_predator_count']} | {run['final_prey_count']} | "
            f"{run['total_kills']} | {run_agg['near_contact_events']} | {run_agg['same_depth_near_contact_events']} | "
            f"{run_agg['cross_depth_near_contact_events']} | {kill_3f_share:.1%} | {'yes' if run['predator_zero_ever'] else 'no'} |"
        )
    lines.append("")
    lines.append("## Questions Answered")
    lines.append("")
    lines.append(
        f"- Are predators usually near prey but in the wrong depth? "
        f"Cross-depth near-contact accounted for {aggregate['share_cross_depth_near_contact']:.1%} of near-contact predator-frames."
    )
    lines.append(
        f"- Are they same-depth near prey but just outside contact radius? "
        f"{aggregate['share_same_depth_just_outside_contact']:.1%} of same-depth near-contact predator-frames were outside the estimated contact radius."
    )
    lines.append(
        f"- Are they repeatedly close to different prey, suggesting target switching? "
        f"Near-contact inferred target switching appeared in {aggregate['share_near_contact_with_target_switch']:.1%} of near-contact predator-frames."
    )
    lines.append(
        f"- Do near-contact events usually precede a kill within 1, 3, 5, or 10 frames? "
        f"Observed follow rates were {aggregate['share_near_contact_followed_by_kill_1f']:.1%}, "
        f"{aggregate['share_near_contact_followed_by_kill_3f']:.1%}, "
        f"{aggregate['share_near_contact_followed_by_kill_5f']:.1%}, and "
        f"{aggregate['share_near_contact_followed_by_kill_10f']:.1%}."
    )
    lines.append(
        f"- Is the problem mostly depth mismatch, radius/timing, target switching, or reproduction after kills? "
        f"This run set most strongly points to `{aggregate['primary_bottleneck']}`."
    )
    lines.append("")
    lines.append("## Recommended Next Change")
    lines.append("")
    lines.append(aggregate["recommended_next_change"])
    lines.append("")
    return "\n".join(lines)


def _run_single_seed(
    seed: int,
    max_ticks: int,
    *,
    scenario_id: str,
) -> dict[str, Any]:
    import pygame

    from primordial.display.mode import _get_fullscreen_resolution
    from primordial.scenarios import build_settings_for_scenario
    from primordial.simulation import Simulation

    scenario, settings = build_settings_for_scenario(scenario_id)
    if settings.sim_mode != _PREDATOR_PREY_MODE:
        raise ValueError(
            f"Scenario {scenario_id!r} uses mode {settings.sim_mode!r}; "
            f"predator_contact_forensics requires predator_prey mode."
        )

    settings.mode_params.setdefault(_PREDATOR_PREY_MODE, {})
    settings.mode_params[_PREDATOR_PREY_MODE]["adaptive_tuning_enabled"] = False

    pygame.init()
    try:
        width, height = _get_fullscreen_resolution()
    finally:
        pygame.quit()

    random.seed(seed)
    simulation = Simulation(width, height, settings, seed=seed)
    aggregate = make_empty_aggregate()
    pending_events: list[PendingNearContactEvent] = []
    previous_nearest_by_predator: dict[int, int | None] = {}
    predator_zero_ever = False
    prey_zero_ever = False

    while True:
        state = simulation._predator_prey_state
        if state.sim_ticks >= max_ticks:
            break
        if simulation.predator_prey_game_over_active:
            break

        predators = [
            creature
            for creature in simulation.creatures
            if creature.species == "predator" and creature.energy > 0.0
        ]
        prey_creatures = [
            creature
            for creature in simulation.creatures
            if creature.species == "prey" and creature.energy > 0.0
        ]
        aggregate["total_ticks"] += 1

        if not predators:
            predator_zero_ever = True
        if not prey_creatures:
            prey_zero_ever = True

        living_predator_ids = {id(predator) for predator in predators}
        previous_nearest_by_predator = {
            predator_id: prey_id
            for predator_id, prey_id in previous_nearest_by_predator.items()
            if predator_id in living_predator_ids
        }

        for predator in predators:
            aggregate["predator_frames_observed"] += 1
            if prey_creatures:
                aggregate["predator_frames_with_prey"] += 1
            observation = observe_predator_proximity(
                predator,
                prey_creatures,
                settings=settings,
                world_width=simulation.width,
                world_height=simulation.height,
            )
            nearest_any_dist = observation["nearest_any_dist"]
            if nearest_any_dist is not None:
                aggregate["sum_nearest_any_dist"] += nearest_any_dist
                aggregate["count_nearest_any_dist"] += 1
            nearest_any_contact_ratio = observation["nearest_any_contact_ratio"]
            if nearest_any_contact_ratio is not None:
                aggregate["sum_nearest_any_contact_ratio"] += nearest_any_contact_ratio
                aggregate["count_nearest_any_contact_ratio"] += 1
            nearest_same_dist = observation["nearest_same_dist"]
            if nearest_same_dist is not None:
                aggregate["sum_nearest_same_dist"] += nearest_same_dist
                aggregate["count_nearest_same_dist"] += 1
            nearest_cross_dist = observation["nearest_cross_dist"]
            if nearest_cross_dist is not None:
                aggregate["sum_nearest_cross_dist"] += nearest_cross_dist
                aggregate["count_nearest_cross_dist"] += 1

            if observation["nearest_same_near"]:
                aggregate["same_depth_near_contact_events"] += 1
                if observation["nearest_same_contact"]:
                    aggregate["same_depth_contact_radius_events"] += 1
                else:
                    aggregate["same_depth_just_outside_contact_events"] += 1

            if observation["nearest_cross_near"]:
                aggregate["cross_depth_near_contact_events"] += 1
                if observation["nearest_cross_contact"]:
                    aggregate["cross_depth_contact_radius_events"] += 1

            current_nearest_id = observation["nearest_any_id"]
            previous_nearest_id = previous_nearest_by_predator.get(id(predator))
            nearest_changed = (
                previous_nearest_id is not None
                and current_nearest_id is not None
                and previous_nearest_id != current_nearest_id
            )
            if nearest_changed:
                aggregate["nearest_prey_changed_events"] += 1

            if observation["near_contact"]:
                aggregate["near_contact_events"] += 1
                if nearest_changed:
                    aggregate["near_contact_target_switch_events"] += 1
                nearest_any = observation["nearest_any"]
                if nearest_any is not None:
                    radial_speed = relative_radial_speed(
                        predator,
                        nearest_any,
                        simulation.width,
                        simulation.height,
                    )
                    if radial_speed > 0.0:
                        aggregate["near_contact_moving_away_events"] += 1
                pending_events.append(PendingNearContactEvent(frame=state.sim_ticks))

            previous_nearest_by_predator[id(predator)] = current_nearest_id

        pre_kills = simulation.predation_kill_count
        simulation.step()
        post_kills = simulation.predation_kill_count
        aggregate["total_kills"] = post_kills
        _increment_follow_counts(
            aggregate,
            pending_events,
            current_frame=simulation._predator_prey_state.sim_ticks,
            kill_delta=post_kills - pre_kills,
        )

        # Renderer normally owns clearing these event queues.
        simulation.death_events.clear()
        simulation.birth_events.clear()

    final_predator_count, final_prey_count = simulation.get_species_counts()
    summary = _make_summary_metrics(aggregate)
    return {
        "seed": seed,
        "scenario_id": scenario_id,
        "max_ticks": max_ticks,
        "final_sim_ticks": simulation._predator_prey_state.sim_ticks,
        "final_predator_count": final_predator_count,
        "final_prey_count": final_prey_count,
        "total_kills": simulation.predation_kill_count,
        "predator_zero_ever": predator_zero_ever or final_predator_count == 0,
        "prey_zero_ever": prey_zero_ever or final_prey_count == 0,
        "aggregate": {
            **aggregate,
            **summary,
        },
    }


def write_reports(
    *,
    output_path: Path,
    json_path: Path,
    seeds: Sequence[int],
    scenario_id: str,
    max_ticks: int,
    runs: Sequence[dict[str, Any]],
    aggregate: dict[str, Any],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = build_markdown_report(
        seeds=seeds,
        scenario_id=scenario_id,
        max_ticks=max_ticks,
        runs=runs,
        aggregate=aggregate,
    )
    output_path.write_text(markdown, encoding="utf-8")

    payload = {
        "report_timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario_id": scenario_id,
        "seeds": list(seeds),
        "max_ticks": max_ticks,
        "aggregate": aggregate,
        "runs": list(runs),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_path = Path(args.output)
    json_path = Path(args.json)

    print(
        f"Running predator contact forensics: {len(args.seeds)} seed(s), "
        f"max {args.max_ticks} ticks each, scenario={args.scenario}",
        flush=True,
    )
    runs: list[dict[str, Any]] = []
    for index, seed in enumerate(args.seeds, start=1):
        print(f"  Seed {seed} ({index}/{len(args.seeds)})...", flush=True)
        run = _run_single_seed(seed, args.max_ticks, scenario_id=args.scenario)
        runs.append(run)
        print(
            f"    ticks={run['final_sim_ticks']}, predators={run['final_predator_count']}, "
            f"prey={run['final_prey_count']}, kills={run['total_kills']}",
            flush=True,
        )

    aggregate = aggregate_runs(runs)
    write_reports(
        output_path=output_path,
        json_path=json_path,
        seeds=args.seeds,
        scenario_id=args.scenario,
        max_ticks=args.max_ticks,
        runs=runs,
        aggregate=aggregate,
    )
    print(f"Markdown written to {output_path}")
    print(f"JSON written to {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
