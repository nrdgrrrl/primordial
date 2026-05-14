"""Inspect Mode — read-only creature observability overlay.

This module provides a non-persistent runtime state object (InspectMode) and
a pure-function creature card builder.  It does **not** mutate simulation
state, consume simulation RNG, or alter ecology dials.  It is purely for
display purposes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .creature_observation import (
    LifeStage,
    classify_life_stage,
    temperament_tags,
    format_tags,
    motion_style_label,
    depth_preference_label,
    infer_behavior_mode,
    infer_attention_target,
)

if TYPE_CHECKING:
    from ..simulation.creature import Creature
    from ..simulation.simulation import Simulation


@dataclass
class InspectMode:
    """Non-persistent runtime state for the creature inspect overlay.

    This object is owned by the main loop — it is never serialised into
    world snapshots or persisted across sessions.
    """

    enabled: bool = False
    pause_mode: str = "pause"          # "pause" or "slow"
    slow_hz: float = 2.0               # sim ticks per second in slow mode
    selected_creature_id: int | None = None   # creature id()` id
    was_paused_before: bool | None = None     # paused state before entering inspect

    _slow_accumulator: float = field(default=0.0, repr=False)

    # ── toggle ───────────────────────────────────────────────────────

    def toggle(self, simulation_paused: bool) -> None:
        """Toggle inspect mode on or off.

        Entering: default to pause mode; remember prior paused state so we
        can restore it on exit.

        Exiting: clear selection; the caller restores the prior paused state
        separately (so it can also reset timing debt).
        """
        if not self.enabled:
            self.enabled = True
            self.was_paused_before = simulation_paused
            self.pause_mode = "pause"
            self._slow_accumulator = 0.0
        else:
            self.enabled = False
            self.selected_creature_id = None
            self.was_paused_before = None
            self._slow_accumulator = 0.0

    def toggle_pause_slow(self) -> None:
        """Switch between pause and slow sub-modes while inspect is active."""
        if not self.enabled:
            return
        self.pause_mode = "slow" if self.pause_mode == "pause" else "pause"
        self._slow_accumulator = 0.0

    # ── query helpers ────────────────────────────────────────────────

    @property
    def should_suppress_sim(self) -> bool:
        """True when simulation stepping should be suppressed this frame."""
        return self.enabled and self.pause_mode == "pause"

    def should_step_slow(self, dt_seconds: float) -> bool:
        """Return True if a slow-mode tick should fire for the given wall dt.

        Callers should pass the real elapsed time.  The method accumulates
        fractional time and returns True when enough has accumulated for one
        tick at *slow_hz*.
        """
        if not self.enabled or self.pause_mode != "slow":
            return False
        self._slow_accumulator += dt_seconds
        tick_interval = 1.0 / max(1.0, self.slow_hz)
        if self._slow_accumulator >= tick_interval:
            self._slow_accumulator -= tick_interval
            return True
        return False

    # ── selection ────────────────────────────────────────────────────

    def select_at_world_pos(
        self,
        world_x: float,
        world_y: float,
        simulation: Simulation,
        *,
        pick_radius: float = 24.0,
    ) -> None:
        """Select the nearest living creature under *world_x, world_y*.

        If no creature is within *pick_radius*, the selection is cleared.
        Selection never mutates simulation state.
        """
        best: Creature | None = None
        best_dist = pick_radius
        for creature in simulation.creatures:
            dx = creature.x - world_x
            dy = creature.y - world_y
            dist = math.sqrt(dx * dx + dy * dy)
            creature_radius = creature.get_radius()
            threshold = max(creature_radius + 8.0, 16.0, pick_radius)
            if dist < threshold and dist < best_dist:
                best = creature
                best_dist = dist
        self.selected_creature_id = id(best) if best is not None else None

    def get_selected_creature(self, simulation: Simulation) -> Creature | None:
        """Return the currently selected creature, or None."""
        if self.selected_creature_id is None:
            return None
        for creature in simulation.creatures:
            if id(creature) == self.selected_creature_id:
                return creature
        self.selected_creature_id = None
        return None

    def clear_selection(self) -> None:
        """Clear the selected creature without exiting inspect mode."""
        self.selected_creature_id = None


# ──────────────────────────────────────────────────────────────────────
# Creature card builder
# ──────────────────────────────────────────────────────────────────────

_TRAIT_LABELS: dict[str, str] = {
    "speed": "Speed",
    "size": "Size",
    "sense_radius": "Sense",
    "aggression": "Aggr",
    "efficiency": "Eff",
    "longevity": "Lifespan",
    "conformity": "Conform",
    "depth_preference": "Depth",
}


def build_creature_card(
    creature: Creature,
    simulation: Simulation,
) -> dict[str, str]:
    """Build a human-readable creature card dict.

    Keys are display labels; values are formatted strings.  This function
    is pure (it reads creature/simulation state but does not mutate it).

    The card is organised into logical sections using prefix conventions
    that renderers can use for grouping:

    - ``section_*`` — section header labels (no colon or value)
    - ``*`` — ordinary key-value rows

    Sections: Identity, Vitals, Genome, Behavior
    """
    age_frac = creature.get_age_fraction()
    max_life = creature.get_max_lifespan()
    age_pct = age_frac * 100.0
    vel = math.sqrt(creature.vx ** 2 + creature.vy ** 2)

    life_stage = classify_life_stage(creature)
    tags = temperament_tags(creature)
    behavior = infer_behavior_mode(creature, simulation)
    motion = motion_style_label(creature.genome.motion_style)
    depth_pref = depth_preference_label(creature.genome.depth_preference)

    card: dict[str, str] = {}

    # ── Identity section ──
    card["section_identity"] = ""
    card["species"] = creature.species.capitalize()
    card["lineage"] = f"#{creature.lineage_id}"
    card["stage"] = life_stage.label
    card["tags"] = format_tags(tags)

    # ── Vitals section ──
    card["section_vitals"] = ""
    card["age"] = f"{creature.age} / {int(max_life)}  ({age_pct:.0f}%)"
    card["energy"] = f"{creature.energy:.2f}"
    card["depth"] = creature.get_depth_band_name()

    if creature.species == "predator":
        card["recent_animal_e"] = f"{creature.recent_animal_energy:.3f}"
        card["satiety"] = f"{creature.satiety_ticks_remaining}t"

    card["pos"] = f"({creature.x:.0f}, {creature.y:.0f})"

    # ── Genome section ──
    card["section_genome"] = ""
    card["speed"] = f"{creature.genome.speed:.2f}"
    card["size"] = f"{creature.genome.size:.2f}"
    card["sense"] = f"{creature.genome.sense_radius:.2f}"
    card["aggr"] = f"{creature.genome.aggression:.2f}"
    card["eff"] = f"{creature.genome.efficiency:.2f}"
    card["motion"] = motion
    card["depth_pref"] = depth_pref

    # ── Behavior section ──
    card["section_behavior"] = ""
    card["behavior"] = behavior
    card["vel"] = f"{vel:.2f}"

    attention = infer_attention_target(creature, simulation)
    if attention is not None:
        card["attention"] = attention.kind
        card["attention_conf"] = f"{attention.confidence:.0%}"

    return card


# ──────────────────────────────────────────────────────────────────────
# Coordinate conversion
# ──────────────────────────────────────────────────────────────────────

def display_to_world(
    display_x: int,
    display_y: int,
    display_width: int,
    display_height: int,
    world_width: int,
    world_height: int,
) -> tuple[float, float]:
    """Convert display (screen) pixel coordinates to world (simulation) coords.

    Handles the case where the display is scaled relative to the world.
    """
    wx = display_x * (world_width / max(1, display_width))
    wy = display_y * (world_height / max(1, display_height))
    return wx, wy