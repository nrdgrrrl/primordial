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

    # Glyph traits
    complexity: float = 0.5    # 0-1 → 2-7 strokes in the glyph
    symmetry: float = 0.5      # 0=asymmetric, 0.33=bilateral, 0.66=3-fold, 1.0=4-fold radial
    stroke_scale: float = 0.5  # Overall proportion/delicacy of strokes
    appendages: float = 0.3    # 0-1 → 0-4 extra limb strokes attached at perimeter
    rotation_speed: float = 0.3  # Glyph rotation speed (slow drift to steady spin)

    # Motion trait
    motion_style: float = 0.5  # 0-0.33=glide, 0.34-0.66=swim, 0.67-1.0=dart

    # Lifespan trait (added in selection-pressure pass)
    longevity: float = 0.5  # 0=short-lived cheap, 1=long-lived costly

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
            complexity=random.random(),
            symmetry=random.random(),
            stroke_scale=random.random(),
            appendages=random.random(),
            rotation_speed=random.random(),
            motion_style=random.random(),
            longevity=random.random(),
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
            complexity=mutate_trait(self.complexity),
            symmetry=mutate_trait(self.symmetry),
            stroke_scale=mutate_trait(self.stroke_scale),
            appendages=mutate_trait(self.appendages),
            rotation_speed=mutate_trait(self.rotation_speed),
            motion_style=mutate_trait(self.motion_style),
            longevity=mutate_trait(self.longevity),
        )

    def mutate_one(self, std: float = 0.15) -> tuple["Genome", str]:
        """
        Apply a cosmic-ray mutation: randomly pick one trait and shift it.

        Args:
            std: Gaussian standard deviation for the shift (larger than normal).

        Returns:
            Tuple of (new_genome, trait_name_mutated).
        """
        trait_names = [
            "speed", "size", "sense_radius", "aggression",
            "hue", "saturation", "efficiency",
            "complexity", "symmetry", "stroke_scale",
            "appendages", "rotation_speed", "motion_style", "longevity",
        ]
        trait = random.choice(trait_names)
        new_val = max(0.0, min(1.0, getattr(self, trait) + random.gauss(0, std)))
        new_genome = Genome(**{
            **{t: getattr(self, t) for t in trait_names},
            trait: new_val,
        })
        return new_genome, trait

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
            complexity=self.complexity,
            symmetry=self.symmetry,
            stroke_scale=self.stroke_scale,
            appendages=self.appendages,
            rotation_speed=self.rotation_speed,
            motion_style=self.motion_style,
            longevity=self.longevity,
        )
