"""Themes module - visual styling for the simulation."""

from __future__ import annotations

import math
import random as _random_module
from abc import ABC, abstractmethod

# Isolated RNG for rendering — prevents visual randomness from polluting
# the simulation's global random.Random() state.
_render_rng = _random_module.Random()
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    surface: Any = field(default=None, repr=False)  # pre-rendered surface


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
    def resolve_color_for_species(
        self,
        species: str,
        hue: float,
        saturation: float,
    ) -> tuple[int, int, int]:
        """Return the rendered RGB color for a species/genome combination."""
        pass

    def resolve_color_for_creature(self, creature: Creature) -> tuple[int, int, int]:
        """Resolve the rendered color for one creature instance."""
        return self.resolve_color_for_species(
            creature.species,
            creature.genome.hue,
            creature.genome.saturation,
        )

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
        self._age_overlay_cache: dict[tuple[int, int], pygame.Surface] = {}
        self._rotated_glyph_cache: dict[tuple[int, int, int], pygame.Surface] = {}

        # Pre-rendered food surfaces at 16 alpha levels (avoid per-frame alloc)
        # Food: radius=3, color=(200,255,255), alpha range [60, 150]
        self._food_surfs: list[pygame.Surface] = []
        for i in range(16):
            t = i / 15
            alpha = int(60 + (150 - 60) * t)
            surf = pygame.Surface((12, 12), pygame.SRCALPHA)
            pygame.draw.circle(surf, (200, 255, 255, alpha // 3), (6, 6), 6)
            pygame.draw.circle(surf, (200, 255, 255, alpha), (6, 6), 3)
            self._food_surfs.append(surf)

        # Shared trail surface (lazy-init to screen size on first use)
        self._trail_surf: pygame.Surface | None = None

    def invalidate_runtime_caches(self) -> None:
        """Drop transient caches tied to live creature and surface state."""
        self._trail_surf = None
        self._rotated_glyph_cache.clear()

    def _get_rotated_glyph(
        self,
        creature: Creature,
        glyph: pygame.Surface,
        angle_degrees: float,
    ) -> pygame.Surface:
        """Return a cached steady-state rotated glyph surface."""
        angle_bucket = int(round(angle_degrees / 3.0)) % 120
        creature_id = id(creature)
        glyph_id = id(glyph)
        cache_key = (creature_id, glyph_id, angle_bucket)
        cached = self._rotated_glyph_cache.get(cache_key)
        if cached is not None:
            return cached

        rotated = pygame.transform.rotate(glyph, angle_bucket * 3.0)
        if len(self._rotated_glyph_cache) >= 8192:
            self._rotated_glyph_cache.clear()
        self._rotated_glyph_cache[cache_key] = rotated
        return rotated

    def _get_age_overlay(self, radius: int, alpha: int) -> pygame.Surface:
        """Cached grey age-wash overlay by radius and alpha."""
        key = (radius, alpha)
        cached = self._age_overlay_cache.get(key)
        if cached is not None:
            return cached
        surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surf, (80, 90, 110, alpha), (radius, radius), radius)
        if len(self._age_overlay_cache) < 160:
            self._age_overlay_cache[key] = surf
        return surf

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

    def resolve_color_for_species(
        self,
        species: str,
        hue: float,
        saturation: float,
    ) -> tuple[int, int, int]:
        """Bias predators into a distinctive warm family while keeping variation."""
        base_color = self.get_creature_color(hue, saturation)
        if species != "predator":
            return base_color

        warm_anchor_a = (255, 120, 84)
        warm_anchor_b = (255, 196, 92)
        anchor_blend = 0.5 + 0.5 * math.sin(hue * math.pi)
        anchor = tuple(
            int((left * (1.0 - anchor_blend)) + (right * anchor_blend))
            for left, right in zip(warm_anchor_a, warm_anchor_b)
        )
        tint_strength = 0.64 + (0.16 * saturation)
        red = int(base_color[0] * (1.0 - tint_strength) + anchor[0] * tint_strength)
        green = int(base_color[1] * (1.0 - tint_strength) + anchor[1] * tint_strength)
        blue = int(base_color[2] * (1.0 - tint_strength * 0.92) + anchor[2] * tint_strength * 0.32)
        return (
            min(255, max(red, green + 16, blue + 36)),
            min(255, green),
            min(255, blue),
        )

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
            return self._glow_cache[cache_key]

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
            self._glow_cache[cache_key] = surface

        return surface

    def _get_depth_render_style(self, creature: Creature) -> tuple[float, float]:
        """Return compact scale and brightness cues for bounded depth."""
        if creature.depth_band <= 0:
            return 1.08, 1.12
        if creature.depth_band >= 2:
            return 0.92, 0.82
        return 1.0, 1.0

    def render_creature_trail(
        self,
        creature: Creature,
        time: float,
        scale: float = 1.0,
    ) -> None:
        """
        Draw creature trail onto the shared _trail_surf (no per-frame alloc).

        Must be called after _trail_surf has been cleared by the renderer.
        """
        if not creature.trail or self._trail_surf is None:
            return

        color = self.resolve_color_for_creature(creature)
        depth_scale, depth_brightness = self._get_depth_render_style(creature)
        color = tuple(min(255, int(channel * depth_brightness)) for channel in color)
        pulse = 1.0 + 0.1 * math.sin(time * 3.14 + creature._glyph_phase)
        radius = max(4, int(creature.get_radius() * pulse * scale * depth_scale))

        trail_len = len(creature.trail)
        for i, (tx, ty) in enumerate(creature.trail):
            trail_alpha = int(25 * (i + 1) / trail_len)
            trail_radius = max(1, int(radius * 0.4 * (i + 1) / trail_len))
            pygame.draw.circle(
                self._trail_surf,
                (*color, trail_alpha),
                (int(tx), int(ty)),
                trail_radius,
            )

    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
        scale: float = 1.0,
    ) -> None:
        """Render a creature with bloom glow halo and symbolic glyph (no trail)."""
        color = self.resolve_color_for_creature(creature)
        depth_scale, depth_brightness = self._get_depth_render_style(creature)
        color = tuple(min(255, int(channel * depth_brightness)) for channel in color)

        # Pulsing animation — uses _glyph_phase so boids flocks can phase-sync
        pulse = 1.0 + 0.1 * math.sin(time * 3.14 + creature._glyph_phase)
        base_radius = creature.get_radius()
        radius = max(4, int(base_radius * pulse * scale * depth_scale))

        # Draw bloom glow halo (behind the glyph)
        glow = self._create_glow_surface(radius, color, 140)
        glow_size = glow.get_width()
        pos = (int(creature.x) - glow_size // 2, int(creature.y) - glow_size // 2)
        surface.blit(glow, pos)

        # Draw glyph on top of glow
        glyph_size = max(32, int(base_radius * 4 * scale * depth_scale))
        # Invalidate glyph cache if size has changed significantly
        if (creature.glyph_surface is not None and
                abs(creature.glyph_surface.get_width() - glyph_size) > 4):
            creature.glyph_surface = None

        glyph = get_glyph_surface(creature, color, glyph_size)

        # Rotate by creature's rotation_angle
        try:
            rotated = self._get_rotated_glyph(creature, glyph, creature.rotation_angle)
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
            grey_surf = self._get_age_overlay(grey_r, grey_alpha)
            surface.blit(grey_surf, (int(creature.x) - grey_r, int(creature.y) - grey_r))

    def render_food(
        self,
        surface: pygame.Surface,
        food: Food,
        time: float,
    ) -> None:
        """Render a food particle with twinkle effect (uses pre-rendered surfaces)."""
        twinkle = math.sin(time * 5 + food.twinkle_phase) * 0.3 + 0.7
        # twinkle ∈ [0.4, 1.0] → index ∈ [0, 15]
        idx = min(15, max(0, int((twinkle - 0.4) / 0.6 * 15)))
        if food.depth_band == 0:
            idx = min(15, idx + 1)
        elif food.depth_band == 2:
            idx = max(0, idx - 3)
        surface.blit(self._food_surfs[idx], (int(food.x) - 6, int(food.y) - 6))

    def render_ambient(
        self,
        surface: pygame.Surface,
        particles: list[AmbientParticle],
        time: float,
    ) -> None:
        """Render ambient background particles (uses pre-rendered surfaces)."""
        for p in particles:
            if p.surface is None:
                continue
            offset_x = math.sin(time * p.speed + p.phase) * 20
            offset_y = math.cos(time * p.speed * 0.7 + p.phase) * 15
            x = int(p.x + offset_x)
            y = int(p.y + offset_y)
            r = int(p.radius)
            surface.blit(p.surface, (x - r, y - r))

    def create_ambient_particles(
        self, width: int, height: int, count: int
    ) -> list[AmbientParticle]:
        """Create ambient background particles with pre-rendered surfaces."""
        particles = []
        for _ in range(count):
            r = _render_rng.uniform(30, 80)
            alpha = _render_rng.randint(8, 20)
            ri = int(r)
            size = ri * 2
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, (20, 40, 80, alpha), (ri, ri), ri)
            particles.append(
                AmbientParticle(
                    x=_render_rng.uniform(0, width),
                    y=_render_rng.uniform(0, height),
                    radius=r,
                    alpha=alpha,
                    phase=_render_rng.uniform(0, 6.28),
                    speed=_render_rng.uniform(0.1, 0.3),
                    surface=surf,
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

    def resolve_color_for_species(
        self,
        species: str,
        hue: float,
        saturation: float,
    ) -> tuple[int, int, int]:
        _ = hue, saturation
        if species == "predator":
            return (255, 128, 96)
        return (100, 150, 200)

    def render_creature(
        self,
        surface: pygame.Surface,
        creature: Creature,
        time: float,
        scale: float = 1.0,
    ) -> None:
        """Basic creature rendering."""
        radius = max(2, int(creature.get_radius() * scale))
        color = self.resolve_color_for_creature(creature)
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
