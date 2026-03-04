"""Creature module - individual organisms in the simulation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from .genome import Genome


@dataclass
class Creature:
    """
    A single creature in the simulation.

    Creatures have position, velocity, energy, and a genome that determines
    their characteristics. They move with smooth steering behavior, seek food,
    reproduce when energy is high, and die when energy depletes.

    Motion styles (from genome.motion_style):
    - Glide (0.00-0.33): smooth, low-frequency curves
    - Swim (0.34-0.66): sinusoidal lateral oscillation
    - Dart (0.67-1.00): mostly still with periodic fast bursts
    """

    x: float
    y: float
    genome: Genome
    vx: float = 0.0
    vy: float = 0.0
    energy: float = 0.5
    age: int = 0
    trail: list[tuple[float, float]] = field(default_factory=list)

    # Lineage tracking
    lineage_id: int = 0

    # Rotation state (degrees, used by renderer)
    rotation_angle: float = 0.0

    # Cached glyph surface (set by renderer, cleared on reproduction)
    glyph_surface: Any = field(default=None)

    # Swim oscillation state
    _swim_phase: float = field(default=0.0)

    # Dart burst state
    _dart_burst_remaining: int = field(default=0)
    _dart_cooldown: int = field(default=0)

    # Steering parameters
    STEER_STRENGTH: float = 0.1
    WANDER_STRENGTH: float = 0.3

    def get_trail_length(self) -> int:
        """
        Get trail length based on motion style.

        Returns:
            Maximum trail positions (glide=14, swim=10, dart=5).
        """
        ms = self.genome.motion_style
        if ms < 0.34:
            return 14  # glide: long smooth trails
        elif ms < 0.67:
            return 10  # swim: sinuous trails
        else:
            return 5   # dart: short sharp trails

    def update_position(
        self, dt: float, world_width: int, world_height: int
    ) -> None:
        """
        Update creature position based on velocity.

        Applies swim oscillation for swim-style creatures.
        Updates rotation angle for glyph rendering.

        Args:
            dt: Time delta (typically 1.0 for frame-based simulation).
            world_width: Width of the world for wrapping.
            world_height: Height of the world for wrapping.
        """
        ms = self.genome.motion_style

        # Apply aging speed reduction (old creatures move slower)
        age_mult = self.get_age_speed_mult()
        if age_mult < 1.0:
            self.vx *= age_mult
            self.vy *= age_mult

        # Apply swim lateral oscillation before moving
        if 0.34 <= ms < 0.67:
            self._swim_phase += 0.15
            speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
            if speed > 0.01:
                # Perpendicular direction to velocity
                perp_x = -self.vy / speed
                perp_y = self.vx / speed
                osc_amp = speed * 0.35
                self.x += perp_x * math.sin(self._swim_phase) * osc_amp * dt
                self.y += perp_y * math.sin(self._swim_phase) * osc_amp * dt

        # Move by velocity
        self.x += self.vx * dt
        self.y += self.vy * dt

        # Wrap around screen edges (toroidal world)
        self.x = self.x % world_width
        self.y = self.y % world_height

        # Update rotation angle for glyph (degrees/frame)
        rot_deg_per_frame = self.genome.rotation_speed * 2.0
        self.rotation_angle = (self.rotation_angle + rot_deg_per_frame * dt) % 360.0

        # Update trail (variable length based on motion style)
        self.trail.append((self.x, self.y))
        max_trail = self.get_trail_length()
        if len(self.trail) > max_trail:
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

        Dart-style creatures use stronger steering to snap toward targets.

        Args:
            target_x: Target x coordinate.
            target_y: Target y coordinate.
            speed_base: Base speed from settings.
            world_width: World width for wrapping calculations.
            world_height: World height for wrapping calculations.
        """
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

        # Dart style uses stronger steer and faster speed
        ms = self.genome.motion_style
        if ms >= 0.67:
            steer = 0.25
            speed_mult = 1.5
            # Trigger a burst when food is sensed
            if self._dart_burst_remaining <= 0 and self._dart_cooldown <= 0:
                self._dart_burst_remaining = random.randint(15, 30)
        else:
            steer = self.STEER_STRENGTH
            speed_mult = 1.0

        max_speed = self.genome.speed * speed_base * speed_mult
        desired_vx = dx * max_speed
        desired_vy = dy * max_speed

        self.vx += (desired_vx - self.vx) * steer
        self.vy += (desired_vy - self.vy) * steer

    def wander(self, speed_base: float) -> None:
        """
        Add wandering behavior when no food is nearby.

        Behavior varies by motion style:
        - Glide: gentle low-frequency curves
        - Swim: moderate wandering (oscillation applied in update_position)
        - Dart: slow drift with periodic fast bursts

        Args:
            speed_base: Base speed from settings.
        """
        ms = self.genome.motion_style

        if ms >= 0.67:
            # Dart: mostly stationary with periodic bursts
            self._wander_dart(speed_base)
        elif ms < 0.34:
            # Glide: very gentle direction changes
            self._wander_glide(speed_base)
        else:
            # Swim: moderate wandering (oscillation handled in update_position)
            self._wander_swim(speed_base)

    def _wander_glide(self, speed_base: float) -> None:
        """Gentle gliding wander - smooth low-frequency curves."""
        angle_change = random.gauss(0, self.WANDER_STRENGTH * 0.25)

        current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        if current_speed < 0.01:
            angle = random.uniform(0, 2 * math.pi)
            current_speed = self.genome.speed * speed_base * 0.4
        else:
            angle = math.atan2(self.vy, self.vx)

        angle += angle_change
        max_speed = self.genome.speed * speed_base * 0.7
        target_speed = min(current_speed + 0.05, max_speed)
        self.vx = math.cos(angle) * target_speed
        self.vy = math.sin(angle) * target_speed

    def _wander_swim(self, speed_base: float) -> None:
        """Swim wander - moderate direction changes, oscillation in update_position."""
        angle_change = random.gauss(0, self.WANDER_STRENGTH * 0.45)

        current_speed = math.sqrt(self.vx * self.vx + self.vy * self.vy)
        if current_speed < 0.01:
            angle = random.uniform(0, 2 * math.pi)
            current_speed = self.genome.speed * speed_base * 0.5
        else:
            angle = math.atan2(self.vy, self.vx)

        angle += angle_change
        max_speed = self.genome.speed * speed_base
        target_speed = min(current_speed + 0.08, max_speed)
        self.vx = math.cos(angle) * target_speed
        self.vy = math.sin(angle) * target_speed

    def _wander_dart(self, speed_base: float) -> None:
        """Dart wander - mostly stationary with periodic bursts."""
        if self._dart_burst_remaining > 0:
            # Currently bursting - maintain burst velocity
            self._dart_burst_remaining -= 1
        elif self._dart_cooldown > 0:
            # Cooling down - slow drift
            self._dart_cooldown -= 1
            self.vx *= 0.92
            self.vy *= 0.92
        else:
            # Check for random burst trigger (~every 3-5 seconds at 60fps)
            if random.random() < 0.005:
                angle = random.uniform(0, 2 * math.pi)
                burst_speed = self.genome.speed * speed_base * 1.8
                self.vx = math.cos(angle) * burst_speed
                self.vy = math.sin(angle) * burst_speed
                self._dart_burst_remaining = random.randint(10, 25)
                self._dart_cooldown = random.randint(80, 150)
            else:
                # Very slow drift
                self.vx *= 0.95
                self.vy *= 0.95
                if math.sqrt(self.vx * self.vx + self.vy * self.vy) < 0.05:
                    # Tiny random nudge to prevent full stop
                    angle = random.uniform(0, 2 * math.pi)
                    self.vx = math.cos(angle) * 0.05
                    self.vy = math.sin(angle) * 0.05

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

    def get_max_lifespan(self) -> float:
        """
        Maximum lifespan in frames based on longevity trait.

        Returns:
            Lifespan in frames (3000–10000, ~50s–167s at 60fps).
        """
        return 3000.0 + self.genome.longevity * 7000.0

    def get_age_fraction(self) -> float:
        """
        Current age as a fraction of max lifespan (0.0–1.0+).

        Returns:
            0.0 at birth, 1.0 at natural death age.
        """
        return self.age / self.get_max_lifespan()

    def get_age_speed_mult(self) -> float:
        """
        Speed multiplier from aging (declines linearly after 70% lifespan).

        Returns:
            1.0 when young, down to 0.5 at max lifespan.
        """
        frac = self.get_age_fraction()
        if frac < 0.7:
            return 1.0
        return max(0.5, 1.0 - (frac - 0.7) / 0.3 * 0.5)

    def get_effective_sense_radius(self) -> float:
        """
        Sense radius accounting for aging (declines after 85% lifespan).

        Returns:
            Sensing radius in pixels, reduced for old creatures.
        """
        base = self.get_sense_radius()
        frac = self.get_age_fraction()
        if frac < 0.85:
            return base
        return base * max(0.6, 1.0 - (frac - 0.85) / 0.15 * 0.4)

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
        lineage_id: int = 0,
        energy: float = 0.5,
    ) -> Creature:
        """
        Spawn a new creature at a random position.

        Args:
            world_width: World width for random placement.
            world_height: World height for random placement.
            genome: Optional genome; creates random if not provided.
            lineage_id: Lineage identifier for kin tracking.

        Returns:
            A new Creature instance.
        """
        return cls(
            x=random.uniform(0, world_width),
            y=random.uniform(0, world_height),
            genome=genome if genome else Genome.random(),
            vx=random.uniform(-1, 1),
            vy=random.uniform(-1, 1),
            energy=energy,
            lineage_id=lineage_id,
        )
