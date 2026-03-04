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
        self, width: int, height: int, settings: Settings
    ) -> None:
        self.width = width
        self.height = height
        self.settings = settings

        # Simulation state
        self.creatures: list[Creature] = []
        self.food_manager = FoodManager(width, height)
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

        # Initialize population
        self._spawn_initial_population()

    # ------------------------------------------------------------------
    # Setup helpers
    # ------------------------------------------------------------------

    def _alloc_lineage_id(self) -> int:
        """Allocate and return a new unique lineage ID."""
        lid = self._next_lineage_id
        self._next_lineage_id += 1
        return lid

    def _spawn_initial_population(self) -> None:
        """Spawn the initial population of creatures."""
        for _ in range(self.settings.initial_population):
            lid = self._alloc_lineage_id()
            creature = Creature.spawn(self.width, self.height, lineage_id=lid)
            self.creatures.append(creature)

    def reset(self) -> None:
        """Reset the simulation to initial state."""
        self.creatures.clear()
        self.food_manager.clear()
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
        self.zone_manager = ZoneManager(
            self.width, self.height,
            self.settings.zone_count,
            self.settings.zone_strength,
        )
        self._spawn_initial_population()

    # ------------------------------------------------------------------
    # Main step
    # ------------------------------------------------------------------

    def step(self) -> None:
        """
        Advance the simulation by one frame.

        Order of operations:
        1. Spawn food (sinusoidal cycle rate)
        2. Clear per-frame attack list
        3. For each creature: hunt/seek food, move, age-based costs,
           baseline costs (aggression, longevity), zone modifier
        4. Cosmic ray mutations
        5. Handle reproduction
        6. Remove dead creatures (energy ≤ 0 or exceeded max lifespan)
        """
        if self.paused:
            return

        self._frame += 1

        # Spawn food (sinusoidal boom/bust)
        self._spawn_food()

        # Reset per-frame attack list (renderer cleared it last frame,
        # but we rebuild it here for the current frame)
        self.active_attacks.clear()

        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []
        dead_causes: dict[int, str] = {}  # id(creature) → "energy" | "age"

        overcrowding_penalty = self._get_overcrowding_penalty()

        for creature in self.creatures:
            # --- Hunting / food seeking ---
            aggression = creature.genome.aggression
            if aggression > 0.6:
                # Hunter: seek prey first; reduced food detection range
                hunted = self._creature_hunt(creature)
                if not hunted:
                    # Fall back to food if no prey found
                    food_sense = creature.get_effective_sense_radius() * 0.7
                    self._creature_seek_food(creature, sense_override=food_sense)
            elif aggression < 0.4:
                # Grazer: pure food seeking with 15% efficiency bonus applied at eat time
                self._creature_seek_food(creature)
            else:
                # Opportunist: eat food normally; attack only very small nearby creatures
                self._creature_seek_food(creature)
                self._creature_opportunist_attack(creature)

            # --- Movement ---
            creature.update_position(1.0, self.width, self.height)

            # --- Energy costs ---
            # Movement cost
            energy_cost = creature.get_movement_cost()
            energy_cost *= 1.0 + overcrowding_penalty

            # Aggression baseline drain (hunters must keep killing to stay alive)
            energy_cost += aggression * 0.002

            # Longevity maintenance cost (long-lived creatures burn more just existing)
            energy_cost += creature.genome.longevity * 0.001

            # Zone modifier (soft selection by region)
            zone_mult = self.zone_manager.get_energy_modifier(creature)
            energy_cost *= zone_mult

            creature.energy -= energy_cost
            creature.energy = max(0.0, creature.energy)

            # --- Cosmic ray check ---
            if random.random() < self.settings.cosmic_ray_rate:
                self._apply_cosmic_ray(creature)

            # --- Reproduction check ---
            if creature.energy >= self.settings.energy_to_reproduce:
                offspring = self._reproduce(creature)
                if offspring:
                    new_creatures.append(offspring)

            # --- Death checks ---
            if creature.energy <= 0:
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "energy"
            elif creature.age >= creature.get_max_lifespan():
                dead_creatures.append(creature)
                dead_causes[id(creature)] = "age"

        # Add new creatures
        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        # Remove dead creatures
        dead_set = set(id(c) for c in dead_creatures)
        for creature in dead_creatures:
            cause = dead_causes[id(creature)]
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
        t = self._frame / self.settings.food_cycle_period
        return self.settings.food_spawn_rate * (0.5 + 0.5 * math.sin(2 * math.pi * t))

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
                # Grazer efficiency bonus: aggression < 0.4 → +15%
                eff_bonus = 1.15 if creature.genome.aggression < 0.4 else 1.0
                energy_gain = nearest_food.energy * (0.5 + creature.genome.efficiency * 0.5) * eff_bonus
                creature.energy = min(1.0, creature.energy + energy_gain)
                self.food_manager.remove(nearest_food)
        else:
            creature.wander(self.settings.creature_speed_base)

    # ------------------------------------------------------------------
    # Hunting / predation
    # ------------------------------------------------------------------

    def _creature_hunt(self, creature: Creature) -> bool:
        """
        Hunter behaviour: seek and attack the nearest smaller creature.

        Returns True if actively pursuing or attacking prey.
        """
        sense = creature.get_effective_sense_radius() * 1.5
        my_radius = creature.get_radius()

        best_prey: Creature | None = None
        best_dist = sense

        for other in self.creatures:
            if other is creature:
                continue
            if other.get_radius() >= my_radius:
                continue  # only attack smaller creatures
            dist = creature.distance_to(other.x, other.y, self.width, self.height)
            if dist < best_dist:
                best_dist = dist
                best_prey = other

        if best_prey is None:
            return False

        # Steer toward prey
        creature.steer_toward(
            best_prey.x, best_prey.y,
            self.settings.creature_speed_base,
            self.width, self.height,
        )

        # Deal damage when within attack range
        attack_range = my_radius * 2
        if best_dist < attack_range:
            drain = creature.genome.aggression * 0.015
            best_prey.energy = max(0.0, best_prey.energy - drain)
            creature.energy = min(1.0, creature.energy + drain)
            # Record attack for renderer (attacker pos, target pos, attacker hue)
            self.active_attacks.append((
                creature.x, creature.y,
                best_prey.x, best_prey.y,
                creature.genome.hue,
            ))

        return True

    def _creature_opportunist_attack(self, creature: Creature) -> None:
        """
        Opportunist behaviour: attack only creatures < 60% own size within size*1.2.
        """
        my_radius = creature.get_radius()
        attack_range = my_radius * 1.2
        prey_size_limit = my_radius * 0.6

        for other in self.creatures:
            if other is creature:
                continue
            if other.get_radius() >= prey_size_limit:
                continue
            dist = creature.distance_to(other.x, other.y, self.width, self.height)
            if dist < attack_range:
                drain = creature.genome.aggression * 0.015
                other.energy = max(0.0, other.energy - drain)
                creature.energy = min(1.0, creature.energy + drain)
                self.active_attacks.append((
                    creature.x, creature.y,
                    other.x, other.y,
                    creature.genome.hue,
                ))
                break  # one attack per frame

    # ------------------------------------------------------------------
    # Cosmic ray mutations
    # ------------------------------------------------------------------

    def _apply_cosmic_ray(self, creature: Creature) -> None:
        """Apply a spontaneous single-trait mutation to a living creature."""
        new_genome, mutated_trait = creature.genome.mutate_one(std=0.15)

        # Speciation event if hue shifted dramatically
        if mutated_trait == "hue":
            hue_diff = abs(new_genome.hue - creature.genome.hue)
            if hue_diff > 0.5:
                hue_diff = 1.0 - hue_diff
            if hue_diff > 0.2:
                creature.lineage_id = self._alloc_lineage_id()

        creature.genome = new_genome  # type: ignore[misc]  # Genome is frozen but creature is mutable
        creature.glyph_surface = None  # invalidate glyph cache

        # Emit position for visual effect
        self.cosmic_ray_events.append((creature.x, creature.y))

    # ------------------------------------------------------------------
    # Reproduction
    # ------------------------------------------------------------------

    def _reproduce(self, creature: Creature) -> Creature | None:
        """Handle creature reproduction with lineage tracking."""
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
        )

        self.generation += 1
        self.total_births += 1

        return offspring

    # ------------------------------------------------------------------
    # Overcrowding
    # ------------------------------------------------------------------

    def _get_overcrowding_penalty(self) -> float:
        """Calculate energy cost penalty for overcrowding."""
        population_ratio = len(self.creatures) / self.settings.max_population
        if population_ratio < 0.5:
            return 0.0
        excess = (population_ratio - 0.5) * 2
        return excess * excess

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
        """
        Count hunters (aggression > 0.6), grazers (< 0.4), opportunists.

        Returns:
            Tuple of (hunter_count, grazer_count, opportunist_count).
        """
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

    @property
    def food_cycle_phase(self) -> float:
        """
        Current food cycle phase (0.0=famine, 1.0=feast).

        Returns value in [0, 1] representing position in the boom/bust cycle.
        """
        if not self.settings.food_cycle_enabled:
            return 1.0
        t = self._frame / self.settings.food_cycle_period
        return 0.5 + 0.5 * math.sin(2 * math.pi * t)

    @property
    def avg_old_age_lifespan_seconds(self) -> float:
        """
        Rolling average lifespan (in seconds) for the last 20 natural deaths.

        Returns 0.0 if no old-age deaths have occurred yet.
        """
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
        ]
        totals = {t: 0.0 for t in trait_names}

        for creature in self.creatures:
            for t in trait_names:
                totals[t] += getattr(creature.genome, t)

        return {k: v / n for k, v in totals.items()}
