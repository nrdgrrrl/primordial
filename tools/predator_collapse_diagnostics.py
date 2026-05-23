#!/usr/bin/env python3
"""Graphical predator-collapse diagnostics runner and report generator.

Runs predator_prey mode in full graphical mode (pygame + renderer) for one
or more seeds, collects predator-life diagnostics, and produces both a
structured JSON file and a human-readable Markdown report.

The simulation must run in graphical mode because rendering affects
simulation outcomes (e.g. frame pacing, predator_prey_game_over timing,
adaptive tuning restarts). Headless stepping diverges from real gameplay.

Usage:
  python tools/predator_collapse_diagnostics.py --runs 5 --max-ticks 20000 \
      --output run_logs/predator_collapse_report.md \
      --json run_logs/predator_collapse_diagnostics.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pygame

from primordial.display.mode import DEFAULT_WINDOWED_SIZE, _get_fullscreen_resolution
from primordial.display.cursor import hide_runtime_cursor, restore_system_cursor
from primordial.rendering import create_renderer, display_flags_for_settings
from primordial.runtime import (
    LoopTimingCollector,
    advance_fixed_step_frame,
    build_frame_metrics,
    create_fixed_step_loop_state,
    get_effective_target_fps,
    simulation_timing_is_suppressed,
)
from primordial.scenarios import build_settings_for_scenario
from primordial.settings import Settings
from primordial.simulation import Simulation
from primordial.simulation.depth import DEPTH_BAND_NAMES

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_SEEDS = [161803, 314159, 271828, 57721, 99991]
_DEFAULT_MAX_TICKS = 20000
_PREDATOR_PREY_MODE = "predator_prey"
_PREY_FRAILTY_OLD_AGE_FRACTION = 0.70


# ---------------------------------------------------------------------------
# Graphical runner (full pygame + renderer loop)
# ---------------------------------------------------------------------------

def run_simulation_graphical(
    seed: int,
    max_ticks: int,
    *,
    scenario_id: str = "predator_prey_medium",
    epistasis: str | None = None,
) -> dict[str, Any]:
    """Run a single predator_prey simulation in full graphical mode and return results."""
    scenario, settings = build_settings_for_scenario(scenario_id)
    if settings.sim_mode != _PREDATOR_PREY_MODE:
        raise ValueError(
            f"Scenario {scenario_id!r} uses mode {settings.sim_mode!r}; "
            f"predator_collapse_diagnostics requires predator_prey mode."
        )

    # Apply epistasis override
    if epistasis == "on":
        settings.epistasis_enabled = True
    elif epistasis == "off":
        settings.epistasis_enabled = False
    # "current" or None → leave defaults

    # Disable adaptive tuning for clean baseline diagnostics
    settings.mode_params.setdefault(_PREDATOR_PREY_MODE, {})
    settings.mode_params[_PREDATOR_PREY_MODE]["adaptive_tuning_enabled"] = False

    # Fullscreen + HUD so the play area matches real gameplay and
    # the operator can visually monitor each run.
    settings.fullscreen = True
    settings.show_hud = True

    pygame.init()
    width, height = _get_fullscreen_resolution()
    screen = pygame.display.set_mode(
        (width, height),
        display_flags_for_settings(settings, pygame.FULLSCREEN | pygame.SCALED),
    )
    pygame.display.set_caption(f"Primordial Diagnostics — seed {seed}")
    hide_runtime_cursor()

    random.seed(seed)
    simulation = Simulation(width, height, settings, seed=seed)
    renderer = create_renderer(screen, settings, debug=False)
    renderer.resize(simulation.width, simulation.height, screen=screen)
    clock = pygame.time.Clock()
    runtime_loop = create_fixed_step_loop_state(settings)

    # Collect periodic species counts for time-series
    species_counts: list[dict[str, int]] = []
    pred_count, prey_count = simulation.get_species_counts()
    species_counts.append({"step": 0, "predators": pred_count, "prey": prey_count})

    game_over = False
    collapse_cause: str | None = None
    tick_of_first_predator_zero: int | None = None

    try:
        while True:
            # Pump events to keep the OS happy
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Treat window close as end-of-run
                    break

            # Handle predator_prey runtime restarts (adaptive tuning)
            if simulation.update_predator_prey_runtime(now_seconds=time.monotonic()):
                renderer.reset_runtime_state()
                runtime_loop.reset_timing_debt()

            sim_suppressed = simulation_timing_is_suppressed(simulation)

            # Stop conditions
            state = simulation._predator_prey_state
            if state.sim_ticks >= max_ticks:
                break
            if simulation.predator_prey_game_over_active:
                game_over = True
                collapse_cause = state.collapse_cause
                break

            sim_ms, sim_steps, clamp_frames, dropped_seconds = advance_fixed_step_frame(
                simulation,
                runtime_loop,
                allow_simulation=not sim_suppressed,
            )

            runtime_loop.restore_buffered_attacks(simulation)
            renderer.draw(simulation)
            pygame.display.flip()
            clock.tick(max(1, get_effective_target_fps(settings)))

            # Record species counts periodically (every ~60 simulation steps)
            current_ticks = state.sim_ticks
            if current_ticks % 60 == 0 and (not species_counts or species_counts[-1]["step"] != current_ticks):
                pred_count, prey_count = simulation.get_species_counts()
                species_counts.append({
                    "step": current_ticks,
                    "predators": pred_count,
                    "prey": prey_count,
                })
                if pred_count == 0 and tick_of_first_predator_zero is None:
                    tick_of_first_predator_zero = current_ticks

    finally:
        restore_system_cursor()
        pygame.quit()

    # Gather diagnostics after the loop
    diagnostics = simulation.export_predator_diagnostics()
    stability = simulation.get_predator_prey_stability_stats()
    epistasis_summary = simulation.get_epistasis_summary()

    final_pred, final_prey = simulation.get_species_counts()

    return {
        "seed": seed,
        "scenario_id": scenario_id,
        "epistasis": epistasis or "current",
        "max_ticks": max_ticks,
        "game_over": game_over,
        "collapse_cause": collapse_cause,
        "final_sim_ticks": state.sim_ticks,
        "final_survival_ticks": state.survival_ticks,
        "final_predator_count": final_pred,
        "final_prey_count": final_prey,
        "tick_of_first_predator_zero": tick_of_first_predator_zero,
        "predator_zero_ticks_at_end": state.predator_zero_ticks,
        "total_kills": simulation.predation_kill_count,
        "species_counts": species_counts,
        "diagnostics": diagnostics,
        "stability": stability,
        "epistasis_summary": epistasis_summary,
    }


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _safe_median(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _safe_mean(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(mean(values))


def _pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return 100.0 * numerator / denominator


def _classify_death_context(context: str | None) -> str:
    """Normalize death context to one of the four canonical labels."""
    if context is None:
        return "unknown"
    if context in ("old_age", "active_hunting", "after_failed_pursuit", "long_scarcity"):
        return context
    return "unknown"


def _depth_band_name(band: int | None) -> str:
    if band is None:
        return "unknown"
    return DEPTH_BAND_NAMES.get(band, f"band_{band}")


def _bucket_killed_prey_age(age_fraction: float) -> str:
    return "old" if age_fraction >= _PREY_FRAILTY_OLD_AGE_FRACTION else "young"


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def _section_a_run_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A. Run summary table — one row per seed."""
    rows = []
    for run in runs:
        rows.append({
            "seed": run["seed"],
            "final_sim_ticks": run["final_sim_ticks"],
            "game_over": run["game_over"],
            "collapse_cause": run["collapse_cause"],
            "first_predator_zero_tick": run["tick_of_first_predator_zero"],
            "predator_zero_ticks_at_end": run["predator_zero_ticks_at_end"],
            "final_predator_count": run["final_predator_count"],
            "final_prey_count": run["final_prey_count"],
            "total_kills": run["total_kills"],
            "survival_ticks": run["final_survival_ticks"],
        })
    return rows


