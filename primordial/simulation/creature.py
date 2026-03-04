"""Creature module - individual organisms in the simulation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .genome import Genome


@dataclass
class Creature:
    """
    A single creature in the simulation.

    Creatures have position, velocity, energy, and a genome that determines
    their characteristics. They move with smooth steering behavior, seek food,
    reproduce when energy is high, and die when energy depletes.
    """

    x: float
    y: float
    genome: Genome
    vx: float = 0.0
    vy: float = 0.0
    energy: float = 0.5
    age: int = 0
    trail: list[tuple[float, float]] = field(default_factory=list)

    # Steering parameters
    STEER_STRENGTH: float = 0.1
    WANDER_STRENGTH: float = 0.3

    def update_position(
        self, dt: float, world_width: int, world_height: int
    ) -> None:
        """
        Update creature position based on velocity.

        Args:
            dt: Time delta (typically 1.0 for frame-based simulation).
            world_width: Width of the world for wrapping.
            world_height: Height of the world for wrapping.
        """
        # Move by velocity
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Wrap around screen edges (toroidal world)
        self.x = self.x % world_width
        self.y = self.y % world_height

        # Update trail (last 8 positions for rendering)
        self.trail.append((self.x, self.y))
        if len(self.trail) > 8:
            self.trail.pop(0)

        # Increment age
        self.age += 1

    def steer_toward(
        self,
        target_x: float,
        target_y: float,
        speed_base: float,
        world_width: int,
        world_height: int,
    ) -> None:
        """
        Steer velocity toward a target position.

        Uses smooth steering that blends current velocity with desired direction.
        Handles toroidal world wrapping for shortest path calculation.

        Args:
            target_x: Target x coordinate.
            target_y: Target y coordinate.
            speed_base: Base speed from settings.
            world_width: World width for wrapping calculations.
            world_height: World height for wrapping calculations.
        """
        # Calculate direction to target with toroidal wrapping
        dx = target_x - self.x
        dy = target_y - self.y

        # Find shortest path considering wrapping
        if abs(dx) > world_width / 2:
            dx = dx - math.copysign(world_width, dx)
        if abs(dy) > world_height / 2:
            dy = dy - math.copysign(world_height, dy)

        # Normalize direction
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dx /= dist
            dy /= dist

        # Calculate desired velocity
        max_speed = self.genome.speed * speed_base
        desired_vx = dx * max_speed
        desired_vy = dy * max_speed

        # Smooth steering (blend current and desired velocity)
        self.vx += (desired_vx - self.vx) * self.STEER_STRENGTH
        self.vy += (desired_vy - self.vy) * self.STEER_STRENGTH

    def wander(self, speed_base: float) -> None:
        """
        Add random wandering behavior when no food is nearby.

        Args:
            speed_base: Base speed from settings.
        """
        # Add small random angle change
        angle_change = random.gauss(0, self.WANDER_STRENGTH)

        # Get current angle and speed
        current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        if current_speed < 0.01:
            # If nearly stationary, pick random direction
            angle = random.uniform(0, 2 * math.pi)
            current_speed = self.genome.speed * speed_base * 0.5
        else:
            angle = math.atan2(self.vy, self.vx)

        # Apply angle change
        angle += angle_change

        # Set velocity
        max_speed = self.genome.speed * speed_base
        target_speed = min(current_speed + 0.1, max_speed)
        self.vx = math.cos(angle) * target_speed
        self.vy = math.sin(angle) * target_speed

    def distance_to(
        self, x: float, y: float, world_width: int, world_height: int
    ) -> float:
        """
        Calculate toroidal distance to a point.

        Args:
            x: Target x coordinate.
            y: Target y coordinate.
            world_width: World width for wrapping.
            world_height: World height for wrapping.

        Returns:
            Euclidean distance considering world wrapping.
        """
        dx = abs(x - self.x)
        dy = abs(y - self.y)

        # Consider wrapping for shortest distance
        if dx > world_width / 2:
            dx = world_width - dx
        if dy > world_height / 2:
            dy = world_height - dy

        return math.sqrt(dx * dx + dy * dy)

    def get_radius(self) -> float:
        """
        Get the creature's body radius based on genome.

        Returns:
            Radius in pixels (4-12 range).
        """
        return 4.0 + self.genome.size * 8.0

    def get_sense_radius(self) -> float:
        """
        Get the creature's sensing radius based on genome.

        Returns:
            Sensing radius in pixels (40-150 range).
        """
        return 40.0 + self.genome.sense_radius * 110.0

    def get_movement_cost(self) -> float:
        """
        Calculate energy cost of movement per frame.

        Cost scales with speed and size.

        Returns:
            Energy cost for current movement.
        """
        speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        size_factor = 0.5 + self.genome.size * 0.5
        return speed * size_factor * 0.001

    @classmethod
    def spawn(
        cls,
        world_width: int,
        world_height: int,
        genome: Genome | None = None,
    ) -> Creature:
        """
        Spawn a new creature at a random position.

        Args:
            world_width: World width for random placement.
            world_height: World height for random placement.
            genome: Optional genome; creates random if not provided.

        Returns:
            A new Creature instance.
        """
        return cls(
            x=random.uniform(0, world_width),
            y=random.uniform(0, world_height),
            genome=genome if genome else Genome.random(),
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=0.5,
        )
