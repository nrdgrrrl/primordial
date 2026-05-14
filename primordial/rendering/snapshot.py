"""Immutable predator/prey render snapshots for GPU backends."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RadialSprite:
    x: float
    y: float
    radius_x: float
    radius_y: float
    color: tuple[float, float, float, float]
    softness: float
    power: float


@dataclass(frozen=True, slots=True)
class GlyphSprite:
    x: float
    y: float
    size: float
    color: tuple[float, float, float, float]
    angle_degrees: float
    genome_key: tuple[float, ...]
    genome: object


@dataclass(frozen=True, slots=True)
class LineSprite:
    ax: float
    ay: float
    bx: float
    by: float
    color: tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class PredatorPreyRenderSnapshot:
    background_color: tuple[float, float, float, float]
    zones: tuple[RadialSprite, ...]
    ambient: tuple[RadialSprite, ...]
    food: tuple[RadialSprite, ...]
    trails: tuple[RadialSprite, ...]
    glows: tuple[RadialSprite, ...]
    bodies: tuple[RadialSprite, ...]
    glyphs: tuple[GlyphSprite, ...]
    lines: tuple[LineSprite, ...]
    predator_highlights: tuple[LineSprite, ...]