def _section_b_predator_life_summary(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """B. Predator life summary aggregate across all runs."""
    all_completed: list[dict] = []
    all_active: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])
        all_active.extend(diag["active_lives"])

    all_lives = all_completed + all_active
    if not all_lives:
        return {"predator_lives_started": 0}

    completed = all_completed
    kills_list = [int(l["kills"]) for l in all_lives]
    births_list = [int(l["births_produced"]) for l in all_lives]
    lifespan_list = [
        (int(l["end_frame"]) - int(l["start_frame"]))
        for l in completed if l["end_frame"] is not None
    ]
    highest_energy_list = [float(l["highest_energy"]) for l in all_lives]
    closest_gap_list = [
        float(l["closest_repro_check_gap"])
        for l in completed
        if l["closest_repro_check_gap"] is not None
        and not l["repro_check_reached_threshold"]
    ]
    threshold_reached = sum(1 for l in all_lives if l["peak_reached_threshold"])
    repro_check_reached = sum(1 for l in all_lives if l["repro_check_reached_threshold"])

    # Lives that had at least one kill but reached threshold post-kill yet
    # still didn't reproduce (post-cost check failure)
    kills_but_no_births = sum(
        1 for l in all_lives if int(l["kills"]) > 0 and int(l["births_produced"]) == 0
    )
    threshold_reached_but_no_births = sum(
        1 for l in all_lives
        if l["peak_reached_threshold"] and int(l["births_produced"]) == 0
    )

    return {
        "predator_lives_started": len(all_lives),
        "completed_predator_lives": len(completed),
        "active_predator_lives_at_end": len(all_active),
        "total_births_produced": sum(births_list),
        "total_kills": sum(kills_list),
        "mean_kills_per_life": _safe_mean(kills_list),
        "median_kills_per_life": _safe_median(kills_list),
        "pct_with_zero_kills": _pct(
            sum(1 for k in kills_list if k == 0), len(kills_list)
        ),
        "pct_with_at_least_one_kill": _pct(
            sum(1 for k in kills_list if k >= 1), len(kills_list)
        ),
        "pct_that_produced_offspring": _pct(
            sum(1 for b in births_list if b > 0), len(births_list)
        ),
        "median_lifespan": _safe_median(lifespan_list),
        "median_highest_energy": _safe_median(highest_energy_list),
        "median_closest_gap_to_reproduction_threshold": _safe_median(closest_gap_list),
        "pct_ever_reached_reproduction_threshold": _pct(
            threshold_reached, len(all_lives)
        ),
        "pct_repro_check_reached_threshold": _pct(
            repro_check_reached, len(all_lives)
        ),
        "kills_but_no_births": kills_but_no_births,
        "threshold_reached_but_no_births": threshold_reached_but_no_births,
    }


def _section_c_death_context_breakdown(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """C. Death context breakdown."""
    all_completed: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])

    if not all_completed:
        return {"contexts": {}, "total": 0}

    context_counts: dict[str, int] = {}
    for life in all_completed:
        ctx = _classify_death_context(life.get("death_context"))
        context_counts[ctx] = context_counts.get(ctx, 0) + 1

    explanations = {
        "old_age": "predators died of natural lifespan — not the collapse problem",
        "active_hunting": "predators found prey but died during/near pursuit",
        "after_failed_pursuit": "predators saw prey recently but failed to convert",
        "long_scarcity": "predators mostly could not find prey or food bridge was insufficient",
        "unknown": "death context could not be determined",
    }

    return {
        "contexts": context_counts,
        "total": len(all_completed),
        "explanations": explanations,
    }


def _section_d_origin_breakdown(
    runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """D. Origin breakdown for predator lives."""
    all_completed: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])

    origins: dict[str, list[dict]] = {}
    for life in all_completed:
        origin = life.get("origin", "unknown")
        origins.setdefault(origin, []).append(life)

    rows = []
    for origin, lives in sorted(origins.items()):
        kills = [int(l["kills"]) for l in lives]
        lifespans = [
            int(l["end_frame"]) - int(l["start_frame"])
            for l in lives
            if l["end_frame"] is not None
        ]
        reproduced = [l for l in lives if int(l["births_produced"]) > 0]
        rows.append({
            "origin": origin,
            "count": len(lives),
            "median_lifespan": _safe_median(lifespans),
            "median_kills": _safe_median(kills),
            "pct_reproduced": _pct(len(reproduced), len(lives)),
        })
    return rows


