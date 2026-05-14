"""Interpreted creature observation helpers for the inspect overlay.

All functions in this module are pure: they read creature/simulation state
but never mutate it, consume RNG, or alter ecology.  They produce
human-readable interpretations of raw simulation data for display purposes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..simulation.creature import Creature
    from ..simulation.simulation import Simulation


# ── Life stage classification ──────────────────────────────────────────

@dataclass(frozen=True)
class LifeStage:
    label: str
    age_fraction: float


_LIFE_STAGES = (
    (0.15, "Larva"),
    (0.40, "Juvenile"),
    (0.60, "Young adult"),
    (0.80, "Adult"),
    (0.95, "Elder"),
)


def classify_life_stage(creature: Creature) -> LifeStage:
    age_frac = creature.get_age_fraction()
    label = "Decrepit"
    for threshold, name in _LIFE_STAGES:
        if age_frac < threshold:
            label = name
            break
    return LifeStage(label=label, age_fraction=age_frac)


# ── Temperament tags ──────────────────────────────────────────────────

def temperament_tags(creature: Creature) -> list[str]:
    g = creature.genome
    tags: list[str] = []

    if g.aggression >= 0.70:
        tags.append("Aggressive")
    elif g.aggression <= 0.30:
        tags.append("Docile")

    if g.speed >= 0.70:
        tags.append("Swift")
    elif g.speed <= 0.30:
        tags.append("Sluggish")

    if g.sense_radius >= 0.70:
        tags.append("Keen-eyed")
    elif g.sense_radius <= 0.30:
        tags.append("Near-blind")

    if g.efficiency >= 0.70:
        tags.append("Efficient")
    elif g.efficiency <= 0.30:
        tags.append("Wasteful")

    if g.size >= 0.70:
        tags.append("Large")
    elif g.size <= 0.30:
        tags.append("Tiny")

    if g.longevity >= 0.70:
        tags.append("Long-lived")
    elif g.longevity <= 0.30:
        tags.append("Short-lived")

    if g.conformity >= 0.70:
        tags.append("Flockish")
    elif g.conformity <= 0.30:
        tags.append("Loner")

    return tags


def format_tags(tags: list[str], max_tags: int = 3) -> str:
    if not tags:
        return "—"
    return ", ".join(tags[:max_tags])


# ── Motion style label ────────────────────────────────────────────────

def motion_style_label(motion_style: float) -> str:
    if motion_style < 0.34:
        return "Glide"
    if motion_style < 0.67:
        return "Swim"
    return "Dart"


# ── Depth preference label ────────────────────────────────────────────

def depth_preference_label(depth_preference: float) -> str:
    if depth_preference < 0.33:
        return "Surface"
    if depth_preference < 0.67:
        return "Mid"
    return "Deep"


# ── Behavior mode inference ───────────────────────────────────────────

_BEHAVIOR_MODES = (
    "starving",
    "fleeing",
    "hunting",
    "stalking",
    "foraging",
    "sated",
    "wandering",
    "flocking",
)


def infer_behavior_mode(creature: Creature, simulation: Simulation) -> str:
    if creature.energy < 0.10:
        return "starving"
    if creature.energy < 0.20:
        return "foraging"

    if creature.species == "predator":
        if creature.satiety_ticks_remaining > 0:
            return "sated"
        if creature.recent_animal_energy >= 0.04:
            return "stalking" if creature.energy < 0.50 else "hunting"
        return "foraging"

    if creature.species == "prey":
        nearby = _nearest_different_species(creature, simulation)
        if nearby is not None and nearby.genome.aggression >= 0.50:
            return "fleeing"
        return "foraging"

    if creature.flock_id >= 0:
        return "flocking"

    return "wandering"


def _nearest_different_species(
    creature: Creature, simulation: Simulation
) -> Creature | None:
    if not hasattr(simulation, "_build_creature_bucket"):
        return None
    bucket = simulation._build_creature_bucket()
    nearby = simulation._nearby_creatures(
        creature.x, creature.y, creature.get_effective_sense_radius(), bucket
    )
    best: Creature | None = None
    best_dist = float("inf")
    for other in nearby:
        if other is creature or other.species == creature.species:
            continue
        dx = other.x - creature.x
        dy = other.y - creature.y
        d = dx * dx + dy * dy
        if d < best_dist:
            best = other
            best_dist = d
    return best


# ── Attention target inference ────────────────────────────────────────

@dataclass(frozen=True)
class AttentionTarget:
    kind: str
    x: float
    y: float
    confidence: float


def infer_attention_target(
    creature: Creature, simulation: Simulation
) -> AttentionTarget | None:
    sense = creature.get_effective_sense_radius()

    if creature.species == "predator":
        target = _nearest_prey(creature, simulation, sense)
        if target is not None:
            return AttentionTarget(
                kind="prey",
                x=target.x,
                y=target.y,
                confidence=_proximity_confidence(creature, target, sense),
            )

    if creature.species == "prey":
        threat = _nearest_predator(creature, simulation, sense)
        if threat is not None:
            return AttentionTarget(
                kind="threat",
                x=threat.x,
                y=threat.y,
                confidence=_proximity_confidence(creature, threat, sense),
            )

    food_target = _nearest_food(creature, simulation, sense)
    if food_target is not None:
        fx, fy = food_target
        return AttentionTarget(
            kind="food",
            x=fx,
            y=fy,
            confidence=_proximity_confidence_xy(creature, fx, fy, sense),
        )

    return None


def _nearest_prey(
    creature: Creature, simulation: Simulation, sense: float
) -> Creature | None:
    if not hasattr(simulation, "_build_creature_bucket"):
        return None
    bucket = simulation._build_creature_bucket()
    nearby = simulation._nearby_creatures(creature.x, creature.y, sense, bucket)
    best: Creature | None = None
    best_dist = float("inf")
    for other in nearby:
        if other.species != "prey":
            continue
        dx = other.x - creature.x
        dy = other.y - creature.y
        d = dx * dx + dy * dy
        if d < best_dist:
            best = other
            best_dist = d
    return best


def _nearest_predator(
    creature: Creature, simulation: Simulation, sense: float
) -> Creature | None:
    if not hasattr(simulation, "_build_creature_bucket"):
        return None
    bucket = simulation._build_creature_bucket()
    nearby = simulation._nearby_creatures(creature.x, creature.y, sense, bucket)
    best: Creature | None = None
    best_dist = float("inf")
    for other in nearby:
        if other.species != "predator":
            continue
        dx = other.x - creature.x
        dy = other.y - creature.y
        d = dx * dx + dy * dy
        if d < best_dist:
            best = other
            best_dist = d
    return best


def _nearest_food(
    creature: Creature, simulation: Simulation, sense: float
) -> tuple[float, float] | None:
    fm = getattr(simulation, "food_manager", None)
    if fm is None:
        return None
    food = fm.find_nearest(creature.x, creature.y, sense, depth_band=creature.depth_band)
    if food is None:
        food = fm.find_nearest(creature.x, creature.y, sense)
    if food is None:
        return None
    return (food.x, food.y)


def _proximity_confidence(
    subject: Creature, target: Creature, sense: float
) -> float:
    dx = target.x - subject.x
    dy = target.y - subject.y
    dist = math.sqrt(dx * dx + dy * dy)
    return max(0.0, min(1.0, 1.0 - dist / max(1.0, sense)))


def _proximity_confidence_xy(
    subject: Creature, tx: float, ty: float, sense: float
) -> float:
    dx = tx - subject.x
    dy = ty - subject.y
    dist = math.sqrt(dx * dx + dy * dy)
    return max(0.0, min(1.0, 1.0 - dist / max(1.0, sense)))