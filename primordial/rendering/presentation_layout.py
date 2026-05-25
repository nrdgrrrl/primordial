"""Presentation layout — reserved dashboard gutters for Inspect mode.

When full Inspect mode is active, the screen is divided into:
  - A central play viewport (scaled, aspect-ratio-preserved)
  - A right gutter for the inspect detail panel
  - A bottom gutter for graphs and HUD

The layout is pure geometry — no rendering, no pygame surfaces.
All sizes are in screen pixels.

Outside Inspect mode the layout collapses to a single fullscreen play viewport
with no gutters, preserving existing behaviour exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ── Minimum sizes for graceful degradation ─────────────────────────────

_MIN_VIEWPORT_WIDTH = 320
_MIN_VIEWPORT_HEIGHT = 240
_MIN_RIGHT_GUTTER_WIDTH = 200
_MIN_BOTTOM_GUTTER_HEIGHT = 92
_MAX_RIGHT_GUTTER_WIDTH = 460
_MAX_BOTTOM_GUTTER_HEIGHT_RATIO = 0.25
_GUTTER_PADDING = 4


@dataclass(frozen=True)
class PresentationLayout:
    """Immutable snapshot of the current presentation geometry.

    All rectangles are in **screen** pixel coordinates (origin top-left).

    ``is_gutter_layout`` is True only when Inspect analysis mode is active and
    the screen is large enough to accommodate at least the minimum right
    gutter alongside a viable play viewport.
    """

    screen_width: int
    screen_height: int

    # Play viewport — the subset of the screen where the simulation is drawn.
    # World coordinates are scaled into this rectangle preserving aspect ratio.
    play_viewport_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # Right gutter — reserved for the inspect detail panel.
    right_gutter_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # Bottom gutter — reserved for graphs and HUD summary.
    bottom_gutter_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # HUD area inside the bottom gutter (left portion).
    hud_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # Graph area inside the bottom gutter (center/right portion).
    graph_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # Action bar area — sits above the bottom gutter or at screen bottom.
    action_bar_rect: tuple[int, int, int, int]  # (x, y, w, h)

    # Scale factor: world units → screen pixels inside the play viewport.
    scale: float

    # Offset to centre the scaled world within the play viewport.
    # These are additive: world_to_screen = (wx * scale + offset_x, wy * scale + offset_y)
    offset_x: float
    offset_y: float

    # True when we are in the reserved-gutter analysis layout.
    is_gutter_layout: bool

    # ── Coordinate transforms ───────────────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """Convert world coordinates to screen pixel coordinates."""
        vx, vy, vw, vh = self.play_viewport_rect
        sx = vx + (wx * self.scale) + self.offset_x
        sy = vy + (wy * self.scale) + self.offset_y
        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Convert screen pixel coordinates to world coordinates.

        Returns coordinates even if the click is outside the play viewport;
        callers should use ``contains_play_viewport`` to reject gutter clicks.
        """
        vx, vy, vw, vh = self.play_viewport_rect
        px = sx - vx - self.offset_x
        py = sy - vy - self.offset_y
        wx = px / self.scale if self.scale > 0 else 0.0
        wy = py / self.scale if self.scale > 0 else 0.0
        return wx, wy

    def contains_play_viewport(self, sx: float, sy: float) -> bool:
        """Return True if (sx, sy) falls inside the play viewport rectangle."""
        vx, vy, vw, vh = self.play_viewport_rect
        return vx <= sx < vx + vw and vy <= sy < vy + vh

    def contains_gutter(self, sx: float, sy: float) -> bool:
        """Return True if (sx, sy) falls inside any gutter (right or bottom)."""
        for rect in (self.right_gutter_rect, self.bottom_gutter_rect):
            rx, ry, rw, rh = rect
            if rx <= sx < rx + rw and ry <= sy < ry + rh:
                return True
        return False


