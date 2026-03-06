"""Offline history capture and seeded comparison helpers for M4."""

from __future__ import annotations

import json
from pathlib import Path
import random
from statistics import mean
from typing import Any

from .scenarios import build_settings_for_scenario
from .simulation import Simulation


HISTORY_SCHEMA_VERSION = 1
HISTORY_ARTIFACT_KIND = "primordial.history"
HISTORY_ARTIFACT_VERSION = 1
COMPARE_REPORT_KIND = "primordial.history_compare"
COMPARE_REPORT_VERSION = 1
MAX_TOP_LINEAGES = 5


def generate_history_artifact(
    scenario_id: str,
    *,
    steps: int,
    sample_every: int,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run a seeded offline simulation and return sampled history."""
    if steps < 1:
        raise ValueError("steps must be at least 1")
    if sample_every < 1:
        raise ValueError("sample_every must be at least 1")

    scenario, settings = build_settings_for_scenario(scenario_id)
    resolved_seed = scenario.seed if seed is None else seed
    random.seed(resolved_seed)

    simulation = Simulation(scenario.width, scenario.height, settings)
    series = [_build_history_sample(simulation, step=0)]
    for step in range(1, steps + 1):
        simulation.step()
        if step % sample_every == 0 or step == steps:
            series.append(_build_history_sample(simulation, step=step))

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "artifact": {
            "kind": HISTORY_ARTIFACT_KIND,
            "version": HISTORY_ARTIFACT_VERSION,
        },
        "scenario": {
            "id": scenario.id,
            "mode": scenario.mode,
            "seed": resolved_seed,
            "width": scenario.width,
            "height": scenario.height,
            "steps_requested": steps,
            "sample_every": sample_every,
        },
        "series": series,
        "summary": _build_history_summary(series),
    }


def write_history_artifact(
    scenario_id: str,
    *,
    steps: int,
    sample_every: int,
    output_path: str | Path,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run a seeded history capture and persist the JSON artifact."""
    artifact = generate_history_artifact(
        scenario_id,
        steps=steps,
        sample_every=sample_every,
        seed=seed,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return artifact


def compare_history_artifacts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded comparison report for two history artifacts."""
    _validate_history_artifact(left)
    _validate_history_artifact(right)

    left_steps = [sample["step"] for sample in left["series"]]
    right_steps = [sample["step"] for sample in right["series"]]

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "report": {
            "kind": COMPARE_REPORT_KIND,
            "version": COMPARE_REPORT_VERSION,
        },
        "left": _artifact_identity(left),
        "right": _artifact_identity(right),
        "comparable": {
            "scenario_id_match": left["scenario"]["id"] == right["scenario"]["id"],
            "mode_match": left["scenario"]["mode"] == right["scenario"]["mode"],
            "sample_count_match": len(left["series"]) == len(right["series"]),
            "sample_steps_match": left_steps == right_steps,
        },
        "determinism": {
            "same_seed": left["scenario"]["seed"] == right["scenario"]["seed"],
            "exact_match": left == right,
        },
        "delta": {
            "population_end": (
                right["summary"]["population"]["end"] - left["summary"]["population"]["end"]
            ),
            "lineages_active_end": (
                right["summary"]["lineage_history"]["active_end"]
                - left["summary"]["lineage_history"]["active_end"]
            ),
            "dominant_zone_switches": (
                right["summary"]["zone_history"]["dominant_zone_switches"]
                - left["summary"]["zone_history"]["dominant_zone_switches"]
            ),
            "dominant_zone_end_match": (
                right["summary"]["zone_history"]["dominant_zone_end"]
                == left["summary"]["zone_history"]["dominant_zone_end"]
            ),
            "strategy_shares": {
                key: right["summary"]["strategy_shares"][key] - left["summary"]["strategy_shares"][key]
                for key in left["summary"]["strategy_shares"]
            },
        },
    }


def write_comparison_report(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    output_path: str | Path,
) -> dict[str, Any]:
    """Persist a comparison report for two history artifacts."""
    report = compare_history_artifacts(left, right)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def format_history_summary(history: dict[str, Any]) -> str:
    """Render a concise human-readable summary for a history artifact."""
    _validate_history_artifact(history)

    summary = history["summary"]
    lines = [
        f"Scenario: {history['scenario']['id']}",
        f"Mode: {history['scenario']['mode']}",
        f"Seed: {history['scenario']['seed']}",
        f"Samples: {summary['samples']}",
        (
            "Population range: "
            f"{summary['population']['min']}..{summary['population']['max']} "
            f"(end {summary['population']['end']})"
        ),
        (
            "Lineages active: "
            f"{summary['lineage_history']['active_start']} -> "
            f"{summary['lineage_history']['active_end']} "
            f"(switches {summary['lineage_history']['dominant_switches']})"
        ),
        (
            "Dominant zone: "
            f"{summary['zone_history']['dominant_zone_start']} -> "
            f"{summary['zone_history']['dominant_zone_end']} "
            f"(switches {summary['zone_history']['dominant_zone_switches']})"
        ),
        (
            "Strategy means: "
            f"H={summary['strategy_shares']['hunters_mean']:.3f} "
            f"G={summary['strategy_shares']['grazers_mean']:.3f} "
            f"O={summary['strategy_shares']['opportunists_mean']:.3f}"
        ),
    ]
    if "species_history" in summary:
        lines.append(
            "Species end: "
            f"predators={summary['species_history']['predators_end']} "
            f"prey={summary['species_history']['prey_end']}"
        )
    if "flock_history" in summary:
        lines.append(
            "Flocks end: "
            f"count={summary['flock_history']['count_end']} "
            f"largest={summary['flock_history']['largest_end']}"
        )
    return "\n".join(lines)


def _build_history_sample(simulation: Simulation, *, step: int) -> dict[str, Any]:
    snapshot = simulation.build_observability_snapshot()
    population = simulation.population
    lineage_counts = simulation.get_lineage_counts()
    top_lineages = [
        {
            "lineage_id": lineage_id,
            "population": count,
            "share": (count / population) if population > 0 else 0.0,
        }
        for lineage_id, count in sorted(
            lineage_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:MAX_TOP_LINEAGES]
    ]

    sample: dict[str, Any] = {
        "step": step,
        "generation": simulation.generation,
        "population": population,
        "food_count": simulation.food_count,
        "lineages": {
            "active": snapshot["lineages"]["active"],
            "largest_population": top_lineages[0]["population"] if top_lineages else 0,
            "largest_share": top_lineages[0]["share"] if top_lineages else 0.0,
            "top": top_lineages,
        },
        "strategies": dict(snapshot["strategies"]),
        "zone_occupancy": dict(snapshot["zone_occupancy"]),
        "dominant_zone": _dominant_zone(snapshot["zone_occupancy"]),
    }
    if "species" in snapshot:
        sample["species"] = dict(snapshot["species"])
    if "flocks" in snapshot:
        sample["flocks"] = dict(snapshot["flocks"])
    return sample


def _build_history_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    populations = [sample["population"] for sample in series]
    active_lineages = [sample["lineages"]["active"] for sample in series]
    dominant_lineages = [
        sample["lineages"]["top"][0]["lineage_id"] if sample["lineages"]["top"] else None
        for sample in series
    ]
    dominant_zones = [sample["dominant_zone"] for sample in series]

    summary: dict[str, Any] = {
        "samples": len(series),
        "sample_steps": [sample["step"] for sample in series],
        "population": {
            "start": populations[0],
            "end": populations[-1],
            "min": min(populations),
            "max": max(populations),
            "mean": mean(populations),
        },
        "lineage_history": {
            "active_start": active_lineages[0],
            "active_end": active_lineages[-1],
            "active_max": max(active_lineages),
            "dominant_switches": _count_switches(dominant_lineages),
            "largest_share_mean": mean(sample["lineages"]["largest_share"] for sample in series),
        },
        "zone_history": {
            "dominant_zone_start": dominant_zones[0],
            "dominant_zone_end": dominant_zones[-1],
            "dominant_zone_switches": _count_switches(dominant_zones),
            "mean_counts": {
                zone: mean(sample["zone_occupancy"][zone] for sample in series)
                for zone in series[0]["zone_occupancy"]
            },
        },
        "strategy_shares": {
            "hunters_mean": mean(_share(sample["strategies"]["hunters"], sample["population"]) for sample in series),
            "grazers_mean": mean(_share(sample["strategies"]["grazers"], sample["population"]) for sample in series),
            "opportunists_mean": mean(
                _share(sample["strategies"]["opportunists"], sample["population"]) for sample in series
            ),
        },
    }

    if "species" in series[-1]:
        predators = [sample["species"]["predators"] for sample in series]
        prey = [sample["species"]["prey"] for sample in series]
        summary["species_history"] = {
            "predators_end": predators[-1],
            "prey_end": prey[-1],
            "predators_mean": mean(predators),
            "prey_mean": mean(prey),
        }
    if "flocks" in series[-1]:
        flock_counts = [sample["flocks"]["count"] for sample in series]
        largest_flocks = [sample["flocks"]["largest"] for sample in series]
        summary["flock_history"] = {
            "count_end": flock_counts[-1],
            "largest_end": largest_flocks[-1],
            "count_mean": mean(flock_counts),
            "largest_mean": mean(largest_flocks),
        }

    return summary


def _dominant_zone(zone_occupancy: dict[str, int]) -> str:
    return max(zone_occupancy.items(), key=lambda item: (item[1], item[0]))[0]


def _count_switches(values: list[Any]) -> int:
    switches = 0
    previous = values[0]
    for current in values[1:]:
        if current != previous:
            switches += 1
            previous = current
    return switches


def _share(count: int, population: int) -> float:
    if population <= 0:
        return 0.0
    return count / population


def _artifact_identity(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": artifact["scenario"]["id"],
        "mode": artifact["scenario"]["mode"],
        "seed": artifact["scenario"]["seed"],
        "samples": artifact["summary"]["samples"],
    }


def _validate_history_artifact(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != HISTORY_SCHEMA_VERSION:
        raise ValueError("Unsupported history schema_version")
    artifact = payload.get("artifact", {})
    if artifact.get("kind") != HISTORY_ARTIFACT_KIND:
        raise ValueError("Unsupported history artifact kind")
