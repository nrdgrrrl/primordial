"""Genome module - heritable traits for creatures."""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Genome:
    """
    Represents the genetic traits of a creature.

    All traits are floats in the range 0.0 to 1.0.
    Genomes are immutable - mutation creates a new instance.
    """

    speed: float = 0.5  # Max movement speed multiplier
    size: float = 0.5  # Body radius, affects collision and energy cost
    sense_radius: float = 0.5  # How far they detect food
    aggression: float = 0.5  # Tendency to chase creatures vs food
    hue: float = 0.5  # Base color hue (visual, heritable)
    saturation: float = 0.5  # Color saturation
    efficiency: float = 0.5  # Energy extracted per food particle

    @classmethod
    def random(cls) -> "Genome":
        """Create a genome with random trait values between 0.0 and 1.0."""
        return cls(
            speed=random.random(),
            size=random.random(),
            sense_radius=random.random(),
            aggression=random.random(),
            hue=random.random(),
            saturation=random.random(),
            efficiency=random.random(),
        )

    def mutate(self, mutation_rate: float) -> "Genome":
        """
        Create a new genome with traits potentially mutated.

        Each trait has a mutation_rate probability of being shifted
        by a gaussian offset (mean 0, std 0.08), clamped to 0.0-1.0.

        Args:
            mutation_rate: Probability of mutating each trait.

        Returns:
            A new Genome with potentially mutated traits.
        """

        def mutate_trait(value: float) -> float:
            if random.random() < mutation_rate:
                value += random.gauss(0, 0.08)
            return max(0.0, min(1.0, value))

        return Genome(
            speed=mutate_trait(self.speed),
            size=mutate_trait(self.size),
            sense_radius=mutate_trait(self.sense_radius),
            aggression=mutate_trait(self.aggression),
            hue=mutate_trait(self.hue),
            saturation=mutate_trait(self.saturation),
            efficiency=mutate_trait(self.efficiency),
        )

    def copy(self) -> "Genome":
        """Create an exact copy of the genome."""
        return Genome(
            speed=self.speed,
            size=self.size,
            sense_radius=self.sense_radius,
            aggression=self.aggression,
            hue=self.hue,
            saturation=self.saturation,
            efficiency=self.efficiency,
        )
