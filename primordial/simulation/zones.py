"""Zone system - environmental regions that create soft selection pressure.

Zones are fixed soft-edged circles placed at startup.  Each zone type
favours certain genome traits (cheaper energy) and penalises others
(costlier energy).  The aggregate effect nudges evolution toward the
trait profile that best matches each region without hard-locking
creatures to any zone.

Zone rendering data is also exposed here so the renderer can draw
atmospheric backgrounds without reimplementing the zone geometry.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .creature import Creature
    from .genome import Genome


# ---------------------------------------------------------------------------
# Zone type definitions
# ---------------------------------------------------------------------------

# Each entry maps zone_type → {favors, penalizes, color}.
# favors/penalizes: list of (trait_name, high_is_good).
#   high_is_good=True  → high trait value earns the bonus/penalty
#   high_is_good=False → low trait value earns the bonus/penalty
# color: (R, G, B) for atmospheric background (very low alpha)
ZONE_DEFINITIONS: dict[str, dict] = {
    "warm_vent": {
        "favors":    [("efficiency", True), ("size", True)],
        "penalizes": [("speed", True)],
        "color": (180, 90, 10),   # deep amber
        "label": "Warm Vent",
    },
    "open_water": {
        "favors":    [("speed", True), ("size", False)],  # low size favoured
        "penalizes": [("aggression", True)],
        "color": (60, 120, 200),  # pale blue
        "label": "Open Water",
    },
    "kelp_forest": {
        "favors":    [("sense_radius", True), ("aggression", False)],
        "penalizes": [("speed", True)],
        "color": (0, 80, 40),     # deep green
        "label": "Kelp Forest",
    },
    "hunting_ground": {
        "favors":    [("aggression", True), ("speed", True)],
        "penalizes": [("longevity", True)],
        "color": (100, 0, 10),    # deep red
        "label": "Hunting Ground",
    },
    "deep_trench": {
        "favors":    [("longevity", True), ("size", False)],
        "penalizes": [("efficiency", True)],
        "color": (15, 5, 80),     # deep indigo
        "label": "Deep Trench",
    },
}

_ZONE_TYPE_ORDER = list(ZONE_DEFINITIONS.keys())

# How clearly local creatures can sense targets in each zone.
_ZONE_SENSING_MODIFIERS: dict[str, float] = {
    "warm_vent": 0.95,
    "open_water": 1.15,
    "kelp_forest": 0.72,
    "hunting_ground": 1.10,
    "deep_trench": 0.68,
}


# ---------------------------------------------------------------------------
# Zone dataclass (pure data, no pygame)
# ---------------------------------------------------------------------------


@dataclass
class Zone:
    """A single environmental zone."""

    x: float
    y: float
    radius: float
    zone_type: str
    local_strength: float  # 0.5–1.0 per-zone random factor


# ---------------------------------------------------------------------------
# ZoneManager
# ---------------------------------------------------------------------------


class ZoneManager:
    """
    Generates and manages fixed environmental zones.

    All geometry is computed at construction time from world dimensions.
    Energy modifier queries are O(zone_count) — trivial even at 250 creatures.
    """

    def __init__(
        self,
        width: int,
        height: int,
        count: int,
        global_strength: float,
    ) -> None:
        self.global_strength = global_strength
        self.zones: list[Zone] = []
        self._generate(width, height, count)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _generate(self, width: int, height: int, count: int) -> None:
        """Place zones randomly, cycling through all zone types."""
        min_dim = min(width, height)
        for i in range(count):
            zone_type = _ZONE_TYPE_ORDER[i % len(_ZONE_TYPE_ORDER)]
            # Keep zones mostly on-screen with organic variation
            self.zones.append(Zone(
                x=random.uniform(0.1 * width, 0.9 * width),
                y=random.uniform(0.1 * height, 0.9 * height),
                radius=random.uniform(0.18 * min_dim, 0.30 * min_dim),
                zone_type=zone_type,
                local_strength=random.uniform(0.75, 1.0),
            ))

    # ------------------------------------------------------------------
    # Energy modifier query
    # ------------------------------------------------------------------

    def get_energy_modifier(self, creature: Creature) -> float:
        """
        Compute the aggregate zone energy cost multiplier for a creature.

        Values < 1.0 reduce energy costs (favoured traits in zone).
        Values > 1.0 increase energy costs (penalised traits in zone).
        Clamped to [0.75, 1.25].

        Args:
            creature: The creature being evaluated.

        Returns:
            Float multiplier for energy cost this frame.
        """
        if self.global_strength <= 0:
            return 1.0

        total_effect = 0.0
        genome = creature.genome

        for zone in self.zones:
            dx = creature.x - zone.x
            dy = creature.y - zone.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist >= zone.radius:
                continue

            # Distance weight: 1.0 at center, 0.0 at edge
            weight = 1.0 - dist / zone.radius
            strength = weight * zone.local_strength * self.global_strength

            effect = self._trait_effect(zone.zone_type, genome)
            total_effect += effect * strength

        return max(0.75, min(1.25, 1.0 + total_effect))

    def _trait_effect(self, zone_type: str, genome: Genome) -> float:
        """
        Net trait match effect for a zone type (range ≈ -0.2 to +0.2).

        Favoured traits contribute negative values (cheaper).
        Penalised traits contribute positive values (costlier).
        """
        defn = ZONE_DEFINITIONS[zone_type]
        effect = 0.0

        favored = defn["favors"]
        penalized = defn["penalizes"]
        per_favor = 0.2 / max(1, len(favored))
        per_penalty = 0.2 / max(1, len(penalized))

        for trait_name, high_is_good in favored:
            val = getattr(genome, trait_name)
            score = val if high_is_good else (1.0 - val)
            effect -= per_favor * score

        for trait_name, high_is_bad in penalized:
            val = getattr(genome, trait_name)
            score = val if high_is_bad else (1.0 - val)
            effect += per_penalty * score

        return effect

    # ------------------------------------------------------------------
    # HUD helpers
    # ------------------------------------------------------------------

    def get_zone_occupancy_counts(self, creatures: list[Creature]) -> dict[str, int]:
        """Count creatures by their strongest containing zone, plus unzoned."""
        counts: dict[str, int] = {k: 0 for k in ZONE_DEFINITIONS}
        counts["unzoned"] = 0
        for creature in creatures:
            best_zone = self._strongest_zone_at(creature.x, creature.y)
            if best_zone is None:
                counts["unzoned"] += 1
            else:
                counts[best_zone.zone_type] += 1
        return counts

    def get_dominant_zone(self, creatures: list[Creature]) -> str:
        """
        Return the label of the zone type containing the most creatures.

        A creature belongs to the zone whose centre it is closest to
        (provided it is within that zone's radius at all).

        Returns:
            Zone label string, or "—" if no creatures are in any zone.
        """
        counts = self.get_zone_occupancy_counts(creatures)

        best = max(ZONE_DEFINITIONS, key=lambda k: counts.get(k, 0))
        if counts[best] == 0:
            return "\u2014"
        return ZONE_DEFINITIONS[best]["label"]

    def get_sensing_modifier_at(self, x: float, y: float) -> float:
        """Return the sensing clarity modifier at a position."""
        zone = self._strongest_zone_at(x, y)
        if zone is None:
            return 1.0
        return _ZONE_SENSING_MODIFIERS.get(zone.zone_type, 1.0)

    def _strongest_zone_at(self, x: float, y: float) -> Zone | None:
        """Return the strongest containing zone at a position, if any."""
        best_zone: Zone | None = None
        best_weight = 0.0
        for zone in self.zones:
            dx = x - zone.x
            dy = y - zone.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist >= zone.radius:
                continue
            weight = 1.0 - dist / zone.radius
            if weight > best_weight:
                best_weight = weight
                best_zone = zone
        return best_zone
