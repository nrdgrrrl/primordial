"""Glyph rendering system - procedurally generated symbolic creature bodies.

Each creature's glyph is fully determined by its genome via a deterministic
hash seed, so related creatures look visually similar and mutations produce
visually close-but-distinct offspring.

Stroke vocabulary:
- arc(angle_start, angle_sweep, radius_ratio)  — partial circle arc
- line(angle, length_ratio)                    — straight line from center
- loop(offset_angle, offset_ratio, size_ratio) — small closed oval attached at point
- fork(angle, spread, length_ratio)            — Y-shaped split
- spiral(turns, radius_ratio)                  — inward spiral
- dot(offset_angle, offset_ratio)              — small filled circle offset from center
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.genome import Genome


# ---------------------------------------------------------------------------
# Stroke drawing functions
# Each takes (surface, cx, cy, size, color, alpha, **params) and draws onto
# the surface in-place using SRCALPHA blending.
# ---------------------------------------------------------------------------


def _draw_arc(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    angle_start: float,
    angle_sweep: float,
    radius_ratio: float,
    width: int = 2,
) -> None:
    """Draw a partial circle arc."""
    r = max(3, int(size * radius_ratio * 0.5))
    if r < 2:
        return

    # Draw arc as a series of line segments
    steps = max(8, int(abs(angle_sweep) / 0.15))
    prev_x: float | None = None
    prev_y: float | None = None

    stroke_color = (*color, alpha)
    arc_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)

    for i in range(steps + 1):
        t = i / steps
        angle = angle_start + angle_sweep * t
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        if prev_x is not None:
            pygame.draw.line(arc_surf, stroke_color,
                             (int(prev_x), int(prev_y)),
                             (int(x), int(y)), width)
        prev_x, prev_y = x, y

    surface.blit(arc_surf, (0, 0))


def _draw_line(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    angle: float,
    length_ratio: float,
    width: int = 2,
) -> None:
    """Draw a straight line radiating from center."""
    length = size * length_ratio * 0.48
    ex = cx + math.cos(angle) * length
    ey = cy + math.sin(angle) * length
    stroke_color = (*color, alpha)
    line_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
    pygame.draw.line(line_surf, stroke_color,
                     (int(cx), int(cy)), (int(ex), int(ey)), width)
    surface.blit(line_surf, (0, 0))


def _draw_loop(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    offset_angle: float,
    offset_ratio: float,
    loop_size_ratio: float,
) -> None:
    """Draw a small closed oval attached at a point offset from center."""
    offset = size * offset_ratio * 0.4
    ox = cx + math.cos(offset_angle) * offset
    oy = cy + math.sin(offset_angle) * offset

    rx = max(3, int(size * loop_size_ratio * 0.18))
    ry = max(2, int(rx * 0.6))

    loop_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
    stroke_color = (*color, alpha)
    fill_color = (*color, alpha // 3)

    rect = pygame.Rect(int(ox) - rx, int(oy) - ry, rx * 2, ry * 2)
    pygame.draw.ellipse(loop_surf, fill_color, rect)
    pygame.draw.ellipse(loop_surf, stroke_color, rect, 2)
    surface.blit(loop_surf, (0, 0))


def _draw_fork(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    angle: float,
    spread: float,
    length_ratio: float,
    width: int = 2,
) -> None:
    """Draw a Y-shaped fork: stem from center, two tines splitting at midpoint."""
    stem_len = size * length_ratio * 0.28
    tine_len = size * length_ratio * 0.2

    # Stem midpoint
    mx = cx + math.cos(angle) * stem_len
    my = cy + math.sin(angle) * stem_len

    # Tine endpoints
    left_x = mx + math.cos(angle - spread) * tine_len
    left_y = my + math.sin(angle - spread) * tine_len
    right_x = mx + math.cos(angle + spread) * tine_len
    right_y = my + math.sin(angle + spread) * tine_len

    stroke_color = (*color, alpha)
    fork_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
    pygame.draw.line(fork_surf, stroke_color,
                     (int(cx), int(cy)), (int(mx), int(my)), width)
    pygame.draw.line(fork_surf, stroke_color,
                     (int(mx), int(my)), (int(left_x), int(left_y)), width)
    pygame.draw.line(fork_surf, stroke_color,
                     (int(mx), int(my)), (int(right_x), int(right_y)), width)
    surface.blit(fork_surf, (0, 0))


def _draw_spiral(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    turns: float,
    radius_ratio: float,
    width: int = 2,
) -> None:
    """Draw a tight inward spiral."""
    max_r = size * radius_ratio * 0.42
    steps = max(16, int(turns * 24))

    stroke_color = (*color, alpha)
    spiral_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)

    prev_x: float | None = None
    prev_y: float | None = None

    for i in range(steps + 1):
        t = i / steps
        angle = t * turns * 2 * math.pi
        r = max_r * (1.0 - t)
        x = cx + math.cos(angle) * r
        y = cy + math.sin(angle) * r
        if prev_x is not None:
            pygame.draw.line(spiral_surf, stroke_color,
                             (int(prev_x), int(prev_y)),
                             (int(x), int(y)), width)
        prev_x, prev_y = x, y

    surface.blit(spiral_surf, (0, 0))


def _draw_dot(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    alpha: int,
    offset_angle: float,
    offset_ratio: float,
) -> None:
    """Draw a small filled circle offset from center."""
    offset = size * offset_ratio * 0.38
    ox = int(cx + math.cos(offset_angle) * offset)
    oy = int(cy + math.sin(offset_angle) * offset)
    r = max(2, int(size * 0.08))

    dot_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
    pygame.draw.circle(dot_surf, (*color, alpha), (ox, oy), r)
    surface.blit(dot_surf, (0, 0))


# ---------------------------------------------------------------------------
# Stroke type constants (indices into STROKE_DRAWERS)
# ---------------------------------------------------------------------------

_STROKE_ARC = 0
_STROKE_LINE = 1
_STROKE_LOOP = 2
_STROKE_FORK = 3
_STROKE_SPIRAL = 4
_STROKE_DOT = 5


# ---------------------------------------------------------------------------
# Glyph assembly
# ---------------------------------------------------------------------------


def _genome_hash_seed(genome: Genome) -> int:
    """
    Produce a deterministic integer seed from genome trait values.

    Same genome always yields same seed, enabling stable glyph generation.
    """
    # Quantize traits to 3 decimal places and hash the resulting tuple
    vals = (
        round(genome.complexity, 3),
        round(genome.symmetry, 3),
        round(genome.stroke_scale, 3),
        round(genome.appendages, 3),
        round(genome.rotation_speed, 3),
        round(genome.hue, 3),
        round(genome.saturation, 3),
        round(genome.speed, 3),
        round(genome.size, 3),
    )
    return hash(vals) & 0x7FFFFFFF


def _symmetry_copies(symmetry: float) -> int:
    """Return number of rotational copies for the given symmetry value."""
    if symmetry < 0.33:
        return 1   # asymmetric
    elif symmetry < 0.66:
        return 2   # bilateral (mirror = 2-fold)
    elif symmetry < 0.83:
        return 3   # 3-fold radial
    else:
        return 4   # 4-fold radial


def _draw_stroke_set(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    color: tuple[int, int, int],
    rng: random.Random,
    num_strokes: int,
    scale: float,
) -> None:
    """
    Draw a set of randomly chosen strokes using the provided RNG.

    Args:
        surface: Target surface (SRCALPHA).
        cx, cy: Center of the glyph on the surface.
        size: Canvas size.
        color: RGB stroke color.
        rng: Seeded RNG for determinism.
        num_strokes: How many strokes to draw.
        scale: Overall stroke scale factor.
    """
    stroke_types = [_STROKE_ARC, _STROKE_LINE, _STROKE_LOOP,
                    _STROKE_FORK, _STROKE_SPIRAL, _STROKE_DOT]

    for _ in range(num_strokes):
        stype = rng.choice(stroke_types)
        base_alpha = rng.randint(160, 220)  # slight variation in alpha for depth

        if stype == _STROKE_ARC:
            _draw_arc(surface, cx, cy, size, color, base_alpha,
                      angle_start=rng.uniform(0, math.pi * 2),
                      angle_sweep=rng.uniform(math.pi * 0.3, math.pi * 1.5) * rng.choice([-1, 1]),
                      radius_ratio=rng.uniform(0.4, 0.9) * scale)

        elif stype == _STROKE_LINE:
            _draw_line(surface, cx, cy, size, color, base_alpha,
                       angle=rng.uniform(0, math.pi * 2),
                       length_ratio=rng.uniform(0.5, 1.0) * scale)

        elif stype == _STROKE_LOOP:
            _draw_loop(surface, cx, cy, size, color, base_alpha,
                       offset_angle=rng.uniform(0, math.pi * 2),
                       offset_ratio=rng.uniform(0.3, 0.8) * scale,
                       loop_size_ratio=rng.uniform(0.4, 1.0) * scale)

        elif stype == _STROKE_FORK:
            _draw_fork(surface, cx, cy, size, color, base_alpha,
                       angle=rng.uniform(0, math.pi * 2),
                       spread=rng.uniform(0.3, 0.8),
                       length_ratio=rng.uniform(0.5, 1.0) * scale)

        elif stype == _STROKE_SPIRAL:
            _draw_spiral(surface, cx, cy, size, color, base_alpha,
                         turns=rng.uniform(0.5, 2.0),
                         radius_ratio=rng.uniform(0.4, 0.85) * scale)

        elif stype == _STROKE_DOT:
            _draw_dot(surface, cx, cy, size, color, base_alpha,
                      offset_angle=rng.uniform(0, math.pi * 2),
                      offset_ratio=rng.uniform(0.2, 0.7) * scale)


def build_glyph_surface(
    genome: Genome,
    color: tuple[int, int, int],
    base_size: int = 48,
) -> pygame.Surface:
    """
    Build a cached glyph surface for a creature from its genome.

    The glyph is entirely deterministic: same genome → same glyph.
    Symmetry is applied by rotating/mirroring the base stroke set.
    Appendages are drawn at the perimeter as extra line strokes.

    Args:
        genome: The creature's genome.
        color: RGB color (from hue/saturation mapping).
        base_size: Canvas size in pixels (scales with creature radius).

    Returns:
        A pygame.Surface with SRCALPHA containing the rendered glyph.
    """
    size = float(base_size)
    cx = size / 2.0
    cy = size / 2.0

    # Deterministic RNG from genome
    seed = _genome_hash_seed(genome)
    rng = random.Random(seed)

    # Number of base strokes: complexity 0-1 → 2-7
    num_strokes = 2 + int(genome.complexity * 5)

    # Overall scale
    scale = 0.4 + genome.stroke_scale * 0.6

    # Symmetry copies
    n_copies = _symmetry_copies(genome.symmetry)

    # Create base stroke surface
    base_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
    _draw_stroke_set(base_surf, cx, cy, size, color, rng, num_strokes, scale)

    # Create final glyph surface
    glyph_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)

    # Blit symmetry copies
    for i in range(n_copies):
        angle_deg = (360.0 / n_copies) * i

        if n_copies == 2 and i == 1:
            # Bilateral: mirror horizontally
            mirrored = pygame.transform.flip(base_surf, True, False)
            glyph_surf.blit(mirrored, (0, 0))
        else:
            # Rotational: rotate base by angle
            rotated = pygame.transform.rotate(base_surf, angle_deg)
            # Re-center after rotation (rotated surface may be larger)
            rx = (int(size) - rotated.get_width()) // 2
            ry = (int(size) - rotated.get_height()) // 2
            glyph_surf.blit(rotated, (rx, ry))

    # Draw appendages: 0-4 extra limb strokes at perimeter
    num_appendages = int(genome.appendages * 4)
    if num_appendages > 0:
        app_rng = random.Random(seed ^ 0xDEAD)
        app_surf = pygame.Surface((int(size), int(size)), pygame.SRCALPHA)
        # Evenly spaced appendages
        for a in range(num_appendages):
            base_angle = (2 * math.pi * a / num_appendages) + app_rng.uniform(-0.2, 0.2)
            # Start from perimeter
            perimeter_r = size * 0.35 * scale
            start_x = cx + math.cos(base_angle) * perimeter_r
            start_y = cy + math.sin(base_angle) * perimeter_r
            end_len = size * 0.18 * scale
            end_x = start_x + math.cos(base_angle) * end_len
            end_y = start_y + math.sin(base_angle) * end_len

            alpha = app_rng.randint(140, 200)
            pygame.draw.line(app_surf, (*color, alpha),
                             (int(start_x), int(start_y)),
                             (int(end_x), int(end_y)), 2)
            # Small dot at tip
            pygame.draw.circle(app_surf, (*color, alpha),
                                (int(end_x), int(end_y)), 2)

        glyph_surf.blit(app_surf, (0, 0))

    return glyph_surf


def get_glyph_surface(
    creature,  # Creature, avoid circular import
    color: tuple[int, int, int],
    base_size: int = 48,
) -> pygame.Surface:
    """
    Return the cached glyph surface for a creature, building it if needed.

    The surface is stored on creature.glyph_surface. It is built once
    and reused each frame. The renderer should set creature.glyph_surface = None
    after reproduction so the new offspring's glyph is regenerated.

    Args:
        creature: The creature instance.
        color: RGB color for the strokes.
        base_size: Canvas size in pixels.

    Returns:
        Cached or freshly built glyph surface.
    """
    if creature.glyph_surface is None:
        creature.glyph_surface = build_glyph_surface(creature.genome, color, base_size)
    return creature.glyph_surface
