"""Deterministic eco-morphological phenotype translation for raw genomes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from .depth import DEPTH_MID, depth_band_from_preference
from .genome import Genome


_STRATEGY_BUCKETS = (
    "swift-small",
    "heavy-hunter",
    "sensory-specialist",
    "efficient-glider",
    "evasive-darter",
    "depth-specialist",
    "generalist",
)


@dataclass(frozen=True)
class EffectivePhenotype:
    """Effective ecological modifiers derived from interacting genome traits."""

    speed_mult: float = 1.0
    movement_cost_mult: float = 1.0
    metabolic_cost_mult: float = 1.0
    sense_radius_mult: float = 1.0
    food_efficiency_mult: float = 1.0
    reproduction_threshold_mult: float = 1.0
    predation_contact_mult: float = 1.0
    flee_agility_mult: float = 1.0
    depth_transition_mult: float = 1.0
    in_band_sense_mult: float = 1.0
    cross_band_sense_mult: float = 1.0
    strategy_bucket: str = "generalist"
    preferred_depth_band: int = DEPTH_MID

    def depth_sense_multiplier(self, separation: int) -> float:
        """Interpolate sensing quality across bounded depth-band separation."""
        separation = max(0, min(2, int(separation)))
        if separation <= 0:
            return self.in_band_sense_mult
        if separation >= 2:
            return self.cross_band_sense_mult
        return (self.in_band_sense_mult + self.cross_band_sense_mult) * 0.5


def strategy_bucket_names() -> tuple[str, ...]:
    """Return the stable observability bucket names."""
    return _STRATEGY_BUCKETS


def strategy_bucket_template() -> dict[str, int]:
    """Return a zeroed strategy-count mapping."""
    return {name: 0 for name in _STRATEGY_BUCKETS}


def resolve_effective_phenotype(
    genome: Genome,
    *,
    species: str = "none",
    epistasis_enabled: bool = True,
    epistasis_strength: float = 1.0,
) -> EffectivePhenotype:
    """Return a cached effective phenotype for one raw genome and role."""
    return _resolve_effective_phenotype_cached(
        genome,
        species,
        bool(epistasis_enabled),
        round(float(epistasis_strength), 4),
    )


@lru_cache(maxsize=8192)
def _resolve_effective_phenotype_cached(
    genome: Genome,
    species: str,
    epistasis_enabled: bool,
    epistasis_strength: float,
) -> EffectivePhenotype:
    preferred_depth_band = depth_band_from_preference(genome.depth_preference)
    if not epistasis_enabled:
        return EffectivePhenotype(preferred_depth_band=preferred_depth_band)

    strength = max(0.0, min(1.5, epistasis_strength))
    if strength <= 0.0:
        return EffectivePhenotype(preferred_depth_band=preferred_depth_band)

    speed = _clamp_unit(genome.speed)
    size = _clamp_unit(genome.size)
    sense = _clamp_unit(genome.sense_radius)
    efficiency = _clamp_unit(genome.efficiency)
    complexity = _clamp_unit(genome.complexity)
    symmetry = _clamp_unit(genome.symmetry)
    appendages = _clamp_unit(genome.appendages)
    motion_style = _clamp_unit(genome.motion_style)
    longevity = _clamp_unit(genome.longevity)
    depth_preference = _clamp_unit(genome.depth_preference)
    aggression = _clamp_unit(genome.aggression)

    speed_high = _high(speed)
    large_body = _high(size)
    small_body = _high(1.0 - size)
    high_sense = _high(sense)
    high_complexity = _high(complexity)
    high_efficiency = _high(efficiency)
    low_symmetry = _high(1.0 - symmetry)
    specialization = abs(depth_preference - 0.5) * 2.0

    glide_affinity = max(0.0, 1.0 - (motion_style / 0.40))
    swim_affinity = max(0.0, 1.0 - (abs(motion_style - 0.50) / 0.22))
    dart_affinity = max(0.0, (motion_style - 0.55) / 0.45)
    flow_affinity = max(glide_affinity, swim_affinity * 0.85)

    role = species
    if role not in {"predator", "prey"}:
        role = "predator" if aggression >= 0.5 else "prey"
    predator_role = 1.0 if role == "predator" else 0.0
    prey_role = 1.0 if role == "prey" else 0.0

    speed_mult = (
        1.0
        + (0.05 * symmetry * flow_affinity)
        + (0.03 * speed_high * small_body)
        - (0.06 * appendages * (0.35 + (size * 0.65)))
    )
    movement_cost_mult = (
        1.0
        + (0.30 * speed_high * large_body)
        + (0.11 * appendages * (0.45 + (size * 0.55)))
        - (0.10 * symmetry * flow_affinity)
    )
    metabolic_cost_mult = (
        1.0
        + (0.16 * high_sense * high_complexity)
        + (0.12 * speed_high * large_body)
        - (0.12 * high_efficiency * (1.0 - (0.35 * speed_high)))
    )
    sense_radius_mult = 1.0 + (0.12 * high_sense * high_complexity)
    food_efficiency_mult = (
        1.0
        + (0.08 * high_efficiency * (0.55 + (0.45 * flow_affinity)))
        - (0.05 * speed_high * (0.55 + (0.45 * large_body)))
    )
    reproduction_threshold_mult = 1.0 + (0.12 * longevity) + (0.05 * large_body * speed_high)
    predation_contact_mult = (
        1.0
        + (0.12 * speed_high * large_body)
        - (0.09 * speed_high * small_body)
        + (0.09 * appendages * predator_role)
    )
    flee_agility_mult = (
        1.0
        + (0.10 * speed_high * small_body)
        + (0.10 * low_symmetry * dart_affinity)
        + (0.09 * appendages * prey_role)
    )
    depth_transition_mult = 1.08 - (0.16 * specialization)
    in_band_sense_mult = 1.0 + (0.14 * specialization)
    cross_band_sense_mult = 1.03 - (0.20 * specialization)

    phenotype = EffectivePhenotype(
        speed_mult=_blend_and_clamp(speed_mult, strength, 0.82, 1.12),
        movement_cost_mult=_blend_and_clamp(movement_cost_mult, strength, 0.75, 1.35),
        metabolic_cost_mult=_blend_and_clamp(metabolic_cost_mult, strength, 0.82, 1.28),
        sense_radius_mult=_blend_and_clamp(sense_radius_mult, strength, 0.88, 1.22),
        food_efficiency_mult=_blend_and_clamp(food_efficiency_mult, strength, 0.88, 1.12),
        reproduction_threshold_mult=_blend_and_clamp(
            reproduction_threshold_mult,
            strength,
            0.92,
            1.25,
        ),
        predation_contact_mult=_blend_and_clamp(predation_contact_mult, strength, 0.82, 1.25),
        flee_agility_mult=_blend_and_clamp(flee_agility_mult, strength, 0.85, 1.22),
        depth_transition_mult=_blend_and_clamp(depth_transition_mult, strength, 0.88, 1.12),
        in_band_sense_mult=_blend_and_clamp(in_band_sense_mult, strength, 0.90, 1.18),
        cross_band_sense_mult=_blend_and_clamp(cross_band_sense_mult, strength, 0.78, 1.05),
        preferred_depth_band=preferred_depth_band,
    )
    return EffectivePhenotype(
        **{
            **phenotype.__dict__,
            "strategy_bucket": _classify_strategy_bucket(
                genome,
                phenotype,
                role=role,
                flow_affinity=flow_affinity,
                dart_affinity=dart_affinity,
                specialization=specialization,
            ),
        }
    )


def _classify_strategy_bucket(
    genome: Genome,
    phenotype: EffectivePhenotype,
    *,
    role: str,
    flow_affinity: float,
    dart_affinity: float,
    specialization: float,
) -> str:
    if (
        role == "predator"
        and genome.size >= 0.62
        and genome.aggression >= 0.65
        and phenotype.predation_contact_mult >= 1.05
    ):
        return "heavy-hunter"
    if genome.speed >= 0.72 and genome.size <= 0.38:
        return "swift-small"
    if (
        genome.sense_radius >= 0.72
        and genome.complexity >= 0.55
        and phenotype.sense_radius_mult >= 1.04
    ):
        return "sensory-specialist"
    if (
        flow_affinity >= 0.55
        and genome.symmetry >= 0.60
        and genome.efficiency >= 0.65
        and phenotype.movement_cost_mult <= 1.0
    ):
        return "efficient-glider"
    if (
        dart_affinity >= 0.50
        and genome.size <= 0.55
        and phenotype.flee_agility_mult >= 1.05
    ):
        return "evasive-darter"
    if specialization >= 0.45 and phenotype.in_band_sense_mult > phenotype.cross_band_sense_mult:
        return "depth-specialist"
    return "generalist"


def describe_phenotype_effect(
    phenotype: EffectivePhenotype,
    genome: Genome,
    *,
    species: str = "none",
) -> str:
    """Return a short human-readable phrase summarising the key phenotype effect.

    The phrase explains *why* the modifier pattern matters for this creature,
    for example "Large fast body: stronger contact, higher movement cost".
    When epistasis is disabled every modifier equals 1.0, so the phrase
    will indicate neutrality.
    """
    g = genome
    bucket = phenotype.strategy_bucket

    # Collect notable deviations from neutral (1.0)
    notable: list[tuple[str, float, str]] = []
    _MOD_FIELDS: list[tuple[str, str, str]] = [
        ("speed_mult", "speed", "faster"),
        ("movement_cost_mult", "move cost", "costlier"),
        ("metabolic_cost_mult", "metabolism", "costlier"),
        ("sense_radius_mult", "sense", "sharper"),
        ("food_efficiency_mult", "food", "richer"),
        ("reproduction_threshold_mult", "repro threshold", "higher"),
        ("predation_contact_mult", "contact", "stronger"),
        ("flee_agility_mult", "flee", "better"),
        ("depth_transition_mult", "depth move", "slower"),
        ("in_band_sense_mult", "in-band sense", "sharper"),
        ("cross_band_sense_mult", "cross-band sense", "fainter"),
    ]
    for attr, label, direction_pos in _MOD_FIELDS:
        value = getattr(phenotype, attr)
        if value > 1.02:
            notable.append((label, value, direction_pos))
        elif value < 0.98:
            direction_neg = {
                "faster": "slower",
                "costlier": "cheaper",
                "sharper": "duller",
                "richer": "poorer",
                "higher": "lower",
                "stronger": "weaker",
                "better": "worse",
                "slower": "faster",
                "fainter": "stronger",
            }.get(direction_pos, "lower")
            notable.append((label, value, direction_neg))

    # Bucket-specific phrases
    if bucket == "heavy-hunter":
        body = "Large fast body"
    elif bucket == "swift-small":
        body = "Small fast body"
    elif bucket == "sensory-specialist":
        body = "High-sense complex body"
    elif bucket == "efficient-glider":
        body = "Symmetric efficient body"
    elif bucket == "evasive-darter":
        body = "Small darting body"
    elif bucket == "depth-specialist":
        body = "Depth-specialised body"
    else:
        body = "Generalist body"

    if not notable:
        return f"{body}: baseline modifiers"

    # Pick the top 2 most impactful deviations
    notable.sort(key=lambda t: abs(t[1] - 1.0), reverse=True)
    top = notable[:2]
    parts = [f"{label} {direction}" for label, _, direction in top]
    return f"{body}: {', '.join(parts)}"


def format_phenotype_modifiers(phenotype: EffectivePhenotype) -> dict[str, str]:
    """Return a dict of formatted modifier strings, e.g. {"speed_mult": "×1.05"}.

    Intended for the inspect overlay detail view.  When all values are exactly
    1.0 (epistasis disabled) this still returns the dict — the caller decides
    how to represent "neutral".
    """
    fields = [
        ("speed_mult", "Speed"),
        ("movement_cost_mult", "Move cost"),
        ("metabolic_cost_mult", "Metabolism"),
        ("sense_radius_mult", "Sense"),
        ("food_efficiency_mult", "Food"),
        ("reproduction_threshold_mult", "Repro thresh"),
        ("predation_contact_mult", "Contact"),
        ("flee_agility_mult", "Flee"),
        ("depth_transition_mult", "Depth move"),
        ("in_band_sense_mult", "In-band sense"),
        ("cross_band_sense_mult", "Cross-band sense"),
    ]
    result: dict[str, str] = {}
    for attr, _label in fields:
        value = getattr(phenotype, attr)
        result[attr] = f"×{value:.2f}"
    return result


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _high(value: float) -> float:
    return max(0.0, (value - 0.5) / 0.5)


def _blend_and_clamp(
    raw_modifier: float,
    strength: float,
    minimum: float,
    maximum: float,
) -> float:
    blended = 1.0 + ((raw_modifier - 1.0) * strength)
    if not math.isfinite(blended):
        return 1.0
    return max(minimum, min(maximum, blended))
