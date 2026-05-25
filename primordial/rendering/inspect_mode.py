"""Inspect Mode — read-only creature observability overlay.

This module provides a non-persistent runtime state object (InspectMode) and
a pure-function creature card builder.  It does **not** mutate simulation
state, consume simulation RNG, or alter ecology dials.  It is purely for
display purposes.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

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
from ..simulation.phenotype import (
    describe_phenotype_effect,
    format_phenotype_modifiers,
)

if TYPE_CHECKING:
    from ..simulation.creature import Creature
    from ..simulation.simulation import Simulation


_PLAYBACK_PAUSE = "pause"
_PLAYBACK_SLOW = "slow"
_PLAYBACK_NORMAL = "normal"
_INSPECT_HISTORY_SAMPLE_INTERVAL_TICKS = 8
_INSPECT_HISTORY_MAX_SAMPLES = 180


@dataclass
class InspectMode:
    """Non-persistent runtime state for the creature inspect overlay.

    This object is owned by the main loop — it is never serialised into
    world snapshots or persisted across sessions.
    """

    enabled: bool = False
    pause_mode: str = _PLAYBACK_PAUSE  # "pause", "slow", or "normal"
    slow_hz: float = 2.0               # sim ticks per second in slow mode
    detail_mode: str = "compact"       # "compact" or "detail"
    selected_creature_id: int | None = None
    selected_lineage_id: int | None = None
    selected_species: str | None = None
    selected_last_known_x: float | None = None
    selected_last_known_y: float | None = None
    selected_last_known_energy: float | None = None
    selected_last_known_age_ticks: int | None = None
    selected_dead: bool = False
    selected_death_cause: str | None = None
    selected_death_tick: int | None = None
    follow_creature_id: int | None = None
    selected_graph_trait_key: str | None = None
    selected_graph_trait_initial_value: float | None = None
    was_paused_before: bool | None = None     # paused state before entering inspect

    _slow_accumulator: float = field(default=0.0, repr=False)
    _last_history_sample_tick: int | None = field(default=None, repr=False)
    _energy_history: deque[tuple[int, float]] = field(
        default_factory=lambda: deque(maxlen=_INSPECT_HISTORY_MAX_SAMPLES),
        repr=False,
    )
    _lineage_population_history: deque[tuple[int, int]] = field(
        default_factory=lambda: deque(maxlen=_INSPECT_HISTORY_MAX_SAMPLES),
        repr=False,
    )
    _lineage_trait_history: deque[tuple[int, float | None]] = field(
        default_factory=lambda: deque(maxlen=_INSPECT_HISTORY_MAX_SAMPLES),
        repr=False,
    )
    _graph_surface_cache: object | None = field(default=None, repr=False)
    _graph_cache_key: tuple[object, ...] | None = field(default=None, repr=False)

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
            self.pause_mode = _PLAYBACK_PAUSE
            self._slow_accumulator = 0.0
        else:
            self.enabled = False
            self.was_paused_before = None
            self._slow_accumulator = 0.0
            self.clear_selection()

    def toggle_pause_slow(self) -> None:
        """Switch between pause and slow sub-modes while inspect is active."""
        if not self.enabled:
            return
        if self.pause_mode == _PLAYBACK_PAUSE:
            self.pause_mode = _PLAYBACK_SLOW
        elif self.pause_mode == _PLAYBACK_SLOW:
            self.pause_mode = _PLAYBACK_PAUSE
        else:
            self.pause_mode = _PLAYBACK_SLOW
        self._slow_accumulator = 0.0

    def set_normal_follow(self) -> None:
        """Run the inspected simulation at full speed without leaving inspect."""
        if not self.enabled:
            return
        self.pause_mode = _PLAYBACK_NORMAL
        self._slow_accumulator = 0.0

    def toggle_detail_level(self) -> None:
        """Switch between compact and detailed inspect-card presentation."""
        if not self.enabled:
            return
        self.detail_mode = "detail" if self.detail_mode == "compact" else "compact"

    # ── query helpers ────────────────────────────────────────────────

    @property
    def should_suppress_sim(self) -> bool:
        """True when simulation stepping should be suppressed this frame."""
        return self.enabled and self.pause_mode == _PLAYBACK_PAUSE

    def should_step_slow(self, dt_seconds: float) -> bool:
        """Return True if a slow-mode tick should fire for the given wall dt.

        Callers should pass the real elapsed time.  The method accumulates
        fractional time and returns True when enough has accumulated for one
        tick at *slow_hz*.
        """
        if not self.enabled or self.pause_mode != _PLAYBACK_SLOW:
            return False
        self._slow_accumulator += dt_seconds
        tick_interval = 1.0 / max(1.0, self.slow_hz)
        if self._slow_accumulator >= tick_interval:
            self._slow_accumulator -= tick_interval
            return True
        return False

    # ── selection ────────────────────────────────────────────────────

    @property
    def has_selection(self) -> bool:
        """Return whether inspect mode is anchored to an organism or lineage."""
        return self.selected_creature_id is not None or self.selected_lineage_id is not None

    def _invalidate_graph_cache(self) -> None:
        self._graph_surface_cache = None
        self._graph_cache_key = None

    def _reset_histories(self) -> None:
        self._last_history_sample_tick = None
        self._energy_history.clear()
        self._lineage_population_history.clear()
        self._lineage_trait_history.clear()
        self._invalidate_graph_cache()

    def _simulation_mode(self, simulation: Simulation) -> str:
        settings = getattr(simulation, "settings", None)
        return str(getattr(settings, "sim_mode", "energy"))

    def _graph_trait_key_for_mode(self, simulation: Simulation) -> str:
        sim_mode = self._simulation_mode(simulation)
        if sim_mode == "predator_prey":
            return "depth_preference"
        if sim_mode == "boids":
            return "conformity"
        return "efficiency"

    def _find_creature_by_id(
        self,
        simulation: Simulation,
        creature_id: int | None,
    ) -> Creature | None:
        if creature_id is None:
            return None
        for creature in simulation.creatures:
            if id(creature) == creature_id:
                return creature
        return None

    def _store_live_snapshot(self, creature: Creature) -> None:
        self.selected_species = str(creature.species)
        self.selected_lineage_id = int(creature.lineage_id)
        self.selected_last_known_x = float(creature.x)
        self.selected_last_known_y = float(creature.y)
        self.selected_last_known_energy = float(creature.energy)
        self.selected_last_known_age_ticks = int(creature.age)

    def _bind_selection(self, creature: Creature, simulation: Simulation) -> None:
        self.selected_creature_id = id(creature)
        self.follow_creature_id = id(creature)
        self.selected_dead = False
        self.selected_death_cause = None
        self.selected_death_tick = None
        self._store_live_snapshot(creature)
        self.selected_graph_trait_key = self._graph_trait_key_for_mode(simulation)
        self.selected_graph_trait_initial_value = float(
            getattr(creature.genome, self.selected_graph_trait_key, 0.0)
        )
        self._reset_histories()

    def _mark_selected_dead(
        self,
        *,
        tick: int,
        cause: str | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> None:
        if self.selected_creature_id is None or self.selected_dead:
            return
        self.selected_dead = True
        self.selected_death_cause = cause
        self.selected_death_tick = tick
        if x is not None:
            self.selected_last_known_x = float(x)
        if y is not None:
            self.selected_last_known_y = float(y)
        self.follow_creature_id = None
        self._invalidate_graph_cache()

    def _find_lineage_proxy(self, simulation: Simulation) -> Creature | None:
        if self.selected_lineage_id is None:
            return None
        lineage_members = [
            creature
            for creature in simulation.creatures
            if int(creature.lineage_id) == int(self.selected_lineage_id)
        ]
        if not lineage_members:
            return None
        if self.selected_last_known_x is None or self.selected_last_known_y is None:
            return lineage_members[0]
        origin_x = self.selected_last_known_x
        origin_y = self.selected_last_known_y
        return min(
            lineage_members,
            key=lambda creature: ((creature.x - origin_x) ** 2) + ((creature.y - origin_y) ** 2),
        )

    def _lineage_stats(self, simulation: Simulation) -> tuple[int, float | None]:
        if self.selected_lineage_id is None:
            return 0, None
        trait_key = self.selected_graph_trait_key or self._graph_trait_key_for_mode(simulation)
        get_lineage_observability = getattr(simulation, "get_lineage_observability", None)
        if callable(get_lineage_observability):
            summary = get_lineage_observability(int(self.selected_lineage_id), traits=(trait_key,))
            count = int(summary.get("count", 0))
            trait_averages = summary.get("trait_averages", {})
            return count, (
                float(trait_averages[trait_key])
                if count > 0 and trait_key in trait_averages
                else None
            )

        count = 0
        total = 0.0
        for creature in simulation.creatures:
            if int(creature.lineage_id) != int(self.selected_lineage_id):
                continue
            count += 1
            total += float(getattr(creature.genome, trait_key, 0.0))
        return count, (total / count) if count > 0 else None

    def select_at_world_pos(
        self,
        world_x: float,
        world_y: float,
        simulation: Simulation,
        *,
        pick_radius: float = 48.0,
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
        if best is None:
            self.clear_selection()
            return
        self._bind_selection(best, simulation)

    def select_at_display_pos(
        self,
        display_x: float,
        display_y: float,
        display_width: int,
        display_height: int,
        simulation: Simulation,
    ) -> None:
        """Select the nearest creature in the current presentation space."""
        best = find_nearest_creature_at_display_pos(
            display_x,
            display_y,
            display_width,
            display_height,
            simulation,
        )
        if best is None:
            self.clear_selection()
            return
        self._bind_selection(best, simulation)

    def get_selected_creature(self, simulation: Simulation) -> Creature | None:
        """Return the currently selected creature, or None."""
        return self._find_creature_by_id(simulation, self.selected_creature_id)

    def get_focus_creature(self, simulation: Simulation) -> Creature | None:
        """Return the creature that should be highlighted for live inspect follow."""
        selected = self.get_selected_creature(simulation)
        if selected is not None:
            self.follow_creature_id = id(selected)
            self._store_live_snapshot(selected)
            return selected
        proxy = self._find_creature_by_id(simulation, self.follow_creature_id)
        if proxy is not None and self.selected_lineage_id is not None:
            if int(proxy.lineage_id) == int(self.selected_lineage_id):
                return proxy
        proxy = self._find_lineage_proxy(simulation)
        if proxy is None:
            self.follow_creature_id = None
            return None
        self.follow_creature_id = id(proxy)
        return proxy

    def observe_simulation(self, simulation: Simulation) -> None:
        """Refresh selection state and bounded history from the latest sim tick."""
        if not self.enabled or not self.has_selection:
            return

        current_tick = int(getattr(simulation, "_frame", 0))
        for event in getattr(simulation, "death_events", ()):
            if int(event.get("creature_id", -1)) != int(self.selected_creature_id or -1):
                continue
            self._mark_selected_dead(
                tick=current_tick,
                cause=str(event.get("cause")) if event.get("cause") is not None else None,
                x=float(event.get("x", 0.0)),
                y=float(event.get("y", 0.0)),
            )

        selected = self.get_selected_creature(simulation)
        if selected is not None:
            self._store_live_snapshot(selected)
        elif self.selected_creature_id is not None and not self.selected_dead:
            self._mark_selected_dead(tick=current_tick, cause="unknown")

        if (
            self._last_history_sample_tick is not None
            and (current_tick - self._last_history_sample_tick) < _INSPECT_HISTORY_SAMPLE_INTERVAL_TICKS
        ):
            return

        self._last_history_sample_tick = current_tick
        if selected is not None:
            self._energy_history.append((current_tick, float(selected.energy)))
        lineage_count, lineage_trait_value = self._lineage_stats(simulation)
        if self.selected_lineage_id is not None:
            self._lineage_population_history.append((current_tick, lineage_count))
            self._lineage_trait_history.append((current_tick, lineage_trait_value))
        self._invalidate_graph_cache()

    def clear_selection(self) -> None:
        """Clear the selected creature without exiting inspect mode."""
        self.selected_creature_id = None
        self.selected_lineage_id = None
        self.selected_species = None
        self.selected_last_known_x = None
        self.selected_last_known_y = None
        self.selected_last_known_energy = None
        self.selected_last_known_age_ticks = None
        self.selected_dead = False
        self.selected_death_cause = None
        self.selected_death_tick = None
        self.follow_creature_id = None
        self.selected_graph_trait_key = None
        self.selected_graph_trait_initial_value = None
        self._reset_histories()


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

_INSPECT_LABELS: dict[str, str] = {
    "selected_status": "Selected",
    "showing": "Showing",
    "lineage_status": "Lineage",
    "stage": "Stage",
    "energy": "Energy",
    "depth": "Depth",
    "age": "Age",
    "vel": "Moving",
    "behavior": "Mode",
    "attention": "Focus",
    "attention_conf": "Confidence",
    "motion": "Motion",
    "depth_pref": "Prefers",
    "speed": "Speed",
    "size": "Size",
    "sense": "Sense",
    "aggr": "Aggression",
    "eff": "Efficiency",
    "pos": "Position",
    "recent_animal_e": "Recent prey E",
    "satiety": "Satiety",
    "tags": "Temperament",
    "likely_goal": "Likely goal",
    "body_plan": "Body plan",
    "key_effect": "Key effect",
    "age_seconds": "Age",
    "lineage_age": "Lin age",
    "lineage_size": "Lin size",
    "species_age_percentile": "Age pct",
    "above_population": "Above avg",
    "below_population": "Below avg",
    "modifier_speed_mult": "Speed",
    "modifier_movement_cost_mult": "Move cost",
    "modifier_metabolic_cost_mult": "Metabolism",
    "modifier_sense_radius_mult": "Sense",
    "modifier_food_efficiency_mult": "Food",
    "modifier_reproduction_threshold_mult": "Repro thresh",
    "modifier_predation_contact_mult": "Contact",
    "modifier_flee_agility_mult": "Flee",
    "modifier_depth_transition_mult": "Depth move",
    "modifier_in_band_sense_mult": "In-band sense",
    "modifier_cross_band_sense_mult": "Cross-band sense",
}

_STORY_STAGE_LABELS: dict[str, str] = {
    "larva": "Larval",
    "juvenile": "Young",
    "young adult": "Young adult",
    "adult": "Adult",
    "elder": "Elder",
    "decrepit": "Decrepit",
}

_DEPTH_STORY_PHRASES: dict[str, str] = {
    "surface": "near the surface",
    "mid": "in mid-depth water",
    "deep": "in deep water",
}

_BEHAVIOR_GOALS: dict[str, str] = {
    "starving": "Find food fast",
    "foraging": "Find food",
    "fleeing": "Open distance from danger",
    "hunting": "Close on prey",
    "stalking": "Set up a strike",
    "sated": "Digest and recover",
    "wandering": "Roam",
    "flocking": "Hold with the flock",
}

_INSPECT_MARGIN = 24
_INSPECT_PANEL_WIDTH = 400
_INSPECT_PANEL_BG = (7, 13, 24, 230)
_INSPECT_PANEL_BORDER = (88, 156, 198, 168)
_INSPECT_DIVIDER = (48, 78, 104, 164)
_INSPECT_TITLE = (228, 239, 250)
_INSPECT_SUMMARY = (192, 214, 232)
_INSPECT_MODE = (154, 188, 214)
_INSPECT_META = (119, 145, 170)
_INSPECT_SECTION = (152, 186, 208)
_INSPECT_LABEL = (130, 154, 177)
_INSPECT_VALUE = (219, 231, 244)


@dataclass(frozen=True)
class InspectPanelLine:
    """One logical line in the inspect overlay presentation model."""

    kind: str
    key: str = ""
    text: str = ""
    label: str = ""
    value: str = ""
    secondary_key: str = ""
    secondary_label: str = ""
    secondary_value: str = ""
    style: str = "body"
    removable: bool = False
    priority: int = 0


@dataclass(frozen=True)
class InspectPanelPlacement:
    """Top-right placement details for the inspect overlay."""

    x: int
    y: int
    width: int
    height: int
    margin: int


@dataclass(frozen=True)
class InspectSelectionDisplay:
    """Readable selection/lineage state shown above live inspect details."""

    title: str
    summary: str
    selected_status: str
    showing: str
    lineage_status: str


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
    try:
        behavior = infer_behavior_mode(creature, simulation)
    except Exception:
        behavior = "unknown"
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

    try:
        creature_obs = simulation.get_creature_observability(creature)
    except Exception:
        creature_obs = {}

    if creature_obs:
        card["age_seconds"] = f"{float(creature_obs.get('age_seconds', 0.0)):.1f}s"
        card["lineage_age"] = f"{float(creature_obs.get('lineage_age_seconds', 0.0)):.1f}s"
        card["lineage_size"] = str(int(creature_obs.get('lineage_size', 1)))
        card["species_age_percentile"] = f"{float(creature_obs.get('species_age_percentile', 0.0)):.0f}%"
        above = creature_obs.get("above_population_traits", ())
        below = creature_obs.get("below_population_traits", ())
        if above:
            card["above_population"] = ", ".join(above)
        if below:
            card["below_population"] = ", ".join(below)


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

    try:
        attention = infer_attention_target(creature, simulation)
    except Exception:
        attention = None
    if attention is not None:
        card["attention"] = attention.kind
        card["attention_conf"] = f"{attention.confidence:.0%}"

    # ── Phenotype / Body plan section ──
    card["section_phenotype"] = ""
    try:
        phenotype = simulation.get_creature_effective_phenotype(creature)
        epistasis_enabled = simulation._epistasis_enabled()
    except Exception:
        phenotype = None
        epistasis_enabled = False

    if phenotype is not None:
        card["body_plan"] = phenotype.strategy_bucket.replace("-", " ")
        card["key_effect"] = describe_phenotype_effect(
            phenotype, creature.genome, species=creature.species
        )
        card["epistasis_enabled"] = "yes" if epistasis_enabled else "no"
        # Store modifier values for detail mode
        mods = format_phenotype_modifiers(phenotype)
        for attr, formatted in mods.items():
            card[f"modifier_{attr}"] = formatted
        card["preferred_depth_band"] = str(phenotype.preferred_depth_band)
    else:
        card["body_plan"] = "—"
        card["key_effect"] = "—"
        card["epistasis_enabled"] = "no"

    return card


def friendly_inspect_label(key: str) -> str:
    """Return a user-facing label for an internal creature-card key."""
    return _INSPECT_LABELS.get(key, key.replace("_", " ").capitalize())


def build_creature_summary(card: Mapping[str, str]) -> str:
    """Return a short narrative sentence describing the selected creature."""
    stage = _story_stage_label(card.get("stage", "Creature"))
    species = card.get("species", "Creature").lower()
    behavior = card.get("behavior", "wandering").strip().lower()
    attention = card.get("attention", "").strip().lower()
    depth_phrase = _depth_story_phrase(card.get("depth", "mid"))

    if behavior == "fleeing":
        object_text = "a threat" if attention == "threat" else "danger"
        return f"{stage} {species} fleeing {object_text} {depth_phrase}"
    if behavior == "hunting":
        object_text = "prey" if attention == "prey" else "its quarry"
        return f"{stage} {species} hunting {object_text} {depth_phrase}"
    if behavior == "stalking":
        object_text = "prey" if attention == "prey" else "its quarry"
        return f"{stage} {species} stalking {object_text} {depth_phrase}"
    if behavior == "foraging":
        object_text = "for food" if attention == "food" else ""
        suffix = f" {object_text}".rstrip()
        return f"{stage} {species} foraging{suffix} {depth_phrase}".replace("  ", " ")
    if behavior == "starving":
        return f"{stage} {species} searching urgently for food {depth_phrase}"
    if behavior == "sated":
        if species == "predator":
            return f"{stage} {species} sated after a kill"
        return f"{stage} {species} resting"
    if behavior == "flocking":
        return f"{stage} {species} holding with its flock {depth_phrase}"
    if behavior == "wandering":
        return f"{stage} {species} drifting {depth_phrase}"
    return f"{stage} {species} {behavior} {depth_phrase}".strip()


def build_inspect_panel_lines(
    card: Mapping[str, str] | None,
    inspect_mode: InspectMode,
    *,
    detail_mode: str | None = None,
    selection_display: InspectSelectionDisplay | None = None,
) -> tuple[InspectPanelLine, ...]:
    """Convert a creature card dict into ordered presentation lines."""
    active_detail_mode = detail_mode or inspect_mode.detail_mode
    lines: list[InspectPanelLine] = [
        InspectPanelLine(kind="mode", text="INSPECT  (I exit)", style="mode"),
        InspectPanelLine(kind="meta", text=_inspect_status_line(inspect_mode), style="meta"),
        InspectPanelLine(kind="divider"),
    ]

    if card is None and selection_display is None:
        lines.extend(
            [
                InspectPanelLine(kind="title", text="INSPECT", style="title"),
                InspectPanelLine(
                    kind="summary",
                    text="Click a creature to inspect",
                    style="summary",
                ),
            ]
        )
        return tuple(lines)

    title = (
        selection_display.title
        if selection_display is not None
        else f"{card.get('species', 'Creature')} {card.get('lineage', '').strip()}".strip()
    )
    summary = (
        selection_display.summary
        if selection_display is not None
        else build_creature_summary(card)
    )
    lines.extend(
        [
            InspectPanelLine(kind="title", text=title, style="title"),
            InspectPanelLine(kind="summary", text=summary, style="summary"),
            InspectPanelLine(kind="divider"),
            InspectPanelLine(kind="section", text="State"),
        ]
    )

    if selection_display is not None:
        lines.extend(
            [
                _build_row("selected_status", selection_display.selected_status),
                _build_row("showing", selection_display.showing, removable=True, priority=15),
                _build_row("lineage_status", selection_display.lineage_status, removable=True, priority=15),
            ]
        )

    if card is None:
        return tuple(lines)

    lines.extend(
        [
            _build_row_pair(
                "stage",
                card.get("stage", "—"),
                "depth",
                _titleize(card.get("depth", "—")),
            ),
            _build_row_pair(
                "energy",
                _format_energy_value(card.get("energy", "—")),
                "vel",
                _format_velocity_value(card.get("vel", "0")),
            ),
            _build_row(
                "age",
                _format_age_value(card.get("age", "—")),
                removable=True,
                priority=35,
            ),
            _build_row_pair("age_seconds", card.get("age_seconds", "—"), "lineage_age", card.get("lineage_age", "—"), removable=True, priority=35),
            _build_row_pair("lineage", card.get("lineage", "—"), "lineage_size", card.get("lineage_size", "—"), removable=True, priority=36),
            InspectPanelLine(kind="section", text="Behavior"),
            _build_row("behavior", _titleize(card.get("behavior", "unknown"))),
        ]
    )

    if "attention" in card:
        lines.append(_build_row("attention", _titleize(card["attention"])))
    if "attention_conf" in card:
        lines.append(
            _build_row(
                "attention_conf",
                _format_confidence_value(card["attention_conf"]),
                removable=True,
                priority=25,
            )
        )
    lines.append(_build_row("likely_goal", _behavior_goal(card)))

    lines.extend(
        [
            InspectPanelLine(kind="section", text="Temperament"),
            _build_row("tags", card.get("tags", "—")),
        ]
    )

    # ── Phenotype / Body plan section (always shown) ──
    body_plan = card.get("body_plan", "—")
    key_effect = card.get("key_effect", "—")
    epistasis_on = card.get("epistasis_enabled", "no") == "yes"

    lines.extend(
        [
            InspectPanelLine(kind="section", text="Body plan"),
            _build_row("body_plan", _titleize(body_plan)),
        ]
    )
    if epistasis_on:
        lines.append(_build_row("key_effect", key_effect))
    else:
        lines.append(
            InspectPanelLine(
                kind="row",
                key="key_effect",
                label=friendly_inspect_label("key_effect"),
                value="Epistasis disabled",
                style="body",
            )
        )

    if active_detail_mode == "detail":
        lines.extend(
            [
                InspectPanelLine(kind="section", text="Details", removable=True, priority=80),
                _build_row(
                    "motion",
                    card.get("motion", "—"),
                    style="detail",
                    removable=True,
                    priority=85,
                ),
                _build_row(
                    "depth_pref",
                    card.get("depth_pref", "—"),
                    style="detail",
                    removable=True,
                    priority=85,
                ),
                _build_row_pair(
                    "speed",
                    card.get("speed", "—"),
                    "size",
                    card.get("size", "—"),
                    style="detail",
                    removable=True,
                    priority=90,
                ),
                _build_row_pair(
                    "sense",
                    card.get("sense", "—"),
                    "aggr",
                    card.get("aggr", "—"),
                    style="detail",
                    removable=True,
                    priority=90,
                ),
                _build_row("eff", card.get("eff", "—"), style="detail", removable=True, priority=90),
                _build_row("species_age_percentile", card.get("species_age_percentile", "—"), style="detail", removable=True, priority=90),
                _build_row("pos", card.get("pos", "—"), style="detail", removable=True, priority=95),
                _build_row("above_population", card.get("above_population", "—"), style="detail", removable=True, priority=96),
                _build_row("below_population", card.get("below_population", "—"), style="detail", removable=True, priority=96),
            ]
        )
        if "recent_animal_e" in card:
            lines.append(
                _build_row(
                    "recent_animal_e",
                    card["recent_animal_e"],
                    style="detail",
                    removable=True,
                    priority=100,
                )
            )
        if "satiety" in card:
            lines.append(
                _build_row(
                    "satiety",
                    card["satiety"],
                    style="detail",
                    removable=True,
                    priority=100,
                )
            )

        # ── Effective Phenotype detail section ──
        if epistasis_on:
            lines.extend(
                [
                    InspectPanelLine(
                        kind="section",
                        text="Effective phenotype",
                        removable=True,
                        priority=110,
                    ),
                    _build_row(
                        "modifier_speed_mult",
                        card.get("modifier_speed_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=115,
                    ),
                    _build_row(
                        "modifier_movement_cost_mult",
                        card.get("modifier_movement_cost_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=115,
                    ),
                    _build_row(
                        "modifier_metabolic_cost_mult",
                        card.get("modifier_metabolic_cost_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=115,
                    ),
                    _build_row_pair(
                        "modifier_sense_radius_mult",
                        card.get("modifier_sense_radius_mult", "×1.00"),
                        "modifier_food_efficiency_mult",
                        card.get("modifier_food_efficiency_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=115,
                    ),
                    _build_row(
                        "modifier_reproduction_threshold_mult",
                        card.get("modifier_reproduction_threshold_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=115,
                    ),
                ]
            )
            # Role-specific modifiers
            if card.get("species", "").lower() == "predator":
                lines.append(
                    _build_row(
                        "modifier_predation_contact_mult",
                        card.get("modifier_predation_contact_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=120,
                    )
                )
            if card.get("species", "").lower() == "prey":
                lines.append(
                    _build_row(
                        "modifier_flee_agility_mult",
                        card.get("modifier_flee_agility_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=120,
                    )
                )
            lines.extend(
                [
                    _build_row_pair(
                        "modifier_depth_transition_mult",
                        card.get("modifier_depth_transition_mult", "×1.00"),
                        "modifier_in_band_sense_mult",
                        card.get("modifier_in_band_sense_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=125,
                    ),
                    _build_row(
                        "modifier_cross_band_sense_mult",
                        card.get("modifier_cross_band_sense_mult", "×1.00"),
                        style="detail",
                        removable=True,
                        priority=125,
                    ),
                ]
            )

    return tuple(lines)


def compute_inspect_panel_placement(
    surface_width: int,
    surface_height: int,
    panel_width: int,
    panel_height: int,
    *,
    margin: int = _INSPECT_MARGIN,
) -> InspectPanelPlacement:
    """Place the inspect panel in the top-right with stable padding."""
    safe_width = max(1, int(surface_width))
    safe_height = max(1, int(surface_height))
    safe_panel_width = max(1, min(int(panel_width), safe_width))
    available_height = max(1, safe_height - (margin * 2))
    safe_panel_height = max(1, min(int(panel_height), available_height))
    x = max(0, safe_width - safe_panel_width - margin)
    y = min(margin, max(0, safe_height - safe_panel_height))
    return InspectPanelPlacement(
        x=x,
        y=y,
        width=safe_panel_width,
        height=safe_panel_height,
        margin=margin,
    )


def _death_cause_label(cause: str | None) -> str:
    if not cause:
        return "dead"
    return cause.replace("_", " ")


def _lineage_status_label(count: int) -> str:
    if count <= 0:
        return "Extinct"
    if count == 1:
        return "1 alive"
    return f"{count} alive"


def _build_selection_display(
    inspect_mode: InspectMode,
    simulation: Simulation,
    *,
    focus_creature: Creature | None,
    card: Mapping[str, str] | None,
) -> InspectSelectionDisplay | None:
    if not inspect_mode.has_selection:
        return None

    lineage_id = inspect_mode.selected_lineage_id
    title_species = (
        str(inspect_mode.selected_species).capitalize()
        if inspect_mode.selected_species
        else card.get("species", "Creature") if card is not None else "Creature"
    )
    title = title_species
    if lineage_id is not None:
        title = f"{title_species} #{lineage_id}"

    lineage_count, _lineage_trait_value = inspect_mode._lineage_stats(simulation)
    lineage_status = _lineage_status_label(lineage_count)
    selected_creature = inspect_mode.get_selected_creature(simulation)
    if selected_creature is not None and card is not None:
        return InspectSelectionDisplay(
            title=title,
            summary=build_creature_summary(card),
            selected_status="Alive",
            showing="Selected organism",
            lineage_status=lineage_status,
        )

    death_label = _death_cause_label(inspect_mode.selected_death_cause)
    if focus_creature is not None:
        showing_species = str(getattr(focus_creature, "species", "creature")).capitalize()
        return InspectSelectionDisplay(
            title=title,
            summary=(
                "Selected organism died. Live state below follows a "
                f"{showing_species.lower()} from the same lineage."
            ),
            selected_status=f"Dead ({death_label})",
            showing=f"{showing_species} lineage organism",
            lineage_status=lineage_status,
        )

    return InspectSelectionDisplay(
        title=title,
        summary="Selected organism died. This lineage is extinct.",
        selected_status=f"Dead ({death_label})",
        showing="No living organism",
        lineage_status=lineage_status,
    )


def _compute_graph_strip_rect(surface_width: int, surface_height: int):
    import pygame

    width = max(240, surface_width - (_INSPECT_MARGIN * 2))
    height = max(92, min(148, int(surface_height * 0.19)))
    rect = pygame.Rect(_INSPECT_MARGIN, 0, width, height)
    rect.bottom = max(height + 8, surface_height - 18)
    return rect


def _graph_trait_title(trait_key: str | None) -> str:
    if trait_key == "depth_preference":
        return "Lineage depth preference"
    if trait_key == "conformity":
        return "Lineage conformity"
    return "Lineage efficiency"


def _build_graph_strip_surface(
    *,
    target_width: int,
    target_height: int,
    inspect_mode: InspectMode,
    simulation: Simulation,
):
    import pygame

    strip_rect = _compute_graph_strip_rect(target_width, target_height)
    cache_key = (
        strip_rect.width,
        strip_rect.height,
        inspect_mode.selected_creature_id,
        inspect_mode.selected_lineage_id,
        inspect_mode.follow_creature_id,
        inspect_mode.selected_dead,
        inspect_mode.selected_death_cause,
        tuple(inspect_mode._energy_history),
        tuple(inspect_mode._lineage_population_history),
        tuple(inspect_mode._lineage_trait_history),
        inspect_mode.selected_graph_trait_key,
        inspect_mode.selected_graph_trait_initial_value,
    )
    if cache_key == inspect_mode._graph_cache_key and inspect_mode._graph_surface_cache is not None:
        return inspect_mode._graph_surface_cache, strip_rect

    surface = pygame.Surface(strip_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(
        surface,
        (6, 14, 24, 126),
        (0, 0, strip_rect.width, strip_rect.height),
        border_radius=14,
    )
    pygame.draw.rect(
        surface,
        (84, 128, 152, 138),
        (0, 0, strip_rect.width, strip_rect.height),
        1,
        border_radius=14,
    )

    title_font = pygame.font.Font(None, 22)
    body_font = pygame.font.Font(None, 20)
    value_font = pygame.font.Font(None, 24)
    if not inspect_mode.has_selection:
        prompt = title_font.render(
            "Select a creature to plot organism and lineage history.",
            True,
            (215, 228, 239),
        )
        surface.blit(
            prompt,
            ((strip_rect.width - prompt.get_width()) // 2, (strip_rect.height - prompt.get_height()) // 2),
        )
        inspect_mode._graph_cache_key = cache_key
        inspect_mode._graph_surface_cache = surface
        return surface, strip_rect

    graph_count = 3 if strip_rect.width >= 900 else 2
    gap = 12
    card_width = (strip_rect.width - ((graph_count + 1) * gap)) // graph_count
    card_height = strip_rect.height - (gap * 2)
    graph_rects = []
    for index in range(graph_count):
        graph_rects.append(
            pygame.Rect(
                gap + index * (card_width + gap),
                gap,
                card_width,
                card_height,
            )
        )

    species = str(inspect_mode.selected_species or "prey").lower()
    organism_color = (245, 140, 108) if species == "predator" else (108, 212, 232)
    lineage_color = (126, 196, 248)
    trait_color = (123, 217, 176)

    energy_series = [(tick, value) for tick, value in inspect_mode._energy_history]
    lineage_series = [(tick, float(value)) for tick, value in inspect_mode._lineage_population_history]
    trait_series = [(tick, value) for tick, value in inspect_mode._lineage_trait_history]
    lineage_status_text = _lineage_status_label(
        int(lineage_series[-1][1]) if lineage_series else 0
    )

    _draw_sparkline_card(
        surface,
        graph_rects[0],
        title="Selected energy",
        current_text=(
            f"{int(round((inspect_mode.selected_last_known_energy or 0.0) * 100.0))}%"
            if not inspect_mode.selected_dead and inspect_mode.selected_last_known_energy is not None
            else "Dead"
        ),
        range_text="0-100%",
        series=energy_series,
        color=organism_color,
        y_min=0.0,
        y_max=1.0,
        empty_text="No organism samples yet",
        body_font=body_font,
        title_font=title_font,
        value_font=value_font,
        baseline=None,
        value_suffix="",
    )
    _draw_sparkline_card(
        surface,
        graph_rects[1],
        title="Selected lineage population",
        current_text=lineage_status_text,
        range_text=(
            f"0-{int(max((point[1] for point in lineage_series), default=1.0))}"
        ),
        series=lineage_series,
        color=lineage_color,
        y_min=0.0,
        y_max=max(1.0, max((point[1] for point in lineage_series), default=1.0)),
        empty_text="No lineage samples yet",
        body_font=body_font,
        title_font=title_font,
        value_font=value_font,
        baseline=None,
        value_suffix="",
    )
    if graph_count >= 3:
        current_trait = next(
            (value for _tick, value in reversed(trait_series) if value is not None),
            None,
        )
        baseline = inspect_mode.selected_graph_trait_initial_value
        trait_delta = (
            current_trait - baseline
            if current_trait is not None and baseline is not None
            else None
        )
        trait_text = (
            f"{current_trait:.2f} ({trait_delta:+.2f})"
            if current_trait is not None and trait_delta is not None
            else "No lineage data"
        )
        _draw_sparkline_card(
            surface,
            graph_rects[2],
            title=_graph_trait_title(inspect_mode.selected_graph_trait_key),
            current_text=trait_text,
            range_text="0.00-1.00",
            series=trait_series,
            color=trait_color,
            y_min=0.0,
            y_max=1.0,
            empty_text="Lineage extinct",
            body_font=body_font,
            title_font=title_font,
            value_font=value_font,
            baseline=baseline,
            value_suffix="",
        )

    inspect_mode._graph_cache_key = cache_key
    inspect_mode._graph_surface_cache = surface
    return surface, strip_rect


def _draw_sparkline_card(
    target,
    rect,
    *,
    title: str,
    current_text: str,
    range_text: str,
    series: list[tuple[int, float | None]],
    color: tuple[int, int, int],
    y_min: float,
    y_max: float,
    empty_text: str,
    body_font,
    title_font,
    value_font,
    baseline: float | None,
    value_suffix: str,
) -> None:
    import pygame

    pygame.draw.rect(target, (10, 20, 31, 118), rect, border_radius=12)
    pygame.draw.rect(target, (64, 98, 122, 144), rect, 1, border_radius=12)

    title_surf = title_font.render(title, True, (214, 228, 237))
    target.blit(title_surf, (rect.x + 10, rect.y + 8))
    current_surf = value_font.render(current_text + value_suffix, True, color)
    target.blit(current_surf, (rect.right - current_surf.get_width() - 10, rect.y + 6))
    range_surf = body_font.render(range_text, True, (140, 166, 184))
    target.blit(range_surf, (rect.x + 10, rect.bottom - range_surf.get_height() - 8))

    plot_rect = pygame.Rect(rect.x + 10, rect.y + 34, rect.width - 20, rect.height - 58)
    pygame.draw.line(
        target,
        (34, 52, 67),
        (plot_rect.x, plot_rect.bottom),
        (plot_rect.right, plot_rect.bottom),
        1,
    )
    if baseline is not None and y_max > y_min:
        baseline_y = plot_rect.bottom - int(round(((baseline - y_min) / (y_max - y_min)) * plot_rect.height))
        pygame.draw.line(
            target,
            (*color, 90),
            (plot_rect.x, baseline_y),
            (plot_rect.right, baseline_y),
            1,
        )

    valid_points = [(tick, value) for tick, value in series if value is not None]
    if len(valid_points) < 2:
        empty = body_font.render(empty_text, True, (156, 181, 196))
        target.blit(
            empty,
            ((plot_rect.centerx - empty.get_width() // 2), plot_rect.centery - empty.get_height() // 2),
        )
        return

    span = max(1, len(series) - 1)
    safe_denominator = max(0.001, y_max - y_min)
    points: list[tuple[int, int]] = []
    for index, (_tick, value) in enumerate(series):
        if value is None:
            if len(points) >= 2:
                pygame.draw.lines(target, color, False, points, 2)
            points = []
            continue
        x = plot_rect.x + int(round((index / span) * plot_rect.width))
        normalized = max(0.0, min(1.0, (float(value) - y_min) / safe_denominator))
        y = plot_rect.bottom - int(round(normalized * plot_rect.height))
        points.append((x, y))
    if len(points) >= 2:
        pygame.draw.lines(target, color, False, points, 2)
    elif len(points) == 1:
        pygame.draw.circle(target, color, points[0], 2)


def draw_inspect_overlay(
    target,
    inspect_mode: InspectMode,
    simulation: Simulation,
) -> None:
    """Draw the shared inspect overlay onto a pygame-compatible surface."""
    if not inspect_mode.enabled:
        return

    creature = inspect_mode.get_focus_creature(simulation)
    card = build_creature_card(creature, simulation) if creature is not None else None
    selection_display = _build_selection_display(
        inspect_mode,
        simulation,
        focus_creature=creature,
        card=card,
    )
    panel_surface = _build_inspect_panel_surface(
        target_width=target.get_width(),
        target_height=target.get_height(),
        inspect_mode=inspect_mode,
        card=card,
        selection_display=selection_display,
    )
    placement = compute_inspect_panel_placement(
        target.get_width(),
        target.get_height(),
        panel_surface.get_width(),
        panel_surface.get_height(),
    )
    target.blit(panel_surface, (placement.x, placement.y))
    graph_surface, graph_rect = _build_graph_strip_surface(
        target_width=target.get_width(),
        target_height=target.get_height(),
        inspect_mode=inspect_mode,
        simulation=simulation,
    )
    target.blit(graph_surface, graph_rect.topleft)


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


def find_nearest_creature_at_display_pos(
    display_x: float,
    display_y: float,
    display_width: int,
    display_height: int,
    simulation: Simulation,
) -> Creature | None:
    """Return the nearest creature to a scaled presentation-space click."""
    world_width = max(1, int(simulation.width))
    world_height = max(1, int(simulation.height))
    safe_display_width = max(1, int(display_width))
    safe_display_height = max(1, int(display_height))

    scale_x = safe_display_width / world_width
    scale_y = safe_display_height / world_height
    uniform_scale = min(scale_x, scale_y)
    base_pick_radius = max(1.0, 48.0 * uniform_scale)

    best: Creature | None = None
    best_dist = base_pick_radius
    for creature in simulation.creatures:
        creature_display_x = creature.x * scale_x
        creature_display_y = creature.y * scale_y
        dx = creature_display_x - display_x
        dy = creature_display_y - display_y
        dist = math.sqrt(dx * dx + dy * dy)

        displayed_radius = creature.get_radius() * uniform_scale
        threshold = max(displayed_radius + 8.0, 16.0 * uniform_scale, base_pick_radius)
        if dist < threshold and dist < best_dist:
            best = creature
            best_dist = dist
    return best


def _inspect_status_line(inspect_mode: InspectMode) -> str:
    if inspect_mode.pause_mode == _PLAYBACK_PAUSE:
        pace = "Paused"
        next_pace = "M: slow"
        normal_hint = "N: normal"
    elif inspect_mode.pause_mode == _PLAYBACK_SLOW:
        pace = f"Slow follow {inspect_mode.slow_hz:.0f} Hz"
        next_pace = "M: pause"
        normal_hint = "N: normal"
    else:
        pace = "Normal follow"
        next_pace = "M: slow"
        normal_hint = ""
    next_detail = "D: details" if inspect_mode.detail_mode == "compact" else "D: compact"
    parts = [pace, next_pace]
    if normal_hint:
        parts.append(normal_hint)
    parts.append(next_detail)
    return " · ".join(parts)


def _build_row(
    key: str,
    value: str,
    *,
    style: str = "body",
    removable: bool = False,
    priority: int = 0,
) -> InspectPanelLine:
    return InspectPanelLine(
        kind="row",
        key=key,
        label=friendly_inspect_label(key),
        value=value,
        style=style,
        removable=removable,
        priority=priority,
    )


def _build_row_pair(
    left_key: str,
    left_value: str,
    right_key: str,
    right_value: str,
    *,
    style: str = "body",
    removable: bool = False,
    priority: int = 0,
) -> InspectPanelLine:
    return InspectPanelLine(
        kind="row_pair",
        key=left_key,
        label=friendly_inspect_label(left_key),
        value=left_value,
        secondary_key=right_key,
        secondary_label=friendly_inspect_label(right_key),
        secondary_value=right_value,
        style=style,
        removable=removable,
        priority=priority,
    )


def _build_inspect_panel_surface(
    *,
    target_width: int,
    target_height: int,
    inspect_mode: InspectMode,
    card: Mapping[str, str] | None,
    selection_display: InspectSelectionDisplay | None,
):
    import pygame

    panel_width = _inspect_panel_width(target_width)
    max_height = max(1, target_height - (_INSPECT_MARGIN * 2))
    line_candidates = [
        build_inspect_panel_lines(
            card,
            inspect_mode,
            detail_mode=inspect_mode.detail_mode,
            selection_display=selection_display,
        )
    ]
    if card is not None and inspect_mode.detail_mode == "detail":
        line_candidates.append(
            build_inspect_panel_lines(
                card,
                inspect_mode,
                detail_mode="compact",
                selection_display=selection_display,
            )
        )

    last_surface = pygame.Surface((panel_width, min(max_height, 160)), pygame.SRCALPHA)
    for lines in line_candidates:
        fitted_lines = _fit_inspect_panel_lines(lines, panel_width, max_height)
        panel_surface = _render_inspect_panel_surface(panel_width, max_height, fitted_lines)
        last_surface = panel_surface
        if panel_surface.get_height() <= max_height:
            return panel_surface
    return last_surface


def _fit_inspect_panel_lines(
    lines: tuple[InspectPanelLine, ...],
    panel_width: int,
    max_height: int,
) -> tuple[InspectPanelLine, ...]:
    current_lines = tuple(lines)
    while _measure_panel_height(panel_width, current_lines) > max_height:
        removable = [line for line in current_lines if line.removable]
        if not removable:
            break
        line_to_remove = max(removable, key=lambda line: (line.priority, current_lines.index(line)))
        removed = False
        next_lines: list[InspectPanelLine] = []
        for line in current_lines:
            if not removed and line is line_to_remove:
                removed = True
                continue
            next_lines.append(line)
        current_lines = _remove_empty_sections(tuple(next_lines))
    return current_lines


def _remove_empty_sections(lines: tuple[InspectPanelLine, ...]) -> tuple[InspectPanelLine, ...]:
    cleaned: list[InspectPanelLine] = []
    total = len(lines)
    for index, line in enumerate(lines):
        if line.kind != "section":
            cleaned.append(line)
            continue
        keep_section = False
        for lookahead in lines[index + 1 : total]:
            if lookahead.kind == "section":
                break
            if lookahead.kind in {"row", "row_pair"}:
                keep_section = True
                break
        if keep_section:
            cleaned.append(line)
    return tuple(cleaned)


def _measure_panel_height(panel_width: int, lines: tuple[InspectPanelLine, ...]) -> int:
    return _render_inspect_panel_surface(panel_width, 100000, lines).get_height()


def _render_inspect_panel_surface(
    panel_width: int,
    max_height: int,
    lines: tuple[InspectPanelLine, ...],
):
    import pygame

    fonts = _inspect_fonts()
    padding = 16
    content_width = max(40, panel_width - (padding * 2))
    rendered_lines = [_render_line(line, fonts, content_width) for line in lines]
    content_height = sum(block["height"] for block in rendered_lines)
    panel_height = min(max_height, content_height + (padding * 2))
    surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    pygame.draw.rect(surface, _INSPECT_PANEL_BG, (0, 0, panel_width, panel_height), border_radius=10)
    pygame.draw.rect(surface, _INSPECT_PANEL_BORDER, (0, 0, panel_width, panel_height), 1, border_radius=10)

    y = padding
    for block in rendered_lines:
        if y >= panel_height - padding:
            break
        kind = block["kind"]
        if kind == "divider":
            draw_y = min(panel_height - padding, y + block["height"] // 2)
            pygame.draw.line(surface, _INSPECT_DIVIDER, (padding, draw_y), (panel_width - padding, draw_y), 1)
            y += block["height"]
            continue
        if kind == "section" and block.get("rule") is not None:
            rule_start, rule_y, rule_end = block["rule"]
            pygame.draw.line(
                surface,
                _INSPECT_DIVIDER,
                (padding + rule_start, y + rule_y),
                (padding + rule_end, y + rule_y),
                1,
            )
        for text_surface, offset_x, offset_y in block["parts"]:
            blit_y = y + offset_y
            if blit_y >= panel_height - padding:
                break
            surface.blit(text_surface, (padding + offset_x, blit_y))
        y += block["height"]
    return surface


def _render_line(line: InspectPanelLine, fonts, content_width: int) -> dict[str, object]:
    import pygame

    if line.kind == "divider":
        return {"kind": "divider", "parts": [], "height": 14}

    if line.kind in {"mode", "meta", "title", "summary", "section"}:
        font = {
            "mode": fonts["mode"],
            "meta": fonts["meta"],
            "title": fonts["title"],
            "summary": fonts["summary"],
            "section": fonts["section"],
        }[line.kind]
        color = {
            "mode": _INSPECT_MODE,
            "meta": _INSPECT_META,
            "title": _INSPECT_TITLE,
            "summary": _INSPECT_SUMMARY,
            "section": _INSPECT_SECTION,
        }[line.kind]
        max_lines = 1 if line.kind in {"mode", "meta", "section"} else 2
        text_lines = _wrap_text(font, line.text, content_width, max_lines=max_lines)
        parts = []
        y = 0
        for text_line in text_lines:
            surf = font.render(text_line, True, color)
            parts.append((surf, 0, y))
            y += surf.get_height() + 1
        extra_space = 10 if line.kind == "title" else 8 if line.kind == "summary" else 4
        rule = None
        if line.kind == "section" and parts:
            label_width = parts[0][0].get_width()
            rule_start = min(content_width, label_width + 10)
            if rule_start < content_width:
                rule = (rule_start, max(7, parts[0][0].get_height() // 2 + 1), content_width)
        return {
            "kind": line.kind,
            "parts": parts,
            "height": max(0, y - 1) + extra_space,
            "rule": rule,
        }

    if line.kind == "row_pair":
        return _render_row_pair(line, fonts, content_width)

    label_font = fonts["label"]
    value_font = fonts["body"] if line.style == "body" else fonts["detail"]
    label_text = f"{line.label}:"
    label_surf = label_font.render(label_text, True, _INSPECT_LABEL)
    if line.key in {"tags", "above_population", "below_population"}:
        wrapped_values = _wrap_comma_separated_text(
            value_font,
            line.value,
            content_width - 14,
            max_lines=3,
        )
        return _render_wrapped_row(label_surf, value_font, wrapped_values, content_width)
    value_space = content_width - label_surf.get_width() - 10
    if value_space < 80:
        wrapped_values = _wrap_text(value_font, line.value, content_width - 14, max_lines=3)
        return _render_wrapped_row(label_surf, value_font, wrapped_values, content_width)
    single_value = _truncate_text(
        value_font,
        line.value,
        value_space,
    )
    value_surf = value_font.render(single_value, True, _INSPECT_VALUE)

    if label_surf.get_width() + 10 + value_surf.get_width() <= content_width:
        height = max(label_surf.get_height(), value_surf.get_height()) + 6
        return {
            "kind": "row",
            "parts": [
                (label_surf, 0, 0),
                (value_surf, label_surf.get_width() + 10, 0),
            ],
            "height": height,
        }

    max_lines = 4 if line.key in {"key_effect", "above_population", "below_population"} else 3
    wrapped_values = _wrap_text(value_font, line.value, content_width - 14, max_lines=max_lines)
    return _render_wrapped_row(label_surf, value_font, wrapped_values, content_width)


def _render_row_pair(line: InspectPanelLine, fonts, content_width: int) -> dict[str, object]:
    label_font = fonts["label"]
    value_font = fonts["body"] if line.style == "body" else fonts["detail"]
    half_width = max(80, (content_width - 16) // 2)
    left_text = _truncate_text(
        value_font,
        f"{line.label}: {line.value}",
        half_width,
    )
    right_text = _truncate_text(
        value_font,
        f"{line.secondary_label}: {line.secondary_value}",
        half_width,
    )
    left_surf = value_font.render(left_text, True, _INSPECT_VALUE)
    right_surf = value_font.render(right_text, True, _INSPECT_VALUE)
    if left_surf.get_width() + 16 + right_surf.get_width() <= content_width:
        height = max(left_surf.get_height(), right_surf.get_height()) + 6
        return {
            "kind": "row_pair",
            "parts": [
                (left_surf, 0, 0),
                (right_surf, content_width - right_surf.get_width(), 0),
            ],
            "height": height,
        }

    parts = []
    left_label = label_font.render(f"{line.label}:", True, _INSPECT_LABEL)
    left_value = value_font.render(
        _truncate_text(value_font, line.value, max(40, content_width - left_label.get_width() - 10)),
        True,
        _INSPECT_VALUE,
    )
    parts.append((left_label, 0, 0))
    parts.append((left_value, left_label.get_width() + 10, 0))
    y = max(left_label.get_height(), left_value.get_height()) + 6
    right_label = label_font.render(f"{line.secondary_label}:", True, _INSPECT_LABEL)
    parts.append((right_label, 0, y))
    y += right_label.get_height() + 1
    right_values = _wrap_text(value_font, line.secondary_value, max(40, content_width - 14), max_lines=2)
    for wrapped in right_values:
        surf = value_font.render(wrapped, True, _INSPECT_VALUE)
        parts.append((surf, 14, y))
        y += surf.get_height() + 1
    return {"kind": "row_pair", "parts": parts, "height": y + 3}


def _render_wrapped_row(label_surf, value_font, wrapped_values: list[str], content_width: int) -> dict[str, object]:
    parts = [(label_surf, 0, 0)]
    y = label_surf.get_height() + 2
    for wrapped in wrapped_values:
        surf = value_font.render(_truncate_text(value_font, wrapped, content_width - 14), True, _INSPECT_VALUE)
        parts.append((surf, 14, y))
        y += surf.get_height() + 2
    return {"kind": "row", "parts": parts, "height": y + 3}


def _inspect_fonts() -> dict[str, object]:
    import pygame

    return {
        "mode": pygame.font.Font(None, 22),
        "meta": pygame.font.Font(None, 20),
        "title": pygame.font.Font(None, 32),
        "summary": pygame.font.Font(None, 26),
        "section": pygame.font.Font(None, 22),
        "label": pygame.font.Font(None, 22),
        "body": pygame.font.Font(None, 24),
        "detail": pygame.font.Font(None, 20),
    }


def wrap_text(font, text: str, max_width: int, *, max_lines: int) -> list[str]:
    if not text:
        return ["—"]
    safe_width = max(20, max_width)
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.size(candidate)[0] <= safe_width:
            current = candidate
            continue
        lines.append(_truncate_text(font, current, safe_width))
        current = word
    lines.append(_truncate_text(font, current, safe_width))
    if len(lines) <= max_lines:
        return lines
    trimmed = lines[: max_lines - 1]
    remainder = " ".join(words[len(" ".join(trimmed).split()):]).strip()
    trimmed.append(_truncate_text(font, remainder, safe_width))
    return trimmed


def wrap_comma_separated_text(font, text: str, max_width: int, *, max_lines: int) -> list[str]:
    if not text:
        return ["—"]
    tokens = [token.strip() for token in text.split(",") if token.strip()]
    if not tokens:
        return [text]

    lines: list[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        candidate = f"{current}, {token}"
        if font.size(candidate)[0] <= max_width:
            current = candidate
            continue
        lines.append(_truncate_text(font, current, max_width))
        current = token
    lines.append(_truncate_text(font, current, max_width))
    if len(lines) <= max_lines:
        return lines

    kept = lines[: max_lines - 1]
    remaining_tokens = tokens[len(", ".join(kept).split(", ")) :]
    kept.append(_truncate_text(font, ", ".join(remaining_tokens), max_width))
    return kept


_wrap_text = wrap_text
_wrap_comma_separated_text = wrap_comma_separated_text


def _truncate_text(font, text: str, max_width: int) -> str:
    safe_width = max(8, max_width)
    if font.size(text)[0] <= safe_width:
        return text
    ellipsis = "..."
    trimmed = text
    while trimmed and font.size(trimmed + ellipsis)[0] > safe_width:
        trimmed = trimmed[:-1]
    return (trimmed + ellipsis) if trimmed else ellipsis


def _inspect_panel_width(target_width: int) -> int:
    desired_width = min(_INSPECT_PANEL_WIDTH, max(280, int(target_width * 0.40)))
    desired_width = min(desired_width, max(200, target_width - (_INSPECT_MARGIN * 2)))
    return max(160, min(target_width, desired_width))


def _story_stage_label(stage: str) -> str:
    return _STORY_STAGE_LABELS.get(stage.strip().lower(), stage.strip() or "Creature")


def _depth_story_phrase(depth: str) -> str:
    return _DEPTH_STORY_PHRASES.get(depth.strip().lower(), "in open water")


def _behavior_goal(card: Mapping[str, str]) -> str:
    behavior = card.get("behavior", "wandering").strip().lower()
    attention = card.get("attention", "").strip().lower()
    if behavior == "foraging" and attention == "food":
        return "Reach food"
    if behavior in {"hunting", "stalking"} and attention == "prey":
        return "Close on prey"
    if behavior == "fleeing" and attention == "threat":
        return "Break line of pursuit"
    return _BEHAVIOR_GOALS.get(behavior, "Observe")


def _format_velocity_value(value: str) -> str:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return value
    if speed < 0.05:
        return "Still"
    if speed < 0.25:
        label = "Slow"
    elif speed < 0.55:
        label = "Cruising"
    elif speed < 0.90:
        label = "Fast"
    else:
        label = "Bursting"
    return f"{label} ({speed:.2f})"


def _format_energy_value(value: str) -> str:
    try:
        energy = float(value)
    except (TypeError, ValueError):
        return value
    pct = max(0, min(100, round(energy * 100)))
    if energy < 0.15:
        label = "Critical"
    elif energy < 0.35:
        label = "Low"
    elif energy < 0.70:
        label = "Steady"
    elif energy < 0.90:
        label = "High"
    else:
        label = "Full"
    return f"{label} ({pct}%)"


def _format_confidence_value(value: str) -> str:
    try:
        pct = int(str(value).strip().rstrip("%"))
    except (TypeError, ValueError):
        return value
    if pct < 45:
        label = "Low"
    elif pct < 75:
        label = "Medium"
    elif pct < 90:
        label = "High"
    else:
        label = "Very high"
    return f"{label} ({pct}%)"


def _format_age_value(value: str) -> str:
    try:
        raw_ticks, raw_rest = str(value).split("/", 1)
        max_life, raw_pct = raw_rest.split("(", 1)
        age_ticks = int(raw_ticks.strip())
        lifespan_ticks = int(max_life.strip())
        pct = int(raw_pct.rstrip(") ").rstrip("%"))
    except (AttributeError, TypeError, ValueError):
        return value
    return f"{pct}% lifespan ({age_ticks} / {lifespan_ticks}t)"


def _titleize(value: str) -> str:
    cleaned = value.replace("_", " ").strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "—"
