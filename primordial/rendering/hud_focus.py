"""HUD focus selection — lightweight organism focus without Inspect Mode.

This module provides a minimal focus overlay for the basic HUD mode.
It does NOT show the Inspect side panel or bottom graphs, does NOT
pause or slow the simulation, and does NOT conflict with full Inspect
Mode selection.

When active, it:
- Draws a subtle selection ring around the focused organism
- Draws the organism's attention line (food/prey/threat)
- Clears automatically when the focused organism dies
- Hides rendering when the HUD is hidden
- Defers to Inspect Mode when Inspect is active
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .creature_observation import infer_attention_target

if TYPE_CHECKING:
    from ..simulation.creature import Creature
    from ..simulation.simulation import Simulation


_HUD_FOCUS_PICK_RADIUS = 48.0
_HUD_FOCUS_ATTENTION_CACHE_INTERVAL_TICKS = 8
_HUD_NO_TARGET = object()


@dataclass
class HUDFocus:
    """Lightweight focus state for HUD-mode organism selection.

    This is separate from InspectMode selection.  When Inspect mode
    is active, HUDFocus rendering is suppressed and InspectMode owns
    all selection behaviour.
    """

    selected_creature_id: int | None = None
    _attention_cache_tick: int = field(default=-1, repr=False)
    _attention_cache_target: object | None = field(default=None, repr=False)
    _creature_lookup_frame: int = field(default=-1, repr=False)
    _creature_lookup_size: int = field(default=-1, repr=False)
    _creature_lookup_by_id: dict[int, Creature] = field(default_factory=dict, repr=False)

    @property
    def has_selection(self) -> bool:
        return self.selected_creature_id is not None

    def select_at_world_pos(
        self,
        world_x: float,
        world_y: float,
        simulation: Simulation,
        *,
        pick_radius: float = _HUD_FOCUS_PICK_RADIUS,
    ) -> None:
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
        if best is None:
            self.clear_selection()
            return
        self.selected_creature_id = id(best)
        self._invalidate_attention_cache()

    def clear_selection(self) -> None:
        self.selected_creature_id = None
        self._invalidate_attention_cache()

    def get_selected_creature(self, simulation: Simulation) -> Creature | None:
        if self.selected_creature_id is None:
            return None
        current_tick = int(getattr(simulation, "_frame", 0))
        creature_count = len(simulation.creatures)
        if (
            self._creature_lookup_frame != current_tick
            or self._creature_lookup_size != creature_count
        ):
            self._creature_lookup_frame = current_tick
            self._creature_lookup_size = creature_count
            self._creature_lookup_by_id = {
                id(c): c for c in simulation.creatures
            }
        return self._creature_lookup_by_id.get(self.selected_creature_id)

    def observe_simulation(self, simulation: Simulation) -> None:
        """Check for death of the focused organism and clear if dead."""
        if not self.has_selection:
            return
        creature = self.get_selected_creature(simulation)
        if creature is None:
            self.clear_selection()

    def get_attention_target(
        self,
        simulation: Simulation,
        creature: Creature | None,
    ):
        if creature is None:
            self._invalidate_attention_cache()
            return None
        current_tick = int(getattr(simulation, "_frame", 0))
        creature_id = id(creature)
        if (
            self._attention_cache_tick >= 0
            and self._attention_cache_creature_id == creature_id
            and (current_tick - self._attention_cache_tick) < _HUD_FOCUS_ATTENTION_CACHE_INTERVAL_TICKS
        ):
            if self._attention_cache_target is _HUD_NO_TARGET:
                return None
            return self._attention_cache_target
        try:
            attention = infer_attention_target(creature, simulation)
        except Exception:
            attention = None
        self._attention_cache_tick = current_tick
        self._attention_cache_creature_id = creature_id
        if attention is None:
            self._attention_cache_target = _HUD_NO_TARGET
        else:
            self._attention_cache_target = attention
        return attention

    def _invalidate_attention_cache(self) -> None:
        self._attention_cache_tick = -1
        self._attention_cache_target = None