"""Simulation module - main simulation controller."""

from __future__ import annotations

import math
import random
from statistics import median
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .creature import Creature
from .depth import (
    DEPTH_BANDS,
    DEPTH_DEEP,
    DEPTH_MID,
    DEPTH_SURFACE,
    clamp_depth_band,
    depth_band_name,
    depth_band_separation,
    step_depth_band_toward,
)
from .food import FoodManager
from .genome import Genome
from .phenotype import (
    resolve_effective_phenotype,
    strategy_bucket_template,
)
from .zones import ZoneManager
from .observability import (
    TRACKED_TRAITS,
    average_age_ticks as obs_average_age_ticks,
    average_traits as obs_average_traits,
    evolution_distance_mean_abs as obs_evolution_distance_mean_abs,
    lineage_summary_for_population,
    top_trait_directions as obs_top_trait_directions,
    trait_deltas as obs_trait_deltas,
)

if TYPE_CHECKING:
    from ..settings import Settings

AttackRenderEvent = tuple[float, float, float, float, str, float, float]
PredationRenderContext = dict[str, float | int | str]

_DEPTH_SENSING_FACTORS = {
    0: 1.0,
    1: 0.6,
    2: 0.25,
}
_PREDATOR_PREY_FOOD_DEPTH_WEIGHTS = (
    (DEPTH_SURFACE, 0.45),
    (DEPTH_MID, 0.35),
    (DEPTH_DEEP, 0.20),
)
_PREDATION_RECENT_WINDOW_SECONDS = 3.0
_PREDATOR_DEPTH_TRACK_URGENCY = 0.28
_PREY_DEPTH_ESCAPE_URGENCY = 0.30
_PREDATOR_DIAG_ACTIVE_HUNT_FRAMES = 10
_PREDATOR_DIAG_FAILED_PURSUIT_FRAMES = 45
_DEFAULT_PREDATOR_PREY_HISTORY_SIZE = 20
_PREDATOR_PREY_GAME_OVER_HOLD_SECONDS = 10.0
_DEFAULT_PREDATOR_PREY_STEP_ESCALATION_RUNS = 5
_DEFAULT_PREDATOR_PREY_STEP_ESCALATION_PERCENT = 25.0
_DEFAULT_PREDATOR_PREY_TRIAL_COUNT = 2
_DEFAULT_PREDATOR_PREY_MAX_CONSECUTIVE_RETRY_TRIALS = 2
_DEFAULT_PREDATOR_PREY_SURVIVAL_DEADBAND = 50
_DEFAULT_PREDATOR_NEAR_EXTINCTION_FLOOR = 5
_DEFAULT_PREY_NEAR_EXTINCTION_FLOOR = 5
_DEFAULT_PREDATOR_FOOD_EFFICIENCY_MULTIPLIER = 0.85
_DEFAULT_PREDATOR_FORAGE_COST_MULTIPLIER = 0.72
_DEFAULT_PREDATOR_RECENT_ANIMAL_ENERGY_REQUIRED = 0.04
_DEFAULT_PREDATOR_RECENT_ANIMAL_ENERGY_DECAY_PER_TICK = 0.0001
_DEFAULT_PREDATOR_SATIETY_TICKS = 120
_DEFAULT_PREDATOR_INTERFERENCE_STRENGTH = 0.12
_DEFAULT_PREDATOR_TARGET_PREY_PER_PREDATOR = 4.0
_DEFAULT_PREDATOR_LOW_PREY_HUNT_FLOOR = 0.35
_DEFAULT_PREY_TO_PREDATOR_AGGRESSION_THRESHOLD = 0.30
_DEFAULT_PREDATOR_TO_PREY_AGGRESSION_THRESHOLD = 0.20
_DEFAULT_EXTINCTION_GRACE_TICKS = 7200
_PREY_FRAILTY_OLD_AGE_FRACTION = 0.70
_PREDATOR_INTERFERENCE_RADIUS = 150.0
_BOIDS_NEIGHBOR_SENSE_SCALE = 1.05
_BOIDS_FLOCK_LINK_SCALE = 0.62
_BOIDS_PREFERRED_SPACING_SCALE = 3.7
_BOIDS_SEPARATION_RANGE_SCALE = 1.15
_BOIDS_CLOSE_SEPARATION_SCALE = 2.2
_BOIDS_SEPARATION_CLOSE_BOOST = 2.8
_BOIDS_ALIGNMENT_BASE = 0.085
_BOIDS_COHESION_BASE = 0.060
_BOIDS_WANDER_BASE = 0.024
_BOIDS_ENERGY_REGEN_BASE = 0.00115
_BOIDS_TARGET_NEIGHBORS = 6.0
_BOIDS_MIN_NEIGHBORS = 2.0
_BOIDS_SOFT_MAX_NEIGHBORS = 9.0


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.9) - 1)
    return float(ordered[index])


@dataclass(frozen=True)
class AdaptiveDialSpec:
    key: str
    minimum: float
    maximum: float
    step: float
    default: float


@dataclass
class PredatorPreyAdaptiveTuningState:
    baseline_values: dict[str, float] = field(default_factory=dict)
    current_values: dict[str, float] = field(default_factory=dict)
    previous_values: dict[str, float] = field(default_factory=dict)
    trial_candidate_values: dict[str, float] = field(default_factory=dict)
    trial_active: bool = False
    trial_phase: str = "candidate"
    trial_dial: str | None = None
    trial_direction: int = 0
    trial_baseline_average: float = 0.0
    trial_id: int | None = None
    next_trial_id: int = 1
    trial_seeds: list[int] = field(default_factory=list)
    trial_seed_index: int = 0
    trial_candidate_results: list[int] = field(default_factory=list)
    trial_baseline_results: list[int] = field(default_factory=list)
    trial_candidate_pressures: list[int] = field(default_factory=list)
    trial_baseline_pressures: list[int] = field(default_factory=list)
    trial_trigger_reason: str | None = None
    last_decision: str = "none"
    last_decision_basis: str | None = None
    last_decision_trial_id: int | None = None
    last_decision_survival_median_candidate: float | None = None
    last_decision_survival_median_baseline: float | None = None
    last_decision_near_extinction_candidate: float | None = None
    last_decision_near_extinction_baseline: float | None = None
    last_decision_pending_log: bool = False
    post_run_trial_decision: str = "none"
    non_improving_run_streak: int = 0
    consecutive_immediate_retry_trials: int = 0
    retry_cap_waiting_for_ordinary_run: bool = False
    last_trial_launch_blocked_by_retry_cap: bool = False


@dataclass
class PredatorPreyStabilityState:
    current_seed: int | None = None
    sim_ticks: int = 0
    survival_ticks: int = 0
    predator_low_ticks: int = 0
    prey_low_ticks: int = 0
    predator_zero_ticks: int = 0
    prey_zero_ticks: int = 0
    run_history: deque[int] = field(
        default_factory=lambda: deque(maxlen=_DEFAULT_PREDATOR_PREY_HISTORY_SIZE)
    )
    highest_survival_ticks: int = 0
    game_over_active: bool = False
    collapse_cause: str | None = None
    collapse_predator_count: int = 0
    collapse_prey_count: int = 0
    collapse_started_at_seconds: float | None = None
    collapse_dial_values: dict[str, float] = field(default_factory=dict)
    collapse_trial_dial: str | None = None
    collapse_trial_phase: str | None = None
    collapse_trial_seed: int | None = None
    collapse_trial_id: int | None = None
    collapse_trial_trigger_reason: str | None = None
    collapse_trial_delta: float = 0.0
    collapse_trial_value: float | None = None
    collapse_trial_decision: str = "none"
    collapse_rolling_average: float = 0.0
    collapse_beat_average: bool = False
    collapse_was_new_highest: bool = False
    adaptive_tuning: PredatorPreyAdaptiveTuningState = field(
        default_factory=PredatorPreyAdaptiveTuningState
    )


@dataclass(frozen=True)
class PredatorRefugeModifiers:
    """Read-only predator habitat bonuses derived from zone and crowding."""

    zone_type: str | None = None
    zone_label: str = ""
    zone_influence: float = 0.0
    local_predator_count: int = 0
    density_factor: float = 0.0
    refuge_factor: float = 0.0
    hunt_sense_mult: float = 1.0
    contact_mult: float = 1.0
    depth_transition_mult: float = 1.0
    hunting_cost_mult: float = 1.0
    active: bool = False


@dataclass(frozen=True)
class PredatorRarityModifiers:
    pressure: float = 0.0
    hunt_sense_bonus: float = 0.0
    contact_bonus: float = 0.0
    depth_transition_bonus: float = 0.0
    hunting_cost_reduction: float = 0.0
    active: bool = False


@dataclass(frozen=True)
class PredatorHuntModifiers:
    refuge: PredatorRefugeModifiers = field(default_factory=PredatorRefugeModifiers)
    rarity: PredatorRarityModifiers = field(default_factory=PredatorRarityModifiers)
    hunt_sense_mult: float = 1.0
    contact_mult: float = 1.0
    depth_transition_mult: float = 1.0
    hunting_cost_mult: float = 1.0
    active: bool = False


@dataclass(frozen=True)
class PredatorHuntResult:
    """Predator-prey hunt outcome plus any refuge context used that frame."""

    engaged: bool
    killed: bool
    hunt_modifiers: PredatorHuntModifiers = field(default_factory=PredatorHuntModifiers)


@dataclass
class PreyChasePressureState:
    current_chase_pressure_ticks: int = 0
    current_frame_chase_events: int = 0
    last_chased_by_predator_id: int | None = None
    last_chase_pressure_frame: int = -1
    depth_escape_fatigue: float = 0.0


_PREDATOR_PREY_ADAPTIVE_DIALS: tuple[AdaptiveDialSpec, ...] = (
    AdaptiveDialSpec(
        key="predator_contact_kill_distance_scale",
        minimum=0.80,
        maximum=1.20,
        step=0.03,
        default=1.00,
    ),
    AdaptiveDialSpec(
        key="predator_kill_energy_gain_cap",
        minimum=0.35,
        maximum=0.65,
        step=0.02,
        default=0.40,
    ),
    AdaptiveDialSpec(
        key="predator_hunt_sense_multiplier",
        minimum=1.50,
        maximum=2.50,
        step=0.05,
        default=2.00,
    ),
    AdaptiveDialSpec(
        key="prey_flee_sense_multiplier",
        minimum=1.00,
        maximum=1.60,
        step=0.05,
        default=1.20,
    ),
    AdaptiveDialSpec(
        key="predator_prey_scarcity_penalty_multiplier",
        minimum=1.40,
        maximum=2.60,
        step=0.10,
        default=2.00,
    ),
    AdaptiveDialSpec(
        key="food_cycle_amplitude",
        minimum=0.40,
        maximum=1.00,
        step=0.05,
        default=1.00,
    ),
)
_PREDATOR_PREY_ADAPTIVE_DIALS_BY_KEY = {
    spec.key: spec for spec in _PREDATOR_PREY_ADAPTIVE_DIALS
}


