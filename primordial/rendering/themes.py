"""Themes module - visual styling for the simulation."""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.creature import Creature
    from ..simulation.food import Food


@dataclass
class AmbientParticle:
    """A background ambient particle for depth effect."""

    x: float
    y: float
    radius: float
    alpha: int
    phase: float  # For sinusoidal movement
    speed: float


class Theme(ABC):
    """
    Abstract base class for visual themes.

    Themes control all visual styling: colors, effects, and rendering methods.
    New themes must implement all abstract methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the theme name."""
        pass

    @property
    @abstractmethod
    def background_color(self) -> tuple[int, int, int]:
        """Return the background RGB color."""
        pass

    @abstractmethod
    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
    ) -> None:
        """
        Render a creature to the surface.

        Args:
            surface: Pygame surface to draw on.
            creature: The creature to render.
            time: Current simulation time for animations.
        """
        pass

    @abstractmethod
    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """
        Render a food particle to the surface.

        Args:
            surface: Pygame surface to draw on.
            food: The food particle to render.
            time: Current simulation time for animations.
        """
        pass

    @abstractmethod
    def render_ambient(
        self,
        surface: pygame.Surface,
        particles: list[AmbientParticle],
        time: float,
    ) -> None:
        """
        Render ambient background particles.

        Args:
            surface: Pygame surface to draw on.
            particles: List of ambient particles.
            time: Current simulation time for animations.
        """
        pass

    @abstractmethod
    def create_ambient_particles(
        self, width: int, height: int, count: int
    ) -> list[AmbientParticle]:
        """
        Create ambient background particles.

        Args:
            width: World width.
            height: World height.
            count: Number of particles to create.

        Returns:
            List of AmbientParticle instances.
        """
        pass


