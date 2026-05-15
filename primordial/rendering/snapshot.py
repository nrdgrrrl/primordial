"""Immutable predator/prey render snapshots and pure line builders."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable


_GPU_PREDATOR_PREY_KIN_LINE_DEFAULT_DISTANCE = 110.0
_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR = 0.20
_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR = 0.05
_GPU_PREDATOR_PREY_KIN_LINE_MAX_NEIGHBORS_PER_CREATURE = 2
_GPU_PREDATOR_PREY_KIN_LINE_MAX_LINES_PER_LINEAGE = 96
_GPU_PREDATOR_PREY_KIN_LINE_MAX_TOTAL_LINES = 512


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
    kin_lines: tuple[LineSprite, ...]
    glows: tuple[RadialSprite, ...]
    bodies: tuple[RadialSprite, ...]
    glyphs: tuple[GlyphSprite, ...]
    attack_lines: tuple[LineSprite, ...]
    predator_highlights: tuple[LineSprite, ...]


def resolve_gpu_predator_prey_kin_line_distance(settings: object) -> float:
    """Return the effective GPU predator/prey kin-line distance."""
    configured = max(0.0, float(getattr(settings, "kin_line_max_distance", 0.0)))
    if configured > 0.0:
        return configured
    explicit = getattr(settings, "is_render_setting_explicit", None)
    if callable(explicit) and explicit("kin_line_max_distance"):
        return 0.0
    if getattr(settings, "sim_mode", None) == "predator_prey":
        return _GPU_PREDATOR_PREY_KIN_LINE_DEFAULT_DISTANCE
    return 0.0


def build_gpu_kin_line_sprites(
    creatures: Iterable[object],
    *,
    world_width: float,
    world_height: float,
    max_distance: float,
    min_group: int,
    color_for_member: Callable[[object], tuple[float, float, float]],
    alpha_near: float = _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR,
    alpha_far: float = _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR,
    max_neighbors_per_creature: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_NEIGHBORS_PER_CREATURE,
    max_lines_per_lineage: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_LINES_PER_LINEAGE,
    max_total_lines: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_TOTAL_LINES,
) -> tuple[LineSprite, ...]:
    """Build bounded, deterministic kin-line sprites for the GPU renderer."""
    if max_distance <= 0.0 or min_group <= 1:
        return ()

    safe_width = max(1.0, float(world_width))
    safe_height = max(1.0, float(world_height))
    max_distance_sq = max_distance * max_distance
    cell_size = max(1.0, max_distance)
    grid_w = max(1, int(math.ceil(safe_width / cell_size)))
    grid_h = max(1, int(math.ceil(safe_height / cell_size)))

    indexed_creatures = list(enumerate(creatures))
    lineage_buckets: dict[int, list[tuple[int, object]]] = defaultdict(list)
    for index, creature in indexed_creatures:
        lineage_buckets[int(getattr(creature, "lineage_id", -1))].append((index, creature))

    lines: list[LineSprite] = []
    total_seen_pairs: set[tuple[int, int]] = set()
    for lineage_id in sorted(lineage_buckets):
        members = lineage_buckets[lineage_id]
        if len(members) < min_group:
            continue

        cell_buckets: dict[tuple[int, int], list[tuple[int, object]]] = defaultdict(list)
        for item in members:
            _, creature = item
            key = (
                int(float(getattr(creature, "x", 0.0)) // cell_size) % grid_w,
                int(float(getattr(creature, "y", 0.0)) // cell_size) % grid_h,
            )
            cell_buckets[key].append(item)
        for bucket in cell_buckets.values():
            bucket.sort(key=lambda item: item[0])

        lineage_line_count = 0
        lineage_color = color_for_member(members[0][1])
        local_neighbor_counts: dict[int, int] = defaultdict(int)
        for key in sorted(cell_buckets):
            lineage_line_count = _append_kin_lines_for_bucket_pair(
                lines=lines,
                seen_pairs=total_seen_pairs,
                local_neighbor_counts=local_neighbor_counts,
                left_members=cell_buckets[key],
                right_members=cell_buckets[key],
                same_bucket=True,
                world_width=safe_width,
                world_height=safe_height,
                max_distance=max_distance,
                max_distance_sq=max_distance_sq,
                color=lineage_color,
                alpha_near=alpha_near,
                alpha_far=alpha_far,
                max_neighbors_per_creature=max_neighbors_per_creature,
                lineage_line_count=lineage_line_count,
                max_lines_per_lineage=max_lines_per_lineage,
                max_total_lines=max_total_lines,
            )
            if lineage_line_count >= max_lines_per_lineage or len(lines) >= max_total_lines:
                break
            for offset_x, offset_y in ((1, -1), (1, 0), (1, 1), (0, 1)):
                neighbor_key = ((key[0] + offset_x) % grid_w, (key[1] + offset_y) % grid_h)
                if neighbor_key == key or neighbor_key not in cell_buckets:
                    continue
                lineage_line_count = _append_kin_lines_for_bucket_pair(
                    lines=lines,
                    seen_pairs=total_seen_pairs,
                    local_neighbor_counts=local_neighbor_counts,
                    left_members=cell_buckets[key],
                    right_members=cell_buckets[neighbor_key],
                    same_bucket=False,
                    world_width=safe_width,
                    world_height=safe_height,
                    max_distance=max_distance,
                    max_distance_sq=max_distance_sq,
                    color=lineage_color,
                    alpha_near=alpha_near,
                    alpha_far=alpha_far,
                    max_neighbors_per_creature=max_neighbors_per_creature,
                    lineage_line_count=lineage_line_count,
                    max_lines_per_lineage=max_lines_per_lineage,
                    max_total_lines=max_total_lines,
                )
                if lineage_line_count >= max_lines_per_lineage or len(lines) >= max_total_lines:
                    break
            if lineage_line_count >= max_lines_per_lineage or len(lines) >= max_total_lines:
                break
        if len(lines) >= max_total_lines:
            break
    return tuple(lines)


def _append_kin_lines_for_bucket_pair(
    *,
    lines: list[LineSprite],
    seen_pairs: set[tuple[int, int]],
    local_neighbor_counts: dict[int, int],
    left_members: list[tuple[int, object]],
    right_members: list[tuple[int, object]],
    same_bucket: bool,
    world_width: float,
    world_height: float,
    max_distance: float,
    max_distance_sq: float,
    color: tuple[float, float, float],
    alpha_near: float,
    alpha_far: float,
    max_neighbors_per_creature: int,
    lineage_line_count: int,
    max_lines_per_lineage: int,
    max_total_lines: int,
) -> int:
    for left_pos, (left_index, left) in enumerate(left_members):
        if local_neighbor_counts[left_index] >= max_neighbors_per_creature:
            continue
        candidate_pairs: list[tuple[float, int, int, object, object]] = []
        start = left_pos + 1 if same_bucket else 0
        for right_index, right in right_members[start:]:
            pair = (left_index, right_index) if left_index < right_index else (right_index, left_index)
            if pair in seen_pairs:
                continue
            if local_neighbor_counts[right_index] >= max_neighbors_per_creature:
                continue
            distance = _toroidal_distance(left, right, world_width, world_height)
            if distance is None:
                continue
            dist_sq, wraps_screen = distance
            if wraps_screen or dist_sq > max_distance_sq:
                continue
            candidate_pairs.append((dist_sq, right_index, left_index, left, right))

        candidate_pairs.sort(key=lambda item: (item[0], item[1]))
        for dist_sq, right_index, _, left_creature, right_creature in candidate_pairs:
            if local_neighbor_counts[left_index] >= max_neighbors_per_creature:
                break
            if local_neighbor_counts[right_index] >= max_neighbors_per_creature:
                continue
            pair = (left_index, right_index) if left_index < right_index else (right_index, left_index)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            local_neighbor_counts[left_index] += 1
            local_neighbor_counts[right_index] += 1

            dist = math.sqrt(dist_sq)
            fade = min(1.0, max(0.0, dist / max_distance))
            alpha = alpha_near + ((alpha_far - alpha_near) * fade)
            lines.append(
                LineSprite(
                    float(getattr(left_creature, "x", 0.0)),
                    float(getattr(left_creature, "y", 0.0)),
                    float(getattr(right_creature, "x", 0.0)),
                    float(getattr(right_creature, "y", 0.0)),
                    (color[0], color[1], color[2], alpha),
                )
            )
            lineage_line_count += 1
            if lineage_line_count >= max_lines_per_lineage or len(lines) >= max_total_lines:
                return lineage_line_count
    return lineage_line_count


def _toroidal_distance(
    left: object,
    right: object,
    world_width: float,
    world_height: float,
) -> tuple[float, bool] | None:
    raw_dx = float(getattr(right, "x", 0.0)) - float(getattr(left, "x", 0.0))
    raw_dy = float(getattr(right, "y", 0.0)) - float(getattr(left, "y", 0.0))
    dx = raw_dx
    dy = raw_dy
    wraps_x = False
    wraps_y = False
    if abs(dx) > world_width / 2.0:
        dx -= math.copysign(world_width, dx)
        wraps_x = True
    if abs(dy) > world_height / 2.0:
        dy -= math.copysign(world_height, dy)
        wraps_y = True
    return (dx * dx + dy * dy, wraps_x or wraps_y)