class Simulation:
    """
    Main simulation controller for the Primordial screensaver.

    Manages creatures, food, and the simulation step logic.
    The simulation is completely decoupled from rendering - it only
    updates state and exposes it for the renderer to read.

    Event queues (cleared by renderer each frame):
    - death_events: list of dicts with position/genome/species info for dead creatures
    - birth_events: list of newly created offspring creatures
    - cosmic_ray_events: list of (x, y) positions where cosmic rays hit
    - active_attacks: list of (ax, ay, tx, ty, species, hue, saturation) attack visuals
    """

    def __init__(
        self,
        width: int,
        height: int,
        settings: "Settings",
        *,
        bootstrap_world: bool = True,
        seed: int | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.settings = settings
        self._predator_prey_run_logger: Any = None
        self._predator_prey_milestone_logger: Any = None
        self._predator_prey_adaptive_tuning_enabled = bool(
            self._get_mode_param("adaptive_tuning_enabled", True)
        )
        if seed is not None and self.settings.sim_mode == "predator_prey":
            random.seed(seed)

        # Simulation state
        self.creatures: list[Creature] = []
        self.food_manager = FoodManager(
            width, height, max_particles=settings.food_max_particles
        )
        self.generation = 0
        self.paused = False

        # Frame counter (for food cycle)
        self._frame: int = 0

        # Statistics
        self.total_births = 0
        self.total_deaths = 0

        # Lineage counter — each new lineage gets a unique integer ID
        self._next_lineage_id: int = 1
        self._lineage_first_seen_tick: dict[int, int] = {}
        self._run_baseline_traits: dict[str, float] = {}
        self._lineage_observability_cache_frame: int = -1
        self._lineage_observability_cache: dict[int, dict[str, object]] = {}

        # Event queues read by renderer each frame (renderer clears them)
        self.death_events: list[dict] = []
        self.birth_events: list[Creature] = []
        self.cosmic_ray_events: list[tuple[float, float]] = []
        self.active_attacks: list[AttackRenderEvent] = []
        self.predation_kill_count = 0
        self._recent_kill_frames: deque[int] = deque()
        self._recent_cross_band_miss_frames: deque[int] = deque()
        self._predation_victims_this_frame: set[int] = set()
        self._predation_render_context_by_victim: dict[int, PredationRenderContext] = {}
        self._prey_chase_pressure: dict[int, PreyChasePressureState] = {}
        self._predator_depth_fatigue_summary = self._new_predator_depth_fatigue_summary()

        # Rolling average lifespan for old-age deaths (last 20)
        self._old_age_lifespans: deque[float] = deque(maxlen=20)

        # Zone manager
        zone_count = settings.zone_count if bootstrap_world else 0
        self.zone_manager = ZoneManager(
            width, height,
            zone_count,
            settings.zone_strength,
        )

        # Boids mode state
        self._flock_sizes: dict[int, int] = {}
        self._flock_count: int = 0

        # Focused predator reproduction diagnostics. Kept local to the
        # predator-prey path so it can be removed or extended cleanly.
        self._predator_diag_next_life_id = 1
        self._predator_diag_active: dict[int, dict[str, Any]] = {}
        self._predator_diag_completed: list[dict[str, Any]] = []
        self._predator_diag_kill_energy_summary = self._new_predator_kill_energy_summary()
        self._predator_diag_events: dict[str, list[dict[str, Any]]] = {
            "births": [],
            "cosmic_flips_to_predator": [],
            "cosmic_flips_from_predator": [],
        }
        self._predator_prey_state = self._build_predator_prey_stability_state(seed)

        # Initialize population
        if bootstrap_world:
            self._spawn_initial_population()
        self._capture_run_baseline_observability()

    def set_predator_prey_run_logger(self, run_logger: Any) -> None:
        """Attach an optional run logger used by predator-prey stability mode."""
        self._predator_prey_run_logger = run_logger

    def set_predator_prey_milestone_logger(self, milestone_logger: Any) -> None:
        """Attach an optional milestone logger for predator-prey narrative generation."""
        self._predator_prey_milestone_logger = milestone_logger

    def set_predator_prey_adaptive_tuning_enabled(self, enabled: bool) -> None:
        """Enable or disable predator-prey adaptive tuning updates."""
        self._predator_prey_adaptive_tuning_enabled = bool(enabled)

    # ------------------------------------------------------------------
    # Mode parameter helpers
    # ------------------------------------------------------------------

    def _get_mode_param(self, key: str, fallback=None):
        """Return mode-specific param from config, falling back to base settings.

        Resolution order:
        1. settings.mode_params[current_mode][key]  (canonical mode defaults
           merged with [modes.*] user overrides)
        2. settings.<key>  (generic base default)
        3. fallback argument
        """
        mode = self.settings.sim_mode
        mode_params = getattr(self.settings, "mode_params", {})
        if mode in mode_params and key in mode_params[mode]:
            return mode_params[mode][key]
        if hasattr(self.settings, key):
            return getattr(self.settings, key)
        return fallback

    def _get_reproduction_threshold(self, creature: Creature) -> float:
        """Resolve reproduction threshold with predator/prey role overrides."""
        shared_threshold = float(
            self._get_mode_param(
                "energy_to_reproduce",
                self.settings.energy_to_reproduce,
            )
        )
        threshold = shared_threshold
        if self.settings.sim_mode == "predator_prey" and creature.species == "prey":
            threshold = float(
                self._get_mode_param("prey_energy_to_reproduce", shared_threshold)
            )
        elif self.settings.sim_mode == "predator_prey" and creature.species == "predator":
            threshold = float(
                self._get_mode_param("predator_energy_to_reproduce", shared_threshold)
            )
        phenotype = self._get_effective_phenotype(creature)
        return threshold * phenotype.reproduction_threshold_mult

    def _epistasis_enabled(self) -> bool:
        return bool(getattr(self.settings, "epistasis_enabled", False))

    def _get_epistasis_strength(self) -> float:
        return max(0.0, min(1.5, float(getattr(self.settings, "epistasis_strength", 1.0))))

    def _get_effective_phenotype(self, creature: Creature):
        return resolve_effective_phenotype(
            creature.genome,
            species=creature.species,
            epistasis_enabled=self._epistasis_enabled(),
            epistasis_strength=self._get_epistasis_strength(),
        )

    def get_creature_effective_phenotype(self, creature: Creature):
        """Public accessor for a creature's effective phenotype.

        Returns the EffectivePhenotype for *creature*, or a neutral phenotype
        when epistasis is disabled.  Intended for observability UI (inspect
        mode) — simulation internals should continue to use the private
        ``_get_effective_phenotype`` method.
        """
        return self._get_effective_phenotype(creature)

    def _get_creature_speed_scale(self, creature: Creature) -> float:
        return self._get_effective_phenotype(creature).speed_mult

    def _get_creature_flee_speed_scale(self, creature: Creature) -> float:
        phenotype = self._get_effective_phenotype(creature)
        return phenotype.speed_mult * phenotype.flee_agility_mult

    def _get_creature_movement_cost(self, creature: Creature) -> float:
        return creature.get_movement_cost(
            multiplier=self._get_effective_phenotype(creature).movement_cost_mult
        )

    def _get_creature_metabolic_cost(
        self,
        creature: Creature,
        *,
        aggression_cost: float = 0.0,
        longevity_cost: float = 0.0,
    ) -> float:
        phenotype = self._get_effective_phenotype(creature)
        base_cost = aggression_cost + longevity_cost + self._get_sensing_upkeep_cost(creature)
        return base_cost * phenotype.metabolic_cost_mult

    def _get_creature_food_efficiency_multiplier(self, creature: Creature) -> float:
        return self._get_effective_phenotype(creature).food_efficiency_mult

    def _get_creature_predation_contact_multiplier(self, creature: Creature) -> float:
        return self._get_effective_phenotype(creature).predation_contact_mult

    def _get_predator_kill_energy_gain_cap(self) -> float:
        """Resolve the per-kill predator energy gain cap."""
        return float(self._get_mode_param("predator_kill_energy_gain_cap", 0.40))

    def _get_predator_kill_biomass_bonus(self) -> float:
        """Resolve the per-kill biomass bonus added on top of prey energy."""
        return float(self._get_mode_param("predator_kill_biomass_bonus", 0.0))

    def _get_predator_hunt_sense_multiplier(self) -> float:
        """Resolve predator hunt sensing range multiplier."""
        return float(self._get_mode_param("predator_hunt_sense_multiplier", 2.0))

    def _get_predator_hunt_speed_multiplier(self) -> float:
        """Resolve predator hunt steering speed multiplier."""
        return float(self._get_mode_param("predator_hunt_speed_multiplier", 1.0))

    def _get_predator_contact_kill_distance_scale(self) -> float:
        """Resolve predator contact-kill distance scale."""
        return float(self._get_mode_param("predator_contact_kill_distance_scale", 1.0))

    def _predator_refuge_enabled(self) -> bool:
        return bool(self._get_mode_param("predator_refuge_enabled", True))

    def _get_predator_refuge_hunt_sense_bonus(self) -> float:
        return max(
            0.0,
            min(
                0.25,
                float(self._get_mode_param("predator_refuge_hunt_sense_bonus", 0.08)),
            ),
        )

    def _get_predator_refuge_contact_bonus(self) -> float:
        return max(
            0.0,
            min(
                0.25,
                float(self._get_mode_param("predator_refuge_contact_bonus", 0.08)),
            ),
        )

    def _get_predator_refuge_depth_transition_bonus(self) -> float:
        return max(
            0.0,
            min(
                0.30,
                float(
                    self._get_mode_param(
                        "predator_refuge_depth_transition_bonus",
                        0.10,
                    )
                ),
            ),
        )

    def _get_predator_refuge_movement_cost_reduction(self) -> float:
        return max(
            0.0,
            min(
                0.20,
                float(
                    self._get_mode_param(
                        "predator_refuge_movement_cost_reduction",
                        0.05,
                    )
                ),
            ),
        )

    def _get_predator_refuge_density_radius(self) -> float:
        return max(
            0.0,
            float(self._get_mode_param("predator_refuge_density_radius", 140.0)),
        )

    def _get_predator_refuge_density_soft_cap(self) -> int:
        return max(
            0,
            int(self._get_mode_param("predator_refuge_density_soft_cap", 3)),
        )

    def _get_predator_refuge_density_hard_cap(self) -> int:
        soft_cap = self._get_predator_refuge_density_soft_cap()
        return max(
            soft_cap + 1,
            int(self._get_mode_param("predator_refuge_density_hard_cap", 7)),
        )

    def _predator_rarity_advantage_enabled(self) -> bool:
        return bool(self._get_mode_param("predator_rarity_advantage_enabled", True))

    def _get_predator_rarity_pressure(self, *, predator_count: int, prey_count: int) -> float:
        if self.settings.sim_mode != "predator_prey" or prey_count < int(self._get_mode_param("predator_rarity_min_prey", 30)):
            return 0.0
        floor = max(1, int(self._get_mode_param("predator_rarity_floor", 8)))
        full_bonus_at = max(1, min(floor, int(self._get_mode_param("predator_rarity_full_bonus_at", 3))))
        if predator_count > floor:
            return 0.0
        if predator_count <= full_bonus_at:
            rarity = 1.0
        else:
            rarity = (floor - predator_count) / max(1, floor - full_bonus_at)
        prey_per_predator = prey_count / max(1, predator_count)
        target = max(0.1, float(self._get_mode_param("predator_rarity_target_prey_per_predator", 8.0)))
        prey_scale = max(0.0, min(1.0, prey_per_predator / target))
        return max(0.0, min(1.0, rarity * prey_scale))

    def _get_predator_rarity_modifiers(self, predator: Creature) -> PredatorRarityModifiers:
        if self.settings.sim_mode != "predator_prey" or predator.species != "predator" or not self._predator_rarity_advantage_enabled():
            return PredatorRarityModifiers()
        pred_count, prey_count = self.get_species_counts()
        pressure = self._get_predator_rarity_pressure(predator_count=pred_count, prey_count=prey_count)
        if pressure <= 0.0:
            return PredatorRarityModifiers()
        return PredatorRarityModifiers(
            pressure=pressure,
            hunt_sense_bonus=max(0.0, min(0.20, float(self._get_mode_param("predator_rarity_hunt_sense_bonus", 0.08)))) * pressure,
            contact_bonus=max(0.0, min(0.20, float(self._get_mode_param("predator_rarity_contact_bonus", 0.06)))) * pressure,
            depth_transition_bonus=max(0.0, min(0.20, float(self._get_mode_param("predator_rarity_depth_transition_bonus", 0.08)))) * pressure,
            hunting_cost_reduction=max(0.0, min(0.20, float(self._get_mode_param("predator_rarity_movement_cost_reduction", 0.05)))) * pressure,
            active=True,
        )

    def _get_predator_hunt_modifiers(
        self, predator: Creature, creature_bucket: dict[tuple[int, int], list[Creature]] | None = None
    ) -> PredatorHuntModifiers:
        refuge = self._get_predator_refuge_modifiers(predator, creature_bucket)
        rarity = self._get_predator_rarity_modifiers(predator)
        def _blend(a: float, b: float) -> float:
            high = max(a, b)
            low = min(a, b)
            return high + 0.35 * low
        hunt_bonus = _blend(refuge.hunt_sense_mult - 1.0, rarity.hunt_sense_bonus)
        contact_bonus = _blend(refuge.contact_mult - 1.0, rarity.contact_bonus)
        depth_bonus = _blend(refuge.depth_transition_mult - 1.0, rarity.depth_transition_bonus)
        cost_reduction = _blend(1.0 - refuge.hunting_cost_mult, rarity.hunting_cost_reduction)
        hunt_sense_mult = min(1.15, 1.0 + max(0.0, hunt_bonus))
        contact_mult = min(1.14, 1.0 + max(0.0, contact_bonus))
        depth_transition_mult = min(1.18, 1.0 + max(0.0, depth_bonus))
        hunting_cost_mult = max(0.88, 1.0 - max(0.0, cost_reduction))
        return PredatorHuntModifiers(
            refuge=refuge,
            rarity=rarity,
            hunt_sense_mult=hunt_sense_mult,
            contact_mult=contact_mult,
            depth_transition_mult=depth_transition_mult,
            hunting_cost_mult=hunting_cost_mult,
            active=refuge.active or rarity.active,
        )

    def _get_predator_refuge_modifiers(
        self,
        predator: Creature,
        creature_bucket: dict[tuple[int, int], list[Creature]] | None = None,
    ) -> PredatorRefugeModifiers:
        """Return conservative habitat modifiers for predators already in refuge."""
        zone_context = self.zone_manager.get_zone_context_at(predator.x, predator.y)
        zone_label = zone_context.label or ""
        if self.settings.sim_mode != "predator_prey" or predator.species != "predator":
            return PredatorRefugeModifiers(
                zone_type=zone_context.zone_type,
                zone_label=zone_label,
                zone_influence=zone_context.influence,
            )
        if not self._predator_refuge_enabled():
            return PredatorRefugeModifiers(
                zone_type=zone_context.zone_type,
                zone_label=zone_label,
                zone_influence=zone_context.influence,
            )
        if zone_context.zone_type != "hunting_ground" or zone_context.influence <= 0.0:
            return PredatorRefugeModifiers(
                zone_type=zone_context.zone_type,
                zone_label=zone_label,
                zone_influence=zone_context.influence,
            )

        if creature_bucket is None:
            creature_bucket = self._build_creature_bucket()

        density_radius = self._get_predator_refuge_density_radius()
        nearby_predators = 0
        if density_radius > 0.0:
            for other in self._nearby_creatures(
                predator.x,
                predator.y,
                density_radius,
                creature_bucket,
            ):
                if other is predator or other.species != "predator" or other.energy <= 0.0:
                    continue
                if (
                    predator.distance_to(other.x, other.y, self.width, self.height)
                    <= density_radius
                ):
                    nearby_predators += 1

        soft_cap = self._get_predator_refuge_density_soft_cap()
        hard_cap = self._get_predator_refuge_density_hard_cap()
        if nearby_predators <= soft_cap:
            density_factor = 1.0
        elif nearby_predators >= hard_cap:
            density_factor = 0.0
        else:
            density_factor = 1.0 - (
                (nearby_predators - soft_cap) / max(1, hard_cap - soft_cap)
            )

        refuge_factor = max(
            0.0,
            min(1.0, zone_context.influence * density_factor),
        )
        if refuge_factor <= 0.0:
            return PredatorRefugeModifiers(
                zone_type=zone_context.zone_type,
                zone_label=zone_label,
                zone_influence=zone_context.influence,
                local_predator_count=nearby_predators,
                density_factor=density_factor,
            )

        hunt_sense_mult = min(
            1.12,
            1.0 + (self._get_predator_refuge_hunt_sense_bonus() * refuge_factor),
        )
        contact_mult = min(
            1.12,
            1.0 + (self._get_predator_refuge_contact_bonus() * refuge_factor),
        )
        depth_transition_mult = min(
            1.15,
            1.0
            + (self._get_predator_refuge_depth_transition_bonus() * refuge_factor),
        )
        hunting_cost_mult = max(
            0.90,
            1.0
            - (
                self._get_predator_refuge_movement_cost_reduction() * refuge_factor
            ),
        )
        return PredatorRefugeModifiers(
            zone_type=zone_context.zone_type,
            zone_label=zone_label,
            zone_influence=zone_context.influence,
            local_predator_count=nearby_predators,
            density_factor=density_factor,
            refuge_factor=refuge_factor,
            hunt_sense_mult=hunt_sense_mult,
            contact_mult=contact_mult,
            depth_transition_mult=depth_transition_mult,
            hunting_cost_mult=hunting_cost_mult,
            active=True,
        )

    def _get_prey_flee_sense_multiplier(self) -> float:
        """Resolve prey flee sensing range multiplier."""
        return float(self._get_mode_param("prey_flee_sense_multiplier", 1.2))

    def _get_prey_flee_speed_multiplier(self) -> float:
        """Resolve prey flee movement-speed multiplier."""
        return float(self._get_mode_param("prey_flee_speed_multiplier", 1.30))

    def _prey_flee_age_slowdown_enabled(self) -> bool:
        return bool(self._get_mode_param("prey_flee_age_slowdown_enabled", True))

    def _prey_flee_low_energy_slowdown_enabled(self) -> bool:
        return bool(
            self._get_mode_param("prey_flee_low_energy_slowdown_enabled", True)
        )

    def _get_prey_flee_low_energy_threshold(self) -> float:
        return max(
            0.01,
            min(
                1.0,
                float(self._get_mode_param("prey_flee_low_energy_threshold", 0.35)),
            ),
        )

    def _get_prey_flee_low_energy_min_mult(self) -> float:
        return max(
            0.4,
            min(
                1.0,
                float(self._get_mode_param("prey_flee_low_energy_min_mult", 0.75)),
            ),
        )

    def _get_prey_flee_condition_multiplier(self, prey: Creature) -> float:
        """Return direct flee-speed frailty from age and current energy."""
        age_mult = 1.0
        if self._prey_flee_age_slowdown_enabled():
            age_mult = prey.get_age_speed_mult()

        energy_mult = 1.0
        threshold = self._get_prey_flee_low_energy_threshold()
        if (
            self._prey_flee_low_energy_slowdown_enabled()
            and prey.energy < threshold
        ):
            t = max(0.0, min(1.0, prey.energy / threshold))
            min_mult = self._get_prey_flee_low_energy_min_mult()
            energy_mult = min_mult + ((1.0 - min_mult) * t)

        return age_mult * energy_mult

    def _get_predator_prey_scarcity_penalty_multiplier(self) -> float:
        """Resolve predator prey-scarcity energy penalty multiplier."""
        return float(
            self._get_mode_param("predator_prey_scarcity_penalty_multiplier", 2.0)
        )

    def _get_food_cycle_amplitude(self) -> float:
        """Resolve food-cycle amplitude, allowing predator-prey-only tuning."""
        return float(self._get_mode_param("food_cycle_amplitude", 1.0))

    def _get_predator_near_contact_diagnostic_scale(self) -> float:
        return max(
            1.0,
            min(
                5.0,
                float(
                    self._get_mode_param(
                        "predator_near_contact_diagnostic_scale",
                        1.25,
                    )
                ),
            ),
        )

    def _predator_target_memory_enabled(self) -> bool:
        return bool(self._get_mode_param("predator_target_memory_enabled", True))

    def _get_predator_target_memory_ticks(self) -> int:
        return max(1, int(self._get_mode_param("predator_target_memory_ticks", 45)))

    def _get_predator_target_memory_radius_mult(self) -> float:
        return max(0.5, min(3.0, float(self._get_mode_param("predator_target_memory_radius_mult", 1.35))))

    def _get_predator_target_switch_score_ratio(self) -> float:
        return max(0.1, min(1.0, float(self._get_mode_param("predator_target_switch_score_ratio", 0.70))))

    def _get_predator_memory_steering_mult(self) -> float:
        return max(0.1, min(1.0, float(self._get_mode_param("predator_memory_steering_mult", 0.85))))

    def _get_predator_sustained_chase_min_frames(self) -> int:
        return max(
            1,
            int(
                self._get_mode_param(
                    "predator_sustained_chase_min_frames",
                    20,
                )
            ),
        )

    def _prey_depth_fatigue_enabled(self) -> bool:
        return bool(self._get_mode_param("prey_depth_fatigue_enabled", True))

    def _get_prey_depth_fatigue_min_chase_ticks(self) -> int:
        return max(1, int(self._get_mode_param("prey_depth_fatigue_min_chase_ticks", 90)))

    def _get_prey_depth_fatigue_energy_threshold(self) -> float:
        return max(
            0.01,
            min(1.0, float(self._get_mode_param("prey_depth_fatigue_energy_threshold", 0.35))),
        )

    def _get_prey_depth_fatigue_escape_urgency_mult(self) -> float:
        return max(
            0.1,
            min(1.0, float(self._get_mode_param("prey_depth_fatigue_escape_urgency_mult", 0.75))),
        )

    def _get_prey_depth_fatigue_decay_ticks(self) -> int:
        return max(1, int(self._get_mode_param("prey_depth_fatigue_decay_ticks", 180)))

    def _get_prey_depth_fatigue_max(self) -> float:
        return max(0.0, min(1.0, float(self._get_mode_param("prey_depth_fatigue_max", 1.0))))

    def _predator_committed_depth_tracking_enabled(self) -> bool:
        return bool(self._get_mode_param("predator_committed_depth_tracking_enabled", True))

    def _get_predator_committed_depth_tracking_min_chase_ticks(self) -> int:
        return max(
            1,
            int(self._get_mode_param("predator_committed_depth_tracking_min_chase_ticks", 90)),
        )

    def _get_predator_committed_depth_tracking_near_contact_scale(self) -> float:
        return max(
            1.0,
            min(
                4.0,
                float(
                    self._get_mode_param(
                        "predator_committed_depth_tracking_near_contact_scale",
                        1.75,
                    )
                ),
            ),
        )

    def _get_predator_committed_depth_tracking_cooldown_ticks(self) -> int:
        return max(
            0,
            int(self._get_mode_param("predator_committed_depth_tracking_cooldown_ticks", 45)),
        )

    def _get_predator_food_efficiency_multiplier(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_food_efficiency_multiplier",
                        _DEFAULT_PREDATOR_FOOD_EFFICIENCY_MULTIPLIER,
                    )
                ),
            ),
        )

    def _get_predator_forage_cost_multiplier(self) -> float:
        return max(
            0.1,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_forage_cost_multiplier",
                        _DEFAULT_PREDATOR_FORAGE_COST_MULTIPLIER,
                    )
                ),
            ),
        )

    def _get_predator_recent_animal_energy_required(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_recent_animal_energy_required",
                        _DEFAULT_PREDATOR_RECENT_ANIMAL_ENERGY_REQUIRED,
                    )
                ),
            ),
        )

    def _get_predator_recent_animal_energy_decay_per_tick(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_recent_animal_energy_decay_per_tick",
                        _DEFAULT_PREDATOR_RECENT_ANIMAL_ENERGY_DECAY_PER_TICK,
                    )
                ),
            ),
        )

    def _get_predator_satiety_ticks(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "predator_satiety_ticks",
                    _DEFAULT_PREDATOR_SATIETY_TICKS,
                )
            ),
        )

    def _get_predator_interference_strength(self) -> float:
        return max(
            0.0,
            float(
                self._get_mode_param(
                    "predator_interference_strength",
                    _DEFAULT_PREDATOR_INTERFERENCE_STRENGTH,
                )
            ),
        )

    def _get_predator_target_prey_per_predator(self) -> float:
        return max(
            0.1,
            float(
                self._get_mode_param(
                    "predator_target_prey_per_predator",
                    _DEFAULT_PREDATOR_TARGET_PREY_PER_PREDATOR,
                )
            ),
        )

    def _get_predator_low_prey_hunt_floor(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_low_prey_hunt_floor",
                        _DEFAULT_PREDATOR_LOW_PREY_HUNT_FLOOR,
                    )
                ),
            ),
        )

    def _get_prey_to_predator_aggression_threshold(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "prey_to_predator_aggression_threshold",
                        _DEFAULT_PREY_TO_PREDATOR_AGGRESSION_THRESHOLD,
                    )
                ),
            ),
        )

    def _get_predator_to_prey_aggression_threshold(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(
                    self._get_mode_param(
                        "predator_to_prey_aggression_threshold",
                        _DEFAULT_PREDATOR_TO_PREY_AGGRESSION_THRESHOLD,
                    )
                ),
            ),
        )

    def _get_predator_prey_extinction_grace_ticks(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "extinction_grace_ticks",
                    _DEFAULT_EXTINCTION_GRACE_TICKS,
                )
            ),
        )

    def _get_predator_prey_history_size(self) -> int:
        return max(
            1,
            int(
                self._get_mode_param(
                    "stability_history_size",
                    _DEFAULT_PREDATOR_PREY_HISTORY_SIZE,
                )
            ),
        )

    def _get_predator_prey_step_escalation_runs(self) -> int:
        return max(
            1,
            int(
                self._get_mode_param(
                    "adaptive_step_escalation_runs",
                    _DEFAULT_PREDATOR_PREY_STEP_ESCALATION_RUNS,
                )
            ),
        )

    def _get_predator_prey_step_escalation_percent(self) -> float:
        return max(
            0.0,
            float(
                self._get_mode_param(
                    "adaptive_step_escalation_percent",
                    _DEFAULT_PREDATOR_PREY_STEP_ESCALATION_PERCENT,
                )
            ),
        )

    def _get_predator_prey_trial_count(self) -> int:
        return max(
            1,
            int(
                self._get_mode_param(
                    "adaptive_trial_seed_count",
                    _DEFAULT_PREDATOR_PREY_TRIAL_COUNT,
                )
            ),
        )

    def _get_predator_prey_max_consecutive_retry_trials(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "adaptive_max_consecutive_retry_trials",
                    _DEFAULT_PREDATOR_PREY_MAX_CONSECUTIVE_RETRY_TRIALS,
                )
            ),
        )

    def _get_predator_prey_survival_deadband(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "adaptive_survival_deadband",
                    _DEFAULT_PREDATOR_PREY_SURVIVAL_DEADBAND,
                )
            ),
        )

    def _get_predator_near_extinction_floor(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "adaptive_near_extinction_predator_floor",
                    _DEFAULT_PREDATOR_NEAR_EXTINCTION_FLOOR,
                )
            ),
        )

    def _get_prey_near_extinction_floor(self) -> int:
        return max(
            0,
            int(
                self._get_mode_param(
                    "adaptive_near_extinction_prey_floor",
                    _DEFAULT_PREY_NEAR_EXTINCTION_FLOOR,
                )
            ),
        )

    def _build_predator_prey_run_history(
        self,
        history: list[int] | tuple[int, ...] = (),
    ) -> deque[int]:
        return deque(
            (int(item) for item in history),
            maxlen=self._get_predator_prey_history_size(),
        )

    def _build_predator_prey_stability_state(
        self,
        seed: int | None,
    ) -> PredatorPreyStabilityState:
        current_values = {
            spec.key: self._clamp_predator_prey_dial_value(
                spec,
                float(
                    self.settings.mode_params.get("predator_prey", {}).get(
                        spec.key,
                        spec.default,
                    )
                ),
            )
            for spec in _PREDATOR_PREY_ADAPTIVE_DIALS
        }
        if self._predator_prey_adaptive_tuning_enabled:
            self._apply_predator_prey_tuning_values(current_values)
        return PredatorPreyStabilityState(
            current_seed=seed,
            run_history=self._build_predator_prey_run_history(),
            adaptive_tuning=PredatorPreyAdaptiveTuningState(
                baseline_values=dict(current_values),
                current_values=dict(current_values),
                previous_values=dict(current_values),
            ),
        )

    def _clamp_predator_prey_dial_value(
        self,
        spec: AdaptiveDialSpec,
        value: float,
    ) -> float:
        clamped = max(spec.minimum, min(spec.maximum, float(value)))
        return round(clamped, 4)

    def _apply_predator_prey_tuning_values(self, values: dict[str, float]) -> None:
        mode_params = self.settings.mode_params.setdefault("predator_prey", {})
        for spec in _PREDATOR_PREY_ADAPTIVE_DIALS:
            if spec.key not in values:
                continue
            old_value = mode_params.get(spec.key, spec.default)
            mode_params[spec.key] = self._clamp_predator_prey_dial_value(
                spec,
                values[spec.key],
            )
            new_value = mode_params[spec.key]
            if self._predator_prey_milestone_logger is not None and abs(new_value - old_value) > 0.001:
                self._predator_prey_milestone_logger.log_adaptive_tuning_change(
                    self, spec.key, old_value, new_value,
                )

    def _serialize_predator_prey_dial_values(
        self,
        values: dict[str, Any],
    ) -> dict[str, float]:
        serialized: dict[str, float] = {}
        for spec in _PREDATOR_PREY_ADAPTIVE_DIALS:
            raw = values.get(spec.key, spec.default)
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                numeric = spec.default
            serialized[spec.key] = self._clamp_predator_prey_dial_value(spec, numeric)
        return serialized

    def _default_predator_prey_dial_values(self) -> dict[str, float]:
        return {
            spec.key: self._clamp_predator_prey_dial_value(spec, spec.default)
            for spec in _PREDATOR_PREY_ADAPTIVE_DIALS
        }

    def _resolve_predator_prey_species(
        self,
        current_species: str,
        aggression: float,
    ) -> str:
        if current_species == "predator":
            if aggression < self._get_predator_to_prey_aggression_threshold():
                return "prey"
            return "predator"
        if current_species == "prey":
            if aggression >= self._get_prey_to_predator_aggression_threshold():
                return "predator"
            return "prey"
        return "predator" if aggression >= 0.5 else "prey"

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _alloc_lineage_id(self) -> int:
        """Allocate and return a new unique lineage ID."""
        lid = self._next_lineage_id
        self._next_lineage_id += 1
        self._lineage_first_seen_tick.setdefault(lid, self._frame)
        return lid

    def _spawn_initial_population(self) -> None:
        """Dispatch to mode-specific population initialiser."""
        mode = self.settings.sim_mode
        if mode == "predator_prey":
            self._spawn_initial_population_predator_prey()
        elif mode == "boids":
            self._spawn_initial_population_boids()
        elif mode == "drift":
            self._spawn_initial_population_drift()
        else:
            self._spawn_initial_population_energy()

    def _spawn_initial_population_energy(self) -> None:
        """Spawn the initial population for energy mode."""
        initial_pop = min(
            self.settings.initial_population,
            self._get_population_spawn_limit(),
        )
        for _ in range(initial_pop):
            lid = self._alloc_lineage_id()
            creature = Creature.spawn(
                self.width, self.height, lineage_id=lid, energy=0.7
            )
            self.creatures.append(creature)
        self.food_manager.spawn_batch(200)

    def _spawn_initial_population_predator_prey(self) -> None:
        """Spawn mixed predator/prey population."""
        predator_fraction = float(self._get_mode_param("predator_fraction", 0.25))
        predator_fraction = max(0.0, min(1.0, predator_fraction))
        initial_pop = max(
            0,
            int(self._get_mode_param("initial_population", self.settings.initial_population)),
        )
        initial_pop = min(initial_pop, self._get_population_spawn_limit())
        n_predators = int(initial_pop * predator_fraction)

        for i in range(initial_pop):
            lid = self._alloc_lineage_id()
            is_predator = i < n_predators

            if is_predator:
                # Warm hues (magentas 0.48–0.70, purples 0.70–0.88), high aggression
                genome = Genome(
                    speed=random.uniform(0.5, 0.9),
                    size=random.uniform(0.4, 0.8),
                    sense_radius=random.uniform(0.4, 0.8),
                    aggression=random.uniform(0.62, 0.95),
                    hue=random.uniform(0.48, 0.88),
                    saturation=random.uniform(0.7, 1.0),
                    efficiency=random.random(),
                    complexity=random.random(),
                    symmetry=random.random(),
                    stroke_scale=random.random(),
                    appendages=random.random(),
                    rotation_speed=random.random(),
                    motion_style=random.random(),
                    longevity=random.random(),
                    conformity=random.random(),
                    depth_preference=random.uniform(0.4, 1.0),
                )
                creature = Creature.spawn(
                    self.width, self.height, genome=genome,
                    lineage_id=lid, energy=0.7, species="predator",
                )
            else:
                # Cool hues (cyans 0.0–0.17, turquoise–blue 0.17–0.45), low aggression
                genome = Genome(
                    speed=random.uniform(0.4, 0.8),
                    size=random.uniform(0.2, 0.6),
                    sense_radius=random.uniform(0.5, 0.9),
                    aggression=random.uniform(0.0, 0.38),
                    hue=random.uniform(0.05, 0.45),
                    saturation=random.uniform(0.7, 1.0),
                    efficiency=random.uniform(0.4, 0.9),
                    complexity=random.random(),
                    symmetry=random.random(),
                    stroke_scale=random.random(),
                    appendages=random.random(),
                    rotation_speed=random.random(),
                    motion_style=random.random(),
                    longevity=random.random(),
                    conformity=random.random(),
                    depth_preference=random.uniform(0.0, 0.75),
                )
                creature = Creature.spawn(
                    self.width, self.height, genome=genome,
                    lineage_id=lid, energy=0.7, species="prey",
                )

            self.creatures.append(creature)
            if creature.species == "predator":
                self._register_predator_life(creature, origin="initial")

        # Seed food for prey across the bounded depth bands.
        for _ in range(200):
            self.food_manager.spawn(
                depth_band=self._choose_predator_prey_food_depth_band()
            )

    def _spawn_initial_population_boids(self) -> None:
        """Spawn boids population with mid-range conformity/efficiency."""
        initial_pop = self._get_mode_param("initial_population", self.settings.initial_population)
        initial_pop = min(initial_pop, self._get_population_spawn_limit())
        for _ in range(initial_pop):
            lid = self._alloc_lineage_id()
            genome = Genome(
                speed=random.uniform(0.25, 0.75),
                size=random.uniform(0.18, 0.55),
                sense_radius=random.uniform(0.18, 0.65),
                aggression=random.uniform(0.25, 0.85),
                hue=random.random(),
                saturation=random.uniform(0.6, 1.0),
                efficiency=random.uniform(0.30, 0.85),
                complexity=random.random(),
                symmetry=random.random(),
                stroke_scale=random.random(),
                appendages=random.random(),
                rotation_speed=random.random(),
                motion_style=random.random(),
                longevity=random.random(),
                conformity=random.uniform(0.20, 0.80),
                depth_preference=random.random(),
            )
            creature = Creature.spawn(
                self.width, self.height, genome=genome,
                lineage_id=lid, energy=0.7,
            )
            self.creatures.append(creature)

        self._flock_sizes = {}
        self._flock_count = 0

    def _spawn_initial_population_drift(self) -> None:
        """Spawn drift population — dreamlike, small."""
        initial_pop = self._get_mode_param("initial_population", 60)
        initial_pop = min(initial_pop, self._get_population_spawn_limit())
        for _ in range(initial_pop):
            lid = self._alloc_lineage_id()
            creature = Creature.spawn(
                self.width, self.height, lineage_id=lid, energy=0.7,
            )
            self.creatures.append(creature)

    def reset(
        self,
        *,
        preserve_predator_prey_state: bool = False,
        new_seed: int | None = None,
    ) -> None:
        """Reset the simulation to initial state."""
        if self.settings.sim_mode == "predator_prey":
            self._predator_prey_adaptive_tuning_enabled = bool(
                self._get_mode_param("adaptive_tuning_enabled", True)
            )
            if preserve_predator_prey_state:
                self._prepare_predator_prey_run_restart(new_seed)
            else:
                seed = new_seed if new_seed is not None else self._generate_predator_prey_seed()
                random.seed(seed)
                self._predator_prey_state = self._build_predator_prey_stability_state(seed)

        self.creatures.clear()
        self.food_manager = FoodManager(
            self.width, self.height,
            max_particles=self.settings.food_max_particles,
        )
        self.generation = 0
        self.total_births = 0
        self.total_deaths = 0
        self._frame = 0
        self._next_lineage_id = 1
        self._lineage_first_seen_tick = {}
        self._run_baseline_traits = {}
        self.death_events.clear()
        self.birth_events.clear()
        self.cosmic_ray_events.clear()
        self.active_attacks.clear()
        self.predation_kill_count = 0
        self._recent_kill_frames.clear()
        self._recent_cross_band_miss_frames.clear()
        self._predation_victims_this_frame.clear()
        self._predation_render_context_by_victim.clear()
        self._prey_chase_pressure.clear()
        self._predator_depth_fatigue_summary = self._new_predator_depth_fatigue_summary()
        self._old_age_lifespans.clear()
        self._flock_sizes = {}
        self._flock_count = 0
        self._reset_predator_diagnostics()
        self.zone_manager = ZoneManager(
            self.width, self.height,
            self.settings.zone_count,
            self.settings.zone_strength,
        )
        self._spawn_initial_population()
        self._capture_run_baseline_observability()

    def _generate_predator_prey_seed(self) -> int:
        return random.SystemRandom().randrange(1, 2_147_483_647)

    def _prepare_predator_prey_run_restart(self, new_seed: int | None = None) -> None:
        state = self._predator_prey_state
        seed = self._resolve_predator_prey_restart_seed(new_seed)
        state.current_seed = seed
        state.sim_ticks = 0
        state.survival_ticks = 0
        state.predator_low_ticks = 0
        state.prey_low_ticks = 0
        state.predator_zero_ticks = 0
        state.prey_zero_ticks = 0
        state.game_over_active = False
        state.collapse_cause = None
        state.collapse_predator_count = 0
        state.collapse_prey_count = 0
        state.collapse_started_at_seconds = None
        state.collapse_dial_values = {}
        state.collapse_trial_dial = None
        state.collapse_trial_phase = None
        state.collapse_trial_seed = None
        state.collapse_trial_id = None
        state.collapse_trial_trigger_reason = None
        state.collapse_trial_delta = 0.0
        state.collapse_trial_value = None
        state.collapse_trial_decision = "none"
        state.collapse_rolling_average = 0.0
        state.collapse_beat_average = False
        state.collapse_was_new_highest = False
        self._apply_predator_prey_tuning_values(state.adaptive_tuning.current_values)
        random.seed(seed)

    def _resolve_predator_prey_restart_seed(self, new_seed: int | None = None) -> int:
        if new_seed is not None:
            return new_seed

        tuning = self._predator_prey_state.adaptive_tuning
        if tuning.trial_active and tuning.trial_seeds:
            index = min(max(tuning.trial_seed_index, 0), len(tuning.trial_seeds) - 1)
            return int(tuning.trial_seeds[index])
        return self._generate_predator_prey_seed()

    def resize(self, width: int, height: int) -> None:
        """Resize simulation world bounds and rebuild dependent spatial data."""
        self.width = width
        self.height = height
        self.food_manager.resize_world(width, height)

        for creature in self.creatures:
            creature.x = creature.x % width
            creature.y = creature.y % height

        # Zones are world-space geometry; regenerate after resize.
        self.zone_manager = ZoneManager(
            width, height, self.settings.zone_count, self.settings.zone_strength
        )

    def drain_active_attacks(self) -> list[AttackRenderEvent]:
        """Return and clear current attack visuals for loop-level preservation."""
        attacks = list(self.active_attacks)
        self.active_attacks.clear()
        return attacks

    def restore_active_attacks(self, attacks: list[AttackRenderEvent]) -> None:
        """Restore preserved attack visuals immediately before rendering."""
        if not attacks:
            return
        self.active_attacks.extend(attacks)

    def rebuild_derived_state(self) -> None:
        """Rebuild transient and cached state from authoritative world data."""
        self.death_events.clear()
        self.birth_events.clear()
        self.cosmic_ray_events.clear()
        self.active_attacks.clear()
        self._recent_kill_frames.clear()
        self._recent_cross_band_miss_frames.clear()
        self._predation_victims_this_frame.clear()
        self._reset_predator_diagnostics()
        self._prey_chase_pressure.clear()
        self._predator_depth_fatigue_summary = self._new_predator_depth_fatigue_summary()

        self._rebuild_lineage_first_seen_ticks()

        for creature in self.creatures:
            creature.trail = []
            creature.glyph_surface = None
            creature.glyph_surface_cache_key = None
            creature.rotation_angle = 0.0
            creature._glyph_phase = creature.genome.hue * 6.28
            creature.clamp_depth_band()
            creature.recent_animal_energy = max(
                0.0,
                min(1.0, creature.recent_animal_energy),
            )
            creature.satiety_ticks_remaining = max(0, creature.satiety_ticks_remaining)
            if self.settings.sim_mode != "boids":
                creature.flock_id = -1
            if self.settings.sim_mode == "predator_prey":
                creature.species = self._resolve_predator_prey_species(
                    creature.species,
                    creature.genome.aggression,
                )
            if self.settings.sim_mode == "predator_prey" and creature.species == "predator":
                self._register_predator_life(creature, origin="restored")

        if self.settings.sim_mode == "boids":
            creature_bucket = self._build_creature_bucket()
            self._build_boid_neighbor_cache_and_assignments(creature_bucket)
        else:
            self._flock_sizes = {}
            self._flock_count = 0

    # ------------------------------------------------------------------
    # Main step dispatcher
    # ------------------------------------------------------------------

    def step(self) -> None:
        """Advance the simulation by one frame, dispatching by mode."""
        if self.paused or self.predator_prey_game_over_active:
            return

        mode = self.settings.sim_mode
        if mode == "predator_prey":
            self._step_predator_prey()
        elif mode == "boids":
            self._step_boids()
        elif mode == "drift":
            self._step_drift()
        else:
            self._step_energy()

    # ------------------------------------------------------------------
    # Energy mode (original)
    # ------------------------------------------------------------------

    def _step_energy(self) -> None:
        """
        Energy mode step — original simulation logic.

        Order:
        1. Spawn food (sinusoidal cycle)
        2. Clear per-frame attack list
        3. For each creature: hunt/seek food, move, age costs, zone modifier
        4. Cosmic ray mutations
        5. Handle reproduction
        6. Remove dead creatures
        """
        self._frame += 1

        self._spawn_food()
        self.active_attacks.clear()

        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []
        dead_causes: dict[int, str] = {}

        overcrowding_penalty = self._get_overcrowding_penalty()
        creature_bucket = self._build_creature_bucket()

        for creature in self.creatures:
            if self._queue_preexisting_death(creature, dead_creatures, dead_causes):
                continue
            aggression = creature.genome.aggression
            if aggression > 0.6:
                hunted = self._creature_hunt(creature, creature_bucket)
                if not hunted:
                    food_sense = creature.get_effective_sense_radius() * 0.85
                    self._creature_seek_food(creature, sense_override=food_sense)
            elif aggression < 0.4:
                self._creature_seek_food(creature)
            else:
                self._creature_seek_food(creature)
                self._creature_opportunist_attack(creature, creature_bucket)

            creature.update_position(1.0, self.width, self.height)

            energy_cost = self._get_creature_movement_cost(creature)
            energy_cost *= 1.0 + overcrowding_penalty
            energy_cost += self._get_creature_metabolic_cost(
                creature,
                aggression_cost=aggression * 0.0012,
                longevity_cost=creature.genome.longevity * 0.0004,
            )
            zone_mult = self.zone_manager.get_energy_modifier(creature)
            energy_cost *= zone_mult

            creature.energy -= energy_cost
            creature.energy = max(0.0, creature.energy)

            if creature.energy <= 0:
                self._queue_creature_death(
                    creature,
                    dead_creatures,
                    dead_causes,
                    self._resolve_death_cause(creature),
                )
                continue

            if random.random() < self.settings.cosmic_ray_rate:
                self._apply_cosmic_ray(creature)

            if creature.energy >= self._get_reproduction_threshold(creature):
                offspring = self._reproduce(
                    creature,
                    queued_births=len(new_creatures),
                )
                if offspring:
                    new_creatures.append(offspring)

            if creature.energy <= 0:
                self._queue_creature_death(
                    creature,
                    dead_creatures,
                    dead_causes,
                    self._resolve_death_cause(creature),
                )
            elif creature.age >= creature.get_max_lifespan():
                self._queue_creature_death(creature, dead_creatures, dead_causes, "age")

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._sweep_frame_deaths(dead_creatures, dead_causes)
        self._process_deaths(dead_creatures, dead_causes)

    # ------------------------------------------------------------------
    # Predator-Prey mode
    # ------------------------------------------------------------------

    def _step_predator_prey(self) -> None:
        """Lotka-Volterra predator/prey ecosystem step."""
        self._frame += 1
        self._predator_prey_state.sim_ticks += 1
        self._predator_prey_state.survival_ticks += 1
        self._spawn_food()
        self.active_attacks.clear()
        self._predation_victims_this_frame.clear()
        self._predation_render_context_by_victim.clear()

        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []
        dead_causes: dict[int, str] = {}

        overcrowding_penalty = self._get_overcrowding_penalty()
        creature_bucket = self._build_creature_bucket()

        # Ecosystem balance: count species
        pred_count = sum(1 for c in self.creatures if c.species == "predator")
        prey_count = sum(1 for c in self.creatures if c.species == "prey")
        total = max(1, len(self.creatures))
        pred_fraction = pred_count / total
        prey_fraction = prey_count / total
        hunt_balance_factor = self._get_predator_hunt_balance_factor(
            pred_count=pred_count,
            prey_count=prey_count,
        )
        self._check_ecosystem_balance(pred_count=pred_count, prey_count=prey_count)

        # If > 60% predators: increase their reproduction threshold
        pred_repro_penalty = 0.20 if pred_fraction > 0.60 else 0.0
        # If < 15% prey: predators pay an extra scarcity multiplier
        prey_scarce = prey_fraction < 0.15 and pred_count > 0

        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate

        for creature in self.creatures:
            if self._queue_preexisting_death(creature, dead_creatures, dead_causes):
                continue
            if creature.species not in {"predator", "prey"}:
                creature.species = self._resolve_predator_prey_species(
                    creature.species,
                    creature.genome.aggression,
                )
            self._update_predator_prey_depth_band(
                creature,
                creature.get_preferred_depth_band(),
                urgency=0.04,
            )

            if creature.species == "predator":
                self._tick_predator_state(creature)
                repro_threshold = self._get_reproduction_threshold(creature) * (
                    1.0 + pred_repro_penalty
                )
                hunt_result = self._predator_hunt_prey(
                    creature,
                    creature_bucket,
                    repro_threshold=repro_threshold,
                    hunt_balance_factor=hunt_balance_factor,
                    close_range_only=creature.satiety_ticks_remaining > 0,
                )
                if not hunt_result.engaged:
                    self._creature_seek_food(
                        creature,
                        sense_override=(
                            creature.get_sense_radius()
                            * (1.0 + self._get_predator_food_efficiency_multiplier())
                        ),
                    )
                creature.update_position(1.0, self.width, self.height)
                if hunt_result.engaged and not hunt_result.killed:
                    self._resolve_post_move_predator_contact(
                        creature,
                        hunt_result=hunt_result,
                        repro_threshold=repro_threshold,
                    )

                # Broad omnivory softens the legacy predator metabolic premium.
                predator_cost_multiplier = 1.0 + (
                    0.4 * (1.0 - self._get_predator_food_efficiency_multiplier())
                )
                movement_cost = (
                    self._get_creature_movement_cost(creature)
                    * predator_cost_multiplier
                )
                if prey_scarce:
                    scarcity_multiplier = self._get_predator_prey_scarcity_penalty_multiplier()
                    omnivore_buffer = max(
                        1.0,
                        1.0
                        + (
                            (scarcity_multiplier - 1.0)
                            * (1.0 - self._get_predator_food_efficiency_multiplier())
                        ),
                    )
                    movement_cost *= omnivore_buffer
                if not hunt_result.engaged:
                    movement_cost *= self._get_predator_forage_cost_multiplier()
                metabolic_cost = self._get_creature_metabolic_cost(
                    creature,
                    longevity_cost=creature.genome.longevity * 0.0004,
                )
                hunting_cost_mult = (
                    hunt_result.hunt_modifiers.hunting_cost_mult
                    if hunt_result.engaged
                    else 1.0
                )
                energy_cost = (movement_cost + metabolic_cost) * hunting_cost_mult
                energy_cost *= 1.0 + overcrowding_penalty
                energy_cost *= self.zone_manager.get_energy_modifier(creature)
                creature.energy = max(0.0, creature.energy - energy_cost)
                if creature.energy <= 0:
                    self._queue_creature_death(
                        creature,
                        dead_creatures,
                        dead_causes,
                        self._resolve_death_cause(creature),
                    )
                    continue
                self._record_predator_post_cost_state(
                    creature,
                    repro_threshold=repro_threshold,
                    prey_scarce=prey_scarce,
                    creature_bucket=creature_bucket,
                    refuge_modifiers=(
                        hunt_result.hunt_modifiers.refuge
                        if hunt_result.engaged
                        else None
                    ),
                    rarity_modifiers=(
                        hunt_result.hunt_modifiers.rarity
                        if hunt_result.engaged
                        else None
                    ),
                )
                if (
                    creature.energy >= repro_threshold
                    and creature.recent_animal_energy
                    >= self._get_predator_recent_animal_energy_required()
                ):
                    offspring = self._reproduce_pp(
                        creature,
                        mutation_rate,
                        queued_births=len(new_creatures),
                    )
                    if offspring:
                        new_creatures.append(offspring)

            else:  # prey
                fled = self._prey_flee(creature, creature_bucket)
                if not fled:
                    self._creature_seek_food(creature)
                creature.update_position(1.0, self.width, self.height)

                energy_cost = self._get_creature_movement_cost(creature)
                energy_cost += self._get_creature_metabolic_cost(
                    creature,
                    longevity_cost=creature.genome.longevity * 0.0004,
                )
                energy_cost *= 1.0 + overcrowding_penalty
                energy_cost *= self.zone_manager.get_energy_modifier(creature)
                creature.energy = max(0.0, creature.energy - energy_cost)
                if creature.energy <= 0:
                    self._queue_creature_death(
                        creature,
                        dead_creatures,
                        dead_causes,
                        self._resolve_death_cause(creature),
                    )
                    continue

                if creature.energy >= self._get_reproduction_threshold(creature):
                    offspring = self._reproduce_pp(
                        creature,
                        mutation_rate,
                        queued_births=len(new_creatures),
                    )
                    if offspring:
                        new_creatures.append(offspring)

            if random.random() < cosmic_rate:
                self._apply_cosmic_ray_pp(creature)

            if creature.energy <= 0:
                self._queue_creature_death(
                    creature,
                    dead_creatures,
                    dead_causes,
                    self._resolve_death_cause(creature),
                )
            elif creature.age >= creature.get_max_lifespan():
                self._queue_creature_death(creature, dead_creatures, dead_causes, "age")

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._decay_prey_chase_pressure_states()
        self._sweep_frame_deaths(dead_creatures, dead_causes)
        self._process_deaths(dead_creatures, dead_causes)
        self._check_predator_prey_collapse()

        if self._predator_prey_milestone_logger is not None:
            self._predator_prey_milestone_logger.log_population_change(self)
            self._predator_prey_milestone_logger.log_lineage_evolution(self)

    def _tick_predator_state(self, predator: Creature) -> None:
        predator.recent_animal_energy = max(
            0.0,
            predator.recent_animal_energy
            - self._get_predator_recent_animal_energy_decay_per_tick(),
        )
        predator.satiety_ticks_remaining = max(0, predator.satiety_ticks_remaining - 1)

    def _new_predator_depth_fatigue_summary(self) -> dict[str, float | int]:
        return {
            "prey_depth_fatigue_events": 0,
            "depth_escape_fatigue_applied_frames": 0,
            "depth_escape_urgency_reduced_frames": 0,
            "depth_fatigue_present_while_fleeing_frames": 0,
            "committed_depth_tracking_events": 0,
            "committed_depth_tracking_kills": 0,
            "cross_depth_near_contact_before_tracking": 0,
            "cross_depth_near_contact_after_tracking": 0,
            "kills_after_depth_fatigue": 0,
            "kills_after_committed_depth_tracking": 0,
            "contact_kills_pre_move": 0,
            "contact_kills_post_move": 0,
            "post_move_contact_opportunities": 0,
            "post_move_contact_kills": 0,
            "post_move_contact_misses_by_depth": 0,
            "chase_pressure_at_kill_total": 0.0,
            "depth_fatigue_at_kill_total": 0.0,
            "kill_samples_with_chase_pressure": 0,
        }

    def _get_prey_chase_pressure_state(self, prey: Creature) -> PreyChasePressureState:
        return self._prey_chase_pressure.setdefault(id(prey), PreyChasePressureState())

    def _record_prey_chase_pressure(
        self,
        prey: Creature,
        *,
        predator: Creature,
    ) -> None:
        if self.settings.sim_mode != "predator_prey" or prey.species != "prey":
            return
        state = self._get_prey_chase_pressure_state(prey)
        if state.last_chase_pressure_frame != self._frame:
            state.current_chase_pressure_ticks = min(
                state.current_chase_pressure_ticks + 1,
                self._get_prey_depth_fatigue_min_chase_ticks()
                + self._get_prey_depth_fatigue_decay_ticks(),
            )
        life = self._ensure_predator_life(predator)
        frame_targets = life.setdefault("_frame_chased_prey_ids", set())
        frame_targets.add(id(prey))
        state.current_frame_chase_events = int(state.current_frame_chase_events) + 1
        state.last_chased_by_predator_id = id(predator)
        state.last_chase_pressure_frame = self._frame
        if self._prey_depth_fatigue_enabled():
            target = self._calculate_prey_depth_fatigue(prey, state)
            if target > state.depth_escape_fatigue:
                state.depth_escape_fatigue = min(
                    self._get_prey_depth_fatigue_max(),
                    target,
                )

    def _decay_prey_chase_pressure_states(self) -> None:
        if self.settings.sim_mode != "predator_prey":
            return
        live_prey_ids = {id(creature) for creature in self.creatures if creature.species == "prey"}
        for prey_id in list(self._prey_chase_pressure):
            if prey_id not in live_prey_ids:
                self._prey_chase_pressure.pop(prey_id, None)
                continue
            state = self._prey_chase_pressure[prey_id]
            if state.last_chase_pressure_frame == self._frame:
                continue
            state.current_chase_pressure_ticks = max(
                0,
                state.current_chase_pressure_ticks - 1,
            )
            decay_step = self._get_prey_depth_fatigue_max() / max(
                1,
                self._get_prey_depth_fatigue_decay_ticks(),
            )
            state.depth_escape_fatigue = max(0.0, state.depth_escape_fatigue - decay_step)
            if state.current_chase_pressure_ticks <= 0 and state.depth_escape_fatigue <= 0.0:
                self._prey_chase_pressure.pop(prey_id, None)

    def _calculate_prey_depth_fatigue(
        self,
        prey: Creature,
        state: PreyChasePressureState,
    ) -> float:
        if not self._prey_depth_fatigue_enabled():
            return 0.0
        max_fatigue = self._get_prey_depth_fatigue_max()
        if max_fatigue <= 0.0:
            return 0.0
        min_ticks = self._get_prey_depth_fatigue_min_chase_ticks()
        decay_ticks = self._get_prey_depth_fatigue_decay_ticks()
        threshold = self._get_prey_depth_fatigue_energy_threshold()
        pressure_progress = max(
            0.0,
            min(
                1.0,
                (state.current_chase_pressure_ticks - min_ticks) / max(1, decay_ticks),
            ),
        )
        pressure_presence = max(
            0.0,
            min(1.0, state.current_chase_pressure_ticks / max(1, min_ticks)),
        )
        energy_pressure = 0.0
        if prey.energy < threshold:
            energy_pressure = max(0.0, min(1.0, (threshold - prey.energy) / threshold))
        fatigue = max(
            pressure_progress,
            pressure_presence * energy_pressure * 0.6,
        )
        return max(0.0, min(max_fatigue, fatigue * max_fatigue))

    def _get_prey_depth_escape_fatigue(self, prey: Creature) -> float:
        state = self._prey_chase_pressure.get(id(prey))
        if state is None:
            return 0.0
        return max(0.0, min(self._get_prey_depth_fatigue_max(), state.depth_escape_fatigue))

    def _get_prey_depth_escape_urgency(self, prey: Creature) -> float:
        fatigue = self._get_prey_depth_escape_fatigue(prey)
        if fatigue <= 0.0:
            return _PREY_DEPTH_ESCAPE_URGENCY
        urgency = _PREY_DEPTH_ESCAPE_URGENCY * (
            1.0 - (fatigue * self._get_prey_depth_fatigue_escape_urgency_mult())
        )
        return max(_PREY_DEPTH_ESCAPE_URGENCY * 0.35, urgency)

    def _prey_has_meaningful_depth_fatigue(self, prey: Creature) -> bool:
        return self._get_prey_depth_escape_fatigue(prey) >= 0.05

    def _mark_cross_depth_tracking_context(
        self,
        predator: Creature,
    ) -> None:
        life = self._ensure_predator_life(predator)
        if life.get("_current_chase_had_committed_tracking"):
            life["cross_depth_near_contact_after_tracking"] += 1
            self._predator_depth_fatigue_summary[
                "cross_depth_near_contact_after_tracking"
            ] += 1
        else:
            life["cross_depth_near_contact_before_tracking"] += 1
            self._predator_depth_fatigue_summary[
                "cross_depth_near_contact_before_tracking"
            ] += 1

    def _maybe_apply_committed_depth_tracking(
        self,
        predator: Creature,
        prey: Creature,
        *,
        near_contact_dist: float,
        best_dist_sq: float,
        hunt_modifiers: PredatorHuntModifiers,
    ) -> bool:
        if not self._predator_committed_depth_tracking_enabled():
            return False
        if predator.depth_band == prey.depth_band or prey.energy <= 0.0:
            return False
        life = self._ensure_predator_life(predator)
        if int(life.get("_current_chase_frames", 0)) < self._get_predator_committed_depth_tracking_min_chase_ticks():
            return False
        if life.get("_last_target_id") != id(prey):
            return False
        scaled_near_contact = (
            near_contact_dist * self._get_predator_committed_depth_tracking_near_contact_scale()
        )
        if best_dist_sq > (scaled_near_contact * scaled_near_contact):
            return False
        cooldown_until = int(life.get("_committed_depth_tracking_cooldown_until", -1))
        if self._frame < cooldown_until:
            return False
        previous_depth_band = predator.depth_band
        self._update_predator_prey_depth_band(
            predator,
            prey.depth_band,
            urgency=1.0,
            extra_transition_mult=hunt_modifiers.depth_transition_mult,
        )
        if predator.depth_band == previous_depth_band:
            return False
        life["committed_depth_tracking_events"] += 1
        life["_current_chase_had_committed_tracking"] = True
        life["_current_chase_committed_tracking_target_id"] = id(prey)
        life["_last_committed_depth_tracking_frame"] = self._frame
        life["_committed_depth_tracking_cooldown_until"] = (
            self._frame + self._get_predator_committed_depth_tracking_cooldown_ticks()
        )
        self._predator_depth_fatigue_summary["committed_depth_tracking_events"] += 1
        return True

    def _predator_interference_factor(
        self,
        predator: Creature,
        bucket: dict,
    ) -> float:
        strength = self._get_predator_interference_strength()
        if strength <= 0.0:
            return 1.0
        nearby_predators = 0
        for other in self._nearby_creatures(
            predator.x,
            predator.y,
            _PREDATOR_INTERFERENCE_RADIUS,
            bucket,
        ):
            if other is predator or other.species != "predator" or other.energy <= 0.0:
                continue
            if (
                predator.distance_to(other.x, other.y, self.width, self.height)
                <= _PREDATOR_INTERFERENCE_RADIUS
            ):
                nearby_predators += 1
        effective_nearby_predators = max(0, nearby_predators - 1)
        return 1.0 / (1.0 + (effective_nearby_predators * strength))

    def _get_predator_hunt_balance_factor(
        self,
        *,
        pred_count: int,
        prey_count: int,
    ) -> float:
        if pred_count <= 0:
            return 1.0
        prey_per_predator = prey_count / max(1, pred_count)
        target_ratio = self._get_predator_target_prey_per_predator()
        scarcity_scale = prey_per_predator / target_ratio
        return max(
            self._get_predator_low_prey_hunt_floor(),
            min(1.0, scarcity_scale),
        )

    def _resolve_predator_contact_kill(
        self,
        *,
        predator: Creature,
        prey: Creature,
        hunt_modifiers: PredatorHuntModifiers,
        repro_threshold: float,
        pre_move: bool,
    ) -> bool:
        if prey.energy <= 0.0 or id(prey) in self._predation_victims_this_frame:
            return False
        pre_kill_energy = predator.energy
        prey_energy_before_kill = prey.energy
        kill_cap = self._get_predator_kill_energy_gain_cap()
        biomass_bonus = self._get_predator_kill_biomass_bonus()
        raw_kill_energy = prey.energy + biomass_bonus
        energy_gain = min(kill_cap, raw_kill_energy)
        predator.energy = min(1.0, predator.energy + energy_gain)
        predator.recent_animal_energy = min(1.0, predator.recent_animal_energy + energy_gain)
        predator.satiety_ticks_remaining = self._get_predator_satiety_ticks()
        prey.energy = 0.0
        self.predation_kill_count += 1
        self._predation_victims_this_frame.add(id(prey))
        self._predation_render_context_by_victim[id(prey)] = {
            "predator_x": predator.x, "predator_y": predator.y, "predator_species": predator.species,
            "predator_hue": predator.genome.hue, "predator_saturation": predator.genome.saturation,
            "predator_depth_band": predator.depth_band,
        }
        self._recent_kill_frames.append(self._frame)
        if pre_move:
            self._predator_depth_fatigue_summary["contact_kills_pre_move"] += 1
        else:
            self._predator_depth_fatigue_summary["contact_kills_post_move"] += 1
            self._predator_depth_fatigue_summary["post_move_contact_kills"] += 1
        self._record_predator_kill(
            predator, pre_kill_energy=pre_kill_energy, post_kill_energy=predator.energy,
            repro_threshold=repro_threshold, prey=prey, prey_energy_at_kill=prey_energy_before_kill,
            biomass_bonus=biomass_bonus, refuge_modifiers=hunt_modifiers.refuge, rarity_modifiers=hunt_modifiers.rarity,
        )
        self.active_attacks.append((predator.x, predator.y, prey.x, prey.y, predator.species, predator.genome.hue, predator.genome.saturation))
        return True

    def _predator_hunt_prey(
        self,
        predator: Creature,
        bucket: dict,
        *,
        repro_threshold: float | None = None,
        hunt_balance_factor: float = 1.0,
        close_range_only: bool = False,
    ) -> PredatorHuntResult:
        """Predator seeks nearest prey; kills on contact."""
        if repro_threshold is None:
            repro_threshold = self._get_reproduction_threshold(predator)
        interference_factor = self._predator_interference_factor(predator, bucket)
        hunt_modifiers = self._get_predator_hunt_modifiers(predator, bucket)
        sense_multiplier = (
            self._get_predator_hunt_sense_multiplier()
            * interference_factor
            * hunt_balance_factor
            * hunt_modifiers.hunt_sense_mult
        )
        speed_multiplier = (
            self._get_predator_hunt_speed_multiplier()
            * interference_factor
            * hunt_balance_factor
        )
        contact_scale = (
            self._get_predator_contact_kill_distance_scale()
            * interference_factor
            * hunt_balance_factor
            * hunt_modifiers.contact_mult
        )
        sense = self._get_effective_sensing_range(predator, multiplier=sense_multiplier)
        if close_range_only:
            close_range = max(
                24.0,
                predator.get_radius() * 3.0 * self._get_creature_predation_contact_multiplier(predator),
            )
            sense = min(sense, close_range)
        best_prey: Creature | None = None
        best_dist_sq = sense * sense
        best_sensed_prey: tuple[float, float] | None = None
        best_score: float | None = None
        life = self._ensure_predator_life(predator)
        remembered_target_id = life.get("_memory_target_id")

        for other in self._nearby_creatures(predator.x, predator.y, sense, bucket):
            if other is predator or other.species != "prey" or other.energy <= 0.0:
                continue
            dist_sq = self._distance_sq(predator.x, predator.y, other.x, other.y)
            if dist_sq >= (sense * sense):
                continue
            sensed_prey = self._sense_target_position(
                predator,
                other.x,
                other.y,
                sense_multiplier=sense_multiplier,
                target_depth_band=other.depth_band,
            )
            if sensed_prey is None:
                continue
            score = (
                math.sqrt(dist_sq)
                + (depth_band_separation(predator.depth_band, other.depth_band) * 20.0)
            )
            if best_score is None or score < best_score:
                best_score = score
                best_dist_sq = dist_sq
                best_prey = other
                best_sensed_prey = sensed_prey

        used_memory_target = False
        if (
            remembered_target_id is not None
            and best_prey is not None
            and best_score is not None
        ):
            remembered_live_candidate = next(
                (
                    c for c in self.creatures
                    if id(c) == remembered_target_id and c.species == "prey" and c.energy > 0.0
                ),
                None,
            )
            if remembered_live_candidate is not None:
                remembered_dist_sq = self._distance_sq(
                    predator.x,
                    predator.y,
                    remembered_live_candidate.x,
                    remembered_live_candidate.y,
                )
                if remembered_dist_sq < (sense * sense):
                    remembered_sensed_prey = self._sense_target_position(
                        predator,
                        remembered_live_candidate.x,
                        remembered_live_candidate.y,
                        sense_multiplier=sense_multiplier,
                        target_depth_band=remembered_live_candidate.depth_band,
                    )
                    if remembered_sensed_prey is not None:
                        remembered_score = (
                            math.sqrt(remembered_dist_sq)
                            + (
                                depth_band_separation(
                                    predator.depth_band,
                                    remembered_live_candidate.depth_band,
                                )
                                * 20.0
                            )
                        )
                        switch_ratio = self._get_predator_target_switch_score_ratio()
                        if id(best_prey) != remembered_target_id and not (
                            best_score <= (remembered_score * switch_ratio)
                        ):
                            best_prey = remembered_live_candidate
                            best_dist_sq = remembered_dist_sq
                            best_sensed_prey = remembered_sensed_prey
                            best_score = remembered_score
        if best_prey is None or best_sensed_prey is None:
            memory_target = self._get_predator_memory_target(predator, sense=sense)
            if memory_target is not None:
                best_prey, best_sensed_prey = memory_target
                used_memory_target = True
            else:
                self._clear_predator_chase_state(predator)
                predator.wander(
                    self.settings.creature_speed_base,
                    speed_scale=self._get_creature_speed_scale(predator),
                )
                return PredatorHuntResult(engaged=False, killed=False)

        self._update_predator_prey_depth_band(
            predator,
            best_prey.depth_band,
            urgency=_PREDATOR_DEPTH_TRACK_URGENCY,
            extra_transition_mult=hunt_modifiers.depth_transition_mult,
        )
        self._record_prey_chase_pressure(best_prey, predator=predator)

        if not used_memory_target:
            self._record_predator_prey_sighting(predator)
            self._record_predator_chase_target(predator, best_prey)
            self._remember_predator_target(predator, best_prey, best_sensed_prey, best_score)
        else:
            self._record_predator_memory_chase(predator, best_prey)

        memory_steer_mult = self._get_predator_memory_steering_mult() if used_memory_target else 1.0
        predator.steer_toward(
            best_sensed_prey[0], best_sensed_prey[1],
            self.settings.creature_speed_base * speed_multiplier * memory_steer_mult,
            self.width, self.height,
            speed_scale=self._get_creature_speed_scale(predator),
        )

        # Contact kill: distance < sum of radii
        contact_dist = (
            predator.get_radius() + best_prey.get_radius()
        ) * contact_scale * self._get_creature_predation_contact_multiplier(predator)
        near_contact_dist = (
            contact_dist * self._get_predator_near_contact_diagnostic_scale()
        )
        is_near_contact = (
            best_prey.energy > 0.0
            and best_dist_sq <= (near_contact_dist * near_contact_dist)
        )
        committed_tracking_applied = False
        pre_tracking_same_depth = predator.depth_band == best_prey.depth_band
        if is_near_contact:
            self._record_predator_near_contact(
                predator,
                best_prey,
                same_depth=pre_tracking_same_depth,
                no_kill=not (
                    best_dist_sq < (contact_dist * contact_dist)
                    and pre_tracking_same_depth
                ),
            )
        if is_near_contact and best_prey.energy > 0.0 and predator.depth_band != best_prey.depth_band:
            self._mark_cross_depth_tracking_context(predator)
            committed_tracking_applied = self._maybe_apply_committed_depth_tracking(
                predator,
                best_prey,
                near_contact_dist=near_contact_dist,
                best_dist_sq=best_dist_sq,
                hunt_modifiers=hunt_modifiers,
            )
        post_tracking_same_depth = predator.depth_band == best_prey.depth_band
        if is_near_contact and (not pre_tracking_same_depth) and (not post_tracking_same_depth):
            self._mark_cross_depth_tracking_context(predator)
        if (
            best_dist_sq < (contact_dist * contact_dist)
            and best_prey.energy > 0.0
            and post_tracking_same_depth
            and not committed_tracking_applied
        ):
            self._resolve_predator_contact_kill(predator=predator, prey=best_prey, hunt_modifiers=hunt_modifiers, repro_threshold=repro_threshold, pre_move=True)
            return PredatorHuntResult(
                engaged=True,
                killed=True,
                hunt_modifiers=hunt_modifiers,
            )
        elif best_dist_sq < (contact_dist * contact_dist) and best_prey.energy > 0.0:
            self._recent_cross_band_miss_frames.append(self._frame)
            self._record_predator_cross_band_miss(
                predator,
                hunt_modifiers=hunt_modifiers,
            )
        return PredatorHuntResult(
            engaged=True,
            killed=False,
            hunt_modifiers=hunt_modifiers,
        )

    def _resolve_post_move_predator_contact(
        self,
        predator: Creature,
        *,
        hunt_result: PredatorHuntResult,
        repro_threshold: float,
    ) -> None:
        life = self._ensure_predator_life(predator)
        target_id = life.get("_last_target_id")
        if target_id is None:
            return
        prey = next((c for c in self.creatures if id(c) == target_id), None)
        if prey is None or prey.species != "prey" or prey.energy <= 0.0:
            return
        contact_scale = (
            self._get_predator_contact_kill_distance_scale()
            * hunt_result.hunt_modifiers.contact_mult
        )
        contact_dist = (
            predator.get_radius() + prey.get_radius()
        ) * contact_scale * self._get_creature_predation_contact_multiplier(predator)
        dist_sq = self._distance_sq(predator.x, predator.y, prey.x, prey.y)
        if dist_sq <= contact_dist * contact_dist:
            self._predator_depth_fatigue_summary["post_move_contact_opportunities"] += 1
            if predator.depth_band == prey.depth_band:
                self._resolve_predator_contact_kill(
                    predator=predator,
                    prey=prey,
                    hunt_modifiers=hunt_result.hunt_modifiers,
                    repro_threshold=repro_threshold,
                    pre_move=False,
                )
            else:
                self._predator_depth_fatigue_summary["post_move_contact_misses_by_depth"] += 1

    def _prey_flee(self, prey: Creature, bucket: dict) -> bool:
        """Prey flees from nearest predator within a tuned sensing range.

        Returns True if actively fleeing.
        """
        flee_multiplier = self._get_prey_flee_sense_multiplier()
        flee_sense = self._get_effective_sensing_range(prey, multiplier=flee_multiplier)
        nearest_pred: Creature | None = None
        nearest_dist = flee_sense

        for other in self._nearby_creatures(prey.x, prey.y, flee_sense, bucket):
            if other is prey or other.species != "predator":
                continue
            dist = prey.distance_to(other.x, other.y, self.width, self.height)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_pred = other

        if nearest_pred is None:
            return False

        if prey.depth_band == nearest_pred.depth_band:
            if self._prey_has_meaningful_depth_fatigue(prey):
                self._predator_depth_fatigue_summary["prey_depth_fatigue_events"] += 1
            self._update_predator_prey_depth_band(
                prey,
                self._pick_depth_escape_band(prey, nearest_pred.depth_band),
                urgency=self._get_prey_depth_escape_urgency(prey),
            )

        sensed_predator = self._sense_target_position(
            prey,
            nearest_pred.x,
            nearest_pred.y,
            sense_multiplier=flee_multiplier,
            target_depth_band=nearest_pred.depth_band,
        )
        if sensed_predator is None:
            return False

        # Steer away from predator
        dx, dy = self._wrapped_delta(sensed_predator[0], sensed_predator[1], prey.x, prey.y)
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dx /= dist
            dy /= dist

        flee_speed_scale = self._get_creature_flee_speed_scale(prey)
        flee_condition_mult = self._get_prey_flee_condition_multiplier(prey)
        if self._prey_has_meaningful_depth_fatigue(prey):
            self._predator_depth_fatigue_summary[
                "depth_escape_fatigue_applied_frames"
            ] += 1
            self._predator_depth_fatigue_summary["depth_fatigue_present_while_fleeing_frames"] += 1
        if prey.depth_band == nearest_pred.depth_band and self._prey_has_meaningful_depth_fatigue(prey):
            self._predator_depth_fatigue_summary["depth_escape_urgency_reduced_frames"] += 1
        max_speed = (
            prey.genome.speed
            * self.settings.creature_speed_base
            * self._get_prey_flee_speed_multiplier()
            * flee_speed_scale
            * flee_condition_mult
        )
        desired_vx = dx * max_speed
        desired_vy = dy * max_speed
        steer = 0.35 * min(1.15, max(0.92, self._get_effective_phenotype(prey).flee_agility_mult))
        prey.vx += (desired_vx - prey.vx) * steer
        prey.vy += (desired_vy - prey.vy) * steer
        self._clamp_velocity(prey, max_speed)
        return True

    def _clamp_velocity(self, creature: Creature, max_speed: float) -> None:
        """Bound instantaneous velocity without changing direction."""
        speed = math.hypot(creature.vx, creature.vy)
        if speed <= max_speed or speed == 0.0:
            return
        scale = max_speed / speed
        creature.vx *= scale
        creature.vy *= scale

    def _apply_cosmic_ray_pp(self, creature: Creature) -> None:
        """Cosmic ray in predator_prey mode — may flip species via hysteresis thresholds."""
        new_genome, mutated_trait = creature.genome.mutate_one(std=0.15)

        if self._should_branch_lineage(creature.genome, new_genome, hue_threshold=0.2):
            creature.lineage_id = self._alloc_lineage_id()

        # Species flip if aggression crosses 0.5 boundary
        if mutated_trait == "aggression":
            previous_species = creature.species
            next_species = self._resolve_predator_prey_species(
                creature.species,
                new_genome.aggression,
            )
            if previous_species != next_species:
                if previous_species == "predator":
                    self._finalize_predator_life(
                        creature,
                        end_reason="species_flip_to_prey",
                        death_cause="species_flip",
                    )
                    self._predator_diag_events["cosmic_flips_from_predator"].append({
                        "frame": self._frame,
                        "lineage_id": creature.lineage_id,
                    })
                if self._predator_prey_milestone_logger is not None:
                    self._predator_prey_milestone_logger.log_species_flip(
                        self, creature, previous_species, next_species,
                    )
                creature.species = next_species
                if previous_species == "prey":
                    self._prey_chase_pressure.pop(id(creature), None)
                creature.lineage_id = self._alloc_lineage_id()
                creature.recent_animal_energy = 0.0
                creature.satiety_ticks_remaining = 0
                if next_species == "predator":
                    self._predator_diag_events["cosmic_flips_to_predator"].append({
                        "frame": self._frame,
                        "lineage_id": creature.lineage_id,
                    })
                    self._register_predator_life(creature, origin="cosmic_flip")

        creature.genome = new_genome  # type: ignore[misc]
        creature.glyph_surface = None
        creature.glyph_surface_cache_key = None
        creature._glyph_phase = new_genome.hue * 6.28
        self.cosmic_ray_events.append((creature.x, creature.y))

    def _reproduce_pp(
        self,
        creature: Creature,
        mutation_rate: float,
        *,
        queued_births: int = 0,
    ) -> Creature | None:
        """Reproduce in predator_prey mode with hysteresis-based offspring role."""
        if not self._can_queue_birth(queued_births):
            return None

        creature.energy /= 2
        creature.recent_animal_energy *= 0.5
        offspring_genome = creature.genome.mutate(mutation_rate)
        offspring_lineage = self._branch_lineage_id(
            creature.lineage_id,
            creature.genome,
            offspring_genome,
        )
        offspring_species = self._resolve_predator_prey_species(
            creature.species,
            offspring_genome.aggression,
        )

        offspring = Creature(
            x=(creature.x + random.uniform(-10, 10)) % self.width,
            y=(creature.y + random.uniform(-10, 10)) % self.height,
            genome=offspring_genome,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=creature.energy,
            lineage_id=offspring_lineage,
            species=offspring_species,
            recent_animal_energy=0.0,
            satiety_ticks_remaining=0,
            _glyph_phase=offspring_genome.hue * 6.28,
        )

        self.generation += 1
        self.total_births += 1
        if creature.species == "predator":
            life = self._ensure_predator_life(creature)
            life["births_produced"] += 1
            if self._get_predator_rarity_modifiers(creature).active:
                life["births_while_rarity_active"] += 1
            if offspring.species == "predator":
                self._predator_diag_events["births"].append({
                    "frame": self._frame,
                    "parent_life_id": life["life_id"],
                    "parent_lineage_id": creature.lineage_id,
                    "offspring_lineage_id": offspring.lineage_id,
                })
        if offspring.species == "predator":
            self._register_predator_life(offspring, origin="birth")
        return offspring

    def _check_predator_prey_collapse(self, now_seconds: float | None = None) -> None:
        """Freeze predator-prey runs only after sustained zero-count grace windows."""
        if self.predator_prey_game_over_active:
            return

        pred_count, prey_count = self.get_species_counts()
        state = self._predator_prey_state
        if pred_count < self._get_predator_near_extinction_floor():
            state.predator_low_ticks += 1
        if prey_count < self._get_prey_near_extinction_floor():
            state.prey_low_ticks += 1
        state.predator_zero_ticks = state.predator_zero_ticks + 1 if pred_count == 0 else 0
        state.prey_zero_ticks = state.prey_zero_ticks + 1 if prey_count == 0 else 0
        if pred_count > 0 and prey_count > 0:
            return

        grace_ticks = self._get_predator_prey_extinction_grace_ticks()
        if (
            state.predator_zero_ticks < grace_ticks
            and state.prey_zero_ticks < grace_ticks
        ):
            return

        if pred_count == 0 and prey_count == 0:
            cause = "Both species collapsed"
        elif pred_count == 0:
            cause = "Predators collapsed"
        else:
            cause = "Prey collapsed"

        self._enter_predator_prey_game_over(
            cause,
            predator_count=pred_count,
            prey_count=prey_count,
            now_seconds=now_seconds,
        )

    def _enter_predator_prey_game_over(
        self,
        cause: str,
        *,
        predator_count: int,
        prey_count: int,
        now_seconds: float | None = None,
    ) -> None:
        state = self._predator_prey_state
        state.game_over_active = True
        state.collapse_cause = cause
        state.collapse_predator_count = predator_count
        state.collapse_prey_count = prey_count
        state.collapse_started_at_seconds = (
            time.monotonic() if now_seconds is None else now_seconds
        )
        tuning = state.adaptive_tuning
        prior_average = self.predator_prey_rolling_average
        state.collapse_dial_values = dict(tuning.current_values)
        state.collapse_trial_decision = tuning.last_decision
        state.collapse_rolling_average = prior_average
        state.collapse_beat_average = prior_average > 0 and state.survival_ticks > prior_average
        state.collapse_trial_dial = tuning.trial_dial if tuning.trial_active else None
        state.collapse_trial_phase = tuning.trial_phase if tuning.trial_active else None
        state.collapse_trial_seed = None
        state.collapse_trial_id = tuning.trial_id if tuning.trial_active else None
        state.collapse_trial_trigger_reason = (
            tuning.trial_trigger_reason if tuning.trial_active else None
        )
        if tuning.trial_active and tuning.trial_seeds:
            index = min(max(tuning.trial_seed_index, 0), len(tuning.trial_seeds) - 1)
            state.collapse_trial_seed = int(tuning.trial_seeds[index])
        if tuning.trial_active and tuning.trial_dial is not None:
            previous_value = tuning.previous_values.get(
                tuning.trial_dial,
                tuning.current_values.get(tuning.trial_dial, 0.0),
            )
            current_value = tuning.current_values.get(tuning.trial_dial, previous_value)
            delta = round(current_value - previous_value, 4)
            state.collapse_trial_delta = delta
            state.collapse_trial_value = current_value
        else:
            state.collapse_trial_delta = 0.0
            state.collapse_trial_value = None
        self._finalize_predator_prey_run(state.survival_ticks)
        if self._predator_prey_milestone_logger is not None:
            self._predator_prey_milestone_logger.log_collapse(self, cause)

    def _finalize_predator_prey_run(self, survival_ticks: int) -> None:
        state = self._predator_prey_state
        tuning = state.adaptive_tuning
        prior_average = self.predator_prey_rolling_average
        was_trial = tuning.trial_active
        post_run_trial_decision = "none"
        completed_trial_decision: str | None = None
        state.collapse_was_new_highest = survival_ticks > state.highest_survival_ticks
        state.highest_survival_ticks = max(state.highest_survival_ticks, survival_ticks)

        if was_trial:
            completed_trial_decision = self._advance_predator_prey_trial(survival_ticks)
            if completed_trial_decision is not None:
                post_run_trial_decision = completed_trial_decision

        if prior_average > 0:
            if survival_ticks > prior_average:
                tuning.non_improving_run_streak = 0
            else:
                tuning.non_improving_run_streak += 1
        else:
            tuning.non_improving_run_streak = 0

        state.run_history.append(int(survival_ticks))

        tuning.last_trial_launch_blocked_by_retry_cap = False

        if was_trial and completed_trial_decision == "kept":
            tuning.consecutive_immediate_retry_trials = 0
            tuning.retry_cap_waiting_for_ordinary_run = False
        elif was_trial and completed_trial_decision == "reverted":
            if not self._adaptive_trial_launches_allowed():
                tuning.consecutive_immediate_retry_trials = 0
                tuning.retry_cap_waiting_for_ordinary_run = False
            else:
                retry_cap = self._get_predator_prey_max_consecutive_retry_trials()
                if tuning.consecutive_immediate_retry_trials < retry_cap:
                    launch_result = self._start_predator_prey_trial(
                        self.predator_prey_rolling_average,
                        trigger_reason="immediate_retry_after_revert",
                        preserve_completed_decision=True,
                    )
                    if launch_result == "trial_started":
                        tuning.consecutive_immediate_retry_trials += 1
                        tuning.retry_cap_waiting_for_ordinary_run = False
                    else:
                        tuning.consecutive_immediate_retry_trials = 0
                        tuning.retry_cap_waiting_for_ordinary_run = False
                else:
                    tuning.retry_cap_waiting_for_ordinary_run = True
                    tuning.last_trial_launch_blocked_by_retry_cap = True
        elif not was_trial:
            trigger_reason = "below_rolling_median"
            if tuning.retry_cap_waiting_for_ordinary_run:
                trigger_reason = "blocked_by_retry_cap_then_waited_for_ordinary_run"
            tuning.consecutive_immediate_retry_trials = 0
            if (
                self._adaptive_trial_launches_allowed()
                and prior_average > 0
                and survival_ticks < prior_average
            ):
                post_run_trial_decision = self._start_predator_prey_trial(
                    prior_average,
                    trigger_reason=trigger_reason,
                )
            tuning.retry_cap_waiting_for_ordinary_run = False

        tuning.post_run_trial_decision = post_run_trial_decision

        if self._predator_prey_run_logger is not None:
            self._predator_prey_run_logger.log_completed_run(self)
            if tuning.last_decision_pending_log:
                self._predator_prey_run_logger.log_trial_decision(self)
                tuning.last_decision_pending_log = False

        if self._predator_prey_milestone_logger is not None:
            self._predator_prey_milestone_logger.log_completed_run(self)

    def _check_ecosystem_balance(
        self,
        *,
        pred_count: int,
        prey_count: int,
    ) -> None:
        """Compatibility seam for predator-prey balance hooks and tests."""
        _ = pred_count, prey_count

    def _adaptive_trial_launches_allowed(self) -> bool:
        """Return whether the dormant adaptive-trial system is currently enabled."""
        return self._predator_prey_adaptive_tuning_enabled

    def _start_predator_prey_trial(
        self,
        baseline_average: float,
        *,
        trigger_reason: str,
        preserve_completed_decision: bool = False,
    ) -> str:
        tuning = self._predator_prey_state.adaptive_tuning
        candidates = list(_PREDATOR_PREY_ADAPTIVE_DIALS)
        step_multiplier = self.predator_prey_adjustment_step_multiplier
        random.shuffle(candidates)

        for spec in candidates:
            current_value = tuning.current_values.get(spec.key, spec.default)
            directions = [-1, 1]
            random.shuffle(directions)
            for direction in directions:
                candidate_value = self._clamp_predator_prey_dial_value(
                    spec,
                    current_value + (spec.step * step_multiplier * direction),
                )
                if math.isclose(candidate_value, current_value, abs_tol=1e-9):
                    continue
                baseline_values = dict(tuning.current_values)
                candidate_values = dict(baseline_values)
                candidate_values[spec.key] = candidate_value
                tuning.previous_values = baseline_values
                tuning.current_values = dict(candidate_values)
                tuning.trial_candidate_values = dict(candidate_values)
                tuning.trial_active = True
                tuning.trial_phase = "candidate"
                tuning.trial_dial = spec.key
                tuning.trial_direction = direction
                tuning.trial_baseline_average = baseline_average
                tuning.trial_id = tuning.next_trial_id
                tuning.trial_trigger_reason = trigger_reason
                tuning.next_trial_id += 1
                tuning.trial_seeds = [
                    self._generate_predator_prey_seed()
                    for _ in range(self._get_predator_prey_trial_count())
                ]
                tuning.trial_seed_index = 0
                tuning.trial_candidate_results = []
                tuning.trial_baseline_results = []
                tuning.trial_candidate_pressures = []
                tuning.trial_baseline_pressures = []
                if not preserve_completed_decision:
                    tuning.last_decision = "trial_started"
                    tuning.last_decision_basis = None
                    tuning.last_decision_trial_id = None
                    tuning.last_decision_survival_median_candidate = None
                    tuning.last_decision_survival_median_baseline = None
                    tuning.last_decision_near_extinction_candidate = None
                    tuning.last_decision_near_extinction_baseline = None
                    tuning.last_decision_pending_log = False
                self._apply_predator_prey_tuning_values(tuning.current_values)
                return "trial_started"

        tuning.trial_trigger_reason = None
        if not preserve_completed_decision:
            tuning.last_decision = "trial_skipped"
        return "trial_skipped"

    def _advance_predator_prey_trial(self, survival_ticks: int) -> str | None:
        state = self._predator_prey_state
        tuning = self._predator_prey_state.adaptive_tuning
        phase = tuning.trial_phase
        run_pressure = state.predator_low_ticks + state.prey_low_ticks
        if phase == "baseline":
            tuning.trial_baseline_results.append(int(survival_ticks))
            tuning.trial_baseline_pressures.append(int(run_pressure))
            tuning.trial_baseline_average = self._predator_prey_median(
                tuning.trial_baseline_results
            )
            if len(tuning.trial_baseline_results) >= len(tuning.trial_seeds):
                candidate_score = self._predator_prey_median(
                    tuning.trial_candidate_results
                )
                baseline_score = self._predator_prey_median(
                    tuning.trial_baseline_results
                )
                candidate_pressure = self._predator_prey_median(
                    tuning.trial_candidate_pressures
                )
                baseline_pressure = self._predator_prey_median(
                    tuning.trial_baseline_pressures
                )
                keep_candidate, decision_basis = self._decide_predator_prey_trial_winner(
                    candidate_score=candidate_score,
                    baseline_score=baseline_score,
                    candidate_pressure=candidate_pressure,
                    baseline_pressure=baseline_pressure,
                )
                tuning.last_decision_basis = decision_basis
                tuning.last_decision_trial_id = tuning.trial_id
                tuning.last_decision_survival_median_candidate = candidate_score
                tuning.last_decision_survival_median_baseline = baseline_score
                tuning.last_decision_near_extinction_candidate = candidate_pressure
                tuning.last_decision_near_extinction_baseline = baseline_pressure
                tuning.last_decision_pending_log = True
                if not keep_candidate:
                    tuning.current_values = dict(tuning.previous_values)
                    tuning.last_decision = "reverted"
                else:
                    tuning.current_values = dict(tuning.trial_candidate_values)
                    tuning.previous_values = dict(tuning.current_values)
                    tuning.last_decision = "kept"
                tuning.trial_active = False
                tuning.trial_dial = None
                tuning.trial_direction = 0
                tuning.trial_baseline_average = 0.0
                self._clear_predator_prey_trial_state(tuning)
                self._apply_predator_prey_tuning_values(tuning.current_values)
                return tuning.last_decision

            tuning.trial_seed_index += 1
            tuning.trial_phase = "candidate"
            tuning.current_values = dict(tuning.trial_candidate_values)
            self._apply_predator_prey_tuning_values(tuning.current_values)
            return "trial_started"

        tuning.trial_candidate_results.append(int(survival_ticks))
        tuning.trial_candidate_pressures.append(int(run_pressure))
        tuning.trial_phase = "baseline"
        tuning.current_values = dict(tuning.previous_values)
        self._apply_predator_prey_tuning_values(tuning.current_values)
        return "trial_started"

    def _decide_predator_prey_trial_winner(
        self,
        *,
        candidate_score: float,
        baseline_score: float,
        candidate_pressure: float,
        baseline_pressure: float,
    ) -> tuple[bool, str]:
        survival_diff = candidate_score - baseline_score
        if abs(survival_diff) > self._get_predator_prey_survival_deadband():
            return (candidate_score > baseline_score, "survival")
        if candidate_pressure < baseline_pressure:
            return (True, "near_extinction_tiebreak")
        if candidate_pressure > baseline_pressure:
            return (False, "near_extinction_tiebreak")
        if candidate_score > baseline_score:
            return (True, "survival")
        if candidate_score < baseline_score:
            return (False, "survival")
        return (False, "exact_tie_revert_candidate")

    def _clear_predator_prey_trial_state(
        self,
        tuning: PredatorPreyAdaptiveTuningState,
    ) -> None:
        tuning.trial_candidate_values = {}
        tuning.trial_phase = "candidate"
        tuning.trial_id = None
        tuning.trial_trigger_reason = None
        tuning.trial_seeds = []
        tuning.trial_seed_index = 0
        tuning.trial_candidate_results = []
        tuning.trial_baseline_results = []
        tuning.trial_candidate_pressures = []
        tuning.trial_baseline_pressures = []

    def update_predator_prey_runtime(self, now_seconds: float | None = None) -> bool:
        """Hold the game-over screen, then restart predator-prey with a new seed."""
        if not self.predator_prey_game_over_active:
            return False

        current_time = time.monotonic() if now_seconds is None else now_seconds
        state = self._predator_prey_state
        if state.collapse_started_at_seconds is None:
            state.collapse_started_at_seconds = current_time
            return False
        if (
            current_time - state.collapse_started_at_seconds
            < _PREDATOR_PREY_GAME_OVER_HOLD_SECONDS
        ):
            return False

        self.restart_predator_prey_run()
        return True

    def restart_predator_prey_run(self, new_seed: int | None = None) -> None:
        """Start a fresh predator-prey run while preserving rolling stability state."""
        self.reset(
            preserve_predator_prey_state=True,
            new_seed=new_seed,
        )
        if self._predator_prey_milestone_logger is not None:
            self._predator_prey_milestone_logger.log_run_start(self)

    def reset_predator_prey_adaptive_tuning(self) -> None:
        """Restore adaptive dials to their baseline values and clear stability history."""
        state = self._predator_prey_state
        tuning = state.adaptive_tuning
        if (
            tuning.trial_active
            and tuning.previous_values
        ):
            baseline_values = dict(tuning.previous_values)
        else:
            baseline_values = dict(tuning.baseline_values)
        if not baseline_values:
            baseline_values = self._default_predator_prey_dial_values()
        tuning.baseline_values = dict(baseline_values)
        tuning.current_values = dict(baseline_values)
        tuning.previous_values = dict(baseline_values)
        tuning.trial_candidate_values = {}
        tuning.trial_active = False
        tuning.trial_phase = "candidate"
        tuning.trial_dial = None
        tuning.trial_direction = 0
        tuning.trial_baseline_average = 0.0
        tuning.trial_id = None
        tuning.trial_seeds = []
        tuning.trial_seed_index = 0
        tuning.trial_candidate_results = []
        tuning.trial_baseline_results = []
        tuning.trial_candidate_pressures = []
        tuning.trial_baseline_pressures = []
        tuning.trial_trigger_reason = None
        tuning.last_decision = "reset_to_baseline"
        tuning.last_decision_basis = None
        tuning.last_decision_trial_id = None
        tuning.last_decision_survival_median_candidate = None
        tuning.last_decision_survival_median_baseline = None
        tuning.last_decision_near_extinction_candidate = None
        tuning.last_decision_near_extinction_baseline = None
        tuning.last_decision_pending_log = False
        tuning.post_run_trial_decision = "reset_to_baseline"
        tuning.non_improving_run_streak = 0
        tuning.consecutive_immediate_retry_trials = 0
        tuning.retry_cap_waiting_for_ordinary_run = False
        tuning.last_trial_launch_blocked_by_retry_cap = False
        state.run_history.clear()
        state.highest_survival_ticks = 0
        state.predator_low_ticks = 0
        state.prey_low_ticks = 0
        state.predator_zero_ticks = 0
        state.prey_zero_ticks = 0
        state.collapse_dial_values = {}
        state.collapse_trial_dial = None
        state.collapse_trial_phase = None
        state.collapse_trial_seed = None
        state.collapse_trial_id = None
        state.collapse_trial_trigger_reason = None
        state.collapse_trial_delta = 0.0
        state.collapse_trial_value = None
        state.collapse_trial_decision = "none"
        state.collapse_rolling_average = 0.0
        state.collapse_beat_average = False
        state.collapse_was_new_highest = False
        self._apply_predator_prey_tuning_values(tuning.current_values)
        if self._predator_prey_run_logger is not None:
            self._predator_prey_run_logger.log_dial_reset(self)
        if self._predator_prey_milestone_logger is not None:
            self._predator_prey_milestone_logger.log_dial_reset(self)

    # ------------------------------------------------------------------
    # Boids mode
    # ------------------------------------------------------------------

    def _step_boids(self) -> None:
        """Flocking simulation — energy from being in a well-formed flock."""
        self._frame += 1
        # No food in boids mode
        self.active_attacks.clear()

        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []
        dead_causes: dict[int, str] = {}

        overcrowding_penalty = self._get_overcrowding_penalty()
        creature_bucket = self._build_creature_bucket()

        # Shared boids neighbor cache for this frame.
        boid_neighbors = self._build_boid_neighbor_cache_and_assignments(
            creature_bucket
        )

        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate
        speed_base = self.settings.creature_speed_base

        for creature in self.creatures:
            if self._queue_preexisting_death(creature, dead_creatures, dead_causes):
                continue
            (
                sep_fx,
                sep_fy,
                align_fx,
                align_fy,
                coh_fx,
                coh_fy,
                n_neighbors,
                alignment_score,
                crowding_score,
                nearest_distance,
                mean_distance,
                _sep_mag,
                _coh_mag,
            ) = self._compute_boid_forces(
                creature,
                boid_neighbors.get(id(creature), []),
            )
            wander_fx, wander_fy = self._compute_boid_wander_force(
                creature,
                neighbor_count=n_neighbors,
                crowding_score=crowding_score,
            )

            # Apply flocking forces
            creature.vx += sep_fx + align_fx + coh_fx + wander_fx
            creature.vy += sep_fy + align_fy + coh_fy + wander_fy

            # Clamp to max speed
            max_speed = creature.genome.speed * speed_base * self._get_creature_speed_scale(creature)
            speed = math.sqrt(creature.vx ** 2 + creature.vy ** 2)
            if speed > max_speed and speed > 0:
                creature.vx = creature.vx / speed * max_speed
                creature.vy = creature.vy / speed * max_speed

            if n_neighbors == 0:
                creature.wander(speed_base, speed_scale=self._get_creature_speed_scale(creature))

            creature.update_position(1.0, self.width, self.height)

            self._update_boid_energy(
                creature,
                neighbor_count=n_neighbors,
                alignment_score=alignment_score,
                crowding_score=crowding_score,
                nearest_distance=nearest_distance,
                mean_distance=mean_distance,
            )

            # Overcrowding penalty
            creature.energy = max(
                0.0,
                creature.energy - self._get_creature_movement_cost(creature) * overcrowding_penalty,
            )
            if overcrowding_penalty > 0.0:
                creature.energy = max(
                    0.0,
                    creature.energy - (0.00025 * overcrowding_penalty),
                )

            if random.random() < cosmic_rate:
                self._apply_cosmic_ray(creature)

            if (
                creature.energy >= self._get_reproduction_threshold(creature)
                and alignment_score >= 0.35
                and 2 <= n_neighbors <= 9
                and crowding_score < 0.55
            ):
                offspring = self._reproduce_boids(
                    creature,
                    mutation_rate,
                    queued_births=len(new_creatures),
                )
                if offspring:
                    new_creatures.append(offspring)

            if creature.energy <= 0:
                self._queue_creature_death(
                    creature,
                    dead_creatures,
                    dead_causes,
                    self._resolve_death_cause(creature),
                )
            elif creature.age >= creature.get_max_lifespan():
                self._queue_creature_death(creature, dead_creatures, dead_causes, "age")

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._sweep_frame_deaths(dead_creatures, dead_causes)
        self._process_deaths(dead_creatures, dead_causes)

        # Phase-sync glyph pulses within flocks
        self._update_boids_glyph_phases()

    def _build_boid_neighbor_cache_and_assignments(
        self, bucket: dict[tuple[int, int], list[Creature]]
    ) -> dict[int, list[tuple[Creature, float, float, float]]]:
        """
        Build directed neighbor lists and flock assignments for boids in one pass.

        Each qualifying nearby pair is evaluated once from the shared creature
        bucket, then contributes directed neighbor entries according to each
        creature's sense radius. Flock connected components are derived from
        the same pair pass so boids mode does not pay for a second graph walk
        over duplicate adjacency data every frame.
        """
        creatures = self.creatures
        creature_count = len(creatures)
        neighbor_cache: dict[int, list[tuple[Creature, float, float, float]]] = {
            id(creature): [] for creature in creatures
        }
        if creature_count == 0:
            self._flock_sizes = {}
            self._flock_count = 0
            return neighbor_cache

        creature_index = {
            id(creature): index for index, creature in enumerate(creatures)
        }
        sense_sq_by_id = {
            id(creature): (
                creature.get_effective_sense_radius(
                    multiplier=(
                        self._get_effective_phenotype(creature).sense_radius_mult
                        * _BOIDS_NEIGHBOR_SENSE_SCALE
                    )
                )
            ) ** 2
            for creature in creatures
        }
        flock_link_sq_by_id = {
            id(creature): (
                creature.get_effective_sense_radius(
                    multiplier=(
                        self._get_effective_phenotype(creature).sense_radius_mult
                        * _BOIDS_FLOCK_LINK_SCALE
                    )
                )
            ) ** 2
            for creature in creatures
        }

        parent = list(range(creature_count))
        component_size = [1] * creature_count

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left_index: int, right_index: int) -> None:
            left_root = find(left_index)
            right_root = find(right_index)
            if left_root == right_root:
                return
            if component_size[left_root] < component_size[right_root]:
                left_root, right_root = right_root, left_root
            parent[right_root] = left_root
            component_size[left_root] += component_size[right_root]

        bs = self._CREATURE_BUCKET_SIZE
        gw = max(1, self.width // bs + 1)
        gh = max(1, self.height // bs + 1)

        for key, bucket_members in bucket.items():
            self._collect_boid_neighbor_pairs(
                bucket_members,
                bucket_members,
                same_bucket=True,
                sense_sq_by_id=sense_sq_by_id,
                flock_link_sq_by_id=flock_link_sq_by_id,
                creature_index=creature_index,
                neighbor_cache=neighbor_cache,
                union=union,
            )
            for off_x, off_y in ((1, -1), (1, 0), (1, 1), (0, 1)):
                neighbor_key = ((key[0] + off_x) % gw, (key[1] + off_y) % gh)
                if neighbor_key == key:
                    continue
                neighbor_members = bucket.get(neighbor_key)
                if not neighbor_members:
                    continue
                self._collect_boid_neighbor_pairs(
                    bucket_members,
                    neighbor_members,
                    same_bucket=False,
                    sense_sq_by_id=sense_sq_by_id,
                    flock_link_sq_by_id=flock_link_sq_by_id,
                    creature_index=creature_index,
                    neighbor_cache=neighbor_cache,
                    union=union,
                )

        flock_sizes_by_root: dict[int, int] = {}
        for index in range(creature_count):
            root = find(index)
            flock_sizes_by_root[root] = flock_sizes_by_root.get(root, 0) + 1

        flock_sizes: dict[int, int] = {}
        flock_id_by_root: dict[int, int] = {}
        next_flock_id = 0
        for index, creature in enumerate(creatures):
            root = find(index)
            size = flock_sizes_by_root[root]
            if size <= 1:
                creature.flock_id = -1
                continue
            flock_id = flock_id_by_root.get(root)
            if flock_id is None:
                flock_id = next_flock_id
                flock_id_by_root[root] = flock_id
                flock_sizes[flock_id] = size
                next_flock_id += 1
            creature.flock_id = flock_id

        self._flock_sizes = flock_sizes
        self._flock_count = len(flock_sizes)
        return neighbor_cache

    def _collect_boid_neighbor_pairs(
        self,
        left_members: list[Creature],
        right_members: list[Creature],
        *,
        same_bucket: bool,
        sense_sq_by_id: dict[int, float],
        flock_link_sq_by_id: dict[int, float],
        creature_index: dict[int, int],
        neighbor_cache: dict[int, list[tuple[Creature, float, float, float]]],
        union: Any,
    ) -> None:
        """Populate boid directed neighbor lists for one or two bucket groups."""
        for left_offset, left in enumerate(left_members):
            start_index = left_offset + 1 if same_bucket else 0
            left_id = id(left)
            left_neighbors = neighbor_cache[left_id]
            left_sense_sq = sense_sq_by_id[left_id]
            left_index = creature_index[left_id]
            for right in right_members[start_index:]:
                right_id = id(right)
                dx, dy = self._wrapped_delta(left.x, left.y, right.x, right.y)
                dist_sq = dx * dx + dy * dy
                left_can_sense = dist_sq < left_sense_sq
                right_can_sense = dist_sq < sense_sq_by_id[right_id]
                if not left_can_sense and not right_can_sense:
                    continue
                if left_can_sense:
                    left_neighbors.append((right, dx, dy, dist_sq))
                if right_can_sense:
                    neighbor_cache[right_id].append((left, -dx, -dy, dist_sq))
                if (
                    dist_sq < flock_link_sq_by_id[left_id]
                    and dist_sq < flock_link_sq_by_id[right_id]
                ):
                    union(left_index, creature_index[right_id])

    def _compute_boid_forces(
        self, creature: Creature, neighbors: list[tuple[Creature, float, float, float]]
    ) -> tuple[float, float, float, float, float, float, int, float, float, float, float, float, float]:
        """
        Compute separation, alignment, and cohesion forces for a boid.

        Strengths: separation=aggression, alignment=conformity, cohesion=efficiency.

        Returns:
            (
                sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy,
                n_neighbors, alignment_score, crowding_score,
                nearest_distance, mean_distance, separation_mag, cohesion_mag,
            )
        """
        if not neighbors:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

        n = len(neighbors)
        body_radius = creature.get_radius()
        preferred_spacing = body_radius * _BOIDS_PREFERRED_SPACING_SCALE
        separation_range = preferred_spacing * _BOIDS_SEPARATION_RANGE_SCALE
        close_range = body_radius * _BOIDS_CLOSE_SEPARATION_SCALE

        sep_x = sep_y = 0.0
        sum_vx = sum_vy = 0.0
        sum_dx = sum_dy = 0.0
        sum_distance = 0.0
        nearest_distance = float("inf")
        local_density = 0.0

        for other, dx, dy, dist_sq in neighbors:
            sum_vx += other.vx
            sum_vy += other.vy
            sum_dx += dx
            sum_dy += dy

            if dist_sq <= 1e-6:
                continue

            dist = math.sqrt(dist_sq)
            sum_distance += dist
            nearest_distance = min(nearest_distance, dist)
            closeness = max(0.0, 1.0 - (dist / separation_range))
            local_density += closeness

            if dist < separation_range:
                inv_dist = 1.0 / dist
                close_pressure = max(0.0, 1.0 - (dist / close_range))
                weight = (
                    (closeness * closeness)
                    + (close_pressure * close_pressure * _BOIDS_SEPARATION_CLOSE_BOOST)
                )
                sep_x += (-dx * inv_dist) * weight
                sep_y += (-dy * inv_dist) * weight

        if nearest_distance == float("inf"):
            nearest_distance = 0.0
        mean_distance = sum_distance / n if n > 0 else 0.0
        crowding_from_density = min(1.0, local_density / max(1.0, n * 0.6))
        crowding_from_spacing = 0.0
        if nearest_distance > 0.0:
            crowding_from_spacing = max(
                0.0,
                min(1.0, (preferred_spacing - nearest_distance) / preferred_spacing),
            )
        crowding_from_count = max(
            0.0,
            min(
                1.0,
                (n - _BOIDS_TARGET_NEIGHBORS)
                / (_BOIDS_SOFT_MAX_NEIGHBORS - _BOIDS_TARGET_NEIGHBORS + 2.0),
            ),
        )
        crowding_score = max(
            crowding_from_density,
            crowding_from_spacing,
            crowding_from_count,
        )

        sep_strength = (0.18 + creature.genome.aggression * 0.32) * (
            1.0 + crowding_score * 0.9
        )
        sep_fx = sep_x * sep_strength
        sep_fy = sep_y * sep_strength

        avg_vx = sum_vx / n
        avg_vy = sum_vy / n
        my_speed = math.sqrt(creature.vx * creature.vx + creature.vy * creature.vy)
        avg_speed = math.sqrt(avg_vx * avg_vx + avg_vy * avg_vy)
        alignment_dot = 0.0
        if my_speed > 0.01 and avg_speed > 0.01:
            alignment_dot = (
                (creature.vx * avg_vx + creature.vy * avg_vy) / (my_speed * avg_speed)
            )
        alignment_score = max(0.0, alignment_dot)

        align_strength = creature.genome.conformity * _BOIDS_ALIGNMENT_BASE * max(
            0.35,
            1.0 - (crowding_score * 0.45),
        )
        align_fx = (avg_vx - creature.vx) * align_strength
        align_fy = (avg_vy - creature.vy) * align_strength

        avg_dx = sum_dx / n
        avg_dy = sum_dy / n
        dist_to_centroid_sq = avg_dx * avg_dx + avg_dy * avg_dy
        if dist_to_centroid_sq > 1e-6:
            dist_to_centroid = math.sqrt(dist_to_centroid_sq)
            inv_dist = 1.0 / dist_to_centroid
            isolation_score = max(
                0.0,
                min(1.0, (_BOIDS_TARGET_NEIGHBORS - n) / _BOIDS_TARGET_NEIGHBORS),
            )
            centroid_pull = max(
                0.0,
                min(
                    1.0,
                    (
                        dist_to_centroid - (preferred_spacing * 0.55)
                    ) / (preferred_spacing * 1.45),
                ),
            )
            coh_drive = centroid_pull * max(
                0.0,
                0.45 + (isolation_score * 0.9) - (crowding_score * 0.60),
            )
            coh_strength = creature.genome.efficiency * _BOIDS_COHESION_BASE * coh_drive
            coh_fx = avg_dx * inv_dist * coh_strength
            coh_fy = avg_dy * inv_dist * coh_strength
        else:
            coh_fx = coh_fy = 0.0

        return (
            sep_fx,
            sep_fy,
            align_fx,
            align_fy,
            coh_fx,
            coh_fy,
            n,
            alignment_score,
            crowding_score,
            nearest_distance,
            mean_distance,
            math.hypot(sep_fx, sep_fy),
            math.hypot(coh_fx, coh_fy),
        )

    def _compute_boid_wander_force(
        self,
        creature: Creature,
        *,
        neighbor_count: int,
        crowding_score: float,
    ) -> tuple[float, float]:
        """Add smooth, low-frequency local variation so schools do not move rigidly."""
        frequency = 0.028 + creature.genome.motion_style * 0.042
        phase = (
            (self._frame * frequency)
            + (creature.lineage_id * 0.61803398875)
            + (creature.genome.hue * math.tau)
        )
        speed = math.hypot(creature.vx, creature.vy)
        if speed > 0.01:
            heading_x = creature.vx / speed
            heading_y = creature.vy / speed
        else:
            heading_x = math.cos(phase)
            heading_y = math.sin(phase)
        perp_x = -heading_y
        perp_y = heading_x
        individuality = 0.25 + (1.0 - creature.genome.conformity) * 0.75
        flock_tension = 1.0 if neighbor_count == 0 else (0.55 + crowding_score * 0.65)
        amplitude = _BOIDS_WANDER_BASE * individuality * flock_tension
        lateral = math.sin(phase)
        forward = math.cos((phase * 0.61) + (creature.genome.motion_style * math.pi))
        return (
            ((perp_x * lateral) + (heading_x * forward * 0.25)) * amplitude,
            ((perp_y * lateral) + (heading_y * forward * 0.25)) * amplitude,
        )

    def _update_boid_energy(
        self,
        creature: Creature,
        *,
        neighbor_count: int,
        alignment_score: float,
        crowding_score: float,
        nearest_distance: float,
        mean_distance: float,
    ) -> None:
        """Reward moderate, well-spaced local flocking while penalizing crowding."""
        if neighbor_count <= 0:
            creature.energy = max(0.0, creature.energy - 0.0007)
            return

        preferred_spacing = creature.get_radius() * _BOIDS_PREFERRED_SPACING_SCALE
        count_score = max(
            0.0,
            1.0 - (
                abs(neighbor_count - _BOIDS_TARGET_NEIGHBORS)
                / 4.0
            ),
        )
        spacing_score = 0.0
        if nearest_distance > 0.0:
            spacing_score = max(
                0.0,
                1.0
                - (
                    abs(nearest_distance - (preferred_spacing * 0.95))
                    / (preferred_spacing * 0.75)
                ),
            )
        mean_spacing_score = 0.0
        if mean_distance > 0.0:
            mean_spacing_score = max(
                0.0,
                1.0
                - (
                    abs(mean_distance - (preferred_spacing * 1.25))
                    / preferred_spacing
                ),
            )
        formation_score = max(
            0.0,
            (alignment_score * 0.42)
            + (spacing_score * 0.33)
            + (mean_spacing_score * 0.15)
            + (count_score * 0.10),
        )
        creature.energy = min(
            1.0,
            creature.energy + (_BOIDS_ENERGY_REGEN_BASE * formation_score),
        )
        if neighbor_count < _BOIDS_MIN_NEIGHBORS:
            creature.energy = max(
                0.0,
                creature.energy - (0.00035 * (_BOIDS_MIN_NEIGHBORS - neighbor_count)),
            )
        if crowding_score > 0.0:
            creature.energy = max(
                0.0,
                creature.energy - (0.00075 * crowding_score),
            )
        if neighbor_count > _BOIDS_SOFT_MAX_NEIGHBORS:
            creature.energy = max(
                0.0,
                creature.energy
                - (0.00020 * (neighbor_count - _BOIDS_SOFT_MAX_NEIGHBORS)),
            )

    def _update_boids_glyph_phases(self) -> None:
        """Lerp each creature's glyph pulse phase toward its flock average."""
        flock_members: dict[int, list[Creature]] = {}
        for c in self.creatures:
            if c.flock_id != -1:
                flock_members.setdefault(c.flock_id, []).append(c)

        for members in flock_members.values():
            if len(members) < 2:
                continue
            # Circular average of phases
            avg_sin = sum(math.sin(m._glyph_phase) for m in members) / len(members)
            avg_cos = sum(math.cos(m._glyph_phase) for m in members) / len(members)
            avg_phase = math.atan2(avg_sin, avg_cos)

            for m in members:
                diff = avg_phase - m._glyph_phase
                # Wrap to [-π, π]
                while diff > math.pi:
                    diff -= 2 * math.pi
                while diff < -math.pi:
                    diff += 2 * math.pi
                m._glyph_phase += diff * 0.05

    def _reproduce_boids(
        self,
        creature: Creature,
        mutation_rate: float,
        *,
        queued_births: int = 0,
    ) -> Creature | None:
        """Reproduce in boids mode."""
        if not self._can_queue_birth(queued_births):
            return None

        creature.energy /= 2
        offspring_genome = creature.genome.mutate(mutation_rate)
        offspring_lineage = self._branch_lineage_id(
            creature.lineage_id,
            creature.genome,
            offspring_genome,
        )

        offspring = Creature(
            x=(creature.x + random.uniform(-10, 10)) % self.width,
            y=(creature.y + random.uniform(-10, 10)) % self.height,
            genome=offspring_genome,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=creature.energy,
            lineage_id=offspring_lineage,
            _glyph_phase=offspring_genome.hue * 6.28,
        )

        self.generation += 1
        self.total_births += 1
        return offspring

    # ------------------------------------------------------------------
    # Drift mode
    # ------------------------------------------------------------------

    def _step_drift(self) -> None:
        """
        Dreamlike drift mode — no selection pressure, pure mutation drift.

        Energy regenerates passively. No food. Die only of old age.
        """
        self._frame += 1
        # No food spawning
        self.active_attacks.clear()

        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []
        dead_causes: dict[int, str] = {}

        # Cosmic ray rate doubled in drift
        cosmic_rate = self._get_mode_param("cosmic_ray_rate", self.settings.cosmic_ray_rate * 2)
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)

        for creature in self.creatures:
            if self._queue_preexisting_death(creature, dead_creatures, dead_causes):
                continue
            # Passive energy regen — no cost for movement
            creature.energy = min(1.0, creature.energy + 0.002)

            # Meditative glide wander (ignores motion_style)
            self._drift_wander(creature)

            # Soft edge repulsion
            self._drift_edge_repulsion(creature)

            # Position update without swim oscillation; doubled trail length
            self._drift_update_position(creature)

            # Zone effect — very soft, no kill
            zone_strength = self._get_mode_param("zone_strength", 0.6)
            if zone_strength > 0:
                zone_mult = self.zone_manager.get_energy_modifier(creature)
                zone_nudge = (zone_mult - 1.0) * zone_strength * 0.0005
                creature.energy = max(0.0, min(1.0, creature.energy + zone_nudge))

            if random.random() < cosmic_rate:
                self._apply_cosmic_ray(creature)

            if creature.energy >= self._get_reproduction_threshold(creature):
                offspring = self._reproduce_drift(
                    creature,
                    mutation_rate,
                    queued_births=len(new_creatures),
                )
                if offspring:
                    new_creatures.append(offspring)

            # Drift: die only of old age
            if creature.age >= creature.get_max_lifespan():
                self._queue_creature_death(creature, dead_creatures, dead_causes, "age")

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._sweep_frame_deaths(dead_creatures, dead_causes)
        self._process_deaths(dead_creatures, dead_causes)

    def _drift_wander(self, creature: Creature) -> None:
        """Meditative glide — slow, smoothly curving paths."""
        speed_base = self.settings.creature_speed_base * 0.25
        current_speed = math.sqrt(creature.vx ** 2 + creature.vy ** 2)

        if current_speed < 0.01:
            angle = random.uniform(0, 2 * math.pi)
            target_speed = (
                creature.genome.speed
                * speed_base
                * self._get_creature_speed_scale(creature)
                * 0.3
            )
            creature.vx = math.cos(angle) * target_speed
            creature.vy = math.sin(angle) * target_speed
            # _swim_phase repurposed: stores rotation direction (+/-) for drift
            creature._swim_phase = 1.0 if random.random() < 0.5 else -1.0
            return

        angle = math.atan2(creature.vy, creature.vx)
        rotation_dir = 1.0 if creature._swim_phase >= 0 else -1.0
        # Very slow rotation proportional to speed genome trait
        rotation_rate = creature.genome.speed * 0.3 * 0.008
        angle += rotation_dir * rotation_rate

        max_speed = creature.genome.speed * speed_base * self._get_creature_speed_scale(creature)
        target_speed = min(current_speed + 0.01, max_speed)
        creature.vx = math.cos(angle) * target_speed
        creature.vy = math.sin(angle) * target_speed

    def _drift_edge_repulsion(self, creature: Creature) -> None:
        """Gentle push toward center when creature drifts near the boundary."""
        margin = min(self.width, self.height) * 0.08
        if creature.x < margin:
            creature.vx += (margin - creature.x) / margin * 0.08
        elif creature.x > self.width - margin:
            creature.vx -= (creature.x - (self.width - margin)) / margin * 0.08

        if creature.y < margin:
            creature.vy += (margin - creature.y) / margin * 0.08
        elif creature.y > self.height - margin:
            creature.vy -= (creature.y - (self.height - margin)) / margin * 0.08

    def _drift_update_position(self, creature: Creature) -> None:
        """
        Position update for drift mode.

        Skips swim oscillation (always glide feel).
        Halves glyph rotation speed.
        Doubles trail length.
        """
        # Aging speed reduction
        age_mult = creature.get_age_speed_mult()
        if age_mult < 1.0:
            creature.vx *= age_mult
            creature.vy *= age_mult

        creature.x = (creature.x + creature.vx) % self.width
        creature.y = (creature.y + creature.vy) % self.height

        # Halved rotation speed for dreamy feel
        rot_deg_per_frame = creature.genome.rotation_speed * 1.0
        creature.rotation_angle = (creature.rotation_angle + rot_deg_per_frame) % 360.0

        # Doubled trail length
        creature.trail.append((creature.x, creature.y))
        max_trail = creature.get_trail_length() * 2
        if len(creature.trail) > max_trail:
            creature.trail.pop(0)

        creature.age += 1

    def _reproduce_drift(
        self,
        creature: Creature,
        mutation_rate: float,
        *,
        queued_births: int = 0,
    ) -> Creature | None:
        """Reproduce in drift mode — offspring appears at same position."""
        if not self._can_queue_birth(queued_births):
            return None

        creature.energy /= 2
        offspring_genome = creature.genome.mutate(mutation_rate)
        offspring_lineage = self._branch_lineage_id(
            creature.lineage_id,
            creature.genome,
            offspring_genome,
        )

        # Offspring drifts away slowly from parent
        drift_angle = random.uniform(0, 2 * math.pi)
        drift_speed = self.settings.creature_speed_base * 0.1

        offspring = Creature(
            x=creature.x,
            y=creature.y,
            genome=offspring_genome,
            vx=math.cos(drift_angle) * drift_speed,
            vy=math.sin(drift_angle) * drift_speed,
            energy=creature.energy,
            lineage_id=offspring_lineage,
            _glyph_phase=offspring_genome.hue * 6.28,
        )

        self.generation += 1
        self.total_births += 1
        return offspring

    # ------------------------------------------------------------------
    # Food spawning
    # ------------------------------------------------------------------

    def _spawn_food(self) -> None:
        """Spawn food particles using sinusoidal boom/bust cycle rate."""
        rate = self._get_food_rate()
        spawn_count = int(rate)
        if random.random() < (rate - spawn_count):
            spawn_count += 1
        if self.settings.sim_mode == "predator_prey":
            for _ in range(spawn_count):
                self.food_manager.spawn(
                    depth_band=self._choose_predator_prey_food_depth_band()
                )
            return
        self.food_manager.spawn_batch(spawn_count)

    def _choose_predator_prey_food_depth_band(self) -> int:
        """Sample a bounded food depth band for predator-prey ecology."""
        roll = random.random()
        total = 0.0
        for band, weight in _PREDATOR_PREY_FOOD_DEPTH_WEIGHTS:
            total += weight
            if roll <= total:
                return band
        return DEPTH_DEEP

    def _get_food_rate(self) -> float:
        """Current food spawn rate accounting for the boom/bust cycle."""
        base_rate = float(
            self._get_mode_param("food_spawn_rate", self.settings.food_spawn_rate)
        )
        # Corrective compatibility path: existing configs often persisted the old
        # energy default of 0.6, which now collapses too easily in interactive runs.
        if self.settings.sim_mode == "energy" and math.isclose(base_rate, 0.6, abs_tol=1e-9):
            base_rate = 0.8
        if not self.settings.food_cycle_enabled:
            return base_rate
        period = max(1, self.settings.food_cycle_period)
        t = self._frame / period
        cycle_phase = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        amplitude = max(0.0, min(1.0, self._get_food_cycle_amplitude()))
        multiplier = (1.0 - amplitude) + (amplitude * cycle_phase)
        return max(0.0, base_rate * multiplier)

    # ------------------------------------------------------------------
    # Food seeking
    # ------------------------------------------------------------------

    def _creature_seek_food(
        self, creature: Creature, sense_override: float | None = None
    ) -> None:
        """Handle creature food-seeking behaviour."""
        sense_radius = self._get_effective_sensing_range(
            creature,
            absolute_radius=sense_override,
        )
        nearest_food = self._find_nearest_food_for_creature(creature, sense_radius)

        if nearest_food:
            sensed_food = self._sense_target_position(
                creature,
                nearest_food.x,
                nearest_food.y,
                absolute_radius=sense_override,
                target_depth_band=nearest_food.depth_band,
            )
            if sensed_food is None:
                creature.wander(
                    self.settings.creature_speed_base,
                    speed_scale=self._get_creature_speed_scale(creature),
                )
                return

            creature.steer_toward(
                sensed_food[0], sensed_food[1],
                self.settings.creature_speed_base,
                self.width, self.height,
                speed_scale=self._get_creature_speed_scale(creature),
            )

            eat_distance = creature.get_radius() + 3
            dist = creature.distance_to(nearest_food.x, nearest_food.y, self.width, self.height)

            if dist < eat_distance:
                eff_bonus = 1.20 if creature.genome.aggression < 0.4 else 1.0
                energy_gain = (
                    nearest_food.energy
                    * (0.5 + creature.genome.efficiency * 0.5)
                    * eff_bonus
                    * self._get_creature_food_efficiency_multiplier(creature)
                )
                if (
                    self.settings.sim_mode == "predator_prey"
                    and creature.species == "predator"
                ):
                    energy_gain *= self._get_predator_food_efficiency_multiplier()
                creature.energy = min(1.0, creature.energy + energy_gain)
                self.food_manager.remove(nearest_food)
        else:
            creature.wander(
                self.settings.creature_speed_base,
                speed_scale=self._get_creature_speed_scale(creature),
            )

    def _find_nearest_food_for_creature(
        self,
        creature: Creature,
        sense_radius: float,
    ):
        """Find food, keeping predator-prey access bounded by the creature's band."""
        if self.settings.sim_mode != "predator_prey":
            return self.food_manager.find_nearest(creature.x, creature.y, sense_radius)

        nearest_food = self.food_manager.find_nearest(
            creature.x,
            creature.y,
            sense_radius,
            depth_band=creature.depth_band,
        )
        if nearest_food is not None:
            return nearest_food

        preferred_band = creature.get_preferred_depth_band()
        target_band: int | None = None
        target_food = None
        best_score = float("inf")
        for band in DEPTH_BANDS:
            if band == creature.depth_band:
                continue
            candidate = self.food_manager.find_nearest(
                creature.x,
                creature.y,
                sense_radius,
                depth_band=band,
            )
            if candidate is None:
                continue
            distance = creature.distance_to(candidate.x, candidate.y, self.width, self.height)
            score = distance + depth_band_separation(creature.depth_band, band) * 30.0
            if score < best_score:
                best_score = score
                target_band = band
                target_food = candidate

        if target_band is not None:
            if target_band != preferred_band or creature.energy < 0.35:
                self._update_predator_prey_depth_band(
                    creature,
                    target_band,
                    urgency=0.22,
                )
            else:
                self._update_predator_prey_depth_band(
                    creature,
                    preferred_band,
                    urgency=0.12,
                )
            if creature.depth_band == target_band:
                return target_food

        self._update_predator_prey_depth_band(
            creature,
            preferred_band,
            urgency=0.08,
        )
        return None

    def _update_predator_prey_depth_band(
        self,
        creature: Creature,
        target_band: int,
        *,
        urgency: float,
        extra_transition_mult: float = 1.0,
    ) -> None:
        """Move a predator-prey creature by at most one bounded band."""
        if self.settings.sim_mode != "predator_prey":
            return
        target = clamp_depth_band(target_band)
        creature.clamp_depth_band()
        if creature.depth_band == target:
            return
        urgency *= self._get_effective_phenotype(creature).depth_transition_mult
        urgency *= max(0.5, min(1.5, extra_transition_mult))
        if random.random() < max(0.0, min(1.0, urgency)):
            creature.depth_band = step_depth_band_toward(creature.depth_band, target)

    def _pick_depth_escape_band(self, creature: Creature, threat_band: int) -> int:
        """Choose a non-threat band closest to the creature preference."""
        preferred_band = creature.get_preferred_depth_band()
        candidates = [band for band in DEPTH_BANDS if band != clamp_depth_band(threat_band)]
        return min(
            candidates,
            key=lambda band: (
                depth_band_separation(band, preferred_band),
                depth_band_separation(band, creature.depth_band),
                band,
            ),
        )

    # ------------------------------------------------------------------
    # Creature spatial bucket
    # ------------------------------------------------------------------

    _CREATURE_BUCKET_SIZE = 150  # pixels per grid cell

    def _build_creature_bucket(self) -> dict[tuple[int, int], list[Creature]]:
        """Build a spatial hash of living creatures for O(1) neighbour lookup."""
        bucket: dict[tuple[int, int], list[Creature]] = {}
        bs = self._CREATURE_BUCKET_SIZE
        gw = max(1, self.width // bs + 1)
        gh = max(1, self.height // bs + 1)
        for c in self.creatures:
            key = (int(c.x // bs) % gw, int(c.y // bs) % gh)
            if key not in bucket:
                bucket[key] = []
            bucket[key].append(c)
        return bucket

    def _nearby_creatures(
        self,
        x: float,
        y: float,
        radius: float,
        bucket: dict[tuple[int, int], list[Creature]],
    ) -> list[Creature]:
        """Return creatures within approximate radius using the spatial bucket."""
        bs = self._CREATURE_BUCKET_SIZE
        gw = max(1, self.width // bs + 1)
        gh = max(1, self.height // bs + 1)
        cells = int(radius // bs) + 1
        cx = int(x // bs)
        cy = int(y // bs)
        result: list[Creature] = []
        dedupe_cells = (cells * 2 + 1) > gw or (cells * 2 + 1) > gh
        seen_cells: set[tuple[int, int]] = set()
        for dx in range(-cells, cells + 1):
            for dy in range(-cells, cells + 1):
                key = ((cx + dx) % gw, (cy + dy) % gh)
                if dedupe_cells:
                    if key in seen_cells:
                        continue
                    seen_cells.add(key)
                result.extend(bucket.get(key, []))
        return result

    def _distance_sq(self, ax: float, ay: float, bx: float, by: float) -> float:
        """Toroidal squared distance helper."""
        dx = abs(bx - ax)
        dy = abs(by - ay)
        if dx > self.width / 2:
            dx = self.width - dx
        if dy > self.height / 2:
            dy = self.height - dy
        return dx * dx + dy * dy

    def _wrapped_delta(
        self, ax: float, ay: float, bx: float, by: float
    ) -> tuple[float, float]:
        """Shortest toroidal delta vector from (ax, ay) to (bx, by)."""
        dx = bx - ax
        dy = by - ay
        if abs(dx) > self.width / 2:
            dx -= math.copysign(self.width, dx)
        if abs(dy) > self.height / 2:
            dy -= math.copysign(self.height, dy)
        return dx, dy

    # ------------------------------------------------------------------
    # Hunting / predation (energy mode)
    # ------------------------------------------------------------------

    def _creature_hunt(
        self, creature: Creature, bucket: dict[tuple[int, int], list[Creature]]
    ) -> bool:
        """Hunter behaviour for energy mode."""
        sense = self._get_effective_sensing_range(creature, multiplier=1.5)
        my_radius = creature.get_radius()
        max_prey_radius = my_radius * 1.3

        best_prey: Creature | None = None
        best_dist_sq = sense * sense

        for other in self._nearby_creatures(creature.x, creature.y, sense, bucket):
            if other is creature:
                continue
            if other.energy <= 0.0:
                continue
            if other.get_radius() > max_prey_radius:
                continue
            dist_sq = self._distance_sq(creature.x, creature.y, other.x, other.y)
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_prey = other

        if best_prey is None:
            return False

        sensed_prey = self._sense_target_position(
            creature,
            best_prey.x,
            best_prey.y,
            sense_multiplier=1.5,
        )
        if sensed_prey is None:
            return False

        creature.steer_toward(
            sensed_prey[0], sensed_prey[1],
            self.settings.creature_speed_base,
            self.width, self.height,
            speed_scale=self._get_creature_speed_scale(creature),
        )

        attack_range = my_radius * 4 * self._get_creature_predation_contact_multiplier(creature)
        if best_dist_sq < (attack_range * attack_range):
            size_ratio = min(2.0, max(0.5, my_radius / max(1.0, best_prey.get_radius())))
            drain = (
                creature.genome.aggression
                * 0.008
                * size_ratio
                * self._get_creature_predation_contact_multiplier(creature)
            )
            transfer = min(drain, best_prey.energy)
            if transfer > 0:
                best_prey.energy = max(0.0, best_prey.energy - transfer)
                creature.energy = min(1.0, creature.energy + transfer)
                self.active_attacks.append((
                    creature.x, creature.y,
                    best_prey.x, best_prey.y,
                    creature.species,
                    creature.genome.hue,
                    creature.genome.saturation,
                ))

        return True

    def _creature_opportunist_attack(
        self, creature: Creature, bucket: dict[tuple[int, int], list[Creature]]
    ) -> None:
        """Opportunist behaviour for energy mode."""
        my_radius = creature.get_radius()
        attack_range = my_radius * 2.5 * self._get_creature_predation_contact_multiplier(creature)
        prey_size_limit = my_radius * 0.6

        for other in self._nearby_creatures(creature.x, creature.y, attack_range, bucket):
            if other is creature:
                continue
            if other.energy <= 0.0:
                continue
            if other.get_radius() >= prey_size_limit:
                continue
            dist_sq = self._distance_sq(creature.x, creature.y, other.x, other.y)
            if dist_sq < (attack_range * attack_range):
                drain = (
                    creature.genome.aggression
                    * 0.008
                    * self._get_creature_predation_contact_multiplier(creature)
                )
                transfer = min(drain, other.energy)
                if transfer > 0:
                    other.energy = max(0.0, other.energy - transfer)
                    creature.energy = min(1.0, creature.energy + transfer)
                    self.active_attacks.append((
                        creature.x, creature.y,
                        other.x, other.y,
                        creature.species,
                        creature.genome.hue,
                        creature.genome.saturation,
                    ))
                    break

    # ------------------------------------------------------------------
    # Cosmic ray mutations
    # ------------------------------------------------------------------

    def _apply_cosmic_ray(self, creature: Creature) -> None:
        """Apply a spontaneous single-trait mutation to a living creature."""
        new_genome, _mutated_trait = creature.genome.mutate_one(std=0.15)

        if self._should_branch_lineage(creature.genome, new_genome, hue_threshold=0.2):
            creature.lineage_id = self._alloc_lineage_id()

        creature.genome = new_genome  # type: ignore[misc]
        creature.glyph_surface = None
        creature.glyph_surface_cache_key = None
        creature._glyph_phase = new_genome.hue * 6.28
        self.cosmic_ray_events.append((creature.x, creature.y))

    # ------------------------------------------------------------------
    # Reproduction (energy / general)
    # ------------------------------------------------------------------

    def _reproduce(
        self,
        creature: Creature,
        *,
        queued_births: int = 0,
    ) -> Creature | None:
        """Handle creature reproduction with lineage tracking (energy mode)."""
        if not self._can_queue_birth(queued_births):
            return None

        creature.energy /= 2

        offspring_genome = creature.genome.mutate(self.settings.mutation_rate)
        offspring_lineage = self._branch_lineage_id(
            creature.lineage_id,
            creature.genome,
            offspring_genome,
        )

        offspring = Creature(
            x=(creature.x + random.uniform(-10, 10)) % self.width,
            y=(creature.y + random.uniform(-10, 10)) % self.height,
            genome=offspring_genome,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=creature.energy,
            lineage_id=offspring_lineage,
            _glyph_phase=offspring_genome.hue * 6.28,
        )

        self.generation += 1
        self.total_births += 1

        return offspring

    # ------------------------------------------------------------------
    # Overcrowding
    # ------------------------------------------------------------------

    def _get_overcrowding_penalty(self) -> float:
        """Calculate energy cost penalty for overcrowding."""
        population_ratio = len(self.creatures) / self._get_carrying_capacity()
        if population_ratio < 0.5:
            return 0.0
        excess = (population_ratio - 0.5) * 2
        return excess * excess

    def _get_carrying_capacity(self) -> int:
        """Return the soft ecological carrying capacity for the active mode."""
        return max(
            1,
            int(self._get_mode_param("max_population", self.settings.max_population)),
        )

    def _get_population_safety_limit(self) -> int:
        """Return the hard emergency population fuse used to bound runtime cost."""
        return max(self._get_carrying_capacity(), int(self.settings.population_safety_limit))

    def _get_population_spawn_limit(self) -> int:
        """Return the maximum safe population for initial world bootstrap."""
        if self._uses_hard_population_cap():
            return min(self._get_population_safety_limit(), self._get_carrying_capacity())
        return self._get_population_safety_limit()

    def _uses_hard_population_cap(self) -> bool:
        """Drift remains explicitly capped until it has real regulating forces."""
        return self.settings.sim_mode == "drift"

    def _can_queue_birth(self, queued_births: int = 0) -> bool:
        """Return whether another offspring can be admitted this frame."""
        projected_population = len(self.creatures) + queued_births
        if projected_population >= self._get_population_safety_limit():
            return False
        if self._uses_hard_population_cap() and projected_population >= self._get_carrying_capacity():
            return False
        return True

    def _resolve_death_cause(self, creature: Creature) -> str:
        """Resolve the current death cause for a zero-energy creature."""
        if (
            self.settings.sim_mode == "predator_prey"
            and id(creature) in self._predation_victims_this_frame
        ):
            return "predation"
        return "energy"

    def _queue_creature_death(
        self,
        creature: Creature,
        dead_creatures: list[Creature],
        dead_causes: dict[int, str],
        cause: str,
    ) -> None:
        """Queue a creature for death processing once per frame."""
        creature_id = id(creature)
        if creature_id in dead_causes:
            return
        dead_creatures.append(creature)
        dead_causes[creature_id] = cause

    def _queue_preexisting_death(
        self,
        creature: Creature,
        dead_creatures: list[Creature],
        dead_causes: dict[int, str],
    ) -> bool:
        """Skip creatures that are already dead before their turn starts."""
        if creature.energy <= 0:
            self._queue_creature_death(
                creature,
                dead_creatures,
                dead_causes,
                self._resolve_death_cause(creature),
            )
            return True
        if creature.age >= creature.get_max_lifespan():
            self._queue_creature_death(creature, dead_creatures, dead_causes, "age")
            return True
        return False

    def _sweep_frame_deaths(
        self,
        dead_creatures: list[Creature],
        dead_causes: dict[int, str],
    ) -> None:
        """Capture victims that were killed after their own turn earlier this frame."""
        for creature in self.creatures:
            if creature.energy <= 0:
                self._queue_creature_death(
                    creature,
                    dead_creatures,
                    dead_causes,
                    self._resolve_death_cause(creature),
                )
            elif creature.age >= creature.get_max_lifespan():
                self._queue_creature_death(creature, dead_creatures, dead_causes, "age")

    def _get_sensing_upkeep_cost(self, creature: Creature) -> float:
        """Return optional upkeep for expensive sensing when epistasis is active."""
        if not self._epistasis_enabled():
            return 0.0
        sense_load = max(0.0, creature.genome.sense_radius - 0.45)
        return sense_load * 0.0003

    def _get_effective_sensing_range(
        self,
        creature: Creature,
        *,
        multiplier: float = 1.0,
        absolute_radius: float | None = None,
        target_depth_band: int | None = None,
    ) -> float:
        """Return the zone-adjusted sensing range for a creature."""
        phenotype = self._get_effective_phenotype(creature)
        base_radius = (
            absolute_radius * phenotype.sense_radius_mult
            if absolute_radius is not None
            else creature.get_effective_sense_radius(
                multiplier=phenotype.sense_radius_mult * multiplier
            )
        )
        zone_modifier = self.zone_manager.get_sensing_modifier_at(creature.x, creature.y)
        depth_modifier = 1.0
        if (
            self.settings.sim_mode == "predator_prey"
            and target_depth_band is not None
        ):
            separation = depth_band_separation(creature.depth_band, target_depth_band)
            depth_modifier = (
                _DEPTH_SENSING_FACTORS[separation]
                * phenotype.depth_sense_multiplier(separation)
            )
        return max(1.0, base_radius * zone_modifier * depth_modifier)

    def _sense_target_position(
        self,
        creature: Creature,
        target_x: float,
        target_y: float,
        *,
        sense_multiplier: float = 1.0,
        absolute_radius: float | None = None,
        target_depth_band: int | None = None,
    ) -> tuple[float, float] | None:
        """Return a noisy sensed target position when the target is in sensing range."""
        effective_radius = self._get_effective_sensing_range(
            creature,
            multiplier=sense_multiplier,
            absolute_radius=absolute_radius,
            target_depth_band=target_depth_band,
        )
        distance = creature.distance_to(target_x, target_y, self.width, self.height)
        if distance > effective_radius:
            return None

        distance_ratio = distance / max(1.0, effective_radius)
        zone_modifier = self.zone_manager.get_sensing_modifier_at(creature.x, creature.y)
        noise_scale = 2.0 * distance_ratio * max(0.5, 1.4 - zone_modifier)
        estimated_x = (target_x + random.gauss(0.0, noise_scale)) % self.width
        estimated_y = (target_y + random.gauss(0.0, noise_scale)) % self.height
        return estimated_x, estimated_y

    def _branch_lineage_id(
        self,
        current_lineage_id: int,
        parent_genome: Genome,
        child_genome: Genome,
    ) -> int:
        """Allocate a new lineage when the child diverges materially from the parent."""
        if self._should_branch_lineage(parent_genome, child_genome):
            return self._alloc_lineage_id()
        return current_lineage_id

    def _should_branch_lineage(
        self,
        parent_genome: Genome,
        child_genome: Genome,
        *,
        hue_threshold: float = 0.15,
    ) -> bool:
        """Return True when divergence is large enough to treat as a new lineage."""
        hue_diff = abs(child_genome.hue - parent_genome.hue)
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff
        if hue_diff > hue_threshold:
            return True

        ecological_traits = (
            "speed",
            "sense_radius",
            "aggression",
            "efficiency",
            "longevity",
            "depth_preference",
        )
        bucket_changes = 0
        max_diff = 0.0
        for trait_name in ecological_traits:
            parent_value = getattr(parent_genome, trait_name)
            child_value = getattr(child_genome, trait_name)
            diff = abs(child_value - parent_value)
            max_diff = max(max_diff, diff)
            if int(parent_value * 4) != int(child_value * 4):
                bucket_changes += 1

        return bucket_changes >= 2 or max_diff >= 0.28

    # ------------------------------------------------------------------
    # Death processing
    # ------------------------------------------------------------------

    def _process_deaths(
        self,
        dead_creatures: list[Creature],
        dead_causes: dict[int, str],
    ) -> None:
        """Remove dead creatures and emit death events."""
        dead_set = set(id(c) for c in dead_creatures)
        for creature in dead_creatures:
            cause = dead_causes.get(id(creature), "energy")
            predation_context = self._predation_render_context_by_victim.pop(
                id(creature), None
            )
            if cause == "age":
                self._old_age_lifespans.append(creature.age)
            if creature.species == "predator":
                death_cause = "old_age" if cause == "age" else "starvation"
                self._finalize_predator_life(
                    creature,
                    end_reason="death",
                    death_cause=death_cause,
                )
            elif creature.species == "prey":
                self._prey_chase_pressure.pop(id(creature), None)
            self.death_events.append({
                "x": creature.x,
                "y": creature.y,
                "genome": creature.genome,
                "species": creature.species,
                "glyph_surface": creature.glyph_surface,
                "lineage_id": creature.lineage_id,
                "creature_id": id(creature),
                "cause": cause,
            })
            if cause == "predation" and predation_context is not None:
                self.death_events[-1].update(predation_context)
            self.total_deaths += 1

        self.creatures = [c for c in self.creatures if id(c) not in dead_set]

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def get_lineage_counts(self) -> dict[int, int]:
        """Count creatures per lineage_id."""
        counts: dict[int, int] = {}
        for c in self.creatures:
            counts[c.lineage_id] = counts.get(c.lineage_id, 0) + 1
        return counts

    def get_lineage_observability(
        self,
        lineage_id: int,
        *,
        traits: tuple[str, ...] = (),
    ) -> dict[str, object]:
        """Return cached count and average trait values for one living lineage."""
        if self._lineage_observability_cache_frame != self._frame:
            tracked = (
                "speed",
                "sense_radius",
                "efficiency",
                "aggression",
                "depth_preference",
                "conformity",
            )
            cache: dict[int, dict[str, object]] = {}
            for creature in self.creatures:
                key = int(creature.lineage_id)
                entry = cache.setdefault(
                    key,
                    {
                        "count": 0,
                        "trait_sums": {trait: 0.0 for trait in tracked},
                    },
                )
                entry["count"] = int(entry["count"]) + 1
                trait_sums = entry["trait_sums"]
                for trait in tracked:
                    trait_sums[trait] += float(getattr(creature.genome, trait, 0.0))
            self._lineage_observability_cache_frame = self._frame
            self._lineage_observability_cache = cache

        cached = self._lineage_observability_cache.get(int(lineage_id))
        if cached is None:
            return {
                "count": 0,
                "trait_averages": {trait: 0.0 for trait in traits},
            }
        count = max(0, int(cached["count"]))
        sums = cached["trait_sums"]
        averages = {
            trait: (float(sums.get(trait, 0.0)) / count) if count > 0 else 0.0
            for trait in traits
        }
        return {
            "count": count,
            "trait_averages": averages,
        }

    def get_hunter_grazer_counts(self) -> tuple[int, int, int]:
        """Count hunters (aggression > 0.6), grazers (< 0.4), opportunists."""
        hunters = grazers = opportunists = 0
        for c in self.creatures:
            a = c.genome.aggression
            if a > 0.6:
                hunters += 1
            elif a < 0.4:
                grazers += 1
            else:
                opportunists += 1
        return hunters, grazers, opportunists

    def get_species_counts(self) -> tuple[int, int]:
        """Return (predator_count, prey_count) for predator_prey mode."""
        pred = sum(1 for c in self.creatures if c.species == "predator")
        prey = sum(1 for c in self.creatures if c.species == "prey")
        return pred, prey

    def get_species_avg_speeds(self) -> tuple[float, float]:
        """Return (avg_predator_speed_trait, avg_prey_speed_trait)."""
        preds = [c for c in self.creatures if c.species == "predator"]
        preys = [c for c in self.creatures if c.species == "prey"]
        pred_speed = sum(c.genome.speed for c in preds) / max(1, len(preds))
        prey_speed = sum(c.genome.speed for c in preys) / max(1, len(preys))
        return pred_speed, prey_speed

    def get_species_avg_actual_speeds(self) -> tuple[float, float]:
        """Return (avg_predator_speed, avg_prey_speed) from live velocities."""
        preds = [c for c in self.creatures if c.species == "predator"]
        preys = [c for c in self.creatures if c.species == "prey"]
        pred_speed = sum(math.hypot(c.vx, c.vy) for c in preds) / max(1, len(preds))
        prey_speed = sum(math.hypot(c.vx, c.vy) for c in preys) / max(1, len(preys))
        return pred_speed, prey_speed

    def get_recent_predation_stats(self) -> dict[str, int]:
        """Return lightweight rolling predator/prey telemetry for the HUD."""
        window_frames = max(
            30,
            int(
                float(
                    self._get_mode_param(
                        "simulation_tick_hz",
                        self.settings.target_fps,
                    )
                )
                * _PREDATION_RECENT_WINDOW_SECONDS
            ),
        )
        cutoff = self._frame - window_frames
        while self._recent_kill_frames and self._recent_kill_frames[0] <= cutoff:
            self._recent_kill_frames.popleft()
        while (
            self._recent_cross_band_miss_frames
            and self._recent_cross_band_miss_frames[0] <= cutoff
        ):
            self._recent_cross_band_miss_frames.popleft()
        return {
            "recent_kills": len(self._recent_kill_frames),
            "recent_cross_band_misses": len(self._recent_cross_band_miss_frames),
            "total_kills": self.predation_kill_count,
        }

    def get_epistasis_summary(self) -> dict[str, Any]:
        """Return lightweight phenotype/strategy observability for the live population."""
        strategy_counts = strategy_bucket_template()
        if not self.creatures:
            return {
                "enabled": self._epistasis_enabled(),
                "strength": self._get_epistasis_strength(),
                "top_strategy": "generalist",
                "top_strategy_share": 0.0,
                "strategy_counts": strategy_counts,
                "average_modifiers": {
                    "speed_mult": 1.0,
                    "movement_cost_mult": 1.0,
                    "metabolic_cost_mult": 1.0,
                    "sense_radius_mult": 1.0,
                    "food_efficiency_mult": 1.0,
                    "reproduction_threshold_mult": 1.0,
                    "predation_contact_mult": 1.0,
                    "flee_agility_mult": 1.0,
                    "depth_transition_mult": 1.0,
                    "in_band_sense_mult": 1.0,
                    "cross_band_sense_mult": 1.0,
                },
            }

        modifier_sums = {
            "speed_mult": 0.0,
            "movement_cost_mult": 0.0,
            "metabolic_cost_mult": 0.0,
            "sense_radius_mult": 0.0,
            "food_efficiency_mult": 0.0,
            "reproduction_threshold_mult": 0.0,
            "predation_contact_mult": 0.0,
            "flee_agility_mult": 0.0,
            "depth_transition_mult": 0.0,
            "in_band_sense_mult": 0.0,
            "cross_band_sense_mult": 0.0,
        }
        for creature in self.creatures:
            phenotype = self._get_effective_phenotype(creature)
            strategy_counts[phenotype.strategy_bucket] += 1
            for key in modifier_sums:
                modifier_sums[key] += getattr(phenotype, key)

        population = len(self.creatures)
        top_strategy, top_count = max(
            strategy_counts.items(),
            key=lambda item: (item[1], item[0] != "generalist", item[0]),
        )
        return {
            "enabled": self._epistasis_enabled(),
            "strength": self._get_epistasis_strength(),
            "top_strategy": top_strategy,
            "top_strategy_share": top_count / population,
            "strategy_counts": strategy_counts,
            "average_modifiers": {
                key: value / population for key, value in modifier_sums.items()
            },
        }

    def get_predator_prey_stability_stats(self) -> dict[str, Any]:
        """Return predator-prey run stability telemetry for HUD and persistence."""
        state = self._predator_prey_state
        grace_ticks = self._get_predator_prey_extinction_grace_ticks()
        trial_direction = ""
        if state.adaptive_tuning.trial_direction > 0:
            trial_direction = "+"
        elif state.adaptive_tuning.trial_direction < 0:
            trial_direction = "-"
        collapse_trial_direction = ""
        if state.collapse_trial_delta > 0:
            collapse_trial_direction = "+"
        elif state.collapse_trial_delta < 0:
            collapse_trial_direction = "-"
        predator_grace_remaining = max(0, grace_ticks - state.predator_zero_ticks)
        prey_grace_remaining = max(0, grace_ticks - state.prey_zero_ticks)
        grace_active = (
            not state.game_over_active
            and (
                state.predator_zero_ticks > 0
                or state.prey_zero_ticks > 0
            )
        )
        if state.predator_zero_ticks > 0 and state.prey_zero_ticks > 0:
            grace_role = "both"
        elif state.predator_zero_ticks > 0:
            grace_role = "predators"
        elif state.prey_zero_ticks > 0:
            grace_role = "prey"
        else:
            grace_role = "none"
        return {
            "current_seed": state.current_seed,
            "sim_ticks": state.sim_ticks,
            "survival_ticks": state.survival_ticks,
            "predator_low_ticks": state.predator_low_ticks,
            "prey_low_ticks": state.prey_low_ticks,
            "predator_zero_ticks": state.predator_zero_ticks,
            "prey_zero_ticks": state.prey_zero_ticks,
            "extinction_grace_ticks": grace_ticks,
            "extinction_grace_active": grace_active,
            "extinction_grace_role": grace_role,
            "predator_grace_remaining_ticks": predator_grace_remaining,
            "prey_grace_remaining_ticks": prey_grace_remaining,
            "near_extinction_pressure": state.predator_low_ticks + state.prey_low_ticks,
            "rolling_average_survival_ticks": self.predator_prey_rolling_average,
            "best_recent_survival_ticks": self.predator_prey_best_recent_ticks,
            "history_window_size": self._get_predator_prey_history_size(),
            "highest_survival_ticks": state.highest_survival_ticks,
            "trial_active": state.adaptive_tuning.trial_active,
            "trial_id": state.adaptive_tuning.trial_id,
            "trial_dial": state.adaptive_tuning.trial_dial,
            "trial_direction": trial_direction,
            "trial_baseline_average": state.adaptive_tuning.trial_baseline_average,
            "trial_trigger_reason": state.adaptive_tuning.trial_trigger_reason,
            "trial_last_decision": state.adaptive_tuning.last_decision,
            "trial_last_decision_basis": state.adaptive_tuning.last_decision_basis,
            "trial_last_decision_trial_id": state.adaptive_tuning.last_decision_trial_id,
            "trial_last_survival_median_candidate": (
                state.adaptive_tuning.last_decision_survival_median_candidate
            ),
            "trial_last_survival_median_baseline": (
                state.adaptive_tuning.last_decision_survival_median_baseline
            ),
            "trial_last_near_extinction_candidate": (
                state.adaptive_tuning.last_decision_near_extinction_candidate
            ),
            "trial_last_near_extinction_baseline": (
                state.adaptive_tuning.last_decision_near_extinction_baseline
            ),
            "verification_seed_count_configured": self._get_predator_prey_trial_count(),
            "adaptive_max_consecutive_retry_trials": (
                self._get_predator_prey_max_consecutive_retry_trials()
            ),
            "survival_deadband": self._get_predator_prey_survival_deadband(),
            "post_run_trial_decision": state.adaptive_tuning.post_run_trial_decision,
            "non_improving_run_streak": state.adaptive_tuning.non_improving_run_streak,
            "consecutive_immediate_retry_trials": (
                state.adaptive_tuning.consecutive_immediate_retry_trials
            ),
            "trial_launch_blocked_by_retry_cap": (
                state.adaptive_tuning.last_trial_launch_blocked_by_retry_cap
            ),
            "adjustment_step_multiplier": self.predator_prey_adjustment_step_multiplier,
            "adjustment_step_increase_percent": (
                (self.predator_prey_adjustment_step_multiplier - 1.0) * 100.0
            ),
            "adjustment_step_escalation_runs": (
                self._get_predator_prey_step_escalation_runs()
            ),
            "adjustment_step_escalation_percent": (
                self._get_predator_prey_step_escalation_percent()
            ),
            "game_over_active": state.game_over_active,
            "collapse_cause": state.collapse_cause,
            "collapse_predators": state.collapse_predator_count,
            "collapse_prey": state.collapse_prey_count,
            "collapse_dial_values": dict(state.collapse_dial_values),
            "collapse_trial_dial": state.collapse_trial_dial,
            "collapse_trial_role": state.collapse_trial_phase,
            "collapse_trial_seed": state.collapse_trial_seed,
            "collapse_trial_id": state.collapse_trial_id,
            "collapse_trial_trigger_reason": state.collapse_trial_trigger_reason,
            "collapse_trial_delta": state.collapse_trial_delta,
            "collapse_trial_direction": collapse_trial_direction,
            "collapse_trial_value": state.collapse_trial_value,
            "collapse_trial_decision": state.collapse_trial_decision,
            "collapse_rolling_average": state.collapse_rolling_average,
            "collapse_beat_average": state.collapse_beat_average,
            "collapse_was_new_highest": state.collapse_was_new_highest,
            "restart_countdown_seconds": self.get_predator_prey_restart_countdown_seconds(),
        }

    def export_predator_prey_runtime_state(self) -> dict[str, Any]:
        state = self._predator_prey_state
        tuning = state.adaptive_tuning
        return {
            "current_seed": state.current_seed,
            "sim_ticks": state.sim_ticks,
            "survival_ticks": state.survival_ticks,
            "predator_low_ticks": state.predator_low_ticks,
            "prey_low_ticks": state.prey_low_ticks,
            "predator_zero_ticks": state.predator_zero_ticks,
            "prey_zero_ticks": state.prey_zero_ticks,
            "run_history": list(state.run_history),
            "highest_survival_ticks": state.highest_survival_ticks,
            "game_over": {
                "active": state.game_over_active,
                "cause": state.collapse_cause,
                "predators": state.collapse_predator_count,
                "prey": state.collapse_prey_count,
                "dial_values": dict(state.collapse_dial_values),
                "trial_dial": state.collapse_trial_dial,
                "trial_role": state.collapse_trial_phase,
                "trial_seed": state.collapse_trial_seed,
                "trial_id": state.collapse_trial_id,
                "trial_trigger_reason": state.collapse_trial_trigger_reason,
                "trial_delta": state.collapse_trial_delta,
                "trial_value": state.collapse_trial_value,
                "trial_decision": state.collapse_trial_decision,
                "rolling_average": state.collapse_rolling_average,
                "beat_average": state.collapse_beat_average,
                "was_new_highest": state.collapse_was_new_highest,
            },
            "adaptive_tuning": {
                "baseline_values": dict(tuning.baseline_values),
                "current_values": dict(tuning.current_values),
                "previous_values": dict(tuning.previous_values),
                "trial_candidate_values": dict(tuning.trial_candidate_values),
                "trial_active": tuning.trial_active,
                "trial_phase": tuning.trial_phase,
                "trial_dial": tuning.trial_dial,
                "trial_direction": tuning.trial_direction,
                "trial_baseline_average": tuning.trial_baseline_average,
                "trial_id": tuning.trial_id,
                "trial_trigger_reason": tuning.trial_trigger_reason,
                "next_trial_id": tuning.next_trial_id,
                "trial_seeds": list(tuning.trial_seeds),
                "trial_seed_index": tuning.trial_seed_index,
                "trial_candidate_results": list(tuning.trial_candidate_results),
                "trial_baseline_results": list(tuning.trial_baseline_results),
                "trial_candidate_pressures": list(tuning.trial_candidate_pressures),
                "trial_baseline_pressures": list(tuning.trial_baseline_pressures),
                "last_decision": tuning.last_decision,
                "last_decision_basis": tuning.last_decision_basis,
                "last_decision_trial_id": tuning.last_decision_trial_id,
                "last_decision_survival_median_candidate": (
                    tuning.last_decision_survival_median_candidate
                ),
                "last_decision_survival_median_baseline": (
                    tuning.last_decision_survival_median_baseline
                ),
                "last_decision_near_extinction_candidate": (
                    tuning.last_decision_near_extinction_candidate
                ),
                "last_decision_near_extinction_baseline": (
                    tuning.last_decision_near_extinction_baseline
                ),
                "post_run_trial_decision": tuning.post_run_trial_decision,
                "non_improving_run_streak": tuning.non_improving_run_streak,
                "consecutive_immediate_retry_trials": (
                    tuning.consecutive_immediate_retry_trials
                ),
                "retry_cap_waiting_for_ordinary_run": (
                    tuning.retry_cap_waiting_for_ordinary_run
                ),
                "last_trial_launch_blocked_by_retry_cap": (
                    tuning.last_trial_launch_blocked_by_retry_cap
                ),
            },
        }

    def export_predator_prey_tuning_state(self) -> dict[str, Any]:
        """Persist only cross-run predator-prey tuning state across launches."""
        state = self._predator_prey_state
        tuning = state.adaptive_tuning
        return {
            "run_history": list(state.run_history),
            "highest_survival_ticks": state.highest_survival_ticks,
            "adaptive_tuning": {
                "baseline_values": dict(tuning.baseline_values),
                "current_values": dict(tuning.current_values),
                "previous_values": dict(tuning.previous_values),
                "trial_candidate_values": dict(tuning.trial_candidate_values),
                "trial_active": tuning.trial_active,
                "trial_phase": tuning.trial_phase,
                "trial_dial": tuning.trial_dial,
                "trial_direction": tuning.trial_direction,
                "trial_baseline_average": tuning.trial_baseline_average,
                "trial_id": tuning.trial_id,
                "trial_trigger_reason": tuning.trial_trigger_reason,
                "next_trial_id": tuning.next_trial_id,
                "trial_seeds": list(tuning.trial_seeds),
                "trial_seed_index": tuning.trial_seed_index,
                "trial_candidate_results": list(tuning.trial_candidate_results),
                "trial_baseline_results": list(tuning.trial_baseline_results),
                "trial_candidate_pressures": list(tuning.trial_candidate_pressures),
                "trial_baseline_pressures": list(tuning.trial_baseline_pressures),
                "last_decision": tuning.last_decision,
                "last_decision_basis": tuning.last_decision_basis,
                "last_decision_trial_id": tuning.last_decision_trial_id,
                "last_decision_survival_median_candidate": (
                    tuning.last_decision_survival_median_candidate
                ),
                "last_decision_survival_median_baseline": (
                    tuning.last_decision_survival_median_baseline
                ),
                "last_decision_near_extinction_candidate": (
                    tuning.last_decision_near_extinction_candidate
                ),
                "last_decision_near_extinction_baseline": (
                    tuning.last_decision_near_extinction_baseline
                ),
                "post_run_trial_decision": tuning.post_run_trial_decision,
                "non_improving_run_streak": tuning.non_improving_run_streak,
                "consecutive_immediate_retry_trials": (
                    tuning.consecutive_immediate_retry_trials
                ),
                "retry_cap_waiting_for_ordinary_run": (
                    tuning.retry_cap_waiting_for_ordinary_run
                ),
                "last_trial_launch_blocked_by_retry_cap": (
                    tuning.last_trial_launch_blocked_by_retry_cap
                ),
            },
        }

    def restore_predator_prey_runtime_state(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return

        state = self._predator_prey_state
        state.current_seed = payload.get("current_seed")
        state.sim_ticks = int(payload.get("sim_ticks", self._frame))
        state.survival_ticks = int(payload.get("survival_ticks", state.sim_ticks))
        state.predator_low_ticks = int(payload.get("predator_low_ticks", 0))
        state.prey_low_ticks = int(payload.get("prey_low_ticks", 0))
        state.predator_zero_ticks = int(payload.get("predator_zero_ticks", 0))
        state.prey_zero_ticks = int(payload.get("prey_zero_ticks", 0))
        history = payload.get("run_history", [])
        state.run_history = self._build_predator_prey_run_history(history)
        state.highest_survival_ticks = int(
            payload.get("highest_survival_ticks", max((0, *state.run_history)))
        )

        game_over = payload.get("game_over", {})
        if isinstance(game_over, dict):
            state.game_over_active = bool(game_over.get("active", False))
            state.collapse_cause = game_over.get("cause")
            state.collapse_predator_count = int(game_over.get("predators", 0))
            state.collapse_prey_count = int(game_over.get("prey", 0))
            state.collapse_started_at_seconds = None
            dial_values = game_over.get("dial_values", {})
            if isinstance(dial_values, dict) and dial_values:
                state.collapse_dial_values = self._serialize_predator_prey_dial_values(
                    dial_values
                )
            else:
                state.collapse_dial_values = {}
            state.collapse_trial_dial = game_over.get("trial_dial")
            state.collapse_trial_phase = game_over.get("trial_role")
            trial_seed = game_over.get("trial_seed")
            state.collapse_trial_seed = None if trial_seed is None else int(trial_seed)
            trial_id = game_over.get("trial_id")
            state.collapse_trial_id = None if trial_id is None else int(trial_id)
            state.collapse_trial_trigger_reason = game_over.get("trial_trigger_reason")
            state.collapse_trial_delta = float(game_over.get("trial_delta", 0.0))
            trial_value = game_over.get("trial_value")
            state.collapse_trial_value = (
                None if trial_value is None else float(trial_value)
            )
            state.collapse_trial_decision = str(
                game_over.get("trial_decision", "none")
            )
            state.collapse_rolling_average = float(game_over.get("rolling_average", 0.0))
            state.collapse_beat_average = bool(game_over.get("beat_average", False))
            state.collapse_was_new_highest = bool(
                game_over.get("was_new_highest", False)
            )

        tuning_payload = payload.get("adaptive_tuning", {})
        if isinstance(tuning_payload, dict):
            tuning = state.adaptive_tuning
            tuning.baseline_values = self._serialize_predator_prey_dial_values(
                tuning_payload.get(
                    "baseline_values",
                    tuning.current_values or self._default_predator_prey_dial_values(),
                )
            )
            tuning.current_values = self._serialize_predator_prey_dial_values(
                tuning_payload.get("current_values", {})
            )
            tuning.previous_values = self._serialize_predator_prey_dial_values(
                tuning_payload.get("previous_values", tuning.current_values)
            )
            candidate_values = tuning_payload.get("trial_candidate_values")
            if isinstance(candidate_values, dict) and not candidate_values:
                tuning.trial_candidate_values = {}
            else:
                tuning.trial_candidate_values = self._serialize_predator_prey_dial_values(
                    candidate_values or tuning.current_values
                )
            tuning.trial_active = bool(tuning_payload.get("trial_active", False))
            tuning.trial_phase = str(
                tuning_payload.get("trial_phase", tuning.trial_phase)
            )
            tuning.trial_dial = tuning_payload.get("trial_dial")
            tuning.trial_direction = int(tuning_payload.get("trial_direction", 0))
            tuning.trial_baseline_average = float(
                tuning_payload.get("trial_baseline_average", 0.0)
            )
            trial_id = tuning_payload.get("trial_id")
            tuning.trial_id = None if trial_id is None else int(trial_id)
            tuning.trial_trigger_reason = tuning_payload.get("trial_trigger_reason")
            tuning.next_trial_id = max(
                1,
                int(tuning_payload.get("next_trial_id", 1)),
            )
            tuning.trial_seeds = [
                int(seed) for seed in tuning_payload.get("trial_seeds", [])
            ]
            tuning.trial_seed_index = max(
                0,
                int(tuning_payload.get("trial_seed_index", 0)),
            )
            tuning.trial_candidate_results = [
                int(score)
                for score in tuning_payload.get("trial_candidate_results", [])
            ]
            tuning.trial_baseline_results = [
                int(score)
                for score in tuning_payload.get("trial_baseline_results", [])
            ]
            tuning.trial_candidate_pressures = [
                int(score)
                for score in tuning_payload.get("trial_candidate_pressures", [])
            ]
            tuning.trial_baseline_pressures = [
                int(score)
                for score in tuning_payload.get("trial_baseline_pressures", [])
            ]
            tuning.last_decision = str(tuning_payload.get("last_decision", "none"))
            tuning.last_decision_basis = tuning_payload.get("last_decision_basis")
            last_decision_trial_id = tuning_payload.get("last_decision_trial_id")
            tuning.last_decision_trial_id = (
                None
                if last_decision_trial_id is None
                else int(last_decision_trial_id)
            )
            tuning.last_decision_survival_median_candidate = self._float_or_none(
                tuning_payload.get("last_decision_survival_median_candidate")
            )
            tuning.last_decision_survival_median_baseline = self._float_or_none(
                tuning_payload.get("last_decision_survival_median_baseline")
            )
            tuning.last_decision_near_extinction_candidate = self._float_or_none(
                tuning_payload.get("last_decision_near_extinction_candidate")
            )
            tuning.last_decision_near_extinction_baseline = self._float_or_none(
                tuning_payload.get("last_decision_near_extinction_baseline")
            )
            tuning.last_decision_pending_log = False
            tuning.post_run_trial_decision = str(
                tuning_payload.get("post_run_trial_decision", "none")
            )
            tuning.non_improving_run_streak = max(
                0,
                int(
                    tuning_payload.get("non_improving_run_streak", 0)
                ),
            )
            tuning.consecutive_immediate_retry_trials = max(
                0,
                int(tuning_payload.get("consecutive_immediate_retry_trials", 0)),
            )
            tuning.retry_cap_waiting_for_ordinary_run = bool(
                tuning_payload.get("retry_cap_waiting_for_ordinary_run", False)
            )
            tuning.last_trial_launch_blocked_by_retry_cap = bool(
                tuning_payload.get("last_trial_launch_blocked_by_retry_cap", False)
            )
            self._apply_predator_prey_tuning_values(tuning.current_values)

        self._frame = state.sim_ticks

    def restore_predator_prey_tuning_state(self, payload: dict[str, Any]) -> None:
        """Restore cross-launch predator-prey tuning without restoring the world."""
        if not isinstance(payload, dict):
            return

        state = self._predator_prey_state
        history = payload.get("run_history", [])
        state.run_history = self._build_predator_prey_run_history(history)
        state.highest_survival_ticks = int(
            payload.get("highest_survival_ticks", max((0, *state.run_history)))
        )

        tuning_payload = payload.get("adaptive_tuning", {})
        if not isinstance(tuning_payload, dict):
            return

        tuning = state.adaptive_tuning
        tuning.baseline_values = self._serialize_predator_prey_dial_values(
            tuning_payload.get(
                "baseline_values",
                tuning.current_values or self._default_predator_prey_dial_values(),
            )
        )
        tuning.current_values = self._serialize_predator_prey_dial_values(
            tuning_payload.get("current_values", {})
        )
        tuning.previous_values = self._serialize_predator_prey_dial_values(
            tuning_payload.get("previous_values", tuning.current_values)
        )
        candidate_values = tuning_payload.get("trial_candidate_values")
        if isinstance(candidate_values, dict) and not candidate_values:
            tuning.trial_candidate_values = {}
        else:
            tuning.trial_candidate_values = self._serialize_predator_prey_dial_values(
                candidate_values or tuning.current_values
            )
        tuning.trial_active = bool(tuning_payload.get("trial_active", False))
        tuning.trial_phase = str(tuning_payload.get("trial_phase", tuning.trial_phase))
        tuning.trial_dial = tuning_payload.get("trial_dial")
        tuning.trial_direction = int(tuning_payload.get("trial_direction", 0))
        tuning.trial_baseline_average = float(
            tuning_payload.get("trial_baseline_average", 0.0)
        )
        trial_id = tuning_payload.get("trial_id")
        tuning.trial_id = None if trial_id is None else int(trial_id)
        tuning.trial_trigger_reason = tuning_payload.get("trial_trigger_reason")
        tuning.next_trial_id = max(
            1,
            int(tuning_payload.get("next_trial_id", 1)),
        )
        tuning.trial_seeds = [int(seed) for seed in tuning_payload.get("trial_seeds", [])]
        tuning.trial_seed_index = max(
            0,
            int(tuning_payload.get("trial_seed_index", 0)),
        )
        tuning.trial_candidate_results = [
            int(score) for score in tuning_payload.get("trial_candidate_results", [])
        ]
        tuning.trial_baseline_results = [
            int(score) for score in tuning_payload.get("trial_baseline_results", [])
        ]
        tuning.trial_candidate_pressures = [
            int(score) for score in tuning_payload.get("trial_candidate_pressures", [])
        ]
        tuning.trial_baseline_pressures = [
            int(score) for score in tuning_payload.get("trial_baseline_pressures", [])
        ]
        tuning.last_decision = str(tuning_payload.get("last_decision", "none"))
        tuning.last_decision_basis = tuning_payload.get("last_decision_basis")
        last_decision_trial_id = tuning_payload.get("last_decision_trial_id")
        tuning.last_decision_trial_id = (
            None if last_decision_trial_id is None else int(last_decision_trial_id)
        )
        tuning.last_decision_survival_median_candidate = self._float_or_none(
            tuning_payload.get("last_decision_survival_median_candidate")
        )
        tuning.last_decision_survival_median_baseline = self._float_or_none(
            tuning_payload.get("last_decision_survival_median_baseline")
        )
        tuning.last_decision_near_extinction_candidate = self._float_or_none(
            tuning_payload.get("last_decision_near_extinction_candidate")
        )
        tuning.last_decision_near_extinction_baseline = self._float_or_none(
            tuning_payload.get("last_decision_near_extinction_baseline")
        )
        tuning.last_decision_pending_log = False
        tuning.post_run_trial_decision = str(
            tuning_payload.get("post_run_trial_decision", "none")
        )
        tuning.non_improving_run_streak = max(
            0,
            int(tuning_payload.get("non_improving_run_streak", 0)),
        )
        tuning.consecutive_immediate_retry_trials = max(
            0,
            int(tuning_payload.get("consecutive_immediate_retry_trials", 0)),
        )
        tuning.retry_cap_waiting_for_ordinary_run = bool(
            tuning_payload.get("retry_cap_waiting_for_ordinary_run", False)
        )
        tuning.last_trial_launch_blocked_by_retry_cap = bool(
            tuning_payload.get("last_trial_launch_blocked_by_retry_cap", False)
        )
        self._apply_predator_prey_tuning_values(tuning.current_values)

    def get_predator_prey_restart_countdown_seconds(
        self,
        now_seconds: float | None = None,
    ) -> float:
        if not self.predator_prey_game_over_active:
            return 0.0
        current_time = time.monotonic() if now_seconds is None else now_seconds
        started = self._predator_prey_state.collapse_started_at_seconds
        if started is None:
            return _PREDATOR_PREY_GAME_OVER_HOLD_SECONDS
        remaining = _PREDATOR_PREY_GAME_OVER_HOLD_SECONDS - (current_time - started)
        return max(0.0, remaining)

    def export_predator_diagnostics(self) -> dict[str, Any]:
        """Return a structured predator-only diagnostic snapshot."""
        base_threshold = float(
            self._get_mode_param(
                "predator_energy_to_reproduce",
                self._get_mode_param(
                    "energy_to_reproduce",
                    self.settings.energy_to_reproduce,
                ),
            )
        )
        kill_energy_gain_cap = self._get_predator_kill_energy_gain_cap()
        return {
            "frame": self._frame,
            "base_threshold": base_threshold,
            "predator_kill_energy_gain_cap": kill_energy_gain_cap,
            "predator_hunt_sense_multiplier": self._get_predator_hunt_sense_multiplier(),
            "predator_hunt_speed_multiplier": self._get_predator_hunt_speed_multiplier(),
            "predator_contact_kill_distance_scale": (
                self._get_predator_contact_kill_distance_scale()
            ),
            "prey_flee_speed_multiplier": self._get_prey_flee_speed_multiplier(),
            "prey_flee_age_slowdown_enabled": self._prey_flee_age_slowdown_enabled(),
            "prey_flee_low_energy_slowdown_enabled": (
                self._prey_flee_low_energy_slowdown_enabled()
            ),
            "prey_flee_low_energy_threshold": (
                self._get_prey_flee_low_energy_threshold()
            ),
            "prey_flee_low_energy_min_mult": (
                self._get_prey_flee_low_energy_min_mult()
            ),
            "prey_depth_fatigue_enabled": self._prey_depth_fatigue_enabled(),
            "prey_depth_fatigue_min_chase_ticks": (
                self._get_prey_depth_fatigue_min_chase_ticks()
            ),
            "prey_depth_fatigue_energy_threshold": (
                self._get_prey_depth_fatigue_energy_threshold()
            ),
            "prey_depth_fatigue_escape_urgency_mult": (
                self._get_prey_depth_fatigue_escape_urgency_mult()
            ),
            "prey_depth_fatigue_decay_ticks": self._get_prey_depth_fatigue_decay_ticks(),
            "prey_depth_fatigue_max": self._get_prey_depth_fatigue_max(),
            "predator_near_contact_diagnostic_scale": (
                self._get_predator_near_contact_diagnostic_scale()
            ),
            "predator_sustained_chase_min_frames": (
                self._get_predator_sustained_chase_min_frames()
            ),
            "predator_committed_depth_tracking_enabled": (
                self._predator_committed_depth_tracking_enabled()
            ),
            "predator_committed_depth_tracking_min_chase_ticks": (
                self._get_predator_committed_depth_tracking_min_chase_ticks()
            ),
            "predator_committed_depth_tracking_near_contact_scale": (
                self._get_predator_committed_depth_tracking_near_contact_scale()
            ),
            "predator_committed_depth_tracking_cooldown_ticks": (
                self._get_predator_committed_depth_tracking_cooldown_ticks()
            ),
            "predator_refuge_enabled": self._predator_refuge_enabled(),
            "predator_refuge_zone_type": "hunting_ground",
            "predator_refuge_hunt_sense_bonus": (
                self._get_predator_refuge_hunt_sense_bonus()
            ),
            "predator_refuge_contact_bonus": (
                self._get_predator_refuge_contact_bonus()
            ),
            "predator_refuge_depth_transition_bonus": (
                self._get_predator_refuge_depth_transition_bonus()
            ),
            "predator_refuge_movement_cost_reduction": (
                self._get_predator_refuge_movement_cost_reduction()
            ),
            "predator_refuge_density_radius": (
                self._get_predator_refuge_density_radius()
            ),
            "predator_refuge_density_soft_cap": (
                self._get_predator_refuge_density_soft_cap()
            ),
            "predator_refuge_density_hard_cap": (
                self._get_predator_refuge_density_hard_cap()
            ),
            "predator_kill_energy_transfer": self._copy_predator_kill_energy_summary(
                self._predator_diag_kill_energy_summary
            ),
            "predator_depth_fatigue_summary": self._copy_predator_depth_fatigue_summary(),
            "completed_lives": [self._copy_predator_life(life) for life in self._predator_diag_completed],
            "active_lives": [
                self._copy_predator_life(life)
                for life in self._predator_diag_active.values()
            ],
            "events": {
                name: [dict(event) for event in events]
                for name, events in self._predator_diag_events.items()
            },
        }

    def get_depth_band_counts(self) -> dict[str, int]:
        """Count living creatures in each bounded depth band."""
        counts = {depth_band_name(band): 0 for band in DEPTH_BANDS}
        for creature in self.creatures:
            counts[depth_band_name(creature.depth_band)] += 1
        return counts

    def get_zone_occupancy_counts(self) -> dict[str, int]:
        """Count creatures by their dominant containing zone."""
        return self.zone_manager.get_zone_occupancy_counts(self.creatures)

    def get_flock_stats(self) -> tuple[int, float, int]:
        """Return (flock_count, avg_flock_size, largest_flock) for boids mode."""
        if not self._flock_sizes:
            return 0, 0.0, 0
        sizes = list(self._flock_sizes.values())
        avg = sum(sizes) / len(sizes)
        return self._flock_count, avg, max(sizes)

    def get_boids_behavior_metrics(self) -> dict[str, Any]:
        """Return boids-specific spacing, flock-size, and force diagnostics."""
        if self.settings.sim_mode != "boids" or not self.creatures:
            return {
                "count": 0,
                "average_size": 0.0,
                "largest": 0,
                "loners": 0,
                "largest_share": 0.0,
                "nearest_neighbor_distance_mean": 0.0,
                "nearest_neighbor_distance_median": 0.0,
                "neighbor_count_mean": 0.0,
                "neighbor_count_median": 0.0,
                "alignment_mean": 0.0,
                "separation_force_mean": 0.0,
                "cohesion_force_mean": 0.0,
                "overcrowded_share": 0.0,
                "dense_cluster_share": 0.0,
                "size_bands": {
                    "small": 0,
                    "medium": 0,
                    "large": 0,
                    "huge": 0,
                },
                "member_bands": {
                    "small": 0,
                    "medium": 0,
                    "large": 0,
                    "huge": 0,
                },
            }

        creature_bucket = self._build_creature_bucket()
        boid_neighbors = self._build_boid_neighbor_cache_and_assignments(
            creature_bucket
        )
        flock_count, avg_flock_size, largest_flock = self.get_flock_stats()
        population = max(1, len(self.creatures))
        loners = sum(1 for creature in self.creatures if creature.flock_id == -1)

        nearest_neighbor_distances: list[float] = []
        neighbor_counts: list[int] = []
        alignment_scores: list[float] = []
        separation_force_magnitudes: list[float] = []
        cohesion_force_magnitudes: list[float] = []
        overcrowded_count = 0
        dense_cluster_count = 0

        for creature in self.creatures:
            neighbors = boid_neighbors.get(id(creature), [])
            (
                sep_fx,
                sep_fy,
                _align_fx,
                _align_fy,
                coh_fx,
                coh_fy,
                neighbor_count,
                alignment_score,
                _crowding_score,
                nearest_distance,
                _mean_distance,
                _sep_mag,
                _coh_mag,
            ) = self._compute_boid_forces(creature, neighbors)
            neighbor_counts.append(neighbor_count)
            alignment_scores.append(alignment_score)
            separation_force_magnitudes.append(math.hypot(sep_fx, sep_fy))
            cohesion_force_magnitudes.append(math.hypot(coh_fx, coh_fy))
            if nearest_distance > 0.0:
                nearest_neighbor_distances.append(nearest_distance)

            radius = creature.get_radius()
            if neighbor_count >= 10 or (
                nearest_distance > 0.0 and nearest_distance < radius * 2.5
            ):
                overcrowded_count += 1
            if neighbor_count >= 14 or (
                nearest_distance > 0.0 and nearest_distance < radius * 1.9
            ):
                dense_cluster_count += 1

        def _size_band(size: int) -> str:
            if size >= 50:
                return "huge"
            if size >= 20:
                return "large"
            if size >= 8:
                return "medium"
            return "small"

        size_bands = {"small": 0, "medium": 0, "large": 0, "huge": 0}
        member_bands = {"small": 0, "medium": 0, "large": 0, "huge": 0}
        for size in self._flock_sizes.values():
            band = _size_band(size)
            size_bands[band] += 1
            member_bands[band] += size

        return {
            "count": flock_count,
            "average_size": avg_flock_size,
            "largest": largest_flock,
            "loners": loners,
            "largest_share": largest_flock / population,
            "nearest_neighbor_distance_mean": (
                sum(nearest_neighbor_distances) / len(nearest_neighbor_distances)
                if nearest_neighbor_distances
                else 0.0
            ),
            "nearest_neighbor_distance_median": (
                median(nearest_neighbor_distances)
                if nearest_neighbor_distances
                else 0.0
            ),
            "neighbor_count_mean": sum(neighbor_counts) / len(neighbor_counts),
            "neighbor_count_median": float(median(neighbor_counts)),
            "alignment_mean": sum(alignment_scores) / len(alignment_scores),
            "separation_force_mean": (
                sum(separation_force_magnitudes) / len(separation_force_magnitudes)
            ),
            "cohesion_force_mean": (
                sum(cohesion_force_magnitudes) / len(cohesion_force_magnitudes)
            ),
            "overcrowded_share": overcrowded_count / population,
            "dense_cluster_share": dense_cluster_count / population,
            "size_bands": size_bands,
            "member_bands": member_bands,
        }

    def get_avg_conformity(self) -> float:
        """Return average conformity trait across population."""
        if not self.creatures:
            return 0.0
        return sum(c.genome.conformity for c in self.creatures) / len(self.creatures)

    def get_lineage_count(self) -> int:
        """Return number of distinct lineages currently alive."""
        return len(set(c.lineage_id for c in self.creatures))

    def _capture_run_baseline_observability(self) -> None:
        self._run_baseline_traits = obs_average_traits(self.creatures, TRACKED_TRAITS)

    def get_simulation_tick_hz(self) -> float:
        """Return active simulation tick rate for observability formatting."""
        configured = self._get_mode_param("simulation_tick_hz", None)
        if isinstance(configured, (int, float)) and configured > 0:
            return float(configured)
        if getattr(self.settings, "target_fps", 0) > 0:
            return float(self.settings.target_fps)
        return 30.0

    def _rebuild_lineage_first_seen_ticks(self) -> None:
        if not self.creatures:
            self._lineage_first_seen_tick = {}
            return
        rebuilt: dict[int, int] = {}
        for creature in self.creatures:
            lineage_id = int(creature.lineage_id)
            known = self._lineage_first_seen_tick.get(lineage_id)
            if known is not None:
                rebuilt[lineage_id] = min(rebuilt.get(lineage_id, known), known)
                continue
            # Older snapshots may not persist first-seen lineage metadata.
            # Conservative fallback: infer a plausible origin from the oldest
            # living member age in the lineage (current_tick - max_member_age).
            inferred = max(0, self._frame - int(creature.age))
            rebuilt[lineage_id] = min(rebuilt.get(lineage_id, inferred), inferred)
        self._lineage_first_seen_tick = rebuilt

    def get_population_observability_summary(self) -> dict[str, float | int]:
        lineage = lineage_summary_for_population(
            self.creatures,
            current_tick=self._frame,
            lineage_first_seen_ticks=self._lineage_first_seen_tick,
        )
        return {
            "average_age_ticks": obs_average_age_ticks(self.creatures),
            "active_lineage_count": lineage.active_lineage_count,
            "average_lineage_age_ticks": lineage.average_lineage_age_ticks,
            "oldest_lineage_age_ticks": lineage.oldest_lineage_age_ticks,
        }

    def get_evolution_summary(self) -> dict[str, object]:
        current = obs_average_traits(self.creatures, TRACKED_TRAITS)
        baseline = self._run_baseline_traits or current
        deltas = obs_trait_deltas(current, baseline)
        return {
            "distance": obs_evolution_distance_mean_abs(deltas),
            "top_directions": obs_top_trait_directions(deltas),
            "deltas": deltas,
        }

    def get_creature_observability(self, creature: Creature) -> dict[str, object]:
        if creature not in self.creatures:
            return {}
        pop_traits = obs_average_traits(self.creatures, ("speed", "size", "sense_radius", "aggression", "efficiency", "depth_preference"))
        lineage_size = int(
            self.get_lineage_observability(int(creature.lineage_id)).get("count", 0)
        )
        first_seen = self._lineage_first_seen_tick.get(creature.lineage_id, max(0, self._frame - creature.age))
        species_ages = [c.age for c in self.creatures if c.species == creature.species] or [creature.age]
        younger_or_equal = sum(1 for age in species_ages if age <= creature.age)
        percentile = younger_or_equal / len(species_ages)

        deltas = {
            "speed": creature.genome.speed - pop_traits["speed"],
            "size": creature.genome.size - pop_traits["size"],
            "sense": creature.genome.sense_radius - pop_traits["sense_radius"],
            "aggr": creature.genome.aggression - pop_traits["aggression"],
        }
        sorted_deltas = sorted(deltas.items(), key=lambda item: abs(item[1]), reverse=True)
        above = tuple(f"{name} {delta:+.02f}" for name, delta in sorted_deltas if delta >= 0.05)
        below = tuple(f"{name} {delta:+.02f}" for name, delta in sorted_deltas if delta <= -0.05)
        tick_hz = self.get_simulation_tick_hz()
        return {
            "age_seconds": creature.age / tick_hz,
            "lineage_age_seconds": max(0, self._frame - first_seen) / tick_hz,
            "lineage_size": lineage_size,
            "species_age_percentile": percentile * 100.0,
            "above_population_traits": above[:3],
            "below_population_traits": below[:3],
        }

    def get_most_variable_trait(self) -> str:
        """Return trait name with highest variance across population."""
        if len(self.creatures) < 2:
            return "—"

        trait_names = [
            "speed", "size", "sense_radius", "aggression", "efficiency",
            "complexity", "symmetry", "stroke_scale", "appendages",
            "rotation_speed", "motion_style", "longevity", "conformity",
            "depth_preference",
        ]
        n = len(self.creatures)
        best_trait = "—"
        best_var = -1.0

        for trait in trait_names:
            values = [getattr(c.genome, trait) for c in self.creatures]
            mean = sum(values) / n
            var = sum((v - mean) ** 2 for v in values) / n
            if var > best_var:
                best_var = var
                best_trait = trait

        return best_trait

    @property
    def food_cycle_phase(self) -> float:
        """Current food cycle phase (0.0=famine, 1.0=feast)."""
        if not self.settings.food_cycle_enabled:
            return 1.0
        t = self._frame / max(1, self.settings.food_cycle_period)
        phase = 0.5 + 0.5 * math.sin(2 * math.pi * t)
        amplitude = max(0.0, min(1.0, self._get_food_cycle_amplitude()))
        return (1.0 - amplitude) + (amplitude * phase)

    @property
    def avg_old_age_lifespan_seconds(self) -> float:
        """Rolling average lifespan (seconds) for last 20 natural deaths."""
        if not self._old_age_lifespans:
            return 0.0
        return (sum(self._old_age_lifespans) / len(self._old_age_lifespans)) / 60.0

    @property
    def predator_prey_game_over_active(self) -> bool:
        return (
            self.settings.sim_mode == "predator_prey"
            and self._predator_prey_state.game_over_active
        )

    @property
    def predator_prey_rolling_average(self) -> float:
        history = self._predator_prey_state.run_history
        if not history:
            return 0.0
        return self._predator_prey_median(history)

    def _predator_prey_median(self, values: deque[int] | list[int]) -> float:
        if not values:
            return 0.0
        return float(median(values))

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def predator_prey_adjustment_step_multiplier(self) -> float:
        streak = max(
            0,
            self._predator_prey_state.adaptive_tuning.non_improving_run_streak,
        )
        threshold = self._get_predator_prey_step_escalation_runs()
        increase_percent = self._get_predator_prey_step_escalation_percent()
        steps = streak // threshold
        return 1.0 + (steps * (increase_percent / 100.0))

    @property
    def predator_prey_best_recent_ticks(self) -> int:
        history = self._predator_prey_state.run_history
        if not history:
            return 0
        return max(history)

    @property
    def population(self) -> int:
        """Current number of living creatures."""
        return len(self.creatures)

    @property
    def oldest_age(self) -> int:
        """Age of the oldest living creature in frames."""
        if not self.creatures:
            return 0
        return max(c.age for c in self.creatures)

    @property
    def food_count(self) -> int:
        """Current number of food particles."""
        return len(self.food_manager)

    def get_dominant_traits(self) -> dict[str, float]:
        """Get the average genome traits of the population."""
        if not self.creatures:
            return {}

        n = len(self.creatures)
        trait_names = [
            "speed", "size", "sense_radius", "aggression",
            "hue", "saturation", "efficiency",
            "complexity", "symmetry", "stroke_scale",
            "appendages", "rotation_speed", "motion_style", "longevity",
            "conformity", "depth_preference",
        ]
        totals = {t: 0.0 for t in trait_names}

        for creature in self.creatures:
            for t in trait_names:
                totals[t] += getattr(creature.genome, t)

        return {k: v / n for k, v in totals.items()}

    def build_observability_snapshot(self) -> dict[str, Any]:
        """Build a low-cost structured snapshot for benchmark summaries."""
        hunters, grazers, opportunists = self.get_hunter_grazer_counts()
        epistasis = self.get_epistasis_summary()
        snapshot: dict[str, Any] = {
            "population": self.population,
            "lineages": {
                "active": self.get_lineage_count(),
            },
            "strategies": {
                "hunters": hunters,
                "grazers": grazers,
                "opportunists": opportunists,
            },
            "epistasis": epistasis,
            "zone_occupancy": self.get_zone_occupancy_counts(),
        }

        if self.settings.sim_mode == "predator_prey":
            predator_count, prey_count = self.get_species_counts()
            depth_counts = self.get_depth_band_counts()
            pred_actual_speed, prey_actual_speed = self.get_species_avg_actual_speeds()
            predation_stats = self.get_recent_predation_stats()
            stability_stats = self.get_predator_prey_stability_stats()
            snapshot["species"] = {
                "predators": predator_count,
                "prey": prey_count,
                "predator_actual_speed": pred_actual_speed,
                "prey_actual_speed": prey_actual_speed,
            }
            snapshot["depth"] = {
                **depth_counts,
                "occupied_bands": sum(1 for count in depth_counts.values() if count > 0),
                "mean_preference": (
                    sum(creature.genome.depth_preference for creature in self.creatures) / len(self.creatures)
                    if self.creatures else 0.0
                ),
            }
            snapshot["predation"] = predation_stats
            snapshot["stability"] = {
                "seed": stability_stats["current_seed"],
                "sim_ticks": stability_stats["sim_ticks"],
                "survival_ticks": stability_stats["survival_ticks"],
                "rolling_average_survival_ticks": (
                    stability_stats["rolling_average_survival_ticks"]
                ),
                "best_recent_survival_ticks": (
                    stability_stats["best_recent_survival_ticks"]
                ),
                "trial_active": stability_stats["trial_active"],
                "trial_dial": stability_stats["trial_dial"],
                "trial_last_decision": stability_stats["trial_last_decision"],
            }
        elif self.settings.sim_mode == "boids":
            snapshot["flocks"] = self.get_boids_behavior_metrics()

        return snapshot

    def _reset_predator_diagnostics(self) -> None:
        self._predator_diag_next_life_id = 1
        self._predator_diag_active.clear()
        self._predator_diag_completed.clear()
        self._predator_diag_kill_energy_summary = self._new_predator_kill_energy_summary()
        self._predator_depth_fatigue_summary = self._new_predator_depth_fatigue_summary()
        for events in self._predator_diag_events.values():
            events.clear()

    def _copy_predator_depth_fatigue_summary(self) -> dict[str, Any]:
        summary = dict(self._predator_depth_fatigue_summary)
        kill_samples = max(0, int(summary.get("kill_samples_with_chase_pressure", 0)))
        summary["average_chase_pressure_at_kill"] = (
            float(summary.get("chase_pressure_at_kill_total", 0.0)) / kill_samples
            if kill_samples > 0
            else None
        )
        summary["average_depth_fatigue_at_kill"] = (
            float(summary.get("depth_fatigue_at_kill_total", 0.0)) / kill_samples
            if kill_samples > 0
            else None
        )
        return summary

    def _new_predator_kill_energy_summary(self) -> dict[str, Any]:
        return {
            "kill_count": 0,
            "total_prey_energy_at_kill": 0.0,
            "kill_energy_nominal_total": 0.0,
            "kill_energy_actual_total": 0.0,
            "kill_energy_wasted_to_full_cap_total": 0.0,
            "kill_energy_unconverted_due_to_kill_cap_total": 0.0,
            "cap_limited_kill_count": 0,
            "predator_full_limited_kill_count": 0,
            "crossed_reproduction_threshold_kill_count": 0,
            "already_reproduction_ready_kill_count": 0,
            "prey_energy_at_kill_values": [],
            "nominal_kill_energy_gain_values": [],
            "actual_kill_energy_gain_values": [],
            "old_formula_nominal_total": 0.0,
            "biomass_added_nominal_total": 0.0,
            "biomass_bonus_helped_kill_count": 0,
        }

    def _build_predator_kill_energy_record(
        self,
        *,
        predator_kill_energy_cap: float,
        predator_pre_kill_energy: float,
        predator_post_kill_energy: float,
        prey_energy_at_kill: float,
        biomass_bonus: float,
        repro_threshold: float,
    ) -> dict[str, Any]:
        raw_kill_energy_before_cap = prey_energy_at_kill + biomass_bonus
        nominal_kill_energy_gain = min(predator_kill_energy_cap, raw_kill_energy_before_cap)
        actual_kill_energy_gain = max(
            0.0,
            predator_post_kill_energy - predator_pre_kill_energy,
        )
        wasted_kill_energy_to_predator_full_cap = max(
            0.0,
            nominal_kill_energy_gain - actual_kill_energy_gain,
        )
        prey_energy_unconverted_due_to_kill_cap = max(
            0.0,
            raw_kill_energy_before_cap - nominal_kill_energy_gain,
        )
        old_formula_nominal_gain = min(predator_kill_energy_cap, prey_energy_at_kill)
        biomass_added_nominal_gain = max(
            0.0,
            nominal_kill_energy_gain - old_formula_nominal_gain,
        )
        return {
            "predator_kill_energy_cap": predator_kill_energy_cap,
            "predator_pre_kill_energy": predator_pre_kill_energy,
            "predator_post_kill_energy": predator_post_kill_energy,
            "prey_energy_at_kill": prey_energy_at_kill,
            "biomass_bonus": biomass_bonus,
            "raw_kill_energy_before_cap": raw_kill_energy_before_cap,
            "nominal_kill_energy_gain": nominal_kill_energy_gain,
            "actual_kill_energy_gain": actual_kill_energy_gain,
            "wasted_kill_energy_to_predator_full_cap": (
                wasted_kill_energy_to_predator_full_cap
            ),
            "prey_energy_unconverted_due_to_kill_cap": (
                prey_energy_unconverted_due_to_kill_cap
            ),
            "old_formula_nominal_gain": old_formula_nominal_gain,
            "biomass_added_nominal_gain": biomass_added_nominal_gain,
            "kill_gain_was_cap_limited": raw_kill_energy_before_cap > predator_kill_energy_cap,
            "kill_gain_was_predator_full_limited": (
                actual_kill_energy_gain < nominal_kill_energy_gain
            ),
            "predator_crossed_reproduction_threshold_on_kill": (
                predator_pre_kill_energy < repro_threshold <= predator_post_kill_energy
            ),
            "predator_was_already_reproduction_ready_before_kill": (
                predator_pre_kill_energy >= repro_threshold
            ),
            "predator_reproduction_energy_surplus_after_kill": max(
                0.0,
                predator_post_kill_energy - repro_threshold,
            ),
        }

    def _record_predator_kill_energy_summary(
        self,
        summary: dict[str, Any],
        record: dict[str, Any],
    ) -> None:
        summary["kill_count"] += 1
        summary["total_prey_energy_at_kill"] += record["prey_energy_at_kill"]
        summary["kill_energy_nominal_total"] += record["nominal_kill_energy_gain"]
        summary["kill_energy_actual_total"] += record["actual_kill_energy_gain"]
        summary["kill_energy_wasted_to_full_cap_total"] += record[
            "wasted_kill_energy_to_predator_full_cap"
        ]
        summary["kill_energy_unconverted_due_to_kill_cap_total"] += record[
            "prey_energy_unconverted_due_to_kill_cap"
        ]
        if record["kill_gain_was_cap_limited"]:
            summary["cap_limited_kill_count"] += 1
        if record["kill_gain_was_predator_full_limited"]:
            summary["predator_full_limited_kill_count"] += 1
        if record["predator_crossed_reproduction_threshold_on_kill"]:
            summary["crossed_reproduction_threshold_kill_count"] += 1
        if record["predator_was_already_reproduction_ready_before_kill"]:
            summary["already_reproduction_ready_kill_count"] += 1
        summary["prey_energy_at_kill_values"].append(record["prey_energy_at_kill"])
        summary["nominal_kill_energy_gain_values"].append(
            record["nominal_kill_energy_gain"]
        )
        summary["actual_kill_energy_gain_values"].append(
            record["actual_kill_energy_gain"]
        )
        summary["old_formula_nominal_total"] += record.get("old_formula_nominal_gain", record["nominal_kill_energy_gain"])
        summary["biomass_added_nominal_total"] += record.get("biomass_added_nominal_gain", 0.0)
        if record.get("biomass_added_nominal_gain", 0.0) > 0.0:
            summary["biomass_bonus_helped_kill_count"] += 1

    def _copy_predator_kill_energy_summary(self, summary: dict[str, Any]) -> dict[str, Any]:
        kill_count = int(summary["kill_count"])
        total_prey_energy_at_kill = float(summary["total_prey_energy_at_kill"])
        nominal_total = float(summary["kill_energy_nominal_total"])
        actual_total = float(summary["kill_energy_actual_total"])
        prey_energy_values = [
            float(value) for value in summary["prey_energy_at_kill_values"]
        ]
        nominal_values = [
            float(value) for value in summary["nominal_kill_energy_gain_values"]
        ]
        actual_values = [
            float(value) for value in summary["actual_kill_energy_gain_values"]
        ]
        return {
            "kill_count": kill_count,
            "total_prey_energy_at_kill": total_prey_energy_at_kill,
            "kill_energy_nominal_total": nominal_total,
            "kill_energy_actual_total": actual_total,
            "kill_energy_wasted_to_full_cap_total": float(
                summary["kill_energy_wasted_to_full_cap_total"]
            ),
            "kill_energy_unconverted_due_to_kill_cap_total": float(
                summary["kill_energy_unconverted_due_to_kill_cap_total"]
            ),
            "kill_energy_efficiency_actual_vs_nominal": _safe_ratio(
                actual_total,
                nominal_total,
            ),
            "kill_energy_conversion_from_prey": _safe_ratio(
                actual_total,
                total_prey_energy_at_kill,
            ),
            "average_prey_energy_at_kill": (
                total_prey_energy_at_kill / kill_count if kill_count > 0 else None
            ),
            "median_prey_energy_at_kill": (
                float(median(prey_energy_values)) if prey_energy_values else None
            ),
            "p90_prey_energy_at_kill": _p90(prey_energy_values),
            "average_nominal_kill_energy_gain": (
                nominal_total / kill_count if kill_count > 0 else None
            ),
            "median_nominal_kill_energy_gain": (
                float(median(nominal_values)) if nominal_values else None
            ),
            "p90_nominal_kill_energy_gain": _p90(nominal_values),
            "average_actual_kill_energy_gain": (
                actual_total / kill_count if kill_count > 0 else None
            ),
            "median_actual_kill_energy_gain": (
                float(median(actual_values)) if actual_values else None
            ),
            "p90_actual_kill_energy_gain": _p90(actual_values),
            "share_of_kills_cap_limited": _safe_ratio(
                float(summary["cap_limited_kill_count"]),
                float(kill_count),
            ),
            "share_of_kills_predator_full_limited": _safe_ratio(
                float(summary["predator_full_limited_kill_count"]),
                float(kill_count),
            ),
            "share_of_kills_crossed_reproduction_threshold": _safe_ratio(
                float(summary["crossed_reproduction_threshold_kill_count"]),
                float(kill_count),
            ),
            "share_of_kills_already_reproduction_ready": _safe_ratio(
                float(summary["already_reproduction_ready_kill_count"]),
                float(kill_count),
            ),
            "predator_kill_biomass_bonus": float(
                self._get_predator_kill_biomass_bonus()
            ) if self.settings.sim_mode == "predator_prey" else 0.0,
            "old_formula_nominal_total": float(summary["old_formula_nominal_total"]),
            "biomass_added_nominal_total": float(summary["biomass_added_nominal_total"]),
            "average_biomass_added_gain_per_kill": (
                float(summary["biomass_added_nominal_total"]) / kill_count
                if kill_count > 0
                else None
            ),
            "share_of_kills_helped_by_biomass_bonus": _safe_ratio(
                float(summary["biomass_bonus_helped_kill_count"]),
                float(kill_count),
            ),
            "actual_conversion_from_prey_and_biomass_raw_energy": _safe_ratio(
                actual_total,
                total_prey_energy_at_kill
                + float(summary["biomass_added_nominal_total"]),
            ),
            "cap_limited_share_after_biomass": _safe_ratio(
                float(summary["cap_limited_kill_count"]),
                float(kill_count),
            ),
            "predator_full_limited_share_after_biomass": _safe_ratio(
                float(summary["predator_full_limited_kill_count"]),
                float(kill_count),
            ),
            "reproduction_threshold_crossing_share_after_biomass": _safe_ratio(
                float(summary["crossed_reproduction_threshold_kill_count"]),
                float(kill_count),
            ),
        }

    def _register_predator_life(self, creature: Creature, *, origin: str) -> dict[str, Any]:
        phenotype = self._get_effective_phenotype(creature)
        predator_count = sum(1 for c in self.creatures if c.species == "predator")
        life = {
            "life_id": self._predator_diag_next_life_id,
            "origin": origin,
            "lineage_id": creature.lineage_id,
            "start_frame": self._frame,
            "end_frame": None,
            "start_energy": creature.energy,
            "end_energy": None,
            "kills": 0,
            "kill_pre_energies": [],
            "kill_post_energies": [],
            "highest_energy": creature.energy,
            "frames_observed": 0,
            "frames_with_prey_sighted": 0,
            "prey_scarce_frames": 0,
            "cross_band_contact_misses": 0,
            "cross_band_misses_inside_refuge": 0,
            "cross_band_misses_outside_refuge": 0,
            "near_contact_frames": 0,
            "near_contact_no_kill_frames": 0,
            "near_contact_same_depth_no_kill_frames": 0,
            "near_contact_cross_depth_no_kill_frames": 0,
            "near_contact_with_old_prey_frames": 0,
            "near_contact_with_low_energy_prey_frames": 0,
            "near_contact_no_kill_with_old_prey_frames": 0,
            "near_contact_no_kill_with_low_energy_prey_frames": 0,
            "sustained_chase_frames": 0,
            "max_sustained_chase_frames": 0,
            "kills_after_sustained_chase": 0,
            "committed_depth_tracking_events": 0,
            "committed_depth_tracking_kills": 0,
            "cross_depth_near_contact_before_tracking": 0,
            "cross_depth_near_contact_after_tracking": 0,
            "kills_after_depth_fatigue": 0,
            "kills_after_committed_depth_tracking": 0,
            "chase_pressure_at_kill_values": [],
            "depth_fatigue_at_kill_values": [],
            "memory_chase_frames": 0,
            "memory_target_reacquisitions": 0,
            "memory_target_dropped_frames": 0,
            "memory_target_expired_drops": 0,
            "target_switches": 0,
            "kills_after_memory_chase": 0,
            "kill_energy_events": [],
            "kill_energy_summary": self._new_predator_kill_energy_summary(),
            "killed_prey_age_fractions": [],
            "killed_prey_energies": [],
            "killed_prey_condition_buckets": [],
            "births_produced": 0,
            "threshold_min": None,
            "threshold_max": None,
            "closest_peak_gap": None,
            "closest_repro_check_gap": None,
            "peak_reached_threshold": False,
            "repro_check_reached_threshold": False,
            "last_saw_prey_frame": None,
            "last_kill_frame": None,
            "death_cause": None,
            "death_context": None,
            "end_reason": None,
            "age_at_death": None,
            "predator_count_at_death": None,
            "prey_count_at_death": None,
            "depth_band_at_death": None,
            "hunting_ground_frames": 0,
            "refuge_frames": 0,
            "refuge_bonus_factor_sum": 0.0,
            "kills_inside_refuge": 0,
            "kills_outside_refuge": 0,
            "died_inside_refuge": False,
            "died_in_hunting_ground": False,
            "death_zone_type": None,
            "refuge_bonus_factor_at_death": 0.0,
            "local_predator_density_at_death": None,
            "strategy_bucket_at_start": phenotype.strategy_bucket,
            "strategy_bucket_at_end": None,
            "phenotype_modifiers_at_start": {
                "speed_mult": phenotype.speed_mult,
                "movement_cost_mult": phenotype.movement_cost_mult,
                "metabolic_cost_mult": phenotype.metabolic_cost_mult,
                "sense_radius_mult": phenotype.sense_radius_mult,
                "food_efficiency_mult": phenotype.food_efficiency_mult,
                "reproduction_threshold_mult": phenotype.reproduction_threshold_mult,
                "predation_contact_mult": phenotype.predation_contact_mult,
                "flee_agility_mult": phenotype.flee_agility_mult,
            },
            "phenotype_modifiers_at_end": None,
            "born_during_low_predator_rarity": predator_count <= 5,
            "rarity_pressure_at_start": 0.0,
            "rarity_pressure_at_end": 0.0,
            "rarity_frames": 0,
            "rarity_pressure_sum": 0.0,
            "avg_rarity_pressure": 0.0,
            "kills_while_rarity_active": 0,
            "births_while_rarity_active": 0,
            "deaths_while_rarity_active": 0,
            "rarity_hunt_sense_bonus_at_death": 0.0,
            "rarity_contact_bonus_at_death": 0.0,
            "rarity_depth_transition_bonus_at_death": 0.0,
            "rarity_hunting_cost_reduction_at_death": 0.0,
            "_last_target_id": None,
            "_current_chase_frames": 0,
            "_memory_target_id": None,
            "_memory_target_pos": None,
            "_memory_target_depth_band": None,
            "_memory_last_seen_frame": None,
            "_memory_last_score": None,
            "_memory_chasing": False,
            "_current_chase_used_memory": False,
            "_current_chase_memory_target_id": None,
            "_last_memory_chase_frame": None,
            "_current_chase_had_committed_tracking": False,
            "_current_chase_committed_tracking_target_id": None,
            "_last_committed_depth_tracking_frame": None,
            "_committed_depth_tracking_cooldown_until": -1,
        }
        self._predator_diag_next_life_id += 1
        self._predator_diag_active[id(creature)] = life
        return life

    def _ensure_predator_life(self, creature: Creature) -> dict[str, Any]:
        life = self._predator_diag_active.get(id(creature))
        if life is None:
            life = self._register_predator_life(creature, origin="observed")
        return life

    def _record_predator_prey_sighting(self, predator: Creature) -> None:
        life = self._ensure_predator_life(predator)
        life["frames_with_prey_sighted"] += 1
        life["last_saw_prey_frame"] = self._frame

    def _clear_predator_chase_state(self, predator: Creature) -> None:
        life = self._predator_diag_active.get(id(predator))
        if life is None:
            return
        life["_last_target_id"] = None
        life["_current_chase_frames"] = 0
        life["_current_chase_had_committed_tracking"] = False
        life["_current_chase_committed_tracking_target_id"] = None
        self._clear_predator_memory_target(predator)

    def _record_predator_chase_target(
        self,
        predator: Creature,
        prey: Creature,
    ) -> None:
        life = self._ensure_predator_life(predator)
        target_id = id(prey)
        if life["_last_target_id"] == target_id:
            life["_current_chase_frames"] += 1
        else:
            life["_last_target_id"] = target_id
            life["_current_chase_frames"] = 1
        current_frames = int(life["_current_chase_frames"])
        life["max_sustained_chase_frames"] = max(
            int(life["max_sustained_chase_frames"]),
            current_frames,
        )
        if current_frames >= self._get_predator_sustained_chase_min_frames():
            life["sustained_chase_frames"] += 1

    def _remember_predator_target(self, predator: Creature, prey: Creature, sensed: tuple[float, float], score: float | None) -> None:
        if not self._predator_target_memory_enabled():
            return
        life = self._ensure_predator_life(predator)
        previous = life.get("_memory_target_id")
        current = id(prey)
        was_valid_previous_target = (
            previous is not None
            and any(
                id(c) == previous and c.species == "prey" and c.energy > 0.0
                for c in self.creatures
            )
        )
        if was_valid_previous_target and previous != current:
            life["target_switches"] += 1
        if life.get("_memory_chasing") and previous == current:
            life["memory_target_reacquisitions"] += 1
            life["_current_chase_used_memory"] = True
            life["_current_chase_memory_target_id"] = current
        life["_memory_target_id"] = current
        life["_memory_target_pos"] = (float(sensed[0]), float(sensed[1]))
        life["_memory_target_depth_band"] = int(prey.depth_band)
        life["_memory_last_seen_frame"] = self._frame
        life["_memory_last_score"] = score
        life["_memory_chasing"] = False

    def _get_predator_memory_target(self, predator: Creature, *, sense: float) -> tuple[Creature, tuple[float, float]] | None:
        if not self._predator_target_memory_enabled():
            return None
        life = self._predator_diag_active.get(id(predator))
        if life is None:
            return None
        target_id = life.get("_memory_target_id")
        last_seen = life.get("_memory_last_seen_frame")
        pos = life.get("_memory_target_pos")
        if target_id is None or last_seen is None or pos is None:
            return None
        if (self._frame - int(last_seen)) > self._get_predator_target_memory_ticks():
            life["memory_target_dropped_frames"] += 1
            life["memory_target_expired_drops"] += 1
            self._clear_predator_memory_target(predator)
            return None
        target = next((c for c in self.creatures if id(c) == target_id), None)
        if target is None or target.energy <= 0.0 or target.species != "prey":
            life["memory_target_dropped_frames"] += 1
            self._clear_predator_memory_target(predator)
            return None
        memory_radius = sense * self._get_predator_target_memory_radius_mult()
        if predator.distance_to(pos[0], pos[1], self.width, self.height) > memory_radius:
            life["memory_target_dropped_frames"] += 1
            self._clear_predator_memory_target(predator)
            return None
        life["_memory_chasing"] = True
        return target, (float(pos[0]), float(pos[1]))

    def _record_predator_memory_chase(self, predator: Creature, prey: Creature) -> None:
        life = self._ensure_predator_life(predator)
        life["memory_chase_frames"] += 1
        life["_current_chase_used_memory"] = True
        life["_current_chase_memory_target_id"] = id(prey)
        life["_last_memory_chase_frame"] = self._frame

    def _clear_predator_memory_target(self, predator: Creature) -> None:
        life = self._predator_diag_active.get(id(predator))
        if life is None:
            return
        life["_memory_target_id"] = None
        life["_memory_target_pos"] = None
        life["_memory_target_depth_band"] = None
        life["_memory_last_seen_frame"] = None
        life["_memory_last_score"] = None
        life["_memory_chasing"] = False
        life["_current_chase_used_memory"] = False
        life["_current_chase_memory_target_id"] = None
        life["_last_memory_chase_frame"] = None

    def _classify_prey_condition_bucket(
        self,
        prey: Creature,
        *,
        prey_energy: float | None = None,
    ) -> str:
        age_fraction = prey.get_age_fraction()
        energy = prey.energy if prey_energy is None else prey_energy
        is_old = age_fraction >= _PREY_FRAILTY_OLD_AGE_FRACTION
        is_low_energy = energy < self._get_prey_flee_low_energy_threshold()
        if is_old and is_low_energy:
            return "old_low_energy"
        if is_old:
            return "old"
        if is_low_energy:
            return "low_energy"
        return "young_healthy"

    def _record_predator_near_contact(
        self,
        predator: Creature,
        prey: Creature,
        *,
        same_depth: bool,
        no_kill: bool,
    ) -> None:
        life = self._ensure_predator_life(predator)
        age_fraction = prey.get_age_fraction()
        is_old = age_fraction >= _PREY_FRAILTY_OLD_AGE_FRACTION
        is_low_energy = prey.energy < self._get_prey_flee_low_energy_threshold()
        life["near_contact_frames"] += 1
        if is_old:
            life["near_contact_with_old_prey_frames"] += 1
        if is_low_energy:
            life["near_contact_with_low_energy_prey_frames"] += 1
        if not no_kill:
            return
        life["near_contact_no_kill_frames"] += 1
        if same_depth:
            life["near_contact_same_depth_no_kill_frames"] += 1
        else:
            life["near_contact_cross_depth_no_kill_frames"] += 1
        if is_old:
            life["near_contact_no_kill_with_old_prey_frames"] += 1
        if is_low_energy:
            life["near_contact_no_kill_with_low_energy_prey_frames"] += 1

    def _record_predator_cross_band_miss(
        self,
        predator: Creature,
        *,
        hunt_modifiers: PredatorHuntModifiers,
    ) -> None:
        life = self._ensure_predator_life(predator)
        life["cross_band_contact_misses"] += 1
        if hunt_modifiers.refuge.active:
            life["cross_band_misses_inside_refuge"] += 1
        else:
            life["cross_band_misses_outside_refuge"] += 1

    def _record_predator_kill(
        self,
        predator: Creature,
        *,
        pre_kill_energy: float,
        post_kill_energy: float,
        repro_threshold: float,
        prey: Creature,
        prey_energy_at_kill: float,
        biomass_bonus: float = 0.0,
        refuge_modifiers: PredatorRefugeModifiers,
        rarity_modifiers: PredatorRarityModifiers,
    ) -> None:
        life = self._ensure_predator_life(predator)
        kill_energy_record = self._build_predator_kill_energy_record(
            predator_kill_energy_cap=self._get_predator_kill_energy_gain_cap(),
            predator_pre_kill_energy=pre_kill_energy,
            predator_post_kill_energy=post_kill_energy,
            prey_energy_at_kill=prey_energy_at_kill,
            biomass_bonus=biomass_bonus,
            repro_threshold=repro_threshold,
        )
        life["kills"] += 1
        if refuge_modifiers.active:
            life["kills_inside_refuge"] += 1
        else:
            life["kills_outside_refuge"] += 1
        life["last_kill_frame"] = self._frame
        life["highest_energy"] = max(life["highest_energy"], post_kill_energy)
        life["kill_pre_energies"].append(pre_kill_energy)
        life["kill_post_energies"].append(post_kill_energy)
        life["kill_energy_events"].append(kill_energy_record)
        chase_pressure_state = self._prey_chase_pressure.get(id(prey))
        chase_pressure_at_kill = (
            chase_pressure_state.current_chase_pressure_ticks
            if chase_pressure_state is not None
            else 0
        )
        depth_fatigue_at_kill = (
            chase_pressure_state.depth_escape_fatigue
            if chase_pressure_state is not None
            else 0.0
        )
        life["chase_pressure_at_kill_values"].append(chase_pressure_at_kill)
        life["depth_fatigue_at_kill_values"].append(depth_fatigue_at_kill)
        self._predator_depth_fatigue_summary["chase_pressure_at_kill_total"] += float(
            chase_pressure_at_kill
        )
        self._predator_depth_fatigue_summary["depth_fatigue_at_kill_total"] += float(
            depth_fatigue_at_kill
        )
        self._predator_depth_fatigue_summary["kill_samples_with_chase_pressure"] += 1
        self._record_predator_kill_energy_summary(
            life["kill_energy_summary"],
            kill_energy_record,
        )
        self._record_predator_kill_energy_summary(
            self._predator_diag_kill_energy_summary,
            kill_energy_record,
        )
        life["killed_prey_age_fractions"].append(prey.get_age_fraction())
        life["killed_prey_energies"].append(prey_energy_at_kill)
        life["killed_prey_condition_buckets"].append(
            self._classify_prey_condition_bucket(
                prey,
                prey_energy=prey_energy_at_kill,
            )
        )
        if life["_current_chase_frames"] >= self._get_predator_sustained_chase_min_frames():
            life["kills_after_sustained_chase"] += 1
        if depth_fatigue_at_kill >= 0.05:
            life["kills_after_depth_fatigue"] += 1
            self._predator_depth_fatigue_summary["kills_after_depth_fatigue"] += 1
        if (
            life.get("_current_chase_had_committed_tracking")
            and life.get("_current_chase_committed_tracking_target_id") == id(prey)
        ):
            life["committed_depth_tracking_kills"] += 1
            life["kills_after_committed_depth_tracking"] += 1
            self._predator_depth_fatigue_summary[
                "committed_depth_tracking_kills"
            ] += 1
            self._predator_depth_fatigue_summary[
                "kills_after_committed_depth_tracking"
            ] += 1
        if (
            life.get("_current_chase_used_memory")
            and life.get("_current_chase_memory_target_id") == id(prey)
        ):
            life["kills_after_memory_chase"] += 1
        life["_current_chase_used_memory"] = False
        life["_current_chase_memory_target_id"] = None
        life["_current_chase_had_committed_tracking"] = False
        life["_current_chase_committed_tracking_target_id"] = None
        self._record_predator_gap(
            life,
            key="closest_peak_gap",
            gap=repro_threshold - post_kill_energy,
        )
        if post_kill_energy >= repro_threshold:
            life["peak_reached_threshold"] = True
        if rarity_modifiers.active:
            life["kills_while_rarity_active"] += 1

    def _record_predator_post_cost_state(
        self,
        predator: Creature,
        *,
        repro_threshold: float,
        prey_scarce: bool,
        creature_bucket: dict[tuple[int, int], list[Creature]] | None = None,
        refuge_modifiers: PredatorRefugeModifiers | None = None,
        rarity_modifiers: PredatorRarityModifiers | None = None,
    ) -> None:
        life = self._ensure_predator_life(predator)
        life["frames_observed"] += 1
        if prey_scarce:
            life["prey_scarce_frames"] += 1
        zone_context = self.zone_manager.get_zone_context_at(predator.x, predator.y)
        if zone_context.zone_type == "hunting_ground":
            life["hunting_ground_frames"] += 1
        active_refuge = refuge_modifiers or self._get_predator_refuge_modifiers(
            predator,
            creature_bucket,
        )
        if active_refuge.active:
            life["refuge_frames"] += 1
            life["refuge_bonus_factor_sum"] += active_refuge.refuge_factor
        active_rarity = rarity_modifiers or self._get_predator_rarity_modifiers(predator)
        life["rarity_pressure_at_end"] = active_rarity.pressure
        if life["frames_observed"] == 1:
            life["rarity_pressure_at_start"] = active_rarity.pressure
        if active_rarity.pressure > 0.0:
            life["rarity_pressure_sum"] += active_rarity.pressure
        if active_rarity.active:
            life["rarity_frames"] += 1
        life["highest_energy"] = max(life["highest_energy"], predator.energy)
        if life["threshold_min"] is None or repro_threshold < life["threshold_min"]:
            life["threshold_min"] = repro_threshold
        if life["threshold_max"] is None or repro_threshold > life["threshold_max"]:
            life["threshold_max"] = repro_threshold
        self._record_predator_gap(
            life,
            key="closest_repro_check_gap",
            gap=repro_threshold - predator.energy,
        )
        if predator.energy >= repro_threshold:
            life["repro_check_reached_threshold"] = True

    def _record_predator_gap(self, life: dict[str, Any], *, key: str, gap: float) -> None:
        if gap <= 0.0:
            life[key] = 0.0
            return
        current = life[key]
        if current is None or gap < current:
            life[key] = gap

    def _finalize_predator_life(
        self,
        creature: Creature,
        *,
        end_reason: str,
        death_cause: str,
    ) -> None:
        life = self._predator_diag_active.pop(id(creature), None)
        if life is None:
            return
        life["end_frame"] = self._frame
        life["end_energy"] = creature.energy
        life["lineage_id"] = creature.lineage_id
        life["death_cause"] = death_cause
        life["death_context"] = self._classify_predator_death_context(life, death_cause)
        life["end_reason"] = end_reason
        life["age_at_death"] = creature.age
        predator_count = sum(1 for c in self.creatures if c.species == "predator")
        prey_count = sum(1 for c in self.creatures if c.species == "prey")
        life["predator_count_at_death"] = predator_count
        life["prey_count_at_death"] = prey_count
        life["depth_band_at_death"] = creature.depth_band
        creature_bucket = self._build_creature_bucket()
        refuge_modifiers = self._get_predator_refuge_modifiers(
            creature,
            creature_bucket,
        )
        zone_context = self.zone_manager.get_zone_context_at(creature.x, creature.y)
        life["died_inside_refuge"] = refuge_modifiers.active
        life["died_in_hunting_ground"] = zone_context.zone_type == "hunting_ground"
        life["death_zone_type"] = zone_context.zone_type
        life["refuge_bonus_factor_at_death"] = refuge_modifiers.refuge_factor
        life["local_predator_density_at_death"] = (
            refuge_modifiers.local_predator_count
        )
        end_phenotype = self._get_effective_phenotype(creature)
        rarity_modifiers = self._get_predator_rarity_modifiers(creature)
        life["rarity_pressure_at_end"] = rarity_modifiers.pressure
        if life["frames_observed"] <= 0:
            life["rarity_pressure_at_start"] = rarity_modifiers.pressure
        if rarity_modifiers.active:
            life["deaths_while_rarity_active"] = 1
        life["rarity_hunt_sense_bonus_at_death"] = rarity_modifiers.hunt_sense_bonus
        life["rarity_contact_bonus_at_death"] = rarity_modifiers.contact_bonus
        life["rarity_depth_transition_bonus_at_death"] = rarity_modifiers.depth_transition_bonus
        life["rarity_hunting_cost_reduction_at_death"] = rarity_modifiers.hunting_cost_reduction
        if life["frames_observed"] > 0:
            life["avg_rarity_pressure"] = life["rarity_pressure_sum"] / life["frames_observed"]
        life["strategy_bucket_at_end"] = end_phenotype.strategy_bucket
        life["phenotype_modifiers_at_end"] = {
            "speed_mult": end_phenotype.speed_mult,
            "movement_cost_mult": end_phenotype.movement_cost_mult,
            "metabolic_cost_mult": end_phenotype.metabolic_cost_mult,
            "sense_radius_mult": end_phenotype.sense_radius_mult,
            "food_efficiency_mult": end_phenotype.food_efficiency_mult,
            "reproduction_threshold_mult": end_phenotype.reproduction_threshold_mult,
            "predation_contact_mult": end_phenotype.predation_contact_mult,
            "flee_agility_mult": end_phenotype.flee_agility_mult,
        }
        self._predator_diag_completed.append(life)

    def _classify_predator_death_context(
        self,
        life: dict[str, Any],
        death_cause: str,
    ) -> str:
        if death_cause == "old_age":
            return "old_age"
        last_saw_prey_frame = life["last_saw_prey_frame"]
        if last_saw_prey_frame is None:
            return "long_scarcity"
        frames_since_sighting = self._frame - last_saw_prey_frame
        if frames_since_sighting <= _PREDATOR_DIAG_ACTIVE_HUNT_FRAMES:
            return "active_hunting"
        if frames_since_sighting <= _PREDATOR_DIAG_FAILED_PURSUIT_FRAMES:
            return "after_failed_pursuit"
        return "long_scarcity"

    def _copy_predator_life(self, life: dict[str, Any]) -> dict[str, Any]:
        clone = dict(life)
        clone["kill_pre_energies"] = list(life["kill_pre_energies"])
        clone["kill_post_energies"] = list(life["kill_post_energies"])
        clone["kill_energy_events"] = [
            dict(event) for event in life.get("kill_energy_events", [])
        ]
        clone["kill_energy_summary"] = self._copy_predator_kill_energy_summary(
            life.get("kill_energy_summary", self._new_predator_kill_energy_summary())
        )
        clone["killed_prey_age_fractions"] = list(life["killed_prey_age_fractions"])
        clone["killed_prey_energies"] = list(life["killed_prey_energies"])
        clone["killed_prey_condition_buckets"] = list(
            life["killed_prey_condition_buckets"]
        )
        clone["chase_pressure_at_kill_values"] = list(
            life.get("chase_pressure_at_kill_values", [])
        )
        clone["depth_fatigue_at_kill_values"] = list(
            life.get("depth_fatigue_at_kill_values", [])
        )
        clone["average_chase_pressure_at_kill"] = (
            sum(clone["chase_pressure_at_kill_values"])
            / len(clone["chase_pressure_at_kill_values"])
            if clone["chase_pressure_at_kill_values"]
            else None
        )
        clone["average_depth_fatigue_at_kill"] = (
            sum(clone["depth_fatigue_at_kill_values"])
            / len(clone["depth_fatigue_at_kill_values"])
            if clone["depth_fatigue_at_kill_values"]
            else None
        )
        if life.get("phenotype_modifiers_at_start") is not None:
            clone["phenotype_modifiers_at_start"] = dict(life["phenotype_modifiers_at_start"])
        if life.get("phenotype_modifiers_at_end") is not None:
            clone["phenotype_modifiers_at_end"] = dict(life["phenotype_modifiers_at_end"])
        clone.pop("_last_target_id", None)
        clone.pop("_current_chase_frames", None)
        clone.pop("_current_chase_had_committed_tracking", None)
        clone.pop("_current_chase_committed_tracking_target_id", None)
        clone.pop("_last_committed_depth_tracking_frame", None)
        clone.pop("_committed_depth_tracking_cooldown_until", None)
        return clone