class OceanTheme(Theme):
    """
    Ocean/deep-sea bioluminescent theme.

    Features:
    - Near-black deep blue background
    - Glowing blob creatures with trails
    - Cool bioluminescent color palette
    - Ambient drifting particles for depth
    """

    # Color palette: bioluminescent blues, cyans, greens, magentas
    PALETTE = [
        (0, 200, 255),  # Cyan
        (0, 255, 200),  # Turquoise
        (100, 100, 255),  # Blue
        (200, 50, 255),  # Magenta
        (0, 255, 150),  # Green-cyan
        (150, 0, 255),  # Purple
    ]

    def __init__(self) -> None:
        """Initialize the ocean theme."""
        # Pre-create glow surfaces for different sizes
        self._glow_cache: dict[tuple[int, int, int, int], pygame.Surface] = {}

    @property
    def name(self) -> str:
        return "ocean"

    @property
    def background_color(self) -> tuple[int, int, int]:
        return (2, 8, 24)  # Deep ocean blue, near-black

    def _get_creature_color(self, hue: float, saturation: float) -> tuple[int, int, int]:
        """
        Map genome hue/saturation to a bioluminescent color.

        Args:
            hue: Genome hue value (0-1).
            saturation: Genome saturation value (0-1).

        Returns:
            RGB color tuple.
        """
        # Use hue to pick from palette
        idx = int(hue * len(self.PALETTE)) % len(self.PALETTE)
        base_color = self.PALETTE[idx]

        # Blend with next color for smooth transitions
        next_idx = (idx + 1) % len(self.PALETTE)
        next_color = self.PALETTE[next_idx]
        blend = (hue * len(self.PALETTE)) % 1.0

        r = int(base_color[0] * (1 - blend) + next_color[0] * blend)
        g = int(base_color[1] * (1 - blend) + next_color[1] * blend)
        b = int(base_color[2] * (1 - blend) + next_color[2] * blend)

        # Apply saturation (desaturate toward white)
        gray = (r + g + b) // 3
        r = int(r * saturation + gray * (1 - saturation))
        g = int(g * saturation + gray * (1 - saturation))
        b = int(b * saturation + gray * (1 - saturation))

        return (min(255, r), min(255, g), min(255, b))

    def _create_glow_surface(
        self, radius: int, color: tuple[int, int, int], max_alpha: int
    ) -> pygame.Surface:
        """
        Create a glowing blob surface with concentric circles.

        Args:
            radius: Base radius of the glow.
            color: RGB color.
            max_alpha: Maximum alpha at center.

        Returns:
            Surface with glow effect.
        """
        cache_key = (radius, color[0], color[1], color[2])
        if cache_key in self._glow_cache:
            cached = self._glow_cache[cache_key].copy()
            return cached

        # Create surface with extra space for glow
        glow_radius = int(radius * 2.5)
        size = glow_radius * 2
        surface = pygame.Surface((size, size), pygame.SRCALPHA)

        # Draw concentric circles with decreasing alpha
        layers = 8
        for i in range(layers, 0, -1):
            layer_radius = int(glow_radius * (i / layers))
            alpha = int(max_alpha * ((layers - i + 1) / layers) ** 2)
            layer_color = (*color, alpha)
            pygame.draw.circle(
                surface, layer_color, (glow_radius, glow_radius), layer_radius
            )

        # Cache for reuse
        if len(self._glow_cache) < 100:
            self._glow_cache[cache_key] = surface.copy()

        return surface

    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
    ) -> None:
        """Render a creature with glow effect and trail."""
        color = self._get_creature_color(
            creature.genome.hue, creature.genome.saturation
        )

        # Pulsing animation (sine wave, ~2s period)
        pulse = 1.0 + 0.15 * math.sin(time * 3.14 + creature.genome.hue * 6.28)
        base_radius = creature.get_radius()
        radius = int(base_radius * pulse)

        # Draw trail (fading afterimages)
        if creature.trail:
            trail_len = len(creature.trail)
            for i, (tx, ty) in enumerate(creature.trail):
                trail_alpha = int(30 * (i + 1) / trail_len)
                trail_radius = max(2, int(radius * 0.5 * (i + 1) / trail_len))
                trail_surface = pygame.Surface(
                    (trail_radius * 2, trail_radius * 2), pygame.SRCALPHA
                )
                pygame.draw.circle(
                    trail_surface,
                    (*color, trail_alpha),
                    (trail_radius, trail_radius),
                    trail_radius,
                )
                surface.blit(
                    trail_surface,
                    (int(tx) - trail_radius, int(ty) - trail_radius),
                )

        # Draw main glow blob
        max_alpha = 180
        glow = self._create_glow_surface(radius, color, max_alpha)
        glow_size = glow.get_width()
        pos = (int(creature.x) - glow_size // 2, int(creature.y) - glow_size // 2)
        surface.blit(glow, pos)

    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """Render a food particle with twinkle effect."""
        # Twinkle effect: random alpha flicker
        base_alpha = 150
        twinkle = math.sin(time * 5 + food.twinkle_phase) * 0.3 + 0.7
        alpha = int(base_alpha * twinkle)

        # Pale cyan glow
        color = (200, 255, 255, alpha)
        radius = 3

        # Draw soft glow
        glow_surface = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surface, (*color[:3], alpha // 3), (radius * 2, radius * 2), radius * 2
        )
        pygame.draw.circle(
            glow_surface, color, (radius * 2, radius * 2), radius
        )

        surface.blit(
            glow_surface,
            (int(food.x) - radius * 2, int(food.y) - radius * 2),
        )

    def render_ambient(
        self,
        surface: pygame.Surface,
        particles: list[AmbientParticle],
        time: float,
    ) -> None:
        """Render ambient background particles."""
        for p in particles:
            # Sinusoidal drift
            offset_x = math.sin(time * p.speed + p.phase) * 20
            offset_y = math.cos(time * p.speed * 0.7 + p.phase) * 15

            x = int(p.x + offset_x)
            y = int(p.y + offset_y)

            # Draw soft circle
            color = (20, 40, 80, p.alpha)
            particle_surface = pygame.Surface(
                (int(p.radius * 2), int(p.radius * 2)), pygame.SRCALPHA
            )
            pygame.draw.circle(
                particle_surface,
                color,
                (int(p.radius), int(p.radius)),
                int(p.radius),
            )
            surface.blit(particle_surface, (x - int(p.radius), y - int(p.radius)))

    def create_ambient_particles(
        self, width: int, height: int, count: int
    ) -> list[AmbientParticle]:
        """Create ambient background particles for depth effect."""
        particles = []
        for _ in range(count):
            particles.append(
                AmbientParticle(
                    x=random.uniform(0, width),
                    y=random.uniform(0, height),
                    radius=random.uniform(30, 80),
                    alpha=random.randint(8, 20),
                    phase=random.uniform(0, 6.28),
                    speed=random.uniform(0.1, 0.3),
                )
            )
        return particles


class StubTheme(Theme):
    """
    Placeholder theme for unimplemented visual styles.

    Shows a "coming soon" message and basic rendering.
    """

    def __init__(self, theme_name: str) -> None:
        """Initialize stub theme with a name."""
        self._name = theme_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def background_color(self) -> tuple[int, int, int]:
        return (20, 20, 30)

    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
    ) -> None:
        """Basic creature rendering."""
        radius = int(creature.get_radius())
        color = (100, 150, 200)
        pygame.draw.circle(surface, color, (int(creature.x), int(creature.y)), radius)

    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """Basic food rendering."""
        pygame.draw.circle(
            surface, (200, 200, 150), (int(food.x), int(food.y)), 2
        )

    def render_ambient(
        self,
        surface: pygame.Surface,
        particles: list[AmbientParticle],
        time: float,
    ) -> None:
        """No ambient particles for stub theme."""
        pass

    def create_ambient_particles(
        self, width: int, height: int, count: int
    ) -> list[AmbientParticle]:
        """No ambient particles for stub theme."""
        return []


def get_theme(name: str) -> Theme:
    """
    Get a theme instance by name.

    Args:
        name: Theme name (ocean, petri, geometric, chaotic).

    Returns:
        Theme instance.
    """
    if name == "ocean":
        return OceanTheme()
    else:
        # Return stub for unimplemented themes
        return StubTheme(name)
