"""Tests for PresentationLayout — reserved dashboard gutters for Inspect mode."""

import math
import pytest

from primordial.rendering.presentation_layout import (
    PresentationLayout,
    compute_layout,
    compute_inspect_panel_placement,
    compute_graph_strip_rect,
    _MIN_VIEWPORT_WIDTH,
    _MIN_VIEWPORT_HEIGHT,
    _MIN_RIGHT_GUTTER_WIDTH,
    _MIN_BOTTOM_GUTTER_HEIGHT,
)


# ── Layout computation ───────────────────────────────────────────────────

class TestComputeLayoutNormal:
    """Normal mode (inspect not active) should produce a fullscreen layout."""

    def test_normal_produces_fullscreen_viewport(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        assert layout.play_viewport_rect == (0, 0, 1920, 1080)
        assert layout.is_gutter_layout is False
        assert layout.right_gutter_rect == (0, 0, 0, 0)
        assert layout.bottom_gutter_rect == (0, 0, 0, 0)

    def test_normal_scale_is_1_when_world_matches_screen(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        assert layout.scale == pytest.approx(1.0)

    def test_normal_scale_preserves_aspect_ratio(self):
        layout = compute_layout(1280, 720, 1920, 1080, inspect_active=False)
        scale = min(1280 / 1920, 720 / 1080)
        assert layout.scale == pytest.approx(scale)

    def test_normal_offset_centers_letterboxed(self):
        layout = compute_layout(1920, 1080, 960, 540, inspect_active=False)
        # 960*2 = 1920 width fits, 540*2 = 1080 height fits
        # scale = min(1920/960, 1080/540) = min(2, 2) = 2
        assert layout.scale == pytest.approx(2.0)
        assert layout.offset_x == pytest.approx(0.0)
        assert layout.offset_y == pytest.approx(0.0)

    def test_normal_offset_centers_pillarboxed(self):
        layout = compute_layout(1920, 1080, 800, 1080, inspect_active=False)
        # scale = min(1920/800, 1080/1080) = min(2.4, 1.0) = 1.0
        assert layout.scale == pytest.approx(1.0)
        expected_offset_x = (1920 - 800) / 2.0
        assert layout.offset_x == pytest.approx(expected_offset_x)
        assert layout.offset_y == pytest.approx(0.0)


class TestComputeLayoutInspect:
    """Inspect gutter layout basics."""

    def test_inspect_active_produces_gutter_layout(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.is_gutter_layout is True
        assert layout.right_gutter_rect[2] > 0  # has width
        assert layout.bottom_gutter_rect[3] > 0  # has height

    def test_inspect_play_viewport_is_smaller_than_screen(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        vx, vy, vw, vh = layout.play_viewport_rect
        assert vw < 1920 or vh < 1080  # at least one gutter removed space

    def test_inspect_right_gutter_docks_to_right(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        rx, ry, rw, rh = layout.right_gutter_rect
        assert rx + rw == 1920  # right edge aligns with screen right

    def test_inspect_bottom_gutter_docks_to_bottom(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        bx, by, bw, bh = layout.bottom_gutter_rect
        assert by + bh == 1080  # bottom edge aligns with screen bottom

    def test_inspect_right_gutter_minimum_width(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.right_gutter_rect[2] >= _MIN_RIGHT_GUTTER_WIDTH

    def test_inspect_bottom_gutter_minimum_height(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.bottom_gutter_rect[3] >= _MIN_BOTTOM_GUTTER_HEIGHT

    def test_inspect_play_viewport_does_not_overlap_right_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        vx, vy, vw, vh = layout.play_viewport_rect
        rx, ry, rw, rh = layout.right_gutter_rect
        # Play viewport right edge should not extend into right gutter
        if rw > 0:
            assert vx + vw <= rx + 1  # +1 for rounding

    def test_inspect_play_viewport_does_not_overlap_bottom_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        vx, vy, vw, vh = layout.play_viewport_rect
        bx, by, bw, bh = layout.bottom_gutter_rect
        if bh > 0:
            assert vy + vh <= by + 1

    def test_inspect_hud_rect_inside_bottom_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        bx, by, bw, bh = layout.bottom_gutter_rect
        hx, hy, hw, hh = layout.hud_rect
        assert hx >= bx
        assert hy >= by
        assert hx + hw <= bx + bw
        assert hy + hh <= by + bh

    def test_inspect_graph_rect_inside_bottom_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        bx, by, bw, bh = layout.bottom_gutter_rect
        gx, gy, gw, gh = layout.graph_rect
        assert gx >= bx
        assert gy >= by
        assert gx + gw <= bx + bw + 1
        assert gy + gh <= by + bh + 1

    def test_inspect_hud_does_not_overlap_graph(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        hx, hy, hw, hh = layout.hud_rect
        gx, gy, gw, gh = layout.graph_rect
        if hw > 0 and gw > 0:
            assert hx + hw <= gx


class TestComputeLayoutSmallWindow:
    """Graceful degradation on small windows."""

    def test_very_small_window_falls_back_to_normal(self):
        """Screen too small for gutters should fall back to normal layout."""
        layout = compute_layout(400, 300, 400, 300, inspect_active=True)
        # May or may not have gutters depending on thresholds
        vx, vy, vw, vh = layout.play_viewport_rect
        # Play viewport should always be at least MIN_VIEWPORT size
        assert vw >= _MIN_VIEWPORT_WIDTH or not layout.is_gutter_layout
        assert vh >= _MIN_VIEWPORT_HEIGHT or not layout.is_gutter_layout

    def test_1366x768_has_gutters(self):
        layout = compute_layout(1366, 768, 1366, 768, inspect_active=True)
        assert layout.is_gutter_layout is True
        assert layout.right_gutter_rect[2] > 0

    def test_1280x720_has_gutters(self):
        layout = compute_layout(1280, 720, 1280, 720, inspect_active=True)
        assert layout.is_gutter_layout is True

    def test_2560x1080_ultrawide_has_gutters(self):
        layout = compute_layout(2560, 1080, 2560, 1080, inspect_active=True)
        assert layout.is_gutter_layout is True
        assert layout.right_gutter_rect[2] > 0

    def test_right_gutter_max_width_cap(self):
        layout = compute_layout(3840, 2160, 3840, 2160, inspect_active=True)
        assert layout.right_gutter_rect[2] <= 400  # _MAX_RIGHT_GUTTER_WIDTH


class TestCoordinateMapping:
    """world_to_screen / screen_to_world round-tripping."""

    def test_round_trip_normal(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        wx, wy = 500.0, 300.0
        sx, sy = layout.world_to_screen(wx, wy)
        wx2, wy2 = layout.screen_to_world(sx, sy)
        assert wx2 == pytest.approx(wx, abs=0.5)
        assert wy2 == pytest.approx(wy, abs=0.5)

    def test_round_trip_inspect(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        wx, wy = 500.0, 300.0
        sx, sy = layout.world_to_screen(wx, wy)
        # Should land in the play viewport
        assert layout.contains_play_viewport(sx, sy)
        wx2, wy2 = layout.screen_to_world(sx, sy)
        assert wx2 == pytest.approx(wx, abs=1.0)
        assert wy2 == pytest.approx(wy, abs=1.0)

    def test_round_trip_different_aspect(self):
        layout = compute_layout(1280, 720, 1920, 1080, inspect_active=True)
        wx, wy = 960.0, 540.0
        sx, sy = layout.world_to_screen(wx, wy)
        wx2, wy2 = layout.screen_to_world(sx, sy)
        assert wx2 == pytest.approx(wx, abs=1.0)
        assert wy2 == pytest.approx(wy, abs=1.0)

    def test_gutter_click_not_in_play_viewport(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        rx, ry, rw, rh = layout.right_gutter_rect
        # Click in the middle of the right gutter
        gutter_sx = rx + rw / 2
        gutter_sy = ry + rh / 2
        assert not layout.contains_play_viewport(gutter_sx, gutter_sy)
        assert layout.contains_gutter(gutter_sx, gutter_sy)

    def test_bottom_gutter_click_not_in_play_viewport(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        bx, by, bw, bh = layout.bottom_gutter_rect
        gutter_sx = bx + bw / 2
        gutter_sy = by + bh / 2
        assert not layout.contains_play_viewport(gutter_sx, gutter_sy)
        assert layout.contains_gutter(gutter_sx, gutter_sy)

    def test_play_viewport_origin_maps_correctly(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        # Origin of world should map into the play viewport
        sx, sy = layout.world_to_screen(0.0, 0.0)
        assert layout.contains_play_viewport(sx, sy)

    def test_scale_is_consistent(self):
        """World-to-screen distance should be consistent with scale factor."""
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        p1 = layout.world_to_screen(100.0, 100.0)
        p2 = layout.world_to_screen(200.0, 200.0)
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        assert dx == pytest.approx(100.0 * layout.scale, abs=0.5)
        assert dy == pytest.approx(100.0 * layout.scale, abs=0.5)


class TestModeTransitions:
    """Layout should transition cleanly between normal and inspect."""

    def test_toggle_inspect_changes_layout(self):
        normal = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        inspect = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert normal.is_gutter_layout is False
        assert inspect.is_gutter_layout is True

    def test_toggle_inspect_does_not_change_screen_size(self):
        normal = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        inspect = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert normal.screen_width == inspect.screen_width
        assert normal.screen_height == inspect.screen_height

    def test_enter_exit_inspect_no_stale_state(self):
        """Repeated enter/exit should produce identical layouts."""
        layout1 = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        layout2 = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        layout3 = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout1 == layout3
        assert layout2.is_gutter_layout is False

    def test_resize_invalidates_layout(self):
        """Different screen size should produce different layout."""
        layout_a = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        layout_b = compute_layout(1280, 720, 1280, 720, inspect_active=True)
        assert layout_a.play_viewport_rect != layout_b.play_viewport_rect
        assert layout_a.scale != layout_b.scale

    def test_fullscreen_toggle_while_inspect(self):
        """Toggle fullscreen while inspect is active recalculates."""
        layout_w = compute_layout(1280, 720, 1280, 720, inspect_active=True)
        layout_f = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout_w.play_viewport_rect != layout_f.play_viewport_rect
        assert layout_w.right_gutter_rect != layout_f.right_gutter_rect


class TestInspectPanelPlacement:
    def test_basic_placement(self):
        x, y, w, h = compute_inspect_panel_placement(400, 800, 350, 700)
        assert x == 8  # margin
        assert y == 8
        assert w == 350
        assert h == min(700, 800 - 2 * 8)

    def test_panel_clipped_to_gutter(self):
        x, y, w, h = compute_inspect_panel_placement(300, 600, 500, 800)
        assert w <= 300 - 2 * 8
        assert h <= 600 - 2 * 8


class TestGraphStripRect:
    def test_basic_rect(self):
        gx, gy, gw, gh = compute_graph_strip_rect((100, 900, 800, 160))
        assert gw > 0
        assert gh > 0
        assert gx >= 100
        assert gy >= 900

    def test_empty_graph_area(self):
        gx, gy, gw, gh = compute_graph_strip_rect((0, 0, 0, 0))
        assert (gx, gy, gw, gh) == (0, 0, 0, 0)


class TestCoordinateMappingWithLayout:
    """window_to_world_with_layout and layout-aware coordinate mapping."""

    def test_fallback_when_layout_is_none(self):
        from primordial.display.coordinates import (
            window_to_world,
            window_to_world_with_layout,
        )
        from unittest.mock import MagicMock

        sim = MagicMock()
        sim.width = 1920
        sim.height = 1080
        result = window_to_world_with_layout(960.0, 540.0, sim, None)
        expected = window_to_world(960.0, 540.0, sim)
        assert result[0] == pytest.approx(expected[0])
        assert result[1] == pytest.approx(expected[1])

    def test_layout_normal_mode_uses_proportional(self):
        from primordial.display.coordinates import (
            window_to_world,
            window_to_world_with_layout,
        )
        from unittest.mock import MagicMock

        sim = MagicMock()
        sim.width = 1920
        sim.height = 1080
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        result = window_to_world_with_layout(960.0, 540.0, sim, layout)
        expected = window_to_world(960.0, 540.0, sim)
        assert result[0] == pytest.approx(expected[0])
        assert result[1] == pytest.approx(expected[1])

    def test_layout_gutter_mode_uses_screen_to_world(self):
        from primordial.display.coordinates import window_to_world_with_layout
        from unittest.mock import MagicMock

        sim = MagicMock()
        sim.width = 1920
        sim.height = 1080
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        result = window_to_world_with_layout(480.0, 270.0, sim, layout)
        wx, wy = layout.screen_to_world(480.0, 270.0)
        assert result[0] == pytest.approx(wx)
        assert result[1] == pytest.approx(wy)


class TestLayoutProperties:
    """Layout property caching and invalidation."""

    def test_layout_caches_on_same_parameters(self):
        layout1 = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        layout2 = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout1 == layout2

    def test_layout_changes_with_inspect_state(self):
        layout_normal = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        layout_inspect = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout_normal.is_gutter_layout is False
        assert layout_inspect.is_gutter_layout is True

    def test_layout_changes_with_screen_size(self):
        layout_a = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        layout_b = compute_layout(1280, 720, 1280, 720, inspect_active=True)
        assert layout_a.play_viewport_rect != layout_b.play_viewport_rect
        assert layout_a.scale != layout_b.scale

    def test_very_small_window_graceful_degradation(self):
        layout = compute_layout(400, 300, 400, 300, inspect_active=True)
        if layout.is_gutter_layout:
            vx, vy, vw, vh = layout.play_viewport_rect
            assert vw >= 200
            assert vh >= 150
        else:
            assert layout.play_viewport_rect == (0, 0, 400, 300)

    def test_scale_preserves_aspect_ratio_in_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        vx, vy, vw, vh = layout.play_viewport_rect
        scale_x = vw / 1920
        scale_y = vh / 1080
        assert layout.scale == pytest.approx(min(scale_x, scale_y), abs=0.01)


class TestRefinedProportions:
    """Tests for the refined gutter proportions."""

    def test_right_gutter_smaller_than_before(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.right_gutter_rect[2] <= 460

    def test_right_gutter_at_23_percent(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        expected = min(400, max(200, int(1920 * 0.23)))
        assert layout.right_gutter_rect[2] == expected

    def test_right_gutter_uses_max_cap(self):
        layout = compute_layout(3840, 2160, 3840, 2160, inspect_active=True)
        assert layout.right_gutter_rect[2] <= 400

    def test_inspect_panel_uses_most_of_right_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        rg_w = layout.right_gutter_rect[2]
        from primordial.rendering.inspect_mode import _inspect_panel_width
        panel_w = _inspect_panel_width(rg_w)
        fill_ratio = panel_w / rg_w if rg_w > 0 else 0
        assert fill_ratio >= 0.90

    def test_bottom_gutter_height_reduced(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.bottom_gutter_rect[3] <= 200

    def test_bottom_gutter_height_capped_at_150(self):
        layout = compute_layout(2560, 1440, 2560, 1440, inspect_active=True)
        assert layout.bottom_gutter_rect[3] <= 150

    def test_bottom_gutter_minimum_height(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        assert layout.bottom_gutter_rect[3] >= 88

    def test_graph_rect_uses_available_height(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        gx, gy, gw, gh = layout.graph_rect
        _, _, bw, bh = layout.bottom_gutter_rect
        assert gh >= bh * 0.88

    def test_hud_rect_and_graph_rect_do_not_overlap(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        hx, hy, hw, hh = layout.hud_rect
        gx, gy, gw, gh = layout.graph_rect
        if hw > 0 and gw > 0:
            assert hx + hw <= gx

    def test_hud_rect_and_graph_rect_no_overlap_at_1366x768(self):
        layout = compute_layout(1366, 768, 1366, 768, inspect_active=True)
        hx, hy, hw, hh = layout.hud_rect
        gx, gy, gw, gh = layout.graph_rect
        if hw > 0 and gw > 0:
            assert hx + hw <= gx


class TestCornerGutterRect:
    """Tests for the explicitly modeled bottom-right corner gutter."""

    def test_corner_rect_exists_when_both_gutters_present(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        if layout.right_gutter_rect[2] > 0 and layout.bottom_gutter_rect[3] > 0:
            cx, cy, cw, ch = layout.corner_gutter_rect
            assert cw > 0
            assert ch > 0

    def test_corner_rect_position(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        cx, cy, cw, ch = layout.corner_gutter_rect
        rw = layout.right_gutter_rect[2]
        bh = layout.bottom_gutter_rect[3]
        if rw > 0 and bh > 0:
            assert cx + cw == 1920
            assert cy + ch == 1080
            assert cw == rw
            assert ch == bh

    def test_corner_rect_zero_when_no_right_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=False)
        cx, cy, cw, ch = layout.corner_gutter_rect
        assert cw == 0
        assert ch == 0

    def test_corner_click_detected_as_gutter(self):
        layout = compute_layout(1920, 1080, 1920, 1080, inspect_active=True)
        cx, cy, cw, ch = layout.corner_gutter_rect
        if cw > 0 and ch > 0:
            assert layout.contains_gutter(cx + cw / 2, cy + ch / 2)
            assert not layout.contains_play_viewport(cx + cw / 2, cy + ch / 2)


class TestViewportMinimumSize:
    """Play viewport remains at least minimum size across common resolutions."""

    @pytest.mark.parametrize("sw,sh", [(1280, 720), (1920, 1080), (1366, 768), (2560, 1080)])
    def test_viewport_at_least_minimum(self, sw, sh):
        layout = compute_layout(sw, sh, sw, sh, inspect_active=True)
        if layout.is_gutter_layout:
            vx, vy, vw, vh = layout.play_viewport_rect
            assert vw >= _MIN_VIEWPORT_WIDTH
            assert vh >= _MIN_VIEWPORT_HEIGHT

    def test_small_degraded_window_valid_layout(self):
        layout = compute_layout(600, 400, 600, 400, inspect_active=True)
        if layout.is_gutter_layout:
            vx, vy, vw, vh = layout.play_viewport_rect
            assert vw > 0
            assert vh > 0


class TestRoundTripAtCommonResolutions:
    """Coordinate round-trips at common resolutions."""

    @pytest.mark.parametrize("sw,sh", [(1280, 720), (1920, 1080), (1366, 768), (2560, 1080)])
    def test_round_trip_inspect(self, sw, sh):
        layout = compute_layout(sw, sh, sw, sh, inspect_active=True)
        wx, wy = 100.0, 100.0
        sx, sy = layout.world_to_screen(wx, wy)
        wx2, wy2 = layout.screen_to_world(sx, sy)
        assert wx2 == pytest.approx(wx, abs=1.0)
        assert wy2 == pytest.approx(wy, abs=1.0)

    @pytest.mark.parametrize("sw,sh", [(1280, 720), (1920, 1080)])
    def test_gutter_click_no_selection(self, sw, sh):
        layout = compute_layout(sw, sh, sw, sh, inspect_active=True)
        rx, ry, rw, rh = layout.right_gutter_rect
        if rw > 0:
            assert not layout.contains_play_viewport(rx + rw // 2, ry + rh // 2)
        bx, by, bw, bh = layout.bottom_gutter_rect
        if bh > 0:
            assert not layout.contains_play_viewport(bx + bw // 2, by + bh // 2)


class TestGraphStripRefined:
    """Graph strip uses more of the available rect."""

    def test_graph_strip_uses_available_space(self):
        gx, gy, gw, gh = compute_graph_strip_rect((100, 900, 800, 120))
        assert gw >= 800 - 2 * 6 - 4
        assert gh >= 120 - 2 * 6 - 4

    def test_graph_strip_respects_margin(self):
        gx, gy, gw, gh = compute_graph_strip_rect((100, 900, 800, 120))
        assert gx >= 100 + 6
        assert gy >= 900 + 6