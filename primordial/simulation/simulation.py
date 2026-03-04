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

        # Initialize population
        self._spawn_initial_population()

    def _spawn_initial_population(self) -> None:
        """Spawn the initial population of creatures."""
        for _ in range(self.settings.initial_population):
            creature = Creature.spawn(self.width, self.height)
            self.creatures.append(creature)

    def reset(self) -> None:
        """Reset the simulation to initial state."""
        self.creatures.clear()
        self.food_manager.clear()
        self.generation = 0
        self.total_births = 0
        self.total_deaths = 0
        self._spawn_initial_population()

    def step(self) -> None:
        """
        Advance the simulation by one frame.

        This is the main simulation loop. Order of operations:
        1. Spawn food
        2. For each creature: move, seek food, eat, lose energy
        3. Handle reproduction
        4. Remove dead creatures
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

        # Add new creatures
        for creature in new_creatures:
            self.creatures.append(creature)

        # Remove dead creatures
        for creature in dead_creatures:
            self.creatures.remove(creature)
            self.total_deaths += 1

    def _spawn_food(self) -> None:
        """Spawn food particles based on spawn rate."""
        # Spawn rate is particles per frame (can be fractional)
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
            # Steer toward food
            creature.steer_toward(
                nearest_food.x,
                nearest_food.y,
                self.settings.creature_speed_base,
                self.width,
                self.height,
            )

            # Check if close enough to eat
            eat_distance = creature.get_radius() + 3
            dist = creature.distance_to(
                nearest_food.x, nearest_food.y, self.width, self.height
            )

            if dist < eat_distance:
                # Eat the food
                energy_gain = nearest_food.energy * (0.5 + creature.genome.efficiency * 0.5)
                creature.energy += energy_gain
                creature.energy = min(creature.energy, 1.0)
                self.food_manager.remove(nearest_food)
        else:
            # Wander when no food nearby
            creature.wander(self.settings.creature_speed_base)

    def _reproduce(self, creature: Creature) -> Creature | None:
        """
        Handle creature reproduction.

        Args:
            creature: The parent creature.

        Returns:
            The offspring creature, or None if reproduction failed.
        """
        # Check population cap
        if len(self.creatures) >= self.settings.max_population:
            return None

        # Split energy
        creature.energy /= 2

        # Create offspring with mutated genome
        offspring_genome = creature.genome.mutate(self.settings.mutation_rate)
        offspring = Creature(
            x=creature.x + random.uniform(-10, 10),
            y=creature.y + random.uniform(-10, 10),
            genome=offspring_genome,
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=creature.energy,
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
        # Quadratic ramp-up from 0 at 50% to 1.0 at 100% capacity
        excess = (population_ratio - 0.5) * 2
        return excess * excess

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

        Useful for LLM narration integration.

        Returns:
            Dictionary of trait names to average values.
        """
        if not self.creatures:
            return {}

        n = len(self.creatures)
        totals = {
            "speed": 0.0,
            "size": 0.0,
            "sense_radius": 0.0,
            "aggression": 0.0,
            "hue": 0.0,
            "saturation": 0.0,
            "efficiency": 0.0,
        }

        for creature in self.creatures:
            totals["speed"] += creature.genome.speed
            totals["size"] += creature.genome.size
            totals["sense_radius"] += creature.genome.sense_radius
            totals["aggression"] += creature.genome.aggression
            totals["hue"] += creature.genome.hue
            totals["saturation"] += creature.genome.saturation
            totals["efficiency"] += creature.genome.efficiency

        return {k: v / n for k, v in totals.items()}
