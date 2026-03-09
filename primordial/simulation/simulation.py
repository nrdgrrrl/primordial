"""Simulation module - main simulation controller."""

from __future__ import annotations

import math
import random
from collections import deque
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
from .zones import ZoneManager

if TYPE_CHECKING:
    from ..settings import Settings

AttackRenderEvent = tuple[float, float, float, float, float]

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


class Simulation:
    """
    Main simulation controller for the Primordial screensaver.

    Manages creatures, food, and the simulation step logic.
    The simulation is completely decoupled from rendering - it only
    updates state and exposes it for the renderer to read.

    Event queues (cleared by renderer each frame):
    - death_events: list of dicts with position/genome info for dead creatures
    - birth_events: list of newly created offspring creatures
    - cosmic_ray_events: list of (x, y) positions where cosmic rays hit
    - active_attacks: list of (ax, ay, tx, ty, hue) for attack line rendering
    """

    def __init__(
        self,
        width: int,
        height: int,
        settings: "Settings",
        *,
        bootstrap_world: bool = True,
    ) -> None:
        self.width = width
        self.height = height
        self.settings = settings

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

        # Event queues read by renderer each frame (renderer clears them)
        self.death_events: list[dict] = []
        self.birth_events: list[Creature] = []
        self.cosmic_ray_events: list[tuple[float, float]] = []
        self.active_attacks: list[AttackRenderEvent] = []
        self.predation_kill_count = 0
        self._recent_kill_frames: deque[int] = deque()
        self._recent_cross_band_miss_frames: deque[int] = deque()
        self._predation_victims_this_frame: set[int] = set()

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

        # Initialize population
        if bootstrap_world:
            self._spawn_initial_population()

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

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _alloc_lineage_id(self) -> int:
        """Allocate and return a new unique lineage ID."""
        lid = self._next_lineage_id
        self._next_lineage_id += 1
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
        for _ in range(self.settings.initial_population):
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

        # Seed food for prey across the bounded depth bands.
        for _ in range(200):
            self.food_manager.spawn(
                depth_band=self._choose_predator_prey_food_depth_band()
            )

    def _spawn_initial_population_boids(self) -> None:
        """Spawn boids population with mid-range conformity/efficiency."""
        initial_pop = self._get_mode_param("initial_population", self.settings.initial_population)
        for _ in range(initial_pop):
            lid = self._alloc_lineage_id()
            genome = Genome(
                speed=random.uniform(0.3, 0.7),
                size=random.uniform(0.2, 0.6),
                sense_radius=random.uniform(0.4, 0.9),
                aggression=random.uniform(0.3, 0.7),
                hue=random.random(),
                saturation=random.uniform(0.6, 1.0),
                efficiency=random.uniform(0.4, 0.8),
                complexity=random.random(),
                symmetry=random.random(),
                stroke_scale=random.random(),
                appendages=random.random(),
                rotation_speed=random.random(),
                motion_style=random.random(),
                longevity=random.random(),
                conformity=random.uniform(0.3, 0.7),
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
        for _ in range(initial_pop):
            lid = self._alloc_lineage_id()
            creature = Creature.spawn(
                self.width, self.height, lineage_id=lid, energy=0.7,
            )
            self.creatures.append(creature)

    def reset(self) -> None:
        """Reset the simulation to initial state."""
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
        self.death_events.clear()
        self.birth_events.clear()
        self.cosmic_ray_events.clear()
        self.active_attacks.clear()
        self.predation_kill_count = 0
        self._recent_kill_frames.clear()
        self._recent_cross_band_miss_frames.clear()
        self._predation_victims_this_frame.clear()
        self._old_age_lifespans.clear()
        self._flock_sizes = {}
        self._flock_count = 0
        self.zone_manager = ZoneManager(
            self.width, self.height,
            self.settings.zone_count,
            self.settings.zone_strength,
        )
        self._spawn_initial_population()

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

        for creature in self.creatures:
            creature.trail = []
            creature.glyph_surface = None
            creature.rotation_angle = 0.0
            creature._glyph_phase = creature.genome.hue * 6.28
            creature.clamp_depth_band()
            if self.settings.sim_mode != "boids":
                creature.flock_id = -1

        if self.settings.sim_mode == "boids":
            creature_bucket = self._build_creature_bucket()
            boid_neighbors = self._build_boid_neighbor_cache(creature_bucket)
            self._update_flock_assignments(boid_neighbors)
        else:
            self._flock_sizes = {}
            self._flock_count = 0

    # ------------------------------------------------------------------
    # Main step dispatcher
    # ------------------------------------------------------------------

    def step(self) -> None:
        """Advance the simulation by one frame, dispatching by mode."""
        if self.paused:
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

            energy_cost = creature.get_movement_cost()
            energy_cost *= 1.0 + overcrowding_penalty
            energy_cost += aggression * 0.0012
            energy_cost += creature.genome.longevity * 0.0004
            energy_cost += self._get_sensing_upkeep_cost(creature)
            zone_mult = self.zone_manager.get_energy_modifier(creature)
            energy_cost *= zone_mult

            creature.energy -= energy_cost
            creature.energy = max(0.0, creature.energy)

            if random.random() < self.settings.cosmic_ray_rate:
                self._apply_cosmic_ray(creature)

            if creature.energy >= self.settings.energy_to_reproduce:
                offspring = self._reproduce(creature)
                if offspring:
                    new_creatures.append(offspring)

            if creature.energy <= 0:
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "energy"
            elif creature.age >= creature.get_max_lifespan():
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "age"

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._process_deaths(dead_creatures, dead_causes)

    # ------------------------------------------------------------------
    # Predator-Prey mode
    # ------------------------------------------------------------------

    def _step_predator_prey(self) -> None:
        """Lotka-Volterra predator/prey ecosystem step."""
        self._frame += 1
        self._spawn_food()
        self.active_attacks.clear()
        self._predation_victims_this_frame.clear()

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

        # If > 60% predators: reduce their reproduction threshold
        pred_repro_penalty = 0.20 if pred_fraction > 0.60 else 0.0
        # If < 15% prey: predators lose energy 2x faster
        prey_scarce = prey_fraction < 0.15 and pred_count > 0

        energy_to_reproduce = self._get_mode_param("energy_to_reproduce")
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate

        for creature in self.creatures:
            if creature.species not in {"predator", "prey"}:
                creature.species = "predator" if creature.genome.aggression >= 0.5 else "prey"
            self._update_predator_prey_depth_band(
                creature,
                creature.get_preferred_depth_band(),
                urgency=0.04,
            )

            if creature.species == "predator":
                self._predator_hunt_prey(creature, creature_bucket)
                creature.update_position(1.0, self.width, self.height)

                # Predators pay 1.4× movement cost; prey scarcity doubles it
                energy_cost = creature.get_movement_cost() * 1.4
                if prey_scarce:
                    energy_cost *= 2.0
                energy_cost += creature.genome.longevity * 0.0004
                energy_cost += self._get_sensing_upkeep_cost(creature)
                energy_cost *= 1.0 + overcrowding_penalty
                energy_cost *= self.zone_manager.get_energy_modifier(creature)
                creature.energy = max(0.0, creature.energy - energy_cost)

                repro_threshold = energy_to_reproduce * (1.0 - pred_repro_penalty)
                if creature.energy >= repro_threshold:
                    offspring = self._reproduce_pp(creature, mutation_rate)
                    if offspring:
                        new_creatures.append(offspring)

            else:  # prey
                fled = self._prey_flee(creature, creature_bucket)
                if not fled:
                    self._creature_seek_food(creature)
                creature.update_position(1.0, self.width, self.height)

                energy_cost = creature.get_movement_cost()
                energy_cost += creature.genome.longevity * 0.0004
                energy_cost += self._get_sensing_upkeep_cost(creature)
                energy_cost *= 1.0 + overcrowding_penalty
                energy_cost *= self.zone_manager.get_energy_modifier(creature)
                creature.energy = max(0.0, creature.energy - energy_cost)

                if creature.energy >= energy_to_reproduce:
                    offspring = self._reproduce_pp(creature, mutation_rate)
                    if offspring:
                        new_creatures.append(offspring)

            if random.random() < cosmic_rate:
                self._apply_cosmic_ray_pp(creature)

            if creature.energy <= 0:
                dead_creatures.append(creature)
                dead_causes[id(creature)] = (
                    "predation"
                    if id(creature) in self._predation_victims_this_frame
                    else "energy"
                )
            elif creature.age >= creature.get_max_lifespan():
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "age"

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._process_deaths(dead_creatures, dead_causes)
        self._check_ecosystem_balance()

    def _predator_hunt_prey(
        self, predator: Creature, bucket: dict
    ) -> None:
        """Predator seeks nearest prey; kills on contact."""
        sense = self._get_effective_sensing_range(predator, multiplier=2.0)
        best_prey: Creature | None = None
        best_dist_sq = sense * sense

        for other in self._nearby_creatures(predator.x, predator.y, sense, bucket):
            if other is predator or other.species != "prey" or other.energy <= 0.0:
                continue
            dist_sq = self._distance_sq(predator.x, predator.y, other.x, other.y)
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_prey = other

        if best_prey is None:
            predator.wander(self.settings.creature_speed_base)
            return

        self._update_predator_prey_depth_band(
            predator,
            best_prey.depth_band,
            urgency=_PREDATOR_DEPTH_TRACK_URGENCY,
        )

        sensed_prey = self._sense_target_position(
            predator,
            best_prey.x,
            best_prey.y,
            sense_multiplier=2.0,
            target_depth_band=best_prey.depth_band,
        )
        if sensed_prey is None:
            predator.wander(self.settings.creature_speed_base)
            return

        predator.steer_toward(
            sensed_prey[0], sensed_prey[1],
            self.settings.creature_speed_base,
            self.width, self.height,
        )

        # Contact kill: distance < sum of radii
        contact_dist = predator.get_radius() + best_prey.get_radius()
        if (
            best_dist_sq < (contact_dist * contact_dist)
            and best_prey.energy > 0.0
            and predator.depth_band == best_prey.depth_band
        ):
            # Transfer from prey to predator; prevents multiple predators
            # farming energy from an already-dead prey in the same frame.
            energy_gain = min(0.5, best_prey.energy)
            predator.energy = min(1.0, predator.energy + energy_gain)
            best_prey.energy = 0.0
            self.predation_kill_count += 1
            self._predation_victims_this_frame.add(id(best_prey))
            self._recent_kill_frames.append(self._frame)
            self.active_attacks.append((
                predator.x, predator.y,
                best_prey.x, best_prey.y,
                predator.genome.hue,
            ))
        elif best_dist_sq < (contact_dist * contact_dist) and best_prey.energy > 0.0:
            self._recent_cross_band_miss_frames.append(self._frame)

    def _prey_flee(self, prey: Creature, bucket: dict) -> bool:
        """Prey flees from nearest predator within sense_radius * 1.2.

        Returns True if actively fleeing.
        """
        flee_sense = self._get_effective_sensing_range(prey, multiplier=1.2)
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
            self._update_predator_prey_depth_band(
                prey,
                self._pick_depth_escape_band(prey, nearest_pred.depth_band),
                urgency=_PREY_DEPTH_ESCAPE_URGENCY,
            )

        sensed_predator = self._sense_target_position(
            prey,
            nearest_pred.x,
            nearest_pred.y,
            sense_multiplier=1.2,
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

        max_speed = prey.genome.speed * self.settings.creature_speed_base * 1.5
        desired_vx = dx * max_speed
        desired_vy = dy * max_speed
        steer = 0.35
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
        """Cosmic ray in predator_prey mode — can flip species on aggression crossing 0.5."""
        new_genome, mutated_trait = creature.genome.mutate_one(std=0.15)

        if self._should_branch_lineage(creature.genome, new_genome, hue_threshold=0.2):
            creature.lineage_id = self._alloc_lineage_id()

        # Species flip if aggression crosses 0.5 boundary
        if mutated_trait == "aggression":
            was_predator = creature.genome.aggression >= 0.5
            is_predator = new_genome.aggression >= 0.5
            if was_predator != is_predator:
                creature.species = "predator" if is_predator else "prey"
                creature.lineage_id = self._alloc_lineage_id()

        creature.genome = new_genome  # type: ignore[misc]
        creature.glyph_surface = None
        creature._glyph_phase = new_genome.hue * 6.28
        self.cosmic_ray_events.append((creature.x, creature.y))

    def _reproduce_pp(self, creature: Creature, mutation_rate: float) -> Creature | None:
        """Reproduce in predator_prey mode — offspring inherits species."""
        max_pop = self._get_mode_param("max_population", self.settings.max_population)
        if len(self.creatures) >= max_pop:
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
            species=creature.species,
            _glyph_phase=offspring_genome.hue * 6.28,
        )

        self.generation += 1
        self.total_births += 1
        return offspring

    def _check_ecosystem_balance(self) -> None:
        """Rescue predators or prey if either goes extinct."""
        if not self.creatures:
            return

        preds = [c for c in self.creatures if c.species == "predator"]
        preys = [c for c in self.creatures if c.species == "prey"]

        # Predators extinct: convert 3 highest-aggression prey
        if len(preds) == 0 and len(preys) > 0:
            candidates = sorted(preys, key=lambda c: c.genome.aggression, reverse=True)
            for c in candidates[:3]:
                c.species = "predator"
                c.lineage_id = self._alloc_lineage_id()

        # Prey extinct: convert 10 lowest-aggression predators
        elif len(preys) == 0 and len(preds) > 0:
            candidates = sorted(preds, key=lambda c: c.genome.aggression)
            for c in candidates[:10]:
                c.species = "prey"
                c.lineage_id = self._alloc_lineage_id()

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
        boid_neighbors = self._build_boid_neighbor_cache(creature_bucket)
        self._update_flock_assignments(boid_neighbors)

        energy_to_reproduce = self._get_mode_param("energy_to_reproduce")
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate
        speed_base = self.settings.creature_speed_base

        for creature in self.creatures:
            sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n_neighbors, alignment_dot = \
                self._compute_boid_forces(
                    creature, boid_neighbors.get(id(creature), [])
                )

            # Apply flocking forces
            creature.vx += sep_fx + align_fx + coh_fx
            creature.vy += sep_fy + align_fy + coh_fy

            # Clamp to max speed
            max_speed = creature.genome.speed * speed_base
            speed = math.sqrt(creature.vx ** 2 + creature.vy ** 2)
            if speed > max_speed and speed > 0:
                creature.vx = creature.vx / speed * max_speed
                creature.vy = creature.vy / speed * max_speed

            if n_neighbors == 0:
                creature.wander(speed_base)

            creature.update_position(1.0, self.width, self.height)

            # Energy model: optimal band = 3–12 neighbours
            if n_neighbors < 3:
                creature.energy = max(0.0, creature.energy - 0.0005)
            elif n_neighbors > 12:
                creature.energy = max(0.0, creature.energy - 0.0003)
            else:
                regen = 0.0012 * max(0.0, alignment_dot)
                creature.energy = min(1.0, creature.energy + regen)

            # Overcrowding penalty
            creature.energy = max(0.0, creature.energy - creature.get_movement_cost() * overcrowding_penalty)

            if random.random() < cosmic_rate:
                self._apply_cosmic_ray(creature)

            if creature.energy >= energy_to_reproduce:
                offspring = self._reproduce_boids(creature, mutation_rate)
                if offspring:
                    new_creatures.append(offspring)

            if creature.energy <= 0:
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "energy"
            elif creature.age >= creature.get_max_lifespan():
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "age"

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._process_deaths(dead_creatures, dead_causes)

        # Phase-sync glyph pulses within flocks
        self._update_boids_glyph_phases()

    def _build_boid_neighbor_cache(
        self, bucket: dict[tuple[int, int], list[Creature]]
    ) -> dict[int, list[tuple[Creature, float, float, float]]]:
        """
        Build directed neighbor lists for boids.

        Returns mapping:
        creature_id -> list[(other_creature, dx, dy, dist_sq)]
        where (dx, dy) is shortest toroidal vector from creature to neighbor.
        """
        neighbor_cache: dict[int, list[tuple[Creature, float, float, float]]] = {}
        for creature in self.creatures:
            sense = creature.get_effective_sense_radius() * 1.5
            sense_sq = sense * sense
            neighbors: list[tuple[Creature, float, float, float]] = []
            for other in self._nearby_creatures(creature.x, creature.y, sense, bucket):
                if other is creature:
                    continue
                dx, dy = self._wrapped_delta(creature.x, creature.y, other.x, other.y)
                dist_sq = dx * dx + dy * dy
                if dist_sq < sense_sq:
                    neighbors.append((other, dx, dy, dist_sq))
            neighbor_cache[id(creature)] = neighbors
        return neighbor_cache

    def _compute_boid_forces(
        self, creature: Creature, neighbors: list[tuple[Creature, float, float, float]]
    ) -> tuple[float, float, float, float, float, float, int, float]:
        """
        Compute separation, alignment, and cohesion forces for a boid.

        Strengths: separation=aggression, alignment=conformity, cohesion=efficiency.

        Returns:
            (sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n_neighbors, alignment_dot)
        """
        if not neighbors:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0

        n = len(neighbors)
        sep_threshold = creature.get_radius() * 3.0
        sep_threshold_sq = sep_threshold * sep_threshold

        sep_x = sep_y = 0.0
        sum_vx = sum_vy = 0.0
        sum_dx = sum_dy = 0.0

        for other, dx, dy, dist_sq in neighbors:
            sum_vx += other.vx
            sum_vy += other.vy
            sum_dx += dx
            sum_dy += dy

            if dist_sq < sep_threshold_sq and dist_sq > 1e-6:
                dist = math.sqrt(dist_sq)
                weight = (sep_threshold - dist) / sep_threshold
                inv_dist = 1.0 / dist
                sep_x += (-dx * inv_dist) * weight
                sep_y += (-dy * inv_dist) * weight

        sep_strength = creature.genome.aggression * 0.25
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

        align_strength = creature.genome.conformity * 0.12
        align_fx = (avg_vx - creature.vx) * align_strength
        align_fy = (avg_vy - creature.vy) * align_strength

        avg_dx = sum_dx / n
        avg_dy = sum_dy / n
        dist_to_centroid_sq = avg_dx * avg_dx + avg_dy * avg_dy
        if dist_to_centroid_sq > 1e-6:
            inv_dist = 1.0 / math.sqrt(dist_to_centroid_sq)
            coh_strength = creature.genome.efficiency * 0.04
            coh_fx = avg_dx * inv_dist * coh_strength
            coh_fy = avg_dy * inv_dist * coh_strength
        else:
            coh_fx = coh_fy = 0.0

        return sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n, alignment_dot

    def _update_flock_assignments(
        self, neighbor_cache: dict[int, list[tuple[Creature, float, float, float]]]
    ) -> None:
        """
        BFS connected-components flock detection.

        Connectivity is undirected: two creatures are connected if either one
        can sense the other this frame.
        """
        creature_by_id = {id(c): c for c in self.creatures}
        adjacency: dict[int, set[int]] = {cid: set() for cid in creature_by_id}
        for cid, neighbors in neighbor_cache.items():
            for other, _dx, _dy, _dist_sq in neighbors:
                oid = id(other)
                if oid not in adjacency:
                    continue
                adjacency[cid].add(oid)
                adjacency[oid].add(cid)

        assignment: dict[int, int] = {}
        next_flock = 0
        for cid in adjacency:
            if cid in assignment:
                continue
            queue = [cid]
            assignment[cid] = next_flock
            head = 0
            while head < len(queue):
                current = queue[head]
                head += 1
                for neighbor_id in adjacency[current]:
                    if neighbor_id not in assignment:
                        assignment[neighbor_id] = next_flock
                        queue.append(neighbor_id)
            next_flock += 1

        flock_sizes: dict[int, int] = {}
        for fid in assignment.values():
            flock_sizes[fid] = flock_sizes.get(fid, 0) + 1

        for cid, creature in creature_by_id.items():
            fid = assignment.get(cid, -1)
            creature.flock_id = fid if flock_sizes.get(fid, 0) > 1 else -1

        self._flock_sizes = {k: v for k, v in flock_sizes.items() if v > 1}
        self._flock_count = len(self._flock_sizes)

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

    def _reproduce_boids(self, creature: Creature, mutation_rate: float) -> Creature | None:
        """Reproduce in boids mode."""
        max_pop = self._get_mode_param("max_population", self.settings.max_population)
        if len(self.creatures) >= max_pop:
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
        energy_to_reproduce = self._get_mode_param("energy_to_reproduce")
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)

        for creature in self.creatures:
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

            if creature.energy >= energy_to_reproduce:
                offspring = self._reproduce_drift(creature, mutation_rate)
                if offspring:
                    new_creatures.append(offspring)

            # Drift: die only of old age
            if creature.age >= creature.get_max_lifespan():
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "age"

        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        self._process_deaths(dead_creatures, dead_causes)

    def _drift_wander(self, creature: Creature) -> None:
        """Meditative glide — slow, smoothly curving paths."""
        speed_base = self.settings.creature_speed_base * 0.25
        current_speed = math.sqrt(creature.vx ** 2 + creature.vy ** 2)

        if current_speed < 0.01:
            angle = random.uniform(0, 2 * math.pi)
            target_speed = creature.genome.speed * speed_base * 0.3
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

        max_speed = creature.genome.speed * speed_base
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

    def _reproduce_drift(self, creature: Creature, mutation_rate: float) -> Creature | None:
        """Reproduce in drift mode — offspring appears at same position."""
        max_pop = self._get_mode_param("max_population", self.settings.max_population)
        if len(self.creatures) >= max_pop:
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
        base_rate = self.settings.food_spawn_rate
        # Corrective compatibility path: existing configs often persisted the old
        # energy default of 0.6, which now collapses too easily in interactive runs.
        if self.settings.sim_mode == "energy" and math.isclose(base_rate, 0.6, abs_tol=1e-9):
            base_rate = 0.8
        if not self.settings.food_cycle_enabled:
            return base_rate
        period = max(1, self.settings.food_cycle_period)
        t = self._frame / period
        return max(0.0, base_rate * (0.5 + 0.5 * math.sin(2 * math.pi * t)))

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
                creature.wander(self.settings.creature_speed_base)
                return

            creature.steer_toward(
                sensed_food[0], sensed_food[1],
                self.settings.creature_speed_base,
                self.width, self.height,
            )

            eat_distance = creature.get_radius() + 3
            dist = creature.distance_to(nearest_food.x, nearest_food.y, self.width, self.height)

            if dist < eat_distance:
                eff_bonus = 1.20 if creature.genome.aggression < 0.4 else 1.0
                energy_gain = nearest_food.energy * (0.5 + creature.genome.efficiency * 0.5) * eff_bonus
                creature.energy = min(1.0, creature.energy + energy_gain)
                self.food_manager.remove(nearest_food)
        else:
            creature.wander(self.settings.creature_speed_base)

    def _find_nearest_food_for_creature(
        self,
        creature: Creature,
        sense_radius: float,
    ):
        """Find food, keeping predator-prey access bounded by the creature's band."""
        if not (
            self.settings.sim_mode == "predator_prey"
            and creature.species == "prey"
        ):
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
    ) -> None:
        """Move a predator-prey creature by at most one bounded band."""
        if self.settings.sim_mode != "predator_prey":
            return
        target = clamp_depth_band(target_band)
        creature.clamp_depth_band()
        if creature.depth_band == target:
            return
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
        )

        attack_range = my_radius * 4
        if best_dist_sq < (attack_range * attack_range):
            size_ratio = min(2.0, max(0.5, my_radius / max(1.0, best_prey.get_radius())))
            drain = creature.genome.aggression * 0.008 * size_ratio
            transfer = min(drain, best_prey.energy)
            if transfer > 0:
                best_prey.energy = max(0.0, best_prey.energy - transfer)
                creature.energy = min(1.0, creature.energy + transfer)
                self.active_attacks.append((
                    creature.x, creature.y,
                    best_prey.x, best_prey.y,
                    creature.genome.hue,
                ))

        return True

    def _creature_opportunist_attack(
        self, creature: Creature, bucket: dict[tuple[int, int], list[Creature]]
    ) -> None:
        """Opportunist behaviour for energy mode."""
        my_radius = creature.get_radius()
        attack_range = my_radius * 2.5
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
                drain = creature.genome.aggression * 0.008
                transfer = min(drain, other.energy)
                if transfer > 0:
                    other.energy = max(0.0, other.energy - transfer)
                    creature.energy = min(1.0, creature.energy + transfer)
                    self.active_attacks.append((
                        creature.x, creature.y,
                        other.x, other.y,
                        creature.genome.hue,
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
        creature._glyph_phase = new_genome.hue * 6.28
        self.cosmic_ray_events.append((creature.x, creature.y))

    # ------------------------------------------------------------------
    # Reproduction (energy / general)
    # ------------------------------------------------------------------

    def _reproduce(self, creature: Creature) -> Creature | None:
        """Handle creature reproduction with lineage tracking (energy mode)."""
        if len(self.creatures) >= self.settings.max_population:
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
        max_pop = self._get_mode_param("max_population", self.settings.max_population)
        population_ratio = len(self.creatures) / max(1, max_pop)
        if population_ratio < 0.5:
            return 0.0
        excess = (population_ratio - 0.5) * 2
        return excess * excess

    def _get_sensing_upkeep_cost(self, creature: Creature) -> float:
        """M3 corrective pass: keep sensing range-limited and noisy, but not taxing."""
        return 0.0

    def _get_effective_sensing_range(
        self,
        creature: Creature,
        *,
        multiplier: float = 1.0,
        absolute_radius: float | None = None,
        target_depth_band: int | None = None,
    ) -> float:
        """Return the zone-adjusted sensing range for a creature."""
        base_radius = (
            absolute_radius
            if absolute_radius is not None
            else creature.get_effective_sense_radius() * multiplier
        )
        zone_modifier = self.zone_manager.get_sensing_modifier_at(creature.x, creature.y)
        depth_modifier = 1.0
        if (
            self.settings.sim_mode == "predator_prey"
            and target_depth_band is not None
        ):
            separation = depth_band_separation(creature.depth_band, target_depth_band)
            depth_modifier = _DEPTH_SENSING_FACTORS[separation]
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
            if cause == "age":
                self._old_age_lifespans.append(creature.age)
            self.death_events.append({
                "x": creature.x,
                "y": creature.y,
                "genome": creature.genome,
                "glyph_surface": creature.glyph_surface,
                "lineage_id": creature.lineage_id,
                "cause": cause,
            })
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
        window_frames = max(30, int(self.settings.target_fps * _PREDATION_RECENT_WINDOW_SECONDS))
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

    def get_avg_conformity(self) -> float:
        """Return average conformity trait across population."""
        if not self.creatures:
            return 0.0
        return sum(c.genome.conformity for c in self.creatures) / len(self.creatures)

    def get_lineage_count(self) -> int:
        """Return number of distinct lineages currently alive."""
        return len(set(c.lineage_id for c in self.creatures))

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
        return 0.5 + 0.5 * math.sin(2 * math.pi * t)

    @property
    def avg_old_age_lifespan_seconds(self) -> float:
        """Rolling average lifespan (seconds) for last 20 natural deaths."""
        if not self._old_age_lifespans:
            return 0.0
        return (sum(self._old_age_lifespans) / len(self._old_age_lifespans)) / 60.0

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
            "zone_occupancy": self.get_zone_occupancy_counts(),
        }

        if self.settings.sim_mode == "predator_prey":
            predator_count, prey_count = self.get_species_counts()
            depth_counts = self.get_depth_band_counts()
            pred_actual_speed, prey_actual_speed = self.get_species_avg_actual_speeds()
            predation_stats = self.get_recent_predation_stats()
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
        elif self.settings.sim_mode == "boids":
            flock_count, avg_flock_size, largest_flock = self.get_flock_stats()
            snapshot["flocks"] = {
                "count": flock_count,
                "average_size": avg_flock_size,
                "largest": largest_flock,
                "loners": sum(1 for creature in self.creatures if creature.flock_id == -1),
            }

        return snapshot
