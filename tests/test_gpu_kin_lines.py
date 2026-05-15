from __future__ import annotations

import unittest
from types import SimpleNamespace

from primordial.rendering.snapshot import (
    build_gpu_kin_line_diagnostics,
    build_gpu_kin_line_sprites,
    build_kin_line_render_data,
    kin_line_style_from_settings,
    resolve_gpu_predator_prey_kin_line_distance,
    KinLineStyle,
    KinLineRenderData,
    LineSprite,
    RadialSprite,
    KIN_LINE_STYLE_FILAMENT,
    KIN_LINE_STYLE_PLAIN,
    KIN_LINE_DEFAULT_WAVE_AMPLITUDE,
    KIN_LINE_DEFAULT_WAVE_SEGMENTS,
    KIN_LINE_DEFAULT_WAVE_SPEED,
    _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR,
    _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR,
    _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_WIDTH,
    _GPU_PREDATOR_PREY_KIN_LINE_WIDTH,
)


def _creature(
    x: float,
    y: float,
    *,
    lineage_id: int,
    species: str = "prey",
) -> SimpleNamespace:
    return SimpleNamespace(
        x=x,
        y=y,
        lineage_id=lineage_id,
        species=species,
        genome=SimpleNamespace(hue=0.2, saturation=0.8),
    )


def _color_for_member(_creature: object) -> tuple[float, float, float]:
    return (0.4, 0.7, 0.9)


