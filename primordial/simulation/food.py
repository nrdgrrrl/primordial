"""Food module - food particles and spatial management."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .depth import DEPTH_MID, clamp_depth_band


@dataclass
class Food:
    """
    A single food particle in the simulation.

    Food particles are stationary and provide energy when eaten.
    """

    x: float
    y: float
    energy: float = 0.1  # Energy provided when consumed
    depth_band: int = DEPTH_MID
    twinkle_phase: float = field(default_factory=lambda: random.uniform(0, 6.28))


class FoodManager:
    """
    Manages all food particles with spatial bucketing for efficient queries.

    Uses a grid-based spatial hash for O(1) average-case neighbor lookups,
    avoiding O(n²) brute-force searches when creatures seek food.
    """

    def __init__(
        self, world_width: int, world_height: int, bucket_size: int = 100,
        max_particles: int = 500,
    ) -> None:
        """
        Initialize the food manager.

        Args:
            world_width: Width of the simulation world.
            world_height: Height of the simulation world.
            bucket_size: Size of each spatial bucket in pixels.
        """
        self.world_width = world_width
        self.world_height = world_height
        self.bucket_size = bucket_size

        # Calculate grid dimensions
        self.grid_width = (world_width + bucket_size - 1) // bucket_size
        self.grid_height = (world_height + bucket_size - 1) // bucket_size

        # Spatial hash: grid cell -> list of food particles
        self.buckets: dict[tuple[int, int], list[Food]] = {}

        # All food particles (for iteration)
        self.particles: list[Food] = []

        # Maximum food particles allowed
        self.max_particles = max_particles

    def _get_bucket(self, x: float, y: float) -> tuple[int, int]:
        """Get the bucket coordinates for a position."""
        bx = int(x / self.bucket_size) % self.grid_width
        by = int(y / self.bucket_size) % self.grid_height
        return (bx, by)

    def resize_world(self, world_width: int, world_height: int) -> None:
        """
        Resize world bounds and rebuild food buckets safely.

        Existing particles are wrapped into the new bounds so lookups stay valid
        after resolution/fullscreen changes.
        """
        self.world_width = world_width
        self.world_height = world_height
        self.grid_width = (world_width + self.bucket_size - 1) // self.bucket_size
        self.grid_height = (world_height + self.bucket_size - 1) // self.bucket_size

        for food in self.particles:
            food.x = food.x % world_width
            food.y = food.y % world_height
        self.rebuild_buckets()

    def rebuild_buckets(self) -> None:
        """Rebuild the derived spatial hash from the authoritative particles list."""
        self.buckets.clear()
        for food in self.particles:
            bucket = self._get_bucket(food.x, food.y)
            if bucket not in self.buckets:
                self.buckets[bucket] = []
            self.buckets[bucket].append(food)

    def spawn(
        self,
        x: float | None = None,
        y: float | None = None,
        *,
        depth_band: int = DEPTH_MID,
    ) -> Food | None:
        """
        Spawn a new food particle.

        Args:
            x: Optional x position; random if not provided.
            y: Optional y position; random if not provided.

        Returns:
            The spawned Food particle, or None if at capacity.
        """
        if len(self.particles) >= self.max_particles:
            return None

        if x is None:
            x = random.uniform(0, self.world_width)
        if y is None:
            y = random.uniform(0, self.world_height)

        food = Food(x=x, y=y, depth_band=clamp_depth_band(depth_band))
        self.particles.append(food)

        bucket = self._get_bucket(x, y)
        if bucket not in self.buckets:
            self.buckets[bucket] = []
        self.buckets[bucket].append(food)

        return food

    def spawn_batch(self, count: int) -> int:
        """
        Spawn multiple food particles.

        Args:
            count: Number of particles to spawn.

        Returns:
            Number of particles actually spawned.
        """
        spawned = 0
        for _ in range(count):
            if self.spawn() is not None:
                spawned += 1
        return spawned

    def remove(self, food: Food) -> None:
        """
        Remove a food particle from the world.

        Args:
            food: The food particle to remove.
        """
        if food in self.particles:
            self.particles.remove(food)

            bucket = self._get_bucket(food.x, food.y)
            if bucket in self.buckets and food in self.buckets[bucket]:
                self.buckets[bucket].remove(food)

    def find_nearest(
        self,
        x: float,
        y: float,
        max_radius: float,
        *,
        depth_band: int | None = None,
    ) -> Food | None:
        """
        Find the nearest food particle within a radius.

        Uses spatial bucketing for efficient search.

        Args:
            x: Search center x coordinate.
            y: Search center y coordinate.
            max_radius: Maximum search radius.

        Returns:
            Nearest Food particle, or None if none found.
        """
        # Determine which buckets to search
        buckets_to_check = self._get_buckets_in_radius(x, y, max_radius)

        nearest: Food | None = None
        nearest_dist_sq = max_radius * max_radius

        for bucket in buckets_to_check:
            if bucket not in self.buckets:
                continue

            for food in self.buckets[bucket]:
                if depth_band is not None and food.depth_band != depth_band:
                    continue
                # Calculate toroidal distance squared
                dx = abs(food.x - x)
                dy = abs(food.y - y)

                if dx > self.world_width / 2:
                    dx = self.world_width - dx
                if dy > self.world_height / 2:
                    dy = self.world_height - dy

                dist_sq = dx * dx + dy * dy
                if dist_sq < nearest_dist_sq:
                    nearest_dist_sq = dist_sq
                    nearest = food

        return nearest

    def _get_buckets_in_radius(
        self, x: float, y: float, radius: float
    ) -> list[tuple[int, int]]:
        """
        Get all bucket coordinates that could contain points within radius.

        Args:
            x: Center x coordinate.
            y: Center y coordinate.
            radius: Search radius.

        Returns:
            List of bucket coordinate tuples.
        """
        cx, cy = self._get_bucket(x, y)
        buckets_radius = int(radius / self.bucket_size) + 1

        buckets = []
        for dx in range(-buckets_radius, buckets_radius + 1):
            for dy in range(-buckets_radius, buckets_radius + 1):
                bx = (cx + dx) % self.grid_width
                by = (cy + dy) % self.grid_height
                buckets.append((bx, by))

        return buckets

    def clear(self) -> None:
        """Remove all food particles."""
        self.particles.clear()
        self.buckets.clear()

    def __len__(self) -> int:
        """Return the number of food particles."""
        return len(self.particles)

    def __iter__(self):
        """Iterate over all food particles."""
        return iter(self.particles)
