"""Simulation module - main simulation controller."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .creature import Creature
from .food import FoodManager
from .genome import Genome

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
    """

    def __init__(
        self, width: int, height: int, settings: Settings
    ) -> None:
        """
        Initialize the simulation.

        Args:
            width: World width in pixels.
            height: World height in pixels.
            settings: Application settings.
        """
        self.width = width
        self.height = height
        self.settings = settings

        # Simulation state
        self.creatures: list[Creature] = []
        self.food_manager = FoodManager(width, height)
        self.generation = 0
        self.paused = False

        # Statistics
        self.total_births = 0
        self.total_deaths = 0

        # Lineage counter — each new lineage gets a unique integer ID
        self._next_lineage_id: int = 1

        # Event queues read by renderer each frame (renderer clears them)
        self.death_events: list[dict] = []
        self.birth_events: list[Creature] = []

        # Initialize population
        self._spawn_initial_population()

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
        self._next_lineage_id = 1
        self.death_events.clear()
        self.birth_events.clear()
        self._spawn_initial_population()

    def step(self) -> None:
        """
        Advance the simulation by one frame.

        This is the main simulation loop. Order of operations:
        1. Spawn food
        2. For each creature: move, seek food, eat, lose energy
        3. Handle reproduction
        4. Remove dead creatures (emit death_events)
        """
        if self.paused:
            return

        # Spawn food
        self._spawn_food()

        # Process creatures
        new_creatures: list[Creature] = []
        dead_creatures: list[Creature] = []

        # Calculate overcrowding penalty
        overcrowding_penalty = self._get_overcrowding_penalty()

        for creature in self.creatures:
            # Seek and eat food
            self._creature_seek_food(creature)

            # Update position
            creature.update_position(1.0, self.width, self.height)

            # Energy cost of movement
            energy_cost = creature.get_movement_cost()
            energy_cost *= 1.0 + overcrowding_penalty
            creature.energy -= energy_cost

            # Check for reproduction
            if creature.energy >= self.settings.energy_to_reproduce:
                offspring = self._reproduce(creature)
                if offspring:
                    new_creatures.append(offspring)

            # Check for death
            if creature.energy <= 0:
                dead_creatures.append(creature)

        # Add new creatures and emit birth events
        for creature in new_creatures:
            self.creatures.append(creature)
            self.birth_events.append(creature)

        # Remove dead creatures and emit death events
        for creature in dead_creatures:
            self.death_events.append({
                "x": creature.x,
                "y": creature.y,
                "genome": creature.genome,
                "glyph_surface": creature.glyph_surface,
                "lineage_id": creature.lineage_id,
            })
            self.creatures.remove(creature)
            self.total_deaths += 1

    def _spawn_food(self) -> None:
        """Spawn food particles based on spawn rate."""
        spawn_count = int(self.settings.food_spawn_rate)
        fractional = self.settings.food_spawn_rate - spawn_count

        if random.random() < fractional:
            spawn_count += 1

        self.food_manager.spawn_batch(spawn_count)

    def _creature_seek_food(self, creature: Creature) -> None:
        """
        Handle creature food-seeking behavior.

        Args:
            creature: The creature to process.
        """
        sense_radius = creature.get_sense_radius()
        nearest_food = self.food_manager.find_nearest(
            creature.x, creature.y, sense_radius
        )

        if nearest_food:
            creature.steer_toward(
                nearest_food.x,
                nearest_food.y,
                self.settings.creature_speed_base,
                self.width,
                self.height,
            )

            eat_distance = creature.get_radius() + 3
            dist = creature.distance_to(
                nearest_food.x, nearest_food.y, self.width, self.height
            )

            if dist < eat_distance:
                energy_gain = nearest_food.energy * (0.5 + creature.genome.efficiency * 0.5)
                creature.energy += energy_gain
                creature.energy = min(creature.energy, 1.0)
                self.food_manager.remove(nearest_food)
        else:
            creature.wander(self.settings.creature_speed_base)

    def _reproduce(self, creature: Creature) -> Creature | None:
        """
        Handle creature reproduction.

        The offspring inherits the parent's lineage_id unless the hue
        mutates by more than 0.15 (speciation event → new lineage_id).

        Args:
            creature: The parent creature.

        Returns:
            The offspring creature, or None if reproduction failed.
        """
        if len(self.creatures) >= self.settings.max_population:
            return None

        # Split energy
        creature.energy /= 2

        # Create offspring with mutated genome
        offspring_genome = creature.genome.mutate(self.settings.mutation_rate)

        # Determine lineage: new lineage if hue drifted far enough (speciation)
        hue_diff = abs(offspring_genome.hue - creature.genome.hue)
        # Handle circular hue distance
        if hue_diff > 0.5:
            hue_diff = 1.0 - hue_diff

        if hue_diff > 0.15:
            offspring_lineage = self._alloc_lineage_id()
        else:
            offspring_lineage = creature.lineage_id

        offspring = Creature(
            x=creature.x + random.uniform(-10, 10),
            y=creature.y + random.uniform(-10, 10),
            genome=offspring_genome,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=creature.energy,
            lineage_id=offspring_lineage,
        )

        # Wrap position
        offspring.x = offspring.x % self.width
        offspring.y = offspring.y % self.height

        # Update statistics
        self.generation += 1
        self.total_births += 1

        return offspring

    def _get_overcrowding_penalty(self) -> float:
        """
        Calculate energy cost penalty for overcrowding.

        Returns:
            Penalty multiplier (0.0 = no penalty, higher = more costly).
        """
        population_ratio = len(self.creatures) / self.settings.max_population
        if population_ratio < 0.5:
            return 0.0
        excess = (population_ratio - 0.5) * 2
        return excess * excess

    def get_lineage_counts(self) -> dict[int, int]:
        """
        Count creatures per lineage_id.

        Returns:
            Dict mapping lineage_id → creature count.
        """
        counts: dict[int, int] = {}
        for c in self.creatures:
            counts[c.lineage_id] = counts.get(c.lineage_id, 0) + 1
        return counts

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
        """
        Get the average genome traits of the population.

        Returns:
            Dictionary of trait names to average values.
        """
        if not self.creatures:
            return {}

        n = len(self.creatures)
        trait_names = [
            "speed", "size", "sense_radius", "aggression",
            "hue", "saturation", "efficiency",
            "complexity", "symmetry", "stroke_scale",
            "appendages", "rotation_speed", "motion_style",
        ]
        totals = {t: 0.0 for t in trait_names}

        for creature in self.creatures:
            for t in trait_names:
                totals[t] += getattr(creature.genome, t)

        return {k: v / n for k, v in totals.items()}
