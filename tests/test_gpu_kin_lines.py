from __future__ import annotations

import unittest
from types import SimpleNamespace

from primordial.rendering.snapshot import (
    build_gpu_kin_line_sprites,
    resolve_gpu_predator_prey_kin_line_distance,
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


if __name__ == "__main__":
    unittest.main()
