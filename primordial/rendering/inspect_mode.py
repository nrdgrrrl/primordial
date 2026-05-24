"""Inspect Mode — read-only creature observability overlay.

This module provides a non-persistent runtime state object (InspectMode) and
a pure-function creature card builder.  It does **not** mutate simulation
state, consume simulation RNG, or alter ecology dials.  It is purely for
display purposes.
"""

from __future__ import annotations

import math
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


@dataclass
class InspectMode:
    """Non-persistent runtime state for the creature inspect overlay.

    This object is owned by the main loop — it is never serialised into
    world snapshots or persisted across sessions.
    """

    enabled: bool = False
    pause_mode: str = "pause"          # "pause" or "slow"
    slow_hz: float = 2.0               # sim ticks per second in slow mode
    detail_mode: str = "compact"       # "compact" or "detail"
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

    def toggle_detail_level(self) -> None:
        """Switch between compact and detailed inspect-card presentation."""
        if not self.enabled:
            return
        self.detail_mode = "detail" if self.detail_mode == "compact" else "compact"

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
        self.selected_creature_id = id(best) if best is not None else None

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

_INSPECT_LABELS: dict[str, str] = {
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
) -> tuple[InspectPanelLine, ...]:
    """Convert a creature card dict into ordered presentation lines."""
    active_detail_mode = detail_mode or inspect_mode.detail_mode
    lines: list[InspectPanelLine] = [
        InspectPanelLine(kind="mode", text="INSPECT  (I exit)", style="mode"),
        InspectPanelLine(kind="meta", text=_inspect_status_line(inspect_mode), style="meta"),
        InspectPanelLine(kind="divider"),
    ]

    if card is None:
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

    title = f"{card.get('species', 'Creature')} {card.get('lineage', '').strip()}".strip()
    lines.extend(
        [
            InspectPanelLine(kind="title", text=title, style="title"),
            InspectPanelLine(kind="summary", text=build_creature_summary(card), style="summary"),
            InspectPanelLine(kind="divider"),
            InspectPanelLine(kind="section", text="State"),
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


def draw_inspect_overlay(
    target,
    inspect_mode: InspectMode,
    simulation: Simulation,
) -> None:
    """Draw the shared inspect overlay onto a pygame-compatible surface."""
    import pygame

    if not inspect_mode.enabled:
        return

    creature = inspect_mode.get_selected_creature(simulation)
    card = build_creature_card(creature, simulation) if creature is not None else None
    panel_surface = _build_inspect_panel_surface(
        target_width=target.get_width(),
        target_height=target.get_height(),
        inspect_mode=inspect_mode,
        card=card,
    )
    placement = compute_inspect_panel_placement(
        target.get_width(),
        target.get_height(),
        panel_surface.get_width(),
        panel_surface.get_height(),
    )
    target.blit(panel_surface, (placement.x, placement.y))


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
    pace = "Paused" if inspect_mode.pause_mode == "pause" else f"Slow {inspect_mode.slow_hz:.0f} Hz"
    next_pace = "M: slow" if inspect_mode.pause_mode == "pause" else "M: pause"
    next_detail = "D: details" if inspect_mode.detail_mode == "compact" else "D: compact"
    return f"{pace} · {next_pace} · {next_detail}"


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
):
    import pygame

    panel_width = _inspect_panel_width(target_width)
    max_height = max(1, target_height - (_INSPECT_MARGIN * 2))
    line_candidates = [
        build_inspect_panel_lines(card, inspect_mode, detail_mode=inspect_mode.detail_mode)
    ]
    if card is not None and inspect_mode.detail_mode == "detail":
        line_candidates.append(build_inspect_panel_lines(card, inspect_mode, detail_mode="compact"))

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
    import pygame

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
    if line.key == "tags":
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

    wrapped_values = _wrap_text(value_font, line.value, content_width - 14, max_lines=3)
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
