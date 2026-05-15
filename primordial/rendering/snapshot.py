"""Immutable predator/prey render snapshots and pure line builders."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


_GPU_PREDATOR_PREY_KIN_LINE_DEFAULT_DISTANCE = 110.0
_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR = 0.35
_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR = 0.12
_GPU_PREDATOR_PREY_KIN_LINE_WIDTH = 1.5
_GPU_PREDATOR_PREY_KIN_LINE_MAX_NEIGHBORS_PER_CREATURE = 2
_GPU_PREDATOR_PREY_KIN_LINE_MAX_LINES_PER_LINEAGE = 96
_GPU_PREDATOR_PREY_KIN_LINE_MAX_TOTAL_LINES = 512
_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR = 0.75
_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR = 0.35
_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_WIDTH = 3.0

KIN_LINE_STYLE_FILAMENT = "filament"
KIN_LINE_STYLE_PLAIN = "plain"
KIN_LINE_DEFAULT_WAVE_AMPLITUDE = 3.0
KIN_LINE_DEFAULT_WAVE_SEGMENTS = 6
KIN_LINE_DEFAULT_WAVE_SPEED = 1.0
KIN_LINE_DEFAULT_GLOW_ENABLED = True
KIN_LINE_DEFAULT_SHIMMER_ENABLED = True
KIN_LINE_DEFAULT_SHIMMER_STRENGTH = 0.35
KIN_LINE_DEFAULT_GLOW_WIDTH_SCALE = 2.5
KIN_LINE_DEFAULT_GLOW_ALPHA_SCALE = 0.35
KIN_LINE_DEFAULT_SHIMMER_RADIUS = 2.5
KIN_LINE_DEFAULT_SHIMMER_MAX_COUNT = 1


@dataclass(frozen=True, slots=True)
class KinLineStyle:
    style: str = KIN_LINE_STYLE_FILAMENT
    wave_amplitude: float = KIN_LINE_DEFAULT_WAVE_AMPLITUDE
    wave_segments: int = KIN_LINE_DEFAULT_WAVE_SEGMENTS
    wave_speed: float = KIN_LINE_DEFAULT_WAVE_SPEED
    glow_enabled: bool = KIN_LINE_DEFAULT_GLOW_ENABLED
    shimmer_enabled: bool = KIN_LINE_DEFAULT_SHIMMER_ENABLED
    shimmer_strength: float = KIN_LINE_DEFAULT_SHIMMER_STRENGTH
    glow_width_scale: float = KIN_LINE_DEFAULT_GLOW_WIDTH_SCALE
    glow_alpha_scale: float = KIN_LINE_DEFAULT_GLOW_ALPHA_SCALE
    shimmer_radius: float = KIN_LINE_DEFAULT_SHIMMER_RADIUS
    shimmer_max_count: int = KIN_LINE_DEFAULT_SHIMMER_MAX_COUNT


@dataclass(frozen=True, slots=True)
class KinLineRenderData:
    core_lines: tuple[LineSprite, ...]
    glow_lines: tuple[LineSprite, ...]
    shimmer_sprites: tuple[RadialSprite, ...]
    diagnostics: dict[str, int | float] | None


def kin_line_style_from_settings(settings: object) -> KinLineStyle:
    return KinLineStyle(
        style=str(getattr(settings, "kin_line_style", KIN_LINE_STYLE_FILAMENT)),
        wave_amplitude=float(getattr(settings, "kin_line_wave_amplitude", KIN_LINE_DEFAULT_WAVE_AMPLITUDE)),
        wave_segments=int(getattr(settings, "kin_line_wave_segments", KIN_LINE_DEFAULT_WAVE_SEGMENTS)),
        wave_speed=float(getattr(settings, "kin_line_wave_speed", KIN_LINE_DEFAULT_WAVE_SPEED)),
        glow_enabled=bool(getattr(settings, "kin_line_glow", KIN_LINE_DEFAULT_GLOW_ENABLED)),
        shimmer_enabled=bool(getattr(settings, "kin_line_shimmer", KIN_LINE_DEFAULT_SHIMMER_ENABLED)),
        shimmer_strength=float(getattr(settings, "kin_line_shimmer_strength", KIN_LINE_DEFAULT_SHIMMER_STRENGTH)),
        glow_width_scale=float(getattr(settings, "kin_line_glow_width_scale", KIN_LINE_DEFAULT_GLOW_WIDTH_SCALE)),
        glow_alpha_scale=float(getattr(settings, "kin_line_glow_alpha_scale", KIN_LINE_DEFAULT_GLOW_ALPHA_SCALE)),
        shimmer_radius=float(getattr(settings, "kin_line_shimmer_radius", KIN_LINE_DEFAULT_SHIMMER_RADIUS)),
        shimmer_max_count=int(getattr(settings, "kin_line_shimmer_max_count", KIN_LINE_DEFAULT_SHIMMER_MAX_COUNT)),
    )


def _wave_segments_for_line(
    line: LineSprite,
    *,
    segment_count: int,
    amplitude: float,
    wave_speed: float,
    anim_time: float,
    length_scale: float = 50.0,
) -> list[LineSprite]:
    if segment_count < 1:
        segment_count = 1
    dx = line.bx - line.ax
    dy = line.by - line.ay
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.01:
        return [line]
    amp = amplitude * min(1.0, length / length_scale)
    perp_x = -dy / length
    perp_y = dx / length
    phase = (line.ax * 127.1 + line.ay * 311.7 + line.bx * 74.7 + line.by * 269.5) % 6283.185
    points: list[tuple[float, float]] = []
    for i in range(segment_count + 1):
        t = i / segment_count
        offset = amp * math.sin(
            2.0 * math.pi * t + phase / 1000.0 + anim_time * 2.0 * math.pi * wave_speed
        )
        px = line.ax + dx * t + perp_x * offset
        py = line.ay + dy * t + perp_y * offset
        points.append((px, py))
    segments: list[LineSprite] = []
    for i in range(len(points) - 1):
        segments.append(
            LineSprite(
                points[i][0], points[i][1],
                points[i + 1][0], points[i + 1][1],
                line.color,
            )
        )
    return segments


def _shimmer_for_line(
    line: LineSprite,
    *,
    style: KinLineStyle,
    anim_time: float,
) -> RadialSprite | None:
    phase = (line.ax * 127.1 + line.ay * 311.7 + line.bx * 74.7 + line.by * 269.5) % 6283.185
    t = (math.sin(phase / 500.0 + anim_time * 1.5) * 0.5 + 0.5)
    sx = line.ax + (line.bx - line.ax) * t
    sy = line.ay + (line.by - line.ay) * t
    r, g, b, a = line.color
    bright_r = min(1.0, r + 0.15)
    bright_g = min(1.0, g + 0.15)
    bright_b = min(1.0, b + 0.15)
    shimmer_alpha = a * style.shimmer_strength
    return RadialSprite(
        sx, sy,
        style.shimmer_radius, style.shimmer_radius,
        (bright_r, bright_g, bright_b, shimmer_alpha),
        0.8, 1.2,
    )


def build_kin_line_render_data(
    creatures: Iterable[object],
    *,
    world_width: float,
    world_height: float,
    max_distance: float,
    min_group: int,
    color_for_member: Callable[[object], tuple[float, float, float]],
    anim_time: float,
    style: KinLineStyle,
    alpha_near: float = _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR,
    alpha_far: float = _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR,
    max_neighbors_per_creature: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_NEIGHBORS_PER_CREATURE,
    max_lines_per_lineage: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_LINES_PER_LINEAGE,
    max_total_lines: int = _GPU_PREDATOR_PREY_KIN_LINE_MAX_TOTAL_LINES,
    diagnostics: dict[str, int | float] | None = None,
) -> KinLineRenderData:
    logical_lines = build_gpu_kin_line_sprites(
        creatures,
        world_width=world_width,
        world_height=world_height,
        max_distance=max_distance,
        min_group=min_group,
        color_for_member=color_for_member,
        alpha_near=alpha_near,
        alpha_far=alpha_far,
        max_neighbors_per_creature=max_neighbors_per_creature,
        max_lines_per_lineage=max_lines_per_lineage,
        max_total_lines=max_total_lines,
        diagnostics=diagnostics,
    )
    if not logical_lines or style.style == KIN_LINE_STYLE_PLAIN:
        return KinLineRenderData(
            core_lines=logical_lines,
            glow_lines=(),
            shimmer_sprites=(),
            diagnostics=diagnostics,
        )
    core_segments: list[LineSprite] = []
    glow_segments: list[LineSprite] = []
    shimmer_list: list[RadialSprite] = []
    for line in logical_lines:
        segments = _wave_segments_for_line(
            line,
            segment_count=style.wave_segments,
            amplitude=style.wave_amplitude,
            wave_speed=style.wave_speed,
            anim_time=anim_time,
        )
        core_segments.extend(segments)
        if style.glow_enabled:
            r, g, b, a = line.color
            glow_alpha = a * style.glow_alpha_scale
            glow_color = (r, g, b, glow_alpha)
            for seg in segments:
                glow_segments.append(
                    LineSprite(seg.ax, seg.ay, seg.bx, seg.by, glow_color)
                )
        if style.shimmer_enabled and len(shimmer_list) < max_total_lines * style.shimmer_max_count:
            shimmer = _shimmer_for_line(line, style=style, anim_time=anim_time)
            if shimmer is not None:
                shimmer_list.append(shimmer)
    render_diag: dict[str, int | float] = {}
    if diagnostics is not None:
        render_diag.update(diagnostics)
    render_diag["kin_line_count"] = len(logical_lines)
    render_diag["kin_line_segment_count"] = len(core_segments)
    render_diag["kin_line_shimmer_count"] = len(shimmer_list)
    return KinLineRenderData(
        core_lines=tuple(core_segments),
        glow_lines=tuple(glow_segments),
        shimmer_sprites=tuple(shimmer_list),
        diagnostics=render_diag,
    )


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
    kin_glow_lines: tuple[LineSprite, ...]
    kin_shimmer_sprites: tuple[RadialSprite, ...]
    glows: tuple[RadialSprite, ...]
    bodies: tuple[RadialSprite, ...]
    glyphs: tuple[GlyphSprite, ...]
    attack_lines: tuple[LineSprite, ...]
    predator_highlights: tuple[LineSprite, ...]


def resolve_gpu_predator_prey_kin_line_distance(settings: object) -> float:
    """Return the effective GPU predator/prey kin-line distance.

    Resolution order:
    1. If kin_line_max_distance > 0.0 -> use it directly.
    2. If 0.0 is truly explicit (user set it AND it differs from the canonical
       default) -> disabled (0.0). User deliberately chose 0.0.
    3. If 0.0 matches the canonical default (likely auto-saved, not user
       intent) -> fall through to mode-specific defaults.
    4. If sim_mode is predator_prey -> default 110.0.
    5. Otherwise -> disabled (0.0).
    """
    configured = max(0.0, float(getattr(settings, "kin_line_max_distance", 0.0)))
    if configured > 0.0:
        logger.debug("kin_line: using configured distance %.1f", configured)
        return configured
    explicit_fn = getattr(settings, "is_render_setting_explicit", None)
    is_explicit = callable(explicit_fn) and explicit_fn("kin_line_max_distance")
    canonical_fn = getattr(settings, "canonical_render_default", None)
    if is_explicit and callable(canonical_fn):
        canonical_val = canonical_fn("kin_line_max_distance")
        if canonical_val != configured:
            logger.debug("kin_line: explicitly disabled (user chose 0.0, canonical default differs)")
            return 0.0
        logger.debug(
            "kin_line: 0.0 matches canonical default; assuming auto-saved, not explicit"
        )
    elif is_explicit:
        logger.debug("kin_line: explicitly disabled (user set 0.0)")
        return 0.0
    if getattr(settings, "sim_mode", None) == "predator_prey":
        logger.debug(
            "kin_line: predator_prey mode default distance %.1f",
            _GPU_PREDATOR_PREY_KIN_LINE_DEFAULT_DISTANCE,
        )
        return _GPU_PREDATOR_PREY_KIN_LINE_DEFAULT_DISTANCE
    logger.debug("kin_line: disabled (not predator_prey mode)")
    return 0.0


def build_gpu_kin_line_diagnostics(
    creatures: Iterable[object],
    *,
    min_group: int,
) -> dict[str, int | float]:
    """Return lineage diagnostics for kin-line debugging without building lines."""
    lineage_buckets: dict[int, list[object]] = defaultdict(list)
    for creature in creatures:
        lineage_buckets[int(getattr(creature, "lineage_id", -1))].append(creature)
    total_lineages = len(lineage_buckets)
    qualifying = sum(1 for members in lineage_buckets.values() if len(members) >= min_group)
    largest = max((len(members) for members in lineage_buckets.values()), default=0)
    return {
        "total_lineages": total_lineages,
        "qualifying_lineages": qualifying,
        "largest_lineage_size": largest,
    }


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
    diagnostics: dict[str, int | float] | None = None,
) -> tuple[LineSprite, ...]:
    """Build bounded, deterministic kin-line sprites for the GPU renderer."""
    if max_distance <= 0.0 or min_group <= 1:
        if diagnostics is not None:
            diagnostics.update(
                qualifying_lineages=0,
                largest_lineage_size=0,
                total_lineages=0,
            )
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

    qualifying_lineages = 0
    largest_lineage_size = 0

    lines: list[LineSprite] = []
    total_seen_pairs: set[tuple[int, int]] = set()
    for lineage_id in sorted(lineage_buckets):
        members = lineage_buckets[lineage_id]
        member_count = len(members)
        if member_count > largest_lineage_size:
            largest_lineage_size = member_count
        if member_count < min_group:
            continue
        qualifying_lineages += 1

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
    if diagnostics is not None:
        diagnostics.update(
            qualifying_lineages=qualifying_lineages,
            largest_lineage_size=largest_lineage_size,
            total_lineages=len(lineage_buckets),
        )
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
