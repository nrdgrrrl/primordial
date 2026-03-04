"""Themes module - visual styling for the simulation."""

from __future__ import annotations

import math
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

from .glyphs import get_glyph_surface

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
        scale: float = 1.0,
    ) -> None:
        """
        Render a creature to the surface.

        Args:
            surface: Pygame surface to draw on.
            creature: The creature to render.
            time: Current simulation time for animations.
            scale: Optional scale override (used by birth animation).
        """
        pass

    @abstractmethod
    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """Render a food particle to the surface."""
        pass

    @abstractmethod
    def render_ambient(
        self,
        surface: pygame.Surface,
        particles: list[AmbientParticle],
        time: float,
    ) -> None:
        """Render ambient background particles."""
        pass

    @abstractmethod
    def create_ambient_particles(
        self, width: int, height: int, count: int
    ) -> list[AmbientParticle]:
        """Create ambient background particles."""
        pass


class OceanTheme(Theme):
    """
    Ocean/deep-sea bioluminescent theme.

    Features:
    - Near-black deep blue background
    - Procedurally generated symbolic glyphs derived from genome
    - Bloom glow halo behind each glyph
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
        self._glow_cache: dict[tuple[int, int, int, int], pygame.Surface] = {}

    @property
    def name(self) -> str:
        return "ocean"

    @property
    def background_color(self) -> tuple[int, int, int]:
        return (2, 8, 24)  # Deep ocean blue, near-black

    def get_creature_color(self, hue: float, saturation: float) -> tuple[int, int, int]:
        """
        Map genome hue/saturation to a bioluminescent color.

        Args:
            hue: Genome hue value (0-1).
            saturation: Genome saturation value (0-1).

        Returns:
            RGB color tuple.
        """
        idx = int(hue * len(self.PALETTE)) % len(self.PALETTE)
        base_color = self.PALETTE[idx]

        next_idx = (idx + 1) % len(self.PALETTE)
        next_color = self.PALETTE[next_idx]
        blend = (hue * len(self.PALETTE)) % 1.0

        r = int(base_color[0] * (1 - blend) + next_color[0] * blend)
        g = int(base_color[1] * (1 - blend) + next_color[1] * blend)
        b = int(base_color[2] * (1 - blend) + next_color[2] * blend)

        gray = (r + g + b) // 3
        r = int(r * saturation + gray * (1 - saturation))
        g = int(g * saturation + gray * (1 - saturation))
        b = int(b * saturation + gray * (1 - saturation))

        return (min(255, r), min(255, g), min(255, b))

    def _create_glow_surface(
        self, radius: int, color: tuple[int, int, int], max_alpha: int
    ) -> pygame.Surface:
        """
        Create a glowing halo surface with concentric circles.

        Args:
            radius: Base radius of the glow.
            color: RGB color.
            max_alpha: Maximum alpha at center.

        Returns:
            Surface with glow effect.
        """
        cache_key = (radius, color[0], color[1], color[2])
        if cache_key in self._glow_cache:
            return self._glow_cache[cache_key].copy()

        glow_radius = int(radius * 2.5)
        size = glow_radius * 2
        surface = pygame.Surface((size, size), pygame.SRCALPHA)

        layers = 8
        for i in range(layers, 0, -1):
            layer_radius = int(glow_radius * (i / layers))
            alpha = int(max_alpha * ((layers - i + 1) / layers) ** 2)
            layer_color = (*color, alpha)
            pygame.draw.circle(
                surface, layer_color, (glow_radius, glow_radius), layer_radius
            )

        if len(self._glow_cache) < 100:
            self._glow_cache[cache_key] = surface.copy()

        return surface

    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
        scale: float = 1.0,
    ) -> None:
        """Render a creature with bloom glow halo and symbolic glyph."""
        color = self.get_creature_color(
            creature.genome.hue, creature.genome.saturation
        )

        # Pulsing animation tied to genome
        pulse = 1.0 + 0.1 * math.sin(time * 3.14 + creature.genome.hue * 6.28)
        base_radius = creature.get_radius()
        radius = max(4, int(base_radius * pulse * scale))

        # Draw trail (before glow so glow sits on top)
        if creature.trail:
            trail_len = len(creature.trail)
            for i, (tx, ty) in enumerate(creature.trail):
                trail_alpha = int(25 * (i + 1) / trail_len)
                trail_radius = max(1, int(radius * 0.4 * (i + 1) / trail_len))
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

        # Draw bloom glow halo (behind the glyph)
        glow = self._create_glow_surface(radius, color, 140)
        glow_size = glow.get_width()
        pos = (int(creature.x) - glow_size // 2, int(creature.y) - glow_size // 2)
        surface.blit(glow, pos)

        # Draw glyph on top of glow
        glyph_size = max(32, int(base_radius * 4 * scale))
        # Invalidate glyph cache if size has changed significantly
        if (creature.glyph_surface is not None and
                abs(creature.glyph_surface.get_width() - glyph_size) > 4):
            creature.glyph_surface = None

        glyph = get_glyph_surface(creature, color, glyph_size)

        # Rotate by creature's rotation_angle
        try:
            rotated = pygame.transform.rotate(glyph, creature.rotation_angle)
            # Apply birth scale
            if scale != 1.0 and scale < 0.99:
                new_w = max(4, int(rotated.get_width() * scale))
                new_h = max(4, int(rotated.get_height() * scale))
                rotated = pygame.transform.smoothscale(rotated, (new_w, new_h))
            surface.blit(rotated,
                         (int(creature.x) - rotated.get_width() // 2,
                          int(creature.y) - rotated.get_height() // 2))
        except pygame.error:
            pass

        # Age-based desaturation: overlay a faint grey wash at blit time
        # (does NOT touch the glyph cache — purely cosmetic blending layer)
        age_frac = creature.get_age_fraction()
        if age_frac > 0.7:
            grey_alpha = int(((age_frac - 0.7) / 0.3) * 160)
            grey_alpha = min(160, grey_alpha)
            grey_r = int(radius * 2.5)
            grey_surf = pygame.Surface((grey_r * 2, grey_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                grey_surf,
                (80, 90, 110, grey_alpha),
                (grey_r, grey_r),
                grey_r,
            )
            surface.blit(grey_surf, (int(creature.x) - grey_r, int(creature.y) - grey_r))

    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """Render a food particle with twinkle effect."""
        base_alpha = 150
        twinkle = math.sin(time * 5 + food.twinkle_phase) * 0.3 + 0.7
        alpha = int(base_alpha * twinkle)

        color = (200, 255, 255, alpha)
        radius = 3

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
            offset_x = math.sin(time * p.speed + p.phase) * 20
            offset_y = math.cos(time * p.speed * 0.7 + p.phase) * 15

            x = int(p.x + offset_x)
            y = int(p.y + offset_y)

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
        scale: float = 1.0,
    ) -> None:
        """Basic creature rendering."""
        radius = max(2, int(creature.get_radius() * scale))
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
        return StubTheme(name)
