"""Pure helpers for population and lineage observability summaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

TRACKED_TRAITS = (
    "speed",
    "size",
    "sense_radius",
    "aggression",
    "efficiency",
    "longevity",
    "depth_preference",
    "conformity",
    "motion_style",
)


@dataclass(frozen=True)
class LineageObservabilitySummary:
    active_lineage_count: int
    average_lineage_age_ticks: float
    oldest_lineage_age_ticks: int


@dataclass(frozen=True)
class EvolutionSummary:
    average_age_ticks: float
    evolution_distance_mean_abs: float
    top_trait_directions: tuple[str, ...]


def average_age_ticks(creatures: Sequence[object]) -> float:
    if not creatures:
        return 0.0
    return sum(float(c.age) for c in creatures) / len(creatures)


def average_traits(creatures: Sequence[object], traits: Sequence[str] = TRACKED_TRAITS) -> dict[str, float]:
    if not creatures:
        return {trait: 0.0 for trait in traits}
    totals = {trait: 0.0 for trait in traits}
    for creature in creatures:
        for trait in traits:
            totals[trait] += float(getattr(creature.genome, trait))
    pop = float(len(creatures))
    return {trait: value / pop for trait, value in totals.items()}


def trait_deltas(current: Mapping[str, float], baseline: Mapping[str, float]) -> dict[str, float]:
    return {trait: float(current.get(trait, 0.0)) - float(baseline.get(trait, 0.0)) for trait in current.keys()}


def evolution_distance_mean_abs(deltas: Mapping[str, float]) -> float:
    if not deltas:
        return 0.0
    return sum(abs(v) for v in deltas.values()) / len(deltas)


def top_trait_directions(deltas: Mapping[str, float], *, noise_threshold: float = 0.015, limit: int = 3) -> tuple[str, ...]:
    filtered = [(k, v) for k, v in deltas.items() if abs(v) >= noise_threshold]
    filtered.sort(key=lambda item: abs(item[1]), reverse=True)
    out: list[str] = []
    for trait, delta in filtered[:limit]:
        label = trait.replace("_radius", "").replace("_preference", "").replace("_", " ")
        out.append(f"{label} {delta:+.02f}")
    return tuple(out)


def lineage_summary_for_population(
    creatures: Sequence[object],
    *,
    current_tick: int,
    lineage_first_seen_ticks: Mapping[int, int],
) -> LineageObservabilitySummary:
    if not creatures:
        return LineageObservabilitySummary(0, 0.0, 0)

    active_lineages = {int(c.lineage_id) for c in creatures}
    ages: list[int] = []
    for lineage_id in active_lineages:
        first_seen = int(lineage_first_seen_ticks.get(lineage_id, current_tick))
        ages.append(max(0, current_tick - first_seen))
    return LineageObservabilitySummary(
        active_lineage_count=len(active_lineages),
        average_lineage_age_ticks=sum(ages) / len(ages) if ages else 0.0,
        oldest_lineage_age_ticks=max(ages) if ages else 0,
    )