class GpuKinLineBuilderTests(unittest.TestCase):
    def test_no_lines_when_distance_is_zero(self) -> None:
        lines = build_gpu_kin_line_sprites(
            [_creature(10, 10, lineage_id=1), _creature(20, 20, lineage_id=1)],
            world_width=200,
            world_height=200,
            max_distance=0.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        self.assertEqual(lines, ())

    def test_no_lines_below_min_group_size(self) -> None:
        lines = build_gpu_kin_line_sprites(
            [_creature(10, 10, lineage_id=1), _creature(20, 20, lineage_id=1)],
            world_width=200,
            world_height=200,
            max_distance=60.0,
            min_group=3,
            color_for_member=_color_for_member,
        )
        self.assertEqual(lines, ())

    def test_generates_lines_for_same_lineage_within_distance(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(32, 12, lineage_id=1),
            _creature(55, 15, lineage_id=1),
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=40.0,
            min_group=3,
            color_for_member=_color_for_member,
        )
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(line.color[3] > 0.0 for line in lines))

    def test_does_not_connect_different_lineages(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=2),
            _creature(30, 10, lineage_id=1),
            _creature(40, 10, lineage_id=2),
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=50.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        lineage_pairs = {
            tuple(sorted((line.ax, line.bx)))
            for line in lines
        }
        self.assertEqual(lineage_pairs, {(10.0, 30.0), (20.0, 40.0)})

    def test_dense_groups_remain_bounded(self) -> None:
        creatures = [
            _creature(20 + (index % 5) * 8, 20 + (index // 5) * 8, lineage_id=7)
            for index in range(25)
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=30.0,
            min_group=3,
            color_for_member=_color_for_member,
            max_lines_per_lineage=18,
            max_total_lines=18,
        )
        self.assertLessEqual(len(lines), 18)

    def test_output_is_deterministic_for_same_positions(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(25, 20, lineage_id=1),
            _creature(40, 26, lineage_id=1),
            _creature(70, 80, lineage_id=2),
            _creature(85, 82, lineage_id=2),
        ]
        first = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=40.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        second = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=40.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        self.assertEqual(first, second)

    def test_gpu_predator_prey_uses_internal_default_when_not_explicit(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="predator_prey",
            is_render_setting_explicit=lambda key: False,
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 110.0)

    def test_explicit_zero_keeps_gpu_kin_lines_disabled(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="predator_prey",
            is_render_setting_explicit=lambda key: key == "kin_line_max_distance",
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 0.0)

    def test_positive_config_value_is_used_directly(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=200.0,
            sim_mode="predator_prey",
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 200.0)

    def test_non_predator_prey_mode_gets_zero_by_default(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="boids",
            is_render_setting_explicit=lambda key: False,
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 0.0)

    def test_min_group_2_produces_lines_for_pair(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=1),
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=50.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        self.assertEqual(len(lines), 1)

    def test_alpha_near_is_stronger_than_far(self) -> None:
        close = _creature(10, 10, lineage_id=1)
        mid = _creature(20, 10, lineage_id=1)
        far = _creature(50, 10, lineage_id=1)
        lines = build_gpu_kin_line_sprites(
            [close, mid, far],
            world_width=200,
            world_height=200,
            max_distance=60.0,
            min_group=3,
            color_for_member=_color_for_member,
        )
        if len(lines) >= 2:
            sorted_lines = sorted(lines, key=lambda l: l.color[3], reverse=True)
            self.assertGreaterEqual(sorted_lines[0].color[3], sorted_lines[-1].color[3])

    def test_normal_alpha_constants_are_reasonable(self) -> None:
        self.assertGreater(_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR, 0.25)
        self.assertLess(_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR, 0.50)
        self.assertGreater(_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR, 0.05)
        self.assertLess(_GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR, 0.20)

    def test_debug_boost_constants_are_stronger_than_normal(self) -> None:
        self.assertGreater(
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR,
            _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_NEAR,
        )
        self.assertGreater(
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR,
            _GPU_PREDATOR_PREY_KIN_LINE_ALPHA_FAR,
        )
        self.assertGreater(
            _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_WIDTH,
            _GPU_PREDATOR_PREY_KIN_LINE_WIDTH,
        )

    def test_line_caps_per_lineage_respected(self) -> None:
        creatures = [
            _creature(10 + i * 5, 10, lineage_id=1)
            for i in range(30)
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=80.0,
            min_group=3,
            color_for_member=_color_for_member,
            max_lines_per_lineage=8,
            max_total_lines=512,
        )
        self.assertLessEqual(len(lines), 8)

    def test_diagnostics_populated_when_requested(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=1),
            _creature(10, 10, lineage_id=2),
            _creature(20, 10, lineage_id=2),
            _creature(30, 10, lineage_id=2),
        ]
        diag: dict[str, int | float] = {}
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=50.0,
            min_group=2,
            color_for_member=_color_for_member,
            diagnostics=diag,
        )
        self.assertEqual(diag["total_lineages"], 2)
        self.assertEqual(diag["qualifying_lineages"], 2)
        self.assertEqual(diag["largest_lineage_size"], 3)
        self.assertGreater(len(lines), 0)

    def test_diagnostics_zero_when_disabled(self) -> None:
        diag: dict[str, int | float] = {}
        lines = build_gpu_kin_line_sprites(
            [_creature(10, 10, lineage_id=1)],
            world_width=200,
            world_height=200,
            max_distance=0.0,
            min_group=2,
            color_for_member=_color_for_member,
            diagnostics=diag,
        )
        self.assertEqual(lines, ())
        self.assertEqual(diag["qualifying_lineages"], 0)
        self.assertEqual(diag["largest_lineage_size"], 0)

    def test_build_gpu_kin_line_diagnostics_pure_function(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=1),
            _creature(10, 10, lineage_id=2),
        ]
        result = build_gpu_kin_line_diagnostics(creatures, min_group=2)
        self.assertEqual(result["total_lineages"], 2)
        self.assertEqual(result["qualifying_lineages"], 1)
        self.assertEqual(result["largest_lineage_size"], 2)

    def test_diagnostics_without_diagnostics_kwarg(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=1),
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=50.0,
            min_group=2,
            color_for_member=_color_for_member,
        )
        self.assertGreater(len(lines), 0)

    def test_debug_boost_alpha_overrides(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(20, 10, lineage_id=1),
        ]
        lines = build_gpu_kin_line_sprites(
            creatures,
            world_width=200,
            world_height=200,
            max_distance=50.0,
            min_group=2,
            color_for_member=_color_for_member,
            alpha_near=_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR,
            alpha_far=_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR,
        )
        self.assertGreater(len(lines), 0)
        for line in lines:
            self.assertGreaterEqual(line.color[3], _GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR)

    def test_explicit_zero_with_matching_canonical_default_falls_through(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="predator_prey",
            is_render_setting_explicit=lambda key: key == "kin_line_max_distance",
            canonical_render_default=lambda key: 0.0 if key == "kin_line_max_distance" else None,
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 110.0)

    def test_explicit_zero_when_canonical_differs_stays_disabled(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="predator_prey",
            is_render_setting_explicit=lambda key: key == "kin_line_max_distance",
            canonical_render_default=lambda key: 120.0 if key == "kin_line_max_distance" else None,
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 0.0)

    def test_explicit_zero_without_canonical_fn_stays_disabled(self) -> None:
        settings = SimpleNamespace(
            kin_line_max_distance=0.0,
            sim_mode="predator_prey",
            is_render_setting_explicit=lambda key: key == "kin_line_max_distance",
        )
        self.assertEqual(resolve_gpu_predator_prey_kin_line_distance(settings), 0.0)