def _section_e_reproduction_bottleneck(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """E. Reproduction bottleneck analysis."""
    all_lives: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_lives.extend(diag["completed_lives"])
        all_lives.extend(diag["active_lives"])

    if not all_lives:
        return {"note": "No predator lives recorded"}

    # Threshold ranges
    threshold_mins = [
        float(l["threshold_min"])
        for l in all_lives
        if l["threshold_min"] is not None
    ]
    threshold_maxs = [
        float(l["threshold_max"])
        for l in all_lives
        if l["threshold_max"] is not None
    ]

    # Gaps
    closest_peak_gaps = [
        float(l["closest_peak_gap"])
        for l in all_lives
        if l["closest_peak_gap"] is not None
    ]
    closest_repro_gaps = [
        float(l["closest_repro_check_gap"])
        for l in all_lives
        if l["closest_repro_check_gap"] is not None
    ]

    # Kill energy cap from diagnostics
    kill_cap = runs[0]["diagnostics"]["predator_kill_energy_gain_cap"] if runs else None
    base_threshold = runs[0]["diagnostics"]["base_threshold"] if runs else None

    # How often got close but failed
    near_miss_002 = sum(
        1 for g in closest_repro_gaps
        if g is not None and 0 < g <= 0.02
    )
    near_miss_005 = sum(
        1 for g in closest_repro_gaps
        if g is not None and 0 < g <= 0.05
    )

    # Kills without births
    kills_no_births = sum(
        1 for l in all_lives
        if int(l["kills"]) > 0 and int(l["births_produced"]) == 0
    )
    threshold_reached_no_births = sum(
        1 for l in all_lives
        if l["peak_reached_threshold"] and int(l["births_produced"]) == 0
    )

    return {
        "base_reproduction_threshold": base_threshold,
        "predator_kill_energy_gain_cap": kill_cap,
        "threshold_min_seen": min(threshold_mins) if threshold_mins else None,
        "threshold_max_seen": max(threshold_maxs) if threshold_maxs else None,
        "median_closest_peak_gap": _safe_median(closest_peak_gaps),
        "median_closest_repro_check_gap": _safe_median(closest_repro_gaps),
        "peak_reached_threshold_count": sum(
            1 for l in all_lives if l["peak_reached_threshold"]
        ),
        "repro_check_reached_threshold_count": sum(
            1 for l in all_lives if l["repro_check_reached_threshold"]
        ),
        "near_miss_within_0_02": near_miss_002,
        "near_miss_within_0_05": near_miss_005,
        "kill_gap_to_threshold_ratio": (
            f"{kill_cap / base_threshold:.2f}"
            if kill_cap and base_threshold and base_threshold > 0
            else None
        ),
        "kills_but_no_births": kills_no_births,
        "threshold_reached_but_no_births": threshold_reached_no_births,
        "total_predator_lives": len(all_lives),
        "interpretation": {
            "kill_gap_to_threshold_ratio_note": (
                "Ratio of kill_energy_gain_cap to base_reproduction_threshold. "
                "If < 1.0, a single kill cannot supply enough energy to reproduce; "
                "multiple kills or additional foraging are required."
            ),
        },
    }


def _section_f_prey_access(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """F. Prey access / hunting bottleneck analysis."""
    all_completed: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])

    if not all_completed:
        return {"note": "No completed predator lives"}

    prey_sight_shares = []
    for life in all_completed:
        frames = int(life["frames_observed"])
        if frames > 0:
            prey_sight_shares.append(
                int(life["frames_with_prey_sighted"]) / frames
            )

    no_prey_sightings = sum(
        1 for l in all_completed if int(l["frames_with_prey_sighted"]) == 0
    )
    prey_sightings_no_kills = sum(
        1 for l in all_completed
        if int(l["frames_with_prey_sighted"]) > 0 and int(l["kills"]) == 0
    )
    cross_band_misses_list = [
        int(l["cross_band_contact_misses"]) for l in all_completed
    ]
    kills_list = [int(l["kills"]) for l in all_completed]
    total_kills = sum(
        int(l["kills"]) for l in all_completed
    )
    total_cross_band = sum(cross_band_misses_list)
    refuge_frames_per_life = [
        int(l.get("refuge_frames", 0)) for l in all_completed
    ]
    hunting_ground_frames_per_life = [
        int(l.get("hunting_ground_frames", 0)) for l in all_completed
    ]
    refuge_frame_shares = [
        int(l.get("refuge_frames", 0)) / frames
        for l in all_completed
        for frames in [int(l["frames_observed"])]
        if frames > 0
    ]
    hunting_ground_frame_shares = [
        int(l.get("hunting_ground_frames", 0)) / frames
        for l in all_completed
        for frames in [int(l["frames_observed"])]
        if frames > 0
    ]
    kills_inside_refuge = sum(int(l.get("kills_inside_refuge", 0)) for l in all_completed)
    kills_outside_refuge = sum(int(l.get("kills_outside_refuge", 0)) for l in all_completed)
    deaths_inside_refuge = sum(1 for l in all_completed if l.get("died_inside_refuge"))
    refuge_bonus_at_death = [
        float(l.get("refuge_bonus_factor_at_death", 0.0))
        for l in all_completed
    ]
    predator_density_at_death = [
        float(l["local_predator_density_at_death"])
        for l in all_completed
        if l.get("local_predator_density_at_death") is not None
    ]
    cross_band_inside_refuge = sum(
        int(l.get("cross_band_misses_inside_refuge", 0))
        for l in all_completed
    )
    cross_band_outside_refuge = sum(
        int(l.get("cross_band_misses_outside_refuge", 0))
        for l in all_completed
    )

    return {
        "median_prey_sighting_share": _safe_median(prey_sight_shares),
        "predator_hunt_speed_multiplier": float(
            runs[0]["diagnostics"].get("predator_hunt_speed_multiplier", 0.0)
        ),
        "prey_flee_speed_multiplier": float(
            runs[0]["diagnostics"].get("prey_flee_speed_multiplier", 0.0)
        ),
        "predator_contact_kill_distance_scale": float(
            runs[0]["diagnostics"].get("predator_contact_kill_distance_scale", 0.0)
        ),
        "pct_lives_with_no_prey_sightings": _pct(no_prey_sightings, len(all_completed)),
        "pct_lives_with_prey_sightings_but_no_kills": _pct(
            prey_sightings_no_kills, len(all_completed)
        ),
        "pct_lives_with_cross_band_misses": _pct(
            sum(1 for m in cross_band_misses_list if m > 0),
            len(all_completed),
        ),
        "total_cross_band_misses": total_cross_band,
        "total_kills_by_completed_lives": total_kills,
        "cross_band_misses_per_kill": (
            total_cross_band / total_kills
            if total_kills > 0 else None
        ),
        "mean_refuge_frames_per_life": _safe_mean(refuge_frames_per_life),
        "mean_hunting_ground_frames_per_life": _safe_mean(
            hunting_ground_frames_per_life
        ),
        "median_refuge_frame_share": _safe_median(refuge_frame_shares),
        "median_hunting_ground_frame_share": _safe_median(
            hunting_ground_frame_shares
        ),
        "kills_inside_refuge": kills_inside_refuge,
        "kills_outside_refuge": kills_outside_refuge,
        "deaths_inside_refuge": deaths_inside_refuge,
        "pct_deaths_inside_refuge": _pct(deaths_inside_refuge, len(all_completed)),
        "mean_refuge_bonus_factor_at_death": _safe_mean(refuge_bonus_at_death),
        "mean_local_predator_density_at_death": _safe_mean(
            predator_density_at_death
        ),
        "cross_band_misses_inside_refuge": cross_band_inside_refuge,
        "cross_band_misses_outside_refuge": cross_band_outside_refuge,
    }


def _section_g_scarcity(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """G. Scarcity analysis."""
    all_completed: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])

    if not all_completed:
        return {"note": "No completed predator lives"}

    scarce_shares = []
    high_scarcity_deaths = []
    for life in all_completed:
        frames = int(life["frames_observed"])
        if frames > 0:
            share = int(life["prey_scarce_frames"]) / frames
            scarce_shares.append(share)
            if share > 0.75 and life.get("death_context") != "old_age":
                high_scarcity_deaths.append({
                    "life_id": life["life_id"],
                    "prey_scarce_share": round(share, 3),
                    "death_context": life.get("death_context"),
                    "kills": int(life["kills"]),
                    "lifespan": (
                        int(life["end_frame"]) - int(life["start_frame"])
                        if life["end_frame"] is not None else None
                    ),
                })

    # Cross-reference with death context
    context_scarcity: dict[str, list[float]] = {}
    for life in all_completed:
        frames = int(life["frames_observed"])
        ctx = _classify_death_context(life.get("death_context"))
        if frames > 0:
            share = int(life["prey_scarce_frames"]) / frames
            context_scarcity.setdefault(ctx, []).append(share)

    context_median_scarcity = {
        ctx: _safe_median(shares) for ctx, shares in context_scarcity.items()
    }

    return {
        "median_prey_scarce_share": _safe_median(scarce_shares),
        "pct_lives_high_scarcity_gt_75pct": _pct(
            sum(1 for s in scarce_shares if s > 0.75),
            len(scarce_shares),
        ),
        "median_scarcity_by_death_context": context_median_scarcity,
        "high_scarcity_death_count": len(high_scarcity_deaths),
        "high_scarcity_death_examples": high_scarcity_deaths[:10],
    }