def compute_layout(
    screen_width: int,
    screen_height: int,
    world_width: int,
    world_height: int,
    *,
    inspect_active: bool,
) -> PresentationLayout:
    """Compute the presentation layout for the current frame.

    Parameters
    ----------
    screen_width, screen_height:
        The full screen/window size in pixels.
    world_width, world_height:
        The simulation world size (unchanged by layout).
    inspect_active:
        True when Inspect mode is active and should show the gutter layout.

    Returns
    -------
    A ``PresentationLayout`` that is either:
    - a fullscreen play viewport (no gutters) when ``inspect_active`` is False,
      or when the screen is too small for gutters; or
    - a reserved-gutter layout with play viewport, right gutter, and bottom
      gutter when ``inspect_active`` is True and space permits.
    """
    sw = max(1, int(screen_width))
    sh = max(1, int(screen_height))
    ww = max(1, int(world_width))
    wh = max(1, int(world_height))

    # ── Normal (non-inspect) layout: fullscreen play viewport ───────────
    if not inspect_active:
        scale = min(sw / ww, sh / wh)
        offset_x = (sw - ww * scale) / 2.0
        offset_y = (sh - wh * scale) / 2.0
        return PresentationLayout(
            screen_width=sw,
            screen_height=sh,
            play_viewport_rect=(0, 0, sw, sh),
            right_gutter_rect=(0, 0, 0, 0),
            bottom_gutter_rect=(0, 0, 0, 0),
            hud_rect=(0, 0, 0, 0),
            graph_rect=(0, 0, 0, 0),
            action_bar_rect=(0, 0, 0, 0),
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            is_gutter_layout=False,
        )

    # ── Inspect gutter layout ───────────────────────────────────────────

    # Determine gutter sizes with graceful degradation.
    available_width = sw
    available_height = sh

    # Try right gutter first — if we can't fit it, fall back to no right gutter.
    right_gutter_w = min(_MAX_RIGHT_GUTTER_WIDTH, max(_MIN_RIGHT_GUTTER_WIDTH, int(sw * 0.28)))
    if available_width - right_gutter_w < _MIN_VIEWPORT_WIDTH:
        right_gutter_w = 0

    # Try bottom gutter — if we can't fit it, fall back to no bottom gutter.
    bottom_gutter_h = min(
        max(_MIN_BOTTOM_GUTTER_HEIGHT, int(sh * _MAX_BOTTOM_GUTTER_HEIGHT_RATIO)),
        _MAX_BOTTOM_GUTTER_HEIGHT_RATIO * sh,
    )
    bottom_gutter_h = int(bottom_gutter_h)
    if available_height - bottom_gutter_h < _MIN_VIEWPORT_HEIGHT:
        bottom_gutter_h = 0

    # If neither gutter fits, fall back to normal fullscreen.
    if right_gutter_w == 0 and bottom_gutter_h == 0:
        scale = min(sw / ww, sh / wh)
        offset_x = (sw - ww * scale) / 2.0
        offset_y = (sh - wh * scale) / 2.0
        return PresentationLayout(
            screen_width=sw,
            screen_height=sh,
            play_viewport_rect=(0, 0, sw, sh),
            right_gutter_rect=(0, 0, 0, 0),
            bottom_gutter_rect=(0, 0, 0, 0),
            hud_rect=(0, 0, 0, 0),
            graph_rect=(0, 0, 0, 0),
            action_bar_rect=(0, 0, 0, 0),
            scale=scale,
            offset_x=offset_x,
            offset_y=offset_y,
            is_gutter_layout=False,
        )

    # Compute play viewport rect.
    play_w = sw - right_gutter_w if right_gutter_w > 0 else sw
    play_h = sh - bottom_gutter_h if bottom_gutter_h > 0 else sh
    play_x = 0
    play_y = 0

    # Scale world into the play viewport preserving aspect ratio.
    scale_x = play_w / ww
    scale_y = play_h / wh
    scale = min(scale_x, scale_y)
    offset_x = (play_w - ww * scale) / 2.0
    offset_y = (play_h - wh * scale) / 2.0

    # Right gutter: docks to the right side, full height minus bottom gutter.
    if right_gutter_w > 0:
        rg_x = sw - right_gutter_w
        rg_y = 0
        rg_w = right_gutter_w
        rg_h = sh - bottom_gutter_h if bottom_gutter_h > 0 else sh
    else:
        rg_x = rg_y = 0
        rg_w = rg_h = 0
    right_gutter_rect = (rg_x, rg_y, rg_w, rg_h)

    # Bottom gutter: full width (or width minus right gutter), below play viewport.
    if bottom_gutter_h > 0:
        bg_x = 0
        bg_y = sh - bottom_gutter_h
        bg_w = sw - right_gutter_w if right_gutter_w > 0 else sw
        bg_h = bottom_gutter_h
    else:
        bg_x = bg_y = 0
        bg_w = bg_h = 0
    bottom_gutter_rect = (bg_x, bg_y, bg_w, bg_h)

    # HUD area inside bottom gutter — left portion.
    pad = _GUTTER_PADDING
    if bottom_gutter_h > 0:
        hud_w = max(220, min(int(bg_w * 0.38), bg_w - 300))
        hud_h = max(0, bg_h - 2 * pad)
        hud_rect = (bg_x + pad, bg_y + pad, hud_w, hud_h)
    else:
        hud_rect = (0, 0, 0, 0)

    # Graph area inside bottom gutter — center/right portion.
    if bottom_gutter_h > 0 and bg_w > 0:
        graph_x = hud_rect[0] + hud_rect[2] + pad
        graph_w = max(0, bg_w - (graph_x - bg_x) - pad)
        graph_h = max(0, bg_h - 2 * pad)
        graph_rect = (graph_x, bg_y + pad, graph_w, graph_h)
    else:
        graph_rect = (0, 0, 0, 0)

    # Action bar — sits at the bottom of the play viewport or above the bottom gutter.
    ab_w = max(340, min(int(sw * 0.60), sw - 40))
    ab_h = 0  # Action bar height is dynamic, position is all we need.
    ab_y = sh - bottom_gutter_h - pad if bottom_gutter_h > 0 else sh - 20
    ab_x = max(0, (sw - ab_w) // 2)
    action_bar_rect = (ab_x, ab_y, ab_w, ab_h)

    return PresentationLayout(
        screen_width=sw,
        screen_height=sh,
        play_viewport_rect=(play_x, play_y, play_w, play_h),
        right_gutter_rect=right_gutter_rect,
        bottom_gutter_rect=bottom_gutter_rect,
        hud_rect=hud_rect,
        graph_rect=graph_rect,
        action_bar_rect=action_bar_rect,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        is_gutter_layout=True,
    )


def compute_inspect_panel_placement(
    gutter_width: int,
    gutter_height: int,
    panel_width: int,
    panel_height: int,
    *,
    margin: int = 12,
) -> tuple[int, int, int, int]:
    """Place the inspect detail panel within the right gutter.

    Returns (x, y, width, height) anchored top-left within the gutter.
    """
    safe_w = max(1, min(panel_width, gutter_width - 2 * margin))
    safe_h = max(1, min(panel_height, gutter_height - 2 * margin))
    x = margin
    y = margin
    return (x, y, safe_w, safe_h)


def compute_graph_strip_rect(
    graph_rect: tuple[int, int, int, int],
    *,
    margin: int = 8,
) -> tuple[int, int, int, int]:
    """Compute the graph strip rect within the bottom gutter graph area.

    Returns (x, y, width, height) relative to screen coordinates.
    """
    gx, gy, gw, gh = graph_rect
    if gw <= 0 or gh <= 0:
        return (0, 0, 0, 0)
    strip_w = max(240, gw - 2 * margin)
    strip_h = max(92, min(148, gh - 2 * margin))
    strip_x = gx + (gw - strip_w) // 2
    strip_y = gy + (gh - strip_h) // 2
    return (strip_x, strip_y, strip_w, strip_h)