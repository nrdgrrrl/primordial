"""Animation system - death/birth visual effects managed outside simulation.

AnimationManager holds a list of active Animation objects and ticks them
each frame. Animation state is kept entirely in rendering/ and never
touches simulation/.

Death animation (40 frames):
  - Frame 0: brief white flash
  - Frames 0-40: glyph fades alpha 255→0 and scales down to 0.3x
  - Frames 0-20: 4-6 dim scatter particles drift outward

Birth animation (30 frames):
  - Glyph starts at 0.2x scale and eases out to 1.0x
  - Tracked per creature ID; renderer skips normal render while active

Parent pulse:
  - Brief glow brightening on the parent at moment of reproduction
"""

from __future__ import annotations

import math
import random as _random_module
from dataclasses import dataclass, field

# Isolated RNG for rendering — prevents visual randomness from polluting
# the simulation's global random.Random() state.
_render_rng = _random_module.Random()
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.creature import Creature


# ---------------------------------------------------------------------------
# Easing helpers
# ---------------------------------------------------------------------------


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic: fast start, decelerates to end. t in [0,1]."""
    return 1.0 - (1.0 - t) ** 3


# ---------------------------------------------------------------------------
# Scatter particle for death effect
# ---------------------------------------------------------------------------


@dataclass
class ScatterParticle:
    """A tiny dim particle that drifts outward during a death animation."""

    x: float
    y: float
    vx: float
    vy: float
    color: tuple[int, int, int]
    life: int    # frames remaining
    max_life: int


# ---------------------------------------------------------------------------
# Animation base class
# ---------------------------------------------------------------------------


class Animation:
    """Base class for all animations. Subclasses implement tick() and draw()."""

    def tick(self) -> bool:
        """
        Advance one frame.

        Returns:
            True if the animation is still active; False when it should be removed.
        """
        raise NotImplementedError

    def draw(self, surface: pygame.Surface) -> None:
        """Draw current animation frame onto surface."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Death animation
# ---------------------------------------------------------------------------