def _section_g_near_contact_dance(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """G. Near-contact / dance analysis."""
    all_completed: list[dict] = []
    for run in runs:
        all_completed.extend(run["diagnostics"]["completed_lives"])

    if not all_completed:
        return {"note": "No completed predator lives"}

    total_near_contact_frames = sum(
        int(l.get("near_contact_frames", 0)) for l in all_completed
    )
    total_near_contact_no_kill_frames = sum(
        int(l.get("near_contact_no_kill_frames", 0)) for l in all_completed
    )
    total_same_depth_no_kill_frames = sum(
        int(l.get("near_contact_same_depth_no_kill_frames", 0))
        for l in all_completed
    )
    total_cross_depth_no_kill_frames = sum(
        int(l.get("near_contact_cross_depth_no_kill_frames", 0))
        for l in all_completed
    )
    near_contact_old_no_kill_frames = sum(
        int(l.get("near_contact_no_kill_with_old_prey_frames", 0))
        for l in all_completed
    )
    near_contact_low_energy_no_kill_frames = sum(
        int(l.get("near_contact_no_kill_with_low_energy_prey_frames", 0))
        for l in all_completed
    )
    max_sustained_chase_frames = [
        int(l.get("max_sustained_chase_frames", 0)) for l in all_completed
    ]
    sustained_chase_min_frames = max(
        int(run["diagnostics"].get("predator_sustained_chase_min_frames", 20))
        for run in runs
    )
    sustained_chase_lives = sum(
        1 for frames in max_sustained_chase_frames if frames >= sustained_chase_min_frames
    )
    kills_after_sustained_chase = sum(
        int(l.get("kills_after_sustained_chase", 0)) for l in all_completed
    )

    killed_prey_age_fractions: list[float] = []
    killed_prey_energies: list[float] = []
    condition_counts: dict[str, int] = {}
    age_bucket_counts = {"young": 0, "old": 0}
    energy_bucket_counts = {"healthy": 0, "low_energy": 0}
    old_or_low_kill_count = 0
    old_kill_count = 0
    low_energy_kill_count = 0

    for life in all_completed:
        age_fractions = [float(v) for v in life.get("killed_prey_age_fractions", [])]
        energies = [float(v) for v in life.get("killed_prey_energies", [])]
        condition_buckets = [
            str(v) for v in life.get("killed_prey_condition_buckets", [])
        ]
        killed_prey_age_fractions.extend(age_fractions)
        killed_prey_energies.extend(energies)
        for bucket in condition_buckets:
            condition_counts[bucket] = condition_counts.get(bucket, 0) + 1
            if bucket in {"old", "old_low_energy"}:
                old_kill_count += 1
                age_bucket_counts["old"] += 1
            else:
                age_bucket_counts["young"] += 1
            if bucket in {"low_energy", "old_low_energy"}:
                low_energy_kill_count += 1
                energy_bucket_counts["low_energy"] += 1
            else:
                energy_bucket_counts["healthy"] += 1
            if bucket != "young_healthy":
                old_or_low_kill_count += 1

    total_kill_samples = sum(condition_counts.values())

    return {
        "total_near_contact_frames": total_near_contact_frames,
        "near_contact_no_kill_frames": total_near_contact_no_kill_frames,
        "same_depth_near_contact_no_kill_frames": total_same_depth_no_kill_frames,
        "cross_depth_near_contact_no_kill_frames": total_cross_depth_no_kill_frames,
        "near_contact_frames_per_completed_life": (
            total_near_contact_frames / len(all_completed)
            if all_completed else None
        ),
        "pct_lives_with_near_contact_no_kill_frames": _pct(
            sum(
                1
                for l in all_completed
                if int(l.get("near_contact_no_kill_frames", 0)) > 0
            ),
            len(all_completed),
        ),
        "median_max_sustained_chase_frames": _safe_median(
            max_sustained_chase_frames
        ),
        "pct_lives_with_sustained_chase": _pct(
            sustained_chase_lives,
            len(all_completed),
        ),
        "kills_after_sustained_chase": kills_after_sustained_chase,
        "memory_chase_frames": sum(int(l.get("memory_chase_frames", 0)) for l in all_completed),
        "memory_chase_frames_per_completed_life": (
            sum(int(l.get("memory_chase_frames", 0)) for l in all_completed) / len(all_completed)
            if all_completed else None
        ),
        "memory_target_reacquisitions": sum(int(l.get("memory_target_reacquisitions", 0)) for l in all_completed),
        "memory_target_reacquisitions_per_completed_life": (
            sum(int(l.get("memory_target_reacquisitions", 0)) for l in all_completed) / len(all_completed)
            if all_completed else None
        ),
        "target_switches": sum(int(l.get("target_switches", 0)) for l in all_completed),
        "target_switches_per_completed_life": (
            sum(int(l.get("target_switches", 0)) for l in all_completed) / len(all_completed)
            if all_completed else None
        ),
        "memory_target_dropped_frames": sum(int(l.get("memory_target_dropped_frames", 0)) for l in all_completed),
        "memory_target_expired_drops": sum(int(l.get("memory_target_expired_drops", 0)) for l in all_completed),
        "kills_after_memory_chase": sum(int(l.get("kills_after_memory_chase", 0)) for l in all_completed),
        "pct_kills_after_memory_chase": _pct(
            sum(int(l.get("kills_after_memory_chase", 0)) for l in all_completed),
            total_kills,
        ),
        "killed_prey_age_bucket_counts": age_bucket_counts,
        "killed_prey_energy_bucket_counts": energy_bucket_counts,
        "killed_prey_condition_bucket_counts": condition_counts,
        "average_killed_prey_age_fraction": _safe_mean(killed_prey_age_fractions),
        "average_killed_prey_energy": _safe_mean(killed_prey_energies),
        "pct_kills_old_prey": _pct(old_kill_count, total_kill_samples),
        "pct_kills_low_energy_prey": _pct(low_energy_kill_count, total_kill_samples),
        "pct_kills_old_or_low_energy_prey": _pct(
            old_or_low_kill_count,
            total_kill_samples,
        ),
        "pct_near_contact_no_kill_frames_with_old_prey": _pct(
            near_contact_old_no_kill_frames,
            total_near_contact_no_kill_frames,
        ),
        "pct_near_contact_no_kill_frames_with_low_energy_prey": _pct(
            near_contact_low_energy_no_kill_frames,
            total_near_contact_no_kill_frames,
        ),
        "sustained_chase_min_frames": sustained_chase_min_frames,
    }


def _section_rarity_advantage(runs: list[dict[str, Any]]) -> dict[str, Any]:
    all_completed: list[dict] = []
    for run in runs:
        all_completed.extend(run["diagnostics"]["completed_lives"])
    if not all_completed:
        return {"note": "No completed predator lives"}
    rarity_active = [l for l in all_completed if int(l.get("rarity_frames", 0)) > 0]
    rarity_inactive = [l for l in all_completed if int(l.get("rarity_frames", 0)) <= 0]
    active_zero_kill = _pct(sum(1 for l in rarity_active if int(l.get("kills", 0)) == 0), len(rarity_active))
    inactive_zero_kill = _pct(sum(1 for l in rarity_inactive if int(l.get("kills", 0)) == 0), len(rarity_inactive))
    active_repro = _pct(sum(1 for l in rarity_active if int(l.get("births_produced", 0)) > 0), len(rarity_active))
    inactive_repro = _pct(sum(1 for l in rarity_inactive if int(l.get("births_produced", 0)) > 0), len(rarity_inactive))
    active_lifespans = [int(l["end_frame"]) - int(l["start_frame"]) for l in rarity_active if l.get("end_frame") is not None]
    inactive_lifespans = [int(l["end_frame"]) - int(l["start_frame"]) for l in rarity_inactive if l.get("end_frame") is not None]
    return {
        "rarity_active_lives": len(rarity_active),
        "pct_rarity_active_lives": _pct(len(rarity_active), len(all_completed)),
        "median_avg_rarity_pressure": _safe_median([float(l.get("avg_rarity_pressure", 0.0)) for l in rarity_active]),
        "kills_while_rarity_active": sum(int(l.get("kills_while_rarity_active", 0)) for l in all_completed),
        "births_while_rarity_active": sum(int(l.get("births_while_rarity_active", 0)) for l in all_completed),
        "deaths_while_rarity_active": sum(int(l.get("deaths_while_rarity_active", 0)) for l in all_completed),
        "zero_kill_rate_rarity_active": active_zero_kill,
        "zero_kill_rate_rarity_inactive": inactive_zero_kill,
        "repro_rate_rarity_active": active_repro,
        "repro_rate_rarity_inactive": inactive_repro,
        "median_lifespan_rarity_active": _safe_median(active_lifespans),
        "median_lifespan_rarity_inactive": _safe_median(inactive_lifespans),
        "median_kills_rarity_active": _safe_median([int(l.get("kills", 0)) for l in rarity_active]),
        "median_kills_rarity_inactive": _safe_median([int(l.get("kills", 0)) for l in rarity_inactive]),
    }


def _section_h_epistasis(
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """H. Epistasis / body-plan analysis."""
    all_completed: list[dict] = []
    for run in runs:
        diag = run["diagnostics"]
        all_completed.extend(diag["completed_lives"])

    if not all_completed:
        return {"note": "No completed predator lives"}

    # Strategy buckets among deaths
    death_strategy_counts: dict[str, int] = {}
    death_modifier_sums: dict[str, float] = {
        "speed_mult": 0.0,
        "movement_cost_mult": 0.0,
        "metabolic_cost_mult": 0.0,
        "sense_radius_mult": 0.0,
        "food_efficiency_mult": 0.0,
        "reproduction_threshold_mult": 0.0,
        "predation_contact_mult": 0.0,
        "flee_agility_mult": 0.0,
    }
    death_count_with_strategy = 0

    # Strategy buckets among reproducers
    reproducer_strategy_counts: dict[str, int] = {}
    reproducer_count = 0

    for life in all_completed:
        end_bucket = life.get("strategy_bucket_at_end") or life.get("strategy_bucket_at_start") or "unknown"
        death_strategy_counts[end_bucket] = death_strategy_counts.get(end_bucket, 0) + 1
        death_count_with_strategy += 1

        end_mods = life.get("phenotype_modifiers_at_end")
        if end_mods:
            for key in death_modifier_sums:
                if key in end_mods:
                    death_modifier_sums[key] += float(end_mods[key])

        if int(life["births_produced"]) > 0:
            reproducer_strategy_counts[end_bucket] = reproducer_strategy_counts.get(end_bucket, 0) + 1
            reproducer_count += 1

    avg_modifiers = {}
    if death_count_with_strategy > 0:
        for key, total in death_modifier_sums.items():
            avg_modifiers[key] = total / death_count_with_strategy

    # Global epistasis summary from last run
    epi_summary = runs[-1]["epistasis_summary"] if runs else {}

    return {
        "strategy_buckets_among_deaths": death_strategy_counts,
        "strategy_buckets_among_reproducers": reproducer_strategy_counts,
        "reproducer_count": reproducer_count,
        "avg_phenotype_modifiers_for_dead_predators": avg_modifiers,
        "global_epistasis_summary": epi_summary,
    }


def _section_k_recommendations(
    runs: list[dict[str, Any]],
    section_c: dict[str, Any],
    section_g: dict[str, Any],
    section_h: dict[str, Any],
    section_i: dict[str, Any],
    section_f: dict[str, Any],
    section_e: dict[str, Any],
    section_d: list[dict[str, Any]],
    section_j: dict[str, Any],
) -> list[str]:
    """K. Data-driven plain-language intervention recommendations."""
    recommendations: list[str] = []

    contexts = section_c.get("contexts", {})
    total_deaths = section_c.get("total", 0) or 1

    # Check death context dominance
    long_scarcity_pct = 100.0 * contexts.get("long_scarcity", 0) / total_deaths
    active_hunting_pct = 100.0 * contexts.get("active_hunting", 0) / total_deaths
    after_failed_pursuit_pct = 100.0 * contexts.get("after_failed_pursuit", 0) / total_deaths
    old_age_pct = 100.0 * contexts.get("old_age", 0) / total_deaths

    if long_scarcity_pct > 40:
        recommendations.append(
            f"LONG SCARCITY dominates ({long_scarcity_pct:.0f}% of deaths): "
            "Predator rarity advantage or predator refuge likely helps. "
            "Predators are not finding prey often enough."
        )

    if active_hunting_pct + after_failed_pursuit_pct > 40:
        recommendations.append(
            f"ACTIVE/FAILED PURSUIT dominates ({active_hunting_pct:.0f}% active, "
            f"{after_failed_pursuit_pct:.0f}% failed pursuit): "
            "Contact/sense/depth tuning or refuges likely help. "
            "Predators see prey but cannot convert."
        )

    # Check juvenile predators
    for origin_row in section_d:
        origin = origin_row["origin"]
        lifespan = origin_row["median_lifespan"]
        kills = origin_row["median_kills"]
        if origin == "birth" and lifespan is not None and lifespan < 200 and (kills is None or kills == 0):
            recommendations.append(
                f"BIRTH-ORIGIN predators die very young (median lifespan {lifespan}) "
                f"with {kills} kills: juvenile protection likely helps."
            )
            break

    # Check reproduction bottleneck
    kills_no_births = section_e.get("kills_but_no_births", 0)
    threshold_no_births = section_e.get("threshold_reached_but_no_births", 0)
    total_lives = section_e.get("total_predator_lives", 0) or 1

    if threshold_no_births > 0:
        recommendations.append(
            f"Reproduction gate issue: {threshold_no_births} predators "
            f"({100.0 * threshold_no_births / total_lives:.0f}%) reached the energy threshold "
            f"but failed the post-cost reproduction check. Review recent_animal_energy "
            f"gate, satiety ticks, or kill-cap interactions."
        )

    if kills_no_births > total_lives * 0.3:
        recommendations.append(
            f"Kill-without-reproduction: {kills_no_births} predators ({100.0 * kills_no_births / total_lives:.0f}%) "
            f"had kills but never reproduced. Energy decay, threshold height, or "
            f"kill-cap may be the bottleneck."
        )

    # Check cross-band misses
    cross_band_per_kill = section_f.get("cross_band_misses_per_kill")
    if cross_band_per_kill is not None and cross_band_per_kill > 2.0:
        recommendations.append(
            f"Cross-band misses per kill = {cross_band_per_kill:.1f}: "
            "Depth mechanics are the bottleneck. Predators find prey across "
            "depth bands but cannot kill because they are on the wrong band."
        )

    if "note" not in section_g:
        near_contact_no_kill_frames = int(
            section_g.get("near_contact_no_kill_frames", 0)
        )
        same_depth_no_kill_frames = int(
            section_g.get("same_depth_near_contact_no_kill_frames", 0)
        )
        cross_depth_no_kill_frames = int(
            section_g.get("cross_depth_near_contact_no_kill_frames", 0)
        )
        if (
            near_contact_no_kill_frames >= 25
            and same_depth_no_kill_frames >= cross_depth_no_kill_frames
            and same_depth_no_kill_frames >= max(10, near_contact_no_kill_frames * 0.5)
        ):
            recommendations.append(
                "Near-contact same-depth no-kill frames are high: contact/flee "
                "oscillation is likely still trapping predators in close-range dances."
            )
        if (
            cross_depth_no_kill_frames >= 25
            and cross_depth_no_kill_frames > same_depth_no_kill_frames
        ):
            recommendations.append(
                "Near-contact cross-depth misses dominate: depth mismatch appears "
                "to be the main hunting bottleneck rather than flee-speed oscillation."
            )

        pct_lives_with_sustained_chase = float(
            section_g.get("pct_lives_with_sustained_chase", 0.0)
        )
        kills_after_sustained_chase = int(
            section_g.get("kills_after_sustained_chase", 0)
        )
        total_kills = sum(int(run.get("total_kills", 0)) for run in runs)
        if pct_lives_with_sustained_chase >= 20.0 and (
            total_kills <= 0
            or (kills_after_sustained_chase / max(1, total_kills)) < 0.15
        ):
            recommendations.append(
                "Sustained chases are common but rarely end in kills; if this "
                "persists after prey frailty tuning, a later lunge/strike mechanic "
                "would be worth evaluating."
            )

        old_or_low_kill_share = float(
            section_g.get("pct_kills_old_or_low_energy_prey", 0.0)
        )
        if old_or_low_kill_share >= 50.0:
            recommendations.append(
                "Kills skew toward old or low-energy prey, which suggests prey "
                "frailty is functioning as intended without directly changing reproduction."
            )
        young_healthy_kills = int(
            section_g.get("killed_prey_condition_bucket_counts", {}).get(
                "young_healthy",
                0,
            )
        )
        total_kill_samples = sum(
            int(v)
            for v in section_g.get("killed_prey_condition_bucket_counts", {}).values()
        )
        prey_finals = [int(run.get("final_prey_count", 0)) for run in runs]
        if (
            total_kill_samples > 0
            and (young_healthy_kills / total_kill_samples) >= 0.65
            and prey_finals
            and min(prey_finals) <= 0
        ):
            recommendations.append(
                "Healthy-young prey make up most kills and prey collapse occurred; "
                "prey frailty may be too strong or too broadly applied."
            )

    # Check prey abundance vs starvation
    median_scarce_share = section_h.get("median_prey_scarce_share")
    median_prey_sighting = section_f.get("median_prey_sighting_share")
    if median_scarce_share is not None and median_prey_sighting is not None:
        if median_prey_sighting > 0.2 and median_scarce_share > 0.5:
            recommendations.append(
                f"Paradoxical scarcity: usable prey sighting share "
                f"{median_prey_sighting:.0%} but scarce share "
                f"{median_scarce_share:.0%}. Predators see prey in some frames "
                f"but spend most time in scarcity. Predator sensing/refuge/foraging "
                f"bridge may be weak."
            )
    if "note" not in section_i:
        active_pct = float(section_i.get("pct_rarity_active_lives", 0.0))
        active_repro = float(section_i.get("repro_rate_rarity_active", 0.0))
        inactive_repro = float(section_i.get("repro_rate_rarity_inactive", 0.0))
        active_zero = float(section_i.get("zero_kill_rate_rarity_active", 0.0))
        inactive_zero = float(section_i.get("zero_kill_rate_rarity_inactive", 0.0))
        if active_pct < 5.0:
            recommendations.append("Rarity advantage rarely activates; thresholds may be too strict or collapse too abrupt.")
        elif active_repro > inactive_repro and active_zero < inactive_zero:
            recommendations.append("Rarity advantage appears promising: rarity-active lives show better kill/reproduction outcomes.")
        else:
            recommendations.append("Rarity advantage activates but shows weak lift; it may be too weak or applied to suboptimal hunt surfaces.")
        prey_finals = [int(run.get("final_prey_count", 0)) for run in runs]
        if active_repro > inactive_repro and prey_finals and min(prey_finals) <= 0:
            recommendations.append("Rarity-active predators improved, but prey collapses occurred; rarity bonus may be too strong.")

    if not recommendations:
        recommendations.append(
            "No dominant collapse pattern detected in this sample. "
            "Consider running more seeds or examining individual run traces."
        )

    return recommendations


# ---------------------------------------------------------------------------
# Full report builder
# ---------------------------------------------------------------------------

def build_report(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the full structured report from multiple run results."""
    section_a = _section_a_run_summary(runs)
    section_b = _section_b_predator_life_summary(runs)
    section_c = _section_c_death_context_breakdown(runs)
    section_d = _section_d_origin_breakdown(runs)
    section_e = _section_e_reproduction_bottleneck(runs)
    section_f = _section_f_prey_access(runs)
    section_g = _section_g_near_contact_dance(runs)
    section_h = _section_g_scarcity(runs)
    section_i = _section_rarity_advantage(runs)
    section_j = _section_h_epistasis(runs)
    section_k = _section_k_recommendations(
        runs,
        section_c,
        section_g,
        section_h,
        section_i,
        section_f,
        section_e,
        section_d,
        section_j,
    )

    return {
        "report_timestamp": datetime.now(timezone.utc).isoformat(),
        "runs": len(runs),
        "max_ticks": runs[0]["max_ticks"] if runs else 0,
        "section_a_run_summary": section_a,
        "section_b_predator_life_summary": section_b,
        "section_c_death_context_breakdown": section_c,
        "section_d_origin_breakdown": section_d,
        "section_e_reproduction_bottleneck": section_e,
        "section_f_prey_access": section_f,
        "section_g_near_contact_dance_analysis": section_g,
        "section_h_scarcity": section_h,
        "section_i_rarity_advantage_analysis": section_i,
        "section_j_epistasis_body_plan": section_j,
        "section_k_recommendations": section_k,
    }


# ---------------------------------------------------------------------------
# Markdown formatter
# ---------------------------------------------------------------------------

def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _pct_fmt(value: float) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%"


def _share_fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100.0:.1f}%"


def render_markdown(report: dict[str, Any]) -> str:
    """Render the structured report as a human-readable Markdown document."""
    lines: list[str] = []

    lines.append("# Predator Collapse Diagnostics Report")
    lines.append("")
    lines.append(f"- **Runs:** {report['runs']}")
    lines.append(f"- **Max ticks per run:** {report['max_ticks']}")
    lines.append(f"- **Generated:** {report['report_timestamp']}")
    lines.append("")

    # A. Run Summary
    lines.append("## A. Run Summary")
    lines.append("")
    lines.append("| Seed | Ticks | Game Over | Collapse Cause | First Pred 0 | Pred0 Ticks | Pred Count | Prey Count | Total Kills | Survival Ticks |")
    lines.append("|------|-------|-----------|-----------------|--------------|-------------|------------|------------|-------------|----------------|")
    for row in report["section_a_run_summary"]:
        lines.append(
            f"| {row['seed']} "
            f"| {row['final_sim_ticks']} "
            f"| {'Yes' if row['game_over'] else 'No'} "
            f"| {_fmt(row['collapse_cause'])} "
            f"| {_fmt(row['first_predator_zero_tick'])} "
            f"| {row['predator_zero_ticks_at_end']} "
            f"| {row['final_predator_count']} "
            f"| {row['final_prey_count']} "
            f"| {row['total_kills']} "
            f"| {row['survival_ticks']} |"
        )
    lines.append("")

    # B. Predator Life Summary
    lines.append("## B. Predator Life Summary")
    lines.append("")
    b = report["section_b_predator_life_summary"]
    if b.get("predator_lives_started", 0) == 0:
        lines.append("No predator lives recorded.")
    else:
        lines.append(f"- **Lives started:** {b['predator_lives_started']}")
        lines.append(f"- **Completed:** {b['completed_predator_lives']}")
        lines.append(f"- **Active at end:** {b['active_predator_lives_at_end']}")
        lines.append(f"- **Total births produced:** {b['total_births_produced']}")
        lines.append(f"- **Total kills:** {b['total_kills']}")
        lines.append(f"- **Mean kills/life:** {_fmt(b['mean_kills_per_life'])}")
        lines.append(f"- **Median kills/life:** {_fmt(b['median_kills_per_life'])}")
        lines.append(f"- **% with zero kills:** {_pct_fmt(b['pct_with_zero_kills'])}")
        lines.append(f"- **% with ≥1 kill:** {_pct_fmt(b['pct_with_at_least_one_kill'])}")
        lines.append(f"- **% that reproduced:** {_pct_fmt(b['pct_that_produced_offspring'])}")
        lines.append(f"- **Median lifespan:** {_fmt(b['median_lifespan'])} ticks")
        lines.append(f"- **Median highest energy:** {_fmt(b['median_highest_energy'])}")
        lines.append(f"- **Median closest gap to repro threshold:** {_fmt(b['median_closest_gap_to_reproduction_threshold'])}")
        lines.append(f"- **% ever reached repro threshold:** {_pct_fmt(b['pct_ever_reached_reproduction_threshold'])}")
        lines.append(f"- **% repro-check reached threshold:** {_pct_fmt(b['pct_repro_check_reached_threshold'])}")
        lines.append(f"- **Kills but no births:** {b['kills_but_no_births']}")
        lines.append(f"- **Threshold reached but no births:** {b['threshold_reached_but_no_births']}")
    lines.append("")

    # C. Death Context Breakdown
    lines.append("## C. Death Context Breakdown")
    lines.append("")
    c = report["section_c_death_context_breakdown"]
    total = c.get("total", 0) or 1
    for ctx, count in sorted(c.get("contexts", {}).items()):
        explanation = c.get("explanations", {}).get(ctx, "")
        lines.append(
            f"- **{ctx}**: {count} ({100.0 * count / total:.1f}%) — {explanation}"
        )
    lines.append("")

    # D. Origin Breakdown
    lines.append("## D. Origin Breakdown")
    lines.append("")
    lines.append("| Origin | Count | Median Lifespan | Median Kills | % Reproduced |")
    lines.append("|--------|-------|-----------------|--------------|--------------|")
    for row in report["section_d_origin_breakdown"]:
        lines.append(
            f"| {row['origin']} "
            f"| {row['count']} "
            f"| {_fmt(row['median_lifespan'])} "
            f"| {_fmt(row['median_kills'])} "
            f"| {_pct_fmt(row['pct_reproduced'])} |"
        )
    lines.append("")

    # E. Reproduction Bottleneck
    lines.append("## E. Reproduction Bottleneck Analysis")
    lines.append("")
    e = report["section_e_reproduction_bottleneck"]
    lines.append(f"- **Base reproduction threshold:** {_fmt(e.get('base_reproduction_threshold'))}")
    lines.append(f"- **Kill energy gain cap:** {_fmt(e.get('predator_kill_energy_gain_cap'))}")
    lines.append(f"- **Kill-cap / threshold ratio:** {_fmt(e.get('kill_gap_to_threshold_ratio'))}")
    lines.append(f"- **Threshold range seen:** {_fmt(e.get('threshold_min_seen'))} – {_fmt(e.get('threshold_max_seen'))}")
    lines.append(f"- **Median closest peak gap:** {_fmt(e.get('median_closest_peak_gap'))}")
    lines.append(f"- **Median closest repro-check gap:** {_fmt(e.get('median_closest_repro_check_gap'))}")
    lines.append(f"- **Near-miss (≤0.02 gap):** {e.get('near_miss_within_0_02', 0)}")
    lines.append(f"- **Near-miss (≤0.05 gap):** {e.get('near_miss_within_0_05', 0)}")
    lines.append(f"- **Peak reached threshold:** {e.get('peak_reached_threshold_count', 0)}")
    lines.append(f"- **Repro-check reached threshold:** {e.get('repro_check_reached_threshold_count', 0)}")
    lines.append(f"- **Kills but no births:** {e.get('kills_but_no_births', 0)}")
    lines.append(f"- **Threshold reached but no births:** {e.get('threshold_reached_but_no_births', 0)}")
    interp = e.get("interpretation", {})
    for key, val in interp.items():
        lines.append(f"  - {key}: {val}")
    lines.append("")

    # F. Prey Access
    lines.append("## F. Prey Access / Hunting Bottleneck")
    lines.append("")
    f = report["section_f_prey_access"]
    if "note" in f:
        lines.append(f["note"])
    else:
        lines.append(f"- **Median usable prey-sighting share:** {_share_fmt(f.get('median_prey_sighting_share'))}")
        lines.append(f"- **% lives with no prey sightings:** {_pct_fmt(f.get('pct_lives_with_no_prey_sightings'))}")
        lines.append(f"- **% lives with sightings but no kills:** {_pct_fmt(f.get('pct_lives_with_prey_sightings_but_no_kills'))}")
        lines.append("- **Sighting metric note:** Counted only when final depth-adjusted sensing succeeds and a steerable target position exists; this is finite-radius omnidirectional target acquisition, not guaranteed catch opportunity.")
        lines.append(f"- **% lives with cross-band misses:** {_pct_fmt(f.get('pct_lives_with_cross_band_misses'))}")
        lines.append(f"- **Total cross-band misses:** {f.get('total_cross_band_misses', 0)}")
        lines.append(f"- **Total kills by completed lives:** {f.get('total_kills_by_completed_lives', 0)}")
        lines.append(f"- **Cross-band misses per kill:** {_fmt(f.get('cross_band_misses_per_kill'))}")
        lines.append(f"- **Mean refuge frames / life:** {_fmt(f.get('mean_refuge_frames_per_life'))}")
        lines.append(f"- **Mean hunting-ground frames / life:** {_fmt(f.get('mean_hunting_ground_frames_per_life'))}")
        lines.append(f"- **Median refuge frame share:** {_share_fmt(f.get('median_refuge_frame_share'))}")
        lines.append(f"- **Median hunting-ground frame share:** {_share_fmt(f.get('median_hunting_ground_frame_share'))}")
        lines.append(f"- **Kills inside refuge:** {f.get('kills_inside_refuge', 0)}")
        lines.append(f"- **Kills outside refuge:** {f.get('kills_outside_refuge', 0)}")
        lines.append(f"- **Deaths inside refuge:** {f.get('deaths_inside_refuge', 0)} ({_pct_fmt(f.get('pct_deaths_inside_refuge'))})")
        lines.append(f"- **Mean refuge bonus at death:** {_fmt(f.get('mean_refuge_bonus_factor_at_death'))}")
        lines.append(f"- **Mean local predator density at death:** {_fmt(f.get('mean_local_predator_density_at_death'))}")
        lines.append(f"- **Cross-band misses inside refuge:** {f.get('cross_band_misses_inside_refuge', 0)}")
        lines.append(f"- **Cross-band misses outside refuge:** {f.get('cross_band_misses_outside_refuge', 0)}")
    lines.append("")

    # G. Near-Contact / Dance
    lines.append("## G. Near-Contact / Dance Analysis")
    lines.append("")
    g = report["section_g_near_contact_dance_analysis"]
    if "note" in g:
        lines.append(g["note"])
    else:
        lines.append(f"- **Total near-contact frames:** {g.get('total_near_contact_frames', 0)}")
        lines.append(f"- **Near-contact no-kill frames:** {g.get('near_contact_no_kill_frames', 0)}")
        lines.append(f"- **Same-depth near-contact no-kill frames:** {g.get('same_depth_near_contact_no_kill_frames', 0)}")
        lines.append(f"- **Cross-depth near-contact no-kill frames:** {g.get('cross_depth_near_contact_no_kill_frames', 0)}")
        lines.append(f"- **Near-contact frames / completed life:** {_fmt(g.get('near_contact_frames_per_completed_life'))}")
        lines.append(f"- **% lives with near-contact no-kill frames:** {_pct_fmt(g.get('pct_lives_with_near_contact_no_kill_frames'))}")
        lines.append(f"- **Median max sustained chase frames:** {_fmt(g.get('median_max_sustained_chase_frames'))}")
        lines.append(f"- **% lives with sustained chase:** {_pct_fmt(g.get('pct_lives_with_sustained_chase'))}")
        lines.append(f"- **Kills after sustained chase:** {g.get('kills_after_sustained_chase', 0)}")
        lines.append(f"- **Memory chase frames:** {g.get('memory_chase_frames', 0)}")
        lines.append(f"- **Memory chase frames / completed life:** {_fmt(g.get('memory_chase_frames_per_completed_life'))}")
        lines.append(f"- **Memory target reacquisitions:** {g.get('memory_target_reacquisitions', 0)}")
        lines.append(f"- **Reacquisitions / completed life:** {_fmt(g.get('memory_target_reacquisitions_per_completed_life'))}")
        lines.append(f"- **Target switches:** {g.get('target_switches', 0)}")
        lines.append(f"- **Target switches / completed life:** {_fmt(g.get('target_switches_per_completed_life'))}")
        lines.append(f"- **Memory target drops:** {g.get('memory_target_dropped_frames', 0)}")
        lines.append(f"- **Memory expired drops:** {g.get('memory_target_expired_drops', 0)}")
        lines.append(f"- **Kills after memory chase:** {g.get('kills_after_memory_chase', 0)}")
        lines.append(f"- **% kills after memory chase:** {_pct_fmt(g.get('pct_kills_after_memory_chase'))}")
        lines.append("- **Interpretation:** high memory frames with zero kills-after-memory may indicate broken memory-kill instrumentation.")
        lines.append("- **Interpretation:** high target switches per life can indicate twitchy target selection.")
        lines.append(
            f"- **Chase balance note (current run):** predator_hunt_speed_multiplier={_fmt(f.get('predator_hunt_speed_multiplier'))}, prey_flee_speed_multiplier={_fmt(f.get('prey_flee_speed_multiplier'))}, predator_contact_kill_distance_scale={_fmt(f.get('predator_contact_kill_distance_scale'))}, near-contact frames/life={_fmt(g.get('near_contact_frames_per_completed_life'))}"
        )
        lines.append(f"- **Killed prey age buckets:** {g.get('killed_prey_age_bucket_counts', {})}")
        lines.append(f"- **Killed prey energy buckets:** {g.get('killed_prey_energy_bucket_counts', {})}")
        lines.append(f"- **Killed prey condition buckets:** {g.get('killed_prey_condition_bucket_counts', {})}")
        lines.append(f"- **Average killed prey age fraction:** {_fmt(g.get('average_killed_prey_age_fraction'))}")
        lines.append(f"- **Average killed prey energy:** {_fmt(g.get('average_killed_prey_energy'))}")
        lines.append(f"- **% kills of old prey:** {_pct_fmt(g.get('pct_kills_old_prey'))}")
        lines.append(f"- **% kills of low-energy prey:** {_pct_fmt(g.get('pct_kills_low_energy_prey'))}")
        lines.append(f"- **% kills of old-or-low-energy prey:** {_pct_fmt(g.get('pct_kills_old_or_low_energy_prey'))}")
        lines.append(f"- **% near-contact no-kill frames with old prey:** {_pct_fmt(g.get('pct_near_contact_no_kill_frames_with_old_prey'))}")
        lines.append(f"- **% near-contact no-kill frames with low-energy prey:** {_pct_fmt(g.get('pct_near_contact_no_kill_frames_with_low_energy_prey'))}")
    lines.append("")

    # H. Scarcity
    lines.append("## H. Scarcity Analysis")
    lines.append("")
    h = report["section_h_scarcity"]
    if "note" in h:
        lines.append(h["note"])
    else:
        lines.append(f"- **Median prey-scarce share:** {_share_fmt(h.get('median_prey_scarce_share'))}")
        lines.append(f"- **% lives with >75% scarcity:** {_pct_fmt(h.get('pct_lives_high_scarcity_gt_75pct'))}")
        lines.append(f"- **High-scarcity death count:** {h.get('high_scarcity_death_count', 0)}")
        lines.append("")
        lines.append("Median scarcity by death context:")
        for ctx, med in h.get("median_scarcity_by_death_context", {}).items():
            lines.append(f"  - {ctx}: {_share_fmt(med)}")
    lines.append("")

    # I. Rarity Advantage Analysis
    lines.append("## I. Rarity Advantage Analysis")
    lines.append("")
    ra = report["section_i_rarity_advantage_analysis"]
    if "note" in ra:
        lines.append(ra["note"])
    else:
        lines.append(f"- **Predator lives with rarity advantage:** {ra.get('rarity_active_lives', 0)} ({_pct_fmt(ra.get('pct_rarity_active_lives'))})")
        lines.append(f"- **Median avg rarity pressure:** {_fmt(ra.get('median_avg_rarity_pressure'))}")
        lines.append(f"- **Kills while rarity active:** {ra.get('kills_while_rarity_active', 0)}")
        lines.append(f"- **Births while rarity active:** {ra.get('births_while_rarity_active', 0)}")
        lines.append(f"- **Deaths while rarity active:** {ra.get('deaths_while_rarity_active', 0)}")
        lines.append(f"- **Zero-kill rate (rarity-active):** {_pct_fmt(ra.get('zero_kill_rate_rarity_active'))}")
        lines.append(f"- **Zero-kill rate (non-rarity):** {_pct_fmt(ra.get('zero_kill_rate_rarity_inactive'))}")
        lines.append(f"- **Reproduction rate (rarity-active):** {_pct_fmt(ra.get('repro_rate_rarity_active'))}")
        lines.append(f"- **Reproduction rate (non-rarity):** {_pct_fmt(ra.get('repro_rate_rarity_inactive'))}")
        lines.append(f"- **Median lifespan rarity-active vs non-rarity:** {_fmt(ra.get('median_lifespan_rarity_active'))} vs {_fmt(ra.get('median_lifespan_rarity_inactive'))}")
        lines.append(f"- **Median kills rarity-active vs non-rarity:** {_fmt(ra.get('median_kills_rarity_active'))} vs {_fmt(ra.get('median_kills_rarity_inactive'))}")
    lines.append("")

    # J. Epistasis / Body-Plan
    lines.append("## J. Epistasis / Body-Plan Analysis")
    lines.append("")
    j = report["section_j_epistasis_body_plan"]
    if "note" in j:
        lines.append(j["note"])
    else:
        lines.append("Strategy buckets among deaths:")
        for bucket, count in sorted(j.get("strategy_buckets_among_deaths", {}).items()):
            lines.append(f"  - {bucket}: {count}")
        lines.append("")
        lines.append("Strategy buckets among reproducers:")
        for bucket, count in sorted(j.get("strategy_buckets_among_reproducers", {}).items()):
            lines.append(f"  - {bucket}: {count}")
        lines.append("")
        avg_mods = j.get("avg_phenotype_modifiers_for_dead_predators", {})
        if avg_mods:
            lines.append("Average phenotype modifiers for dead predators:")
            for key, val in sorted(avg_mods.items()):
                lines.append(f"  - {key}: {val:.4f}")
        epi = j.get("global_epistasis_summary", {})
        if epi:
            lines.append(f"  - Epistasis enabled: {epi.get('enabled')}")
            lines.append(f"  - Epistasis strength: {epi.get('strength')}")
            lines.append(f"  - Top strategy: {epi.get('top_strategy')} ({_share_fmt(epi.get('top_strategy_share'))})")
    lines.append("")

    # K. Recommendations
    lines.append("## K. Recommendations")
    lines.append("")
    for rec in report["section_k_recommendations"]:
        lines.append(f"1. {rec}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run predator-collapse diagnostics for predator_prey mode.",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Comma-separated list of seeds (default: 5 built-in seeds)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of runs with randomly-assigned seeds (default: 5). "
             "Ignored when --seeds is provided.",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=_DEFAULT_MAX_TICKS,
        help=f"Maximum simulation ticks per run (default: {_DEFAULT_MAX_TICKS})",
    )
    parser.add_argument(
        "--scenario",
        default="predator_prey_medium",
        help="Scenario ID to use (default: predator_prey_medium)",
    )
    parser.add_argument(
        "--output",
        default="run_logs/predator_collapse_report.md",
        help="Path for the Markdown report (default: run_logs/predator_collapse_report.md)",
    )
    parser.add_argument(
        "--json",
        default="run_logs/predator_collapse_diagnostics.json",
        help="Path for the JSON diagnostics file (default: run_logs/predator_collapse_diagnostics.json)",
    )
    parser.add_argument(
        "--epistasis",
        choices=["on", "off", "current"],
        default="current",
        help="Override epistasis setting: on, off, or current (default: current)",
    )
    args = parser.parse_args()

    if args.seeds:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
    else:
        random.seed(42)
        seeds = []
        for _ in range(args.runs):
            seeds.append(random.randint(1, 2_147_483_647))

    print(f"Running predator-collapse diagnostics: {len(seeds)} seed(s), "
          f"max {args.max_ticks} ticks each, scenario={args.scenario}, "
          f"epistasis={args.epistasis}")
    print("Each seed runs in full graphical mode (pygame window will appear).")

    runs: list[dict[str, Any]] = []
    for i, seed in enumerate(seeds):
        print(f"  Seed {seed} ({i + 1}/{len(seeds)})...", flush=True)
        result = run_simulation_graphical(
            seed,
            args.max_ticks,
            scenario_id=args.scenario,
            epistasis=args.epistasis,
        )
        runs.append(result)
        cause = result["collapse_cause"] or "none"
        ticks = result["final_sim_ticks"]
        pred = result["final_predator_count"]
        prey = result["final_prey_count"]
        print(f"    ticks={ticks}, predators={pred}, prey={prey}, "
              f"cause={cause}")

    print("Building report...")
    report = build_report(runs)

    # Write JSON
    json_path = Path(args.json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_payload = {
        "report": report,
        "raw_runs": runs,
    }
    json_path.write_text(
        json.dumps(json_payload, indent=2, sort_keys=False, default=str),
        encoding="utf-8",
    )
    print(f"JSON written to {json_path}")

    # Write Markdown
    md_path = Path(args.output)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_content = render_markdown(report)
    md_path.write_text(md_content, encoding="utf-8")
    print(f"Markdown written to {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
