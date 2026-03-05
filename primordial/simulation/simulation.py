"""Simulation module - main simulation controller."""

from __future__ import annotations

import math
import random
from collections import deque
from typing import TYPE_CHECKING

from .creature import Creature
from .food import FoodManager
from .genome import Genome
from .zones import ZoneManager

if TYPE_CHECKING:
    from ..settings import Settings


# ---------------------------------------------------------------------------
# Per-mode default parameter overrides
# ---------------------------------------------------------------------------

_MODE_DEFAULTS: dict[str, dict] = {
    "predator_prey": {
        "initial_population": 120,
        "predator_fraction": 0.30,
        "food_spawn_rate": 0.5,
        "mutation_rate": 0.08,
        "energy_to_reproduce": 0.70,
    },
    "boids": {
        "initial_population": 150,
        "max_population": 300,
        "mutation_rate": 0.07,
        "energy_to_reproduce": 0.72,
        "food_cycle_enabled": False,
        "zone_strength": 0.5,
    },
    "drift": {
        "initial_population": 60,
        "max_population": 200,
        "mutation_rate": 0.04,
        "cosmic_ray_rate": 0.0006,
        "energy_to_reproduce": 0.95,
        "food_cycle_enabled": False,
        "zone_strength": 0.6,
        "target_fps": 60,
    },
}


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
        self, width: int, height: int, settings: "Settings"
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
        self.active_attacks: list[tuple[float, float, float, float, float]] = []

        # Rolling average lifespan for old-age deaths (last 20)
        self._old_age_lifespans: deque[float] = deque(maxlen=20)

        # Zone manager
        self.zone_manager = ZoneManager(
            width, height,
            settings.zone_count,
            settings.zone_strength,
        )

        # Boids mode state
        self._flock_sizes: dict[int, int] = {}
        self._flock_count: int = 0

        # Initialize population
        self._spawn_initial_population()

    # ------------------------------------------------------------------
    # Mode parameter helpers
    # ------------------------------------------------------------------

    def _get_mode_param(self, key: str, fallback=None):
        """Return mode-specific param, checking user config overrides first."""
        mode = self.settings.sim_mode
        # Check user config overrides (loaded from [modes.*] TOML sections)
        mode_params = getattr(self.settings, "mode_params", {})
        if mode in mode_params and key in mode_params[mode]:
            return type(fallback)(mode_params[mode][key]) if fallback is not None else mode_params[mode][key]
        # Built-in mode defaults
        if mode in _MODE_DEFAULTS and key in _MODE_DEFAULTS[mode]:
            val = _MODE_DEFAULTS[mode][key]
            return type(fallback)(val) if fallback is not None else val
        # Fall back to settings attribute or provided fallback
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
        predator_fraction = self._get_mode_param("predator_fraction", 0.30)
        initial_pop = self._get_mode_param("initial_population", self.settings.initial_population)
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
                )
                creature = Creature.spawn(
                    self.width, self.height, genome=genome,
                    lineage_id=lid, energy=0.7, species="prey",
                )

            self.creatures.append(creature)

        # Seed food for prey
        self.food_manager.spawn_batch(200)

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
        self._old_age_lifespans.clear()
        self._flock_sizes = {}
        self._flock_count = 0
        self.zone_manager = ZoneManager(
            self.width, self.height,
            self.settings.zone_count,
            self.settings.zone_strength,
        )
        self._spawn_initial_population()

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

        energy_to_reproduce = self._get_mode_param("energy_to_reproduce", 0.70)
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate

        for creature in self.creatures:
            if creature.species == "predator":
                self._predator_hunt_prey(creature, creature_bucket)
                creature.update_position(1.0, self.width, self.height)

                # Predators pay 1.4× movement cost; prey scarcity doubles it
                energy_cost = creature.get_movement_cost() * 1.4
                if prey_scarce:
                    energy_cost *= 2.0
                energy_cost += creature.genome.longevity * 0.0004
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
                dead_causes[id(creature)] = "energy"
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
        sense = predator.get_effective_sense_radius() * 2.0
        best_prey: Creature | None = None
        best_dist = sense

        for other in self._nearby_creatures(predator.x, predator.y, sense, bucket):
            if other is predator or other.species != "prey":
                continue
            dist = predator.distance_to(other.x, other.y, self.width, self.height)
            if dist < best_dist:
                best_dist = dist
                best_prey = other

        if best_prey is None:
            predator.wander(self.settings.creature_speed_base)
            return

        predator.steer_toward(
            best_prey.x, best_prey.y,
            self.settings.creature_speed_base,
            self.width, self.height,
        )

        # Contact kill: distance < sum of radii
        contact_dist = predator.get_radius() + best_prey.get_radius()
        if best_dist < contact_dist:
            energy_gain = min(0.5, best_prey.genome.size * 3 * 0.1)
            predator.energy = min(1.0, predator.energy + energy_gain)
            best_prey.energy = 0.0
            self.active_attacks.append((
                predator.x, predator.y,
                best_prey.x, best_prey.y,
                predator.genome.hue,
            ))

    def _prey_flee(self, prey: Creature, bucket: dict) -> bool:
        """Prey flees from nearest predator within sense_radius * 1.2.

        Returns True if actively fleeing.
        """
        flee_sense = prey.get_effective_sense_radius() * 1.2
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

        # Steer away from predator
        dx = prey.x - nearest_pred.x
        dy = prey.y - nearest_pred.y
        if abs(dx) > self.width / 2:
            dx -= math.copysign(self.width, dx)
        if abs(dy) > self.height / 2:
            dy -= math.copysign(self.height, dy)
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dx /= dist
            dy /= dist

        max_speed = prey.genome.speed * self.settings.creature_speed_base * 1.5
        prey.vx += dx * max_speed * 0.3
        prey.vy += dy * max_speed * 0.3
        return True

    def _apply_cosmic_ray_pp(self, creature: Creature) -> None:
        """Cosmic ray in predator_prey mode — can flip species on aggression crossing 0.5."""
        new_genome, mutated_trait = creature.genome.mutate_one(std=0.15)

        if mutated_trait == "hue":
            hue_diff = abs(new_genome.hue - creature.genome.hue)
            if hue_diff > 0.5:
                hue_diff = 1.0 - hue_diff
            if hue_diff > 0.2:
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

        hue_diff = abs(offspring_genome.hue - creature.genome.hue)
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff

        offspring_lineage = (
            self._alloc_lineage_id() if hue_diff > 0.15 else creature.lineage_id
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

        # Flock detection (BFS connected components)
        self._update_flock_assignments(creature_bucket)

        energy_to_reproduce = self._get_mode_param("energy_to_reproduce", 0.72)
        mutation_rate = self._get_mode_param("mutation_rate", self.settings.mutation_rate)
        cosmic_rate = self.settings.cosmic_ray_rate
        speed_base = self.settings.creature_speed_base

        for creature in self.creatures:
            sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n_neighbors, alignment_dot = \
                self._compute_boid_forces(creature, creature_bucket)

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

    def _compute_boid_forces(
        self, creature: Creature, bucket: dict
    ) -> tuple[float, float, float, float, float, float, int, float]:
        """
        Compute separation, alignment, and cohesion forces for a boid.

        Strengths: separation=aggression, alignment=conformity, cohesion=efficiency.

        Returns:
            (sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n_neighbors, alignment_dot)
        """
        sense = creature.get_effective_sense_radius() * 1.5
        sep_threshold = creature.get_radius() * 3.0

        # Gather actual neighbors with distances
        actual_neighbors: list[tuple[Creature, float]] = []
        for other in self._nearby_creatures(creature.x, creature.y, sense, bucket):
            if other is creature:
                continue
            dist = creature.distance_to(other.x, other.y, self.width, self.height)
            if dist < sense:
                actual_neighbors.append((other, dist))

        if not actual_neighbors:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0.0

        n = len(actual_neighbors)

        # --- Separation ---
        sep_x = sep_y = 0.0
        for other, dist in actual_neighbors:
            if dist < sep_threshold and dist > 0.01:
                dx = creature.x - other.x
                dy = creature.y - other.y
                if abs(dx) > self.width / 2:
                    dx -= math.copysign(self.width, dx)
                if abs(dy) > self.height / 2:
                    dy -= math.copysign(self.height, dy)
                weight = (sep_threshold - dist) / sep_threshold
                sep_x += (dx / dist) * weight
                sep_y += (dy / dist) * weight
        sep_strength = creature.genome.aggression * 0.25
        sep_fx = sep_x * sep_strength
        sep_fy = sep_y * sep_strength

        # --- Alignment ---
        avg_vx = sum(o.vx for o, _ in actual_neighbors) / n
        avg_vy = sum(o.vy for o, _ in actual_neighbors) / n

        my_speed = math.sqrt(creature.vx ** 2 + creature.vy ** 2)
        avg_speed = math.sqrt(avg_vx ** 2 + avg_vy ** 2)
        alignment_dot = 0.0
        if my_speed > 0.01 and avg_speed > 0.01:
            alignment_dot = (creature.vx * avg_vx + creature.vy * avg_vy) / (my_speed * avg_speed)

        align_strength = creature.genome.conformity * 0.12
        align_fx = (avg_vx - creature.vx) * align_strength
        align_fy = (avg_vy - creature.vy) * align_strength

        # --- Cohesion ---
        avg_x = sum(o.x for o, _ in actual_neighbors) / n
        avg_y = sum(o.y for o, _ in actual_neighbors) / n
        dx = avg_x - creature.x
        dy = avg_y - creature.y
        if abs(dx) > self.width / 2:
            dx -= math.copysign(self.width, dx)
        if abs(dy) > self.height / 2:
            dy -= math.copysign(self.height, dy)
        dist_to_centroid = math.sqrt(dx ** 2 + dy ** 2)
        if dist_to_centroid > 0.01:
            coh_strength = creature.genome.efficiency * 0.04
            coh_fx = (dx / dist_to_centroid) * coh_strength
            coh_fy = (dy / dist_to_centroid) * coh_strength
        else:
            coh_fx = coh_fy = 0.0

        return sep_fx, sep_fy, align_fx, align_fy, coh_fx, coh_fy, n, alignment_dot

    def _update_flock_assignments(self, bucket: dict) -> None:
        """
        BFS connected-components flock detection.

        Two creatures are connected if either's sense_radius * 1.5 covers the other.
        Loners (flock size = 1) get flock_id = -1.
        """
        # Pre-compute neighbor lists for all creatures (avoids repeated bucket lookups)
        neighbor_map: dict[int, list[Creature]] = {}
        for c in self.creatures:
            sense = c.get_effective_sense_radius() * 1.5
            candidates = self._nearby_creatures(c.x, c.y, sense, bucket)
            neighbor_map[id(c)] = [
                other for other in candidates
                if other is not c and
                c.distance_to(other.x, other.y, self.width, self.height) < sense
            ]

        # BFS connected components
        assignment: dict[int, int] = {}
        next_flock = 0

        for start in self.creatures:
            if id(start) in assignment:
                continue
            queue = [start]
            assignment[id(start)] = next_flock
            head = 0
            while head < len(queue):
                current = queue[head]
                head += 1
                for neighbor in neighbor_map.get(id(current), []):
                    if id(neighbor) not in assignment:
                        assignment[id(neighbor)] = next_flock
                        queue.append(neighbor)
            next_flock += 1

        # Count flock sizes
        flock_sizes: dict[int, int] = {}
        for fid in assignment.values():
            flock_sizes[fid] = flock_sizes.get(fid, 0) + 1

        # Assign flock_id; singletons get -1
        for c in self.creatures:
            fid = assignment.get(id(c), -1)
            c.flock_id = fid if flock_sizes.get(fid, 0) > 1 else -1

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

        hue_diff = abs(offspring_genome.hue - creature.genome.hue)
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff

        offspring_lineage = (
            self._alloc_lineage_id() if hue_diff > 0.15 else creature.lineage_id
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
        energy_to_reproduce = self._get_mode_param("energy_to_reproduce", 0.95)
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

        hue_diff = abs(offspring_genome.hue - creature.genome.hue)
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff

        offspring_lineage = (
            self._alloc_lineage_id() if hue_diff > 0.15 else creature.lineage_id
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
        self.food_manager.spawn_batch(spawn_count)

    def _get_food_rate(self) -> float:
        """Current food spawn rate accounting for the boom/bust cycle."""
        if not self.settings.food_cycle_enabled:
            return self.settings.food_spawn_rate
        period = max(1, self.settings.food_cycle_period)
        t = self._frame / period
        return max(0.0, self.settings.food_spawn_rate * (0.5 + 0.5 * math.sin(2 * math.pi * t)))

    # ------------------------------------------------------------------
    # Food seeking
    # ------------------------------------------------------------------

    def _creature_seek_food(
        self, creature: Creature, sense_override: float | None = None
    ) -> None:
        """Handle creature food-seeking behaviour."""
        sense_radius = sense_override if sense_override is not None else creature.get_effective_sense_radius()
        nearest_food = self.food_manager.find_nearest(creature.x, creature.y, sense_radius)

        if nearest_food:
            creature.steer_toward(
                nearest_food.x, nearest_food.y,
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
        for dx in range(-cells, cells + 1):
            for dy in range(-cells, cells + 1):
                key = ((cx + dx) % gw, (cy + dy) % gh)
                result.extend(bucket.get(key, []))
        return result

    # ------------------------------------------------------------------
    # Hunting / predation (energy mode)
    # ------------------------------------------------------------------

    def _creature_hunt(
        self, creature: Creature, bucket: dict[tuple[int, int], list[Creature]]
    ) -> bool:
        """Hunter behaviour for energy mode."""
        sense = creature.get_effective_sense_radius() * 1.5
        my_radius = creature.get_radius()
        max_prey_radius = my_radius * 1.3

        best_prey: Creature | None = None
        best_dist = sense

        for other in self._nearby_creatures(creature.x, creature.y, sense, bucket):
            if other is creature:
                continue
            if other.get_radius() > max_prey_radius:
                continue
            dist = creature.distance_to(other.x, other.y, self.width, self.height)
            if dist < best_dist:
                best_dist = dist
                best_prey = other

        if best_prey is None:
            return False

        creature.steer_toward(
            best_prey.x, best_prey.y,
            self.settings.creature_speed_base,
            self.width, self.height,
        )

        attack_range = my_radius * 4
        if best_dist < attack_range:
            size_ratio = min(2.0, max(0.5, my_radius / max(1.0, best_prey.get_radius())))
            drain = creature.genome.aggression * 0.008 * size_ratio
            best_prey.energy = max(0.0, best_prey.energy - drain)
            creature.energy = min(1.0, creature.energy + drain)
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
            if other.get_radius() >= prey_size_limit:
                continue
            dist = creature.distance_to(other.x, other.y, self.width, self.height)
            if dist < attack_range:
                drain = creature.genome.aggression * 0.008
                other.energy = max(0.0, other.energy - drain)
                creature.energy = min(1.0, creature.energy + drain)
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
        new_genome, mutated_trait = creature.genome.mutate_one(std=0.15)

        if mutated_trait == "hue":
            hue_diff = abs(new_genome.hue - creature.genome.hue)
            if hue_diff > 0.5:
                hue_diff = 1.0 - hue_diff
            if hue_diff > 0.2:
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

        hue_diff = abs(offspring_genome.hue - creature.genome.hue)
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff

        offspring_lineage = (
            self._alloc_lineage_id() if hue_diff > 0.15 else creature.lineage_id
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
            "conformity",
        ]
        totals = {t: 0.0 for t in trait_names}

        for creature in self.creatures:
            for t in trait_names:
                totals[t] += getattr(creature.genome, t)

        return {k: v / n for k, v in totals.items()}