class DeathAnimation(Animation):
    """
    40-frame creature dissolution effect.

    Frame 0: white flash at death position.
    Frames 0-40: glyph alpha fades to 0 and scales down to 0.3x.
    Frames 0-20: scatter particles drift outward.
    """

    TOTAL_FRAMES = 40
    PARTICLE_LIFE = 20
    MIN_SCALE = 0.3

    def __init__(
        self,
        x: float,
        y: float,
        glyph_surface: pygame.Surface | None,
        color: tuple[int, int, int],
        num_particles: int = 5,
    ) -> None:
        self.x = x
        self.y = y
        self.color = color
        self.frame = 0

        # Copy glyph surface so we own it independently
        if glyph_surface is not None:
            self.glyph = glyph_surface.copy()
        else:
            # Fallback: small white circle
            size = 24
            self.glyph = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(self.glyph, (*color, 200), (size // 2, size // 2), size // 2 - 2, 2)

        self.glyph_size = self.glyph.get_width()

        # Scatter particles
        self.particles: list[ScatterParticle] = []
        for _ in range(num_particles):
            angle = _render_rng.uniform(0, math.pi * 2)
            speed = _render_rng.uniform(0.8, 2.2)
            self.particles.append(ScatterParticle(
                x=x,
                y=y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                color=color,
                life=self.PARTICLE_LIFE,
                max_life=self.PARTICLE_LIFE,
            ))

        # Pre-render particle surfaces at 16 alpha levels to avoid per-frame allocs
        self._p_surfs: list[pygame.Surface] = []
        for i in range(16):
            alpha = int(80 * i / 15)
            surf = pygame.Surface((6, 6), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, alpha), (3, 3), 2)
            self._p_surfs.append(surf)

    def tick(self) -> bool:
        self.frame += 1
        for p in self.particles:
            if p.life > 0:
                p.x += p.vx
                p.y += p.vy
                p.vx *= 0.93
                p.vy *= 0.93
                p.life -= 1
        return self.frame < self.TOTAL_FRAMES

    def draw(self, surface: pygame.Surface) -> None:
        t = self.frame / self.TOTAL_FRAMES  # 0→1

        # --- Fading, shrinking glyph ---
        alpha = int(255 * (1.0 - t))
        scale = self.MIN_SCALE + (1.0 - self.MIN_SCALE) * (1.0 - t)

        new_size = max(4, int(self.glyph_size * scale))
        try:
            scaled = pygame.transform.smoothscale(self.glyph, (new_size, new_size))
            scaled.set_alpha(alpha)
            surface.blit(scaled, (int(self.x) - new_size // 2,
                                  int(self.y) - new_size // 2))
        except pygame.error:
            pass

        # --- Scatter particles (use pre-rendered surfaces, no per-frame alloc) ---
        for p in self.particles:
            if p.life <= 0:
                continue
            idx = int(15 * p.life / p.max_life)
            surface.blit(self._p_surfs[idx], (int(p.x) - 3, int(p.y) - 3))


# ---------------------------------------------------------------------------
# Birth animation scale tracker
# ---------------------------------------------------------------------------


class BirthScaleTracker:
    """
    Tracks birth animation progress for a newly created creature.

    The renderer queries this to get the current render scale and skips
    normal rendering until the animation completes.
    """

    TOTAL_FRAMES = 30
    START_SCALE = 0.2

    def __init__(self, creature_id: int) -> None:
        self.creature_id = creature_id
        self.frame = 0
        self.active = True

    def tick(self) -> bool:
        """Advance one frame. Returns True while active."""
        self.frame += 1
        if self.frame >= self.TOTAL_FRAMES:
            self.active = False
        return self.active

    @property
    def scale(self) -> float:
        """Current render scale using ease-out cubic curve."""
        if not self.active:
            return 1.0
        t = self.frame / self.TOTAL_FRAMES
        return self.START_SCALE + (1.0 - self.START_SCALE) * _ease_out_cubic(t)


# ---------------------------------------------------------------------------
# Parent pulse
# ---------------------------------------------------------------------------


class CosmicRayAnimation(Animation):
    """
    20-frame faint expanding ring for cosmic ray mutation events.

    A single white ring expands outward from the creature position with
    low alpha (max 50).  Quiet and rare — meant to feel like a natural event.
    """

    TOTAL_FRAMES = 20
    _FRAME_CACHE: list[tuple[pygame.Surface, int]] | None = None

    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y
        self.frame = 0

        if CosmicRayAnimation._FRAME_CACHE is None:
            cache: list[tuple[pygame.Surface, int]] = []
            for frame in range(self.TOTAL_FRAMES):
                t = frame / self.TOTAL_FRAMES
                radius = int(6 + t * 24)
                alpha = int(50 * (1.0 - t))
                size = (radius + 2) * 2
                ring_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                if alpha > 0 and radius > 0:
                    pygame.draw.circle(
                        ring_surf,
                        (255, 255, 255, alpha),
                        (size // 2, size // 2),
                        radius,
                        1,
                    )
                cache.append((ring_surf, size))
            CosmicRayAnimation._FRAME_CACHE = cache

    def tick(self) -> bool:
        self.frame += 1
        return self.frame < self.TOTAL_FRAMES

    def draw(self, surface: pygame.Surface) -> None:
        if CosmicRayAnimation._FRAME_CACHE is None:
            return
        ring_surf, size = CosmicRayAnimation._FRAME_CACHE[self.frame]
        surface.blit(ring_surf, (int(self.x) - size // 2, int(self.y) - size // 2))


class ParentPulse(Animation):
    """Brief brightening glow on a parent creature at moment of reproduction."""

    TOTAL_FRAMES = 15
    _COLOR_CACHE: dict[tuple[int, int, int], list[tuple[pygame.Surface, int]]] = {}

    def __init__(self, x: float, y: float, color: tuple[int, int, int]) -> None:
        self.x = x
        self.y = y
        self.color = color
        self.frame = 0

        if color not in self._COLOR_CACHE:
            frames: list[tuple[pygame.Surface, int]] = []
            for frame in range(self.TOTAL_FRAMES):
                t = frame / self.TOTAL_FRAMES
                alpha = int(120 * (1.0 - t))
                radius = int(30 * (1.0 + t * 0.5))
                surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    surf, (*color, alpha), (radius + 2, radius + 2), radius, 2
                )
                frames.append((surf, radius))
            self._COLOR_CACHE[color] = frames

    def tick(self) -> bool:
        self.frame += 1
        return self.frame < self.TOTAL_FRAMES

    def draw(self, surface: pygame.Surface) -> None:
        pulse_surf, radius = self._COLOR_CACHE[self.color][self.frame]
        surface.blit(pulse_surf,
                     (int(self.x) - radius - 2, int(self.y) - radius - 2))


# ---------------------------------------------------------------------------
# AnimationManager
# ---------------------------------------------------------------------------


class AnimationManager:
    """
    Manages all active visual animations.

    Call process_events() each frame to ingest simulation events.
    Call tick_and_draw() to advance and render all active animations.
    """

    def __init__(self, num_particles: int = 5) -> None:
        self._num_particles = num_particles

        # Freestanding animations (death effects, parent pulses)
        self._animations: list[Animation] = []

        # Birth scale trackers keyed by id(creature)
        self._birth_trackers: dict[int, BirthScaleTracker] = {}

    # ------------------------------------------------------------------
    # Event ingestion
    # ------------------------------------------------------------------

    def add_death(
        self,
        x: float,
        y: float,
        glyph_surface: pygame.Surface | None,
        color: tuple[int, int, int],
    ) -> None:
        """Create a death animation at the given position."""
        self._animations.append(
            DeathAnimation(x, y, glyph_surface, color, self._num_particles)
        )

    def add_birth(self, creature: Creature) -> None:
        """Start a birth scale-up animation for a new creature."""
        cid = id(creature)
        self._birth_trackers[cid] = BirthScaleTracker(cid)

    def add_parent_pulse(
        self, x: float, y: float, color: tuple[int, int, int]
    ) -> None:
        """Add a brief glow pulse on a reproducing parent."""
        self._animations.append(ParentPulse(x, y, color))

    def add_cosmic_ray(self, x: float, y: float) -> None:
        """Add a faint expanding ring at the cosmic ray mutation position."""
        self._animations.append(CosmicRayAnimation(x, y))

    # ------------------------------------------------------------------
    # Per-frame interface
    # ------------------------------------------------------------------

    def process_events(
        self,
        death_events: list[dict],
        birth_events: list,
        get_color,  # callable(genome) -> (r,g,b)
    ) -> None:
        """
        Ingest simulation event queues and create animations.

        Args:
            death_events: simulation.death_events (will NOT be cleared here;
                          caller should clear after calling this).
            birth_events: simulation.birth_events list of Creature objects.
            get_color: Callable mapping a Genome to an RGB tuple.
        """
        for event in death_events:
            color = get_color(event["genome"])
            self.add_death(
                event["x"],
                event["y"],
                event["glyph_surface"],
                color,
            )

        for creature in birth_events:
            self.add_birth(creature)

    def get_birth_scale(self, creature) -> float | None:
        """
        Return current birth scale for a creature, or None if not animating.

        Args:
            creature: Creature instance.

        Returns:
            Float scale [0.2, 1.0] if in birth animation, else None.
        """
        cid = id(creature)
        tracker = self._birth_trackers.get(cid)
        if tracker is None or not tracker.active:
            return None
        return tracker.scale

    def tick_and_draw(self, surface: pygame.Surface) -> None:
        """
        Advance all animations by one frame and draw them.

        Args:
            surface: Pygame surface to draw onto.
        """
        # Tick and draw freestanding animations
        still_active: list[Animation] = []
        for anim in self._animations:
            anim.draw(surface)
            if anim.tick():
                still_active.append(anim)
        self._animations = still_active

        # Tick birth trackers; remove completed ones
        completed = [cid for cid, t in self._birth_trackers.items() if not t.tick()]
        for cid in completed:
            del self._birth_trackers[cid]

    @property
    def active_count(self) -> int:
        """Total number of active animations (for debugging)."""
        return len(self._animations) + len(self._birth_trackers)