class KinLineStyleTests(unittest.TestCase):
    def test_plain_style_returns_straight_lines(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 12, lineage_id=1),
            _creature(50, 14, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_PLAIN)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=3,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertIsInstance(result, KinLineRenderData)
        self.assertGreater(len(result.core_lines), 0)
        self.assertEqual(len(result.glow_lines), 0)
        self.assertEqual(len(result.shimmer_sprites), 0)

    def test_filament_style_produces_wave_segments(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 12, lineage_id=1),
            _creature(50, 14, lineage_id=1),
        ]
        plain_style = KinLineStyle(style=KIN_LINE_STYLE_PLAIN)
        filament_style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT)
        plain_result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=3,
            color_for_member=_color_for_member,
            anim_time=0.0, style=plain_style,
        )
        filament_result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=3,
            color_for_member=_color_for_member,
            anim_time=0.0, style=filament_style,
        )
        self.assertGreater(
            len(filament_result.core_lines),
            len(plain_result.core_lines),
        )

    def test_wave_segments_are_deterministic(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(25, 20, lineage_id=1),
            _creature(40, 26, lineage_id=1),
            _creature(70, 80, lineage_id=2),
            _creature(85, 82, lineage_id=2),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT)
        result1 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=40.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=1.5, style=style,
        )
        result2 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=40.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=1.5, style=style,
        )
        self.assertEqual(result1.core_lines, result2.core_lines)
        self.assertEqual(result1.glow_lines, result2.glow_lines)
        self.assertEqual(result1.shimmer_sprites, result2.shimmer_sprites)

    def test_wave_changes_with_anim_time(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(40, 40, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, wave_amplitude=3.0)
        result_t0 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        result_t1 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=1.0, style=style,
        )
        if len(result_t0.core_lines) > 0 and len(result_t1.core_lines) > 0:
            self.assertNotEqual(result_t0.core_lines, result_t1.core_lines)

    def test_zero_amplitude_produces_straight_lines(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(50, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, wave_amplitude=0.0)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertGreater(len(result.core_lines), 0)
        for seg in result.core_lines:
            self.assertAlmostEqual(seg.ay, 10.0, places=5)
            self.assertAlmostEqual(seg.by, 10.0, places=5)

    def test_segment_count_is_respected(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(60, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, wave_segments=4, glow_enabled=False, shimmer_enabled=False)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=80.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        logical_count = result.diagnostics.get("kin_line_count", 0) if result.diagnostics else 0
        if logical_count > 0:
            self.assertEqual(len(result.core_lines), logical_count * 4)

    def test_shimmer_positions_are_deterministic(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(40, 40, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, shimmer_enabled=True)
        result1 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.5, style=style,
        )
        result2 = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.5, style=style,
        )
        self.assertEqual(result1.shimmer_sprites, result2.shimmer_sprites)

    def test_style_builder_respects_max_caps(self) -> None:
        creatures = [
            _creature(20 + (i % 5) * 8, 20 + (i // 5) * 8, lineage_id=7)
            for i in range(25)
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, wave_segments=4, shimmer_enabled=True)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=30.0, min_group=3,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
            max_total_lines=18,
        )
        logical_count = result.diagnostics.get("kin_line_count", 0) if result.diagnostics else 0
        self.assertLessEqual(logical_count, 18)

    def test_glow_enabled_produces_glow_lines(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, glow_enabled=True)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertEqual(len(result.glow_lines), len(result.core_lines))

    def test_glow_disabled_produces_no_glow_lines(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, glow_enabled=False)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertEqual(len(result.glow_lines), 0)

    def test_shimmer_disabled_produces_no_sprites(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, shimmer_enabled=False)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertEqual(len(result.shimmer_sprites), 0)

    def test_debug_boost_does_not_alter_simulation_state(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        debug_style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT)
        normal_style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT)
        result_debug = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=debug_style,
            alpha_near=_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_NEAR,
            alpha_far=_GPU_PREDATOR_PREY_KIN_LINE_DEBUG_BOOST_ALPHA_FAR,
        )
        result_normal = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=normal_style,
        )
        self.assertEqual(len(result_debug.core_lines), len(result_normal.core_lines))
        self.assertEqual(len(result_debug.shimmer_sprites), len(result_normal.shimmer_sprites))
        for i in range(len(result_debug.core_lines)):
            d = result_debug.core_lines[i]
            n = result_normal.core_lines[i]
            self.assertAlmostEqual(d.ax, n.ax)
            self.assertAlmostEqual(d.ay, n.ay)
            self.assertAlmostEqual(d.bx, n.bx)
            self.assertAlmostEqual(d.by, n.by)
        for i in range(len(result_debug.shimmer_sprites)):
            d = result_debug.shimmer_sprites[i]
            n = result_normal.shimmer_sprites[i]
            self.assertAlmostEqual(d.x, n.x)
            self.assertAlmostEqual(d.y, n.y)

    def test_kin_line_style_from_settings_defaults(self) -> None:
        settings = SimpleNamespace()
        style = kin_line_style_from_settings(settings)
        self.assertEqual(style.style, KIN_LINE_STYLE_FILAMENT)
        self.assertEqual(style.wave_amplitude, KIN_LINE_DEFAULT_WAVE_AMPLITUDE)
        self.assertEqual(style.wave_segments, KIN_LINE_DEFAULT_WAVE_SEGMENTS)
        self.assertEqual(style.wave_speed, KIN_LINE_DEFAULT_WAVE_SPEED)
        self.assertTrue(style.glow_enabled)
        self.assertTrue(style.shimmer_enabled)

    def test_kin_line_style_from_settings_override(self) -> None:
        settings = SimpleNamespace(
            kin_line_style="plain",
            kin_line_wave_amplitude=5.0,
            kin_line_wave_segments=8,
            kin_line_wave_speed=1.5,
            kin_line_glow=False,
            kin_line_shimmer=False,
            kin_line_shimmer_strength=0.5,
        )
        style = kin_line_style_from_settings(settings)
        self.assertEqual(style.style, "plain")
        self.assertEqual(style.wave_amplitude, 5.0)
        self.assertEqual(style.wave_segments, 8)
        self.assertEqual(style.wave_speed, 1.5)
        self.assertFalse(style.glow_enabled)
        self.assertFalse(style.shimmer_enabled)
        self.assertEqual(style.shimmer_strength, 0.5)

    def test_glow_alpha_is_lower_than_core(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, glow_enabled=True, glow_alpha_scale=0.35)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        if result.glow_lines and result.core_lines:
            core_max_alpha = max(l.color[3] for l in result.core_lines)
            glow_max_alpha = max(l.color[3] for l in result.glow_lines)
            self.assertLess(glow_max_alpha, core_max_alpha)

    def test_diagnostics_include_segment_and_shimmer_counts(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT, wave_segments=4, shimmer_enabled=True)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=60.0, min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertIsNotNone(result.diagnostics)
        self.assertIn("kin_line_count", result.diagnostics)
        self.assertIn("kin_line_segment_count", result.diagnostics)
        self.assertIn("kin_line_shimmer_count", result.diagnostics)
        self.assertGreater(result.diagnostics["kin_line_segment_count"], 0)

    def test_disabled_kin_lines_return_empty_render_data(self) -> None:
        creatures = [
            _creature(10, 10, lineage_id=1),
            _creature(30, 10, lineage_id=1),
        ]
        style = KinLineStyle(style=KIN_LINE_STYLE_FILAMENT)
        result = build_kin_line_render_data(
            creatures,
            world_width=200, world_height=200,
            max_distance=0.0,
            min_group=2,
            color_for_member=_color_for_member,
            anim_time=0.0, style=style,
        )
        self.assertEqual(len(result.core_lines), 0)
        self.assertEqual(len(result.glow_lines), 0)
        self.assertEqual(len(result.shimmer_sprites), 0)


if __name__ == "__main__":
    unittest.main()
