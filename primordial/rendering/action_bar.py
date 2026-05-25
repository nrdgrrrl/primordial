"""Mouse-activated runtime action bar shown during normal playback."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.simulation import Simulation


VISIBLE_DURATION_SECONDS = 5.0
FADE_DURATION_SECONDS = 10.0
MAX_OPACITY = 0.80
MIN_MOUSE_MOVEMENT_PIXELS = 2

_BAR_MARGIN_BOTTOM = 20
_BAR_MIN_WIDTH = 340
_BAR_MAX_WIDTH_RATIO = 0.94
_BAR_PADDING_X = 18
_BAR_PADDING_Y = 12
_ROW_GAP = 8
_CHIP_GAP = 14
_ITEM_GAP = 8
_BADGE_PAD_X = 10
_BADGE_PAD_Y = 6
_PANEL_RADIUS = 14


@dataclass(frozen=True)
class ShortcutHint:
    """Single displayed shortcut/action pair."""

    key_label: str
    action_label: str


@dataclass(frozen=True)
class ActionBarContext:
    """Runtime state needed to filter the action bar."""

    runtime_mode: str
    sim_mode: str
    paused: bool
    inspect_enabled: bool
    settings_visible: bool
    help_visible: bool
    tutorial_visible: bool
    game_over_visible: bool

    @property
    def overlays_visible(self) -> bool:
        return self.settings_visible or self.help_visible or self.tutorial_visible


@dataclass(frozen=True)
class ActionBarLayout:
    """Resolved geometry for a drawn action bar."""

    panel_rect: pygame.Rect
    row_rects: tuple[pygame.Rect, ...]


_NORMAL_SHORTCUTS: tuple[ShortcutHint, ...] = (
    ShortcutHint("S", "Settings"),
    ShortcutHint("H", "Help"),
    ShortcutHint("U", "HUD"),
    ShortcutHint("Space", "Pause/Resume"),
    ShortcutHint("F", "Fullscreen"),
    ShortcutHint("R", "Reset"),
    ShortcutHint("I", "Inspect"),
    ShortcutHint("+/-", "Food rate"),
    ShortcutHint("Esc/Q", "Quit"),
)

_PREDATOR_PREY_EXTRA: tuple[ShortcutHint, ...] = (
    ShortcutHint("Hold P", "Highlight predators"),
)

_INSPECT_SHORTCUTS: tuple[ShortcutHint, ...] = (
    ShortcutHint("I", "Exit inspect"),
    ShortcutHint("M", "Pause/Slow"),
    ShortcutHint("N", "Normal follow"),
    ShortcutHint("D", "Details"),
    ShortcutHint("S", "Settings"),
    ShortcutHint("F", "Fullscreen"),
    ShortcutHint("Esc/Q", "Quit"),
)

_GAME_OVER_SHORTCUTS: tuple[ShortcutHint, ...] = (
    ShortcutHint("Space", "Skip countdown"),
    ShortcutHint("S", "Settings"),
    ShortcutHint("U", "HUD"),
    ShortcutHint("F", "Fullscreen"),
    ShortcutHint("Esc/Q", "Quit"),
)


class ActionBar:
    """Transient, informational bottom action bar."""

    def __init__(self) -> None:
        pygame.font.init()
        self.runtime_mode = "normal"
        self.last_mouse_motion_time: float | None = None
        self._font = pygame.font.Font(None, 22)
        self._badge_font = pygame.font.Font(None, 22)
        self._panel_surface_cache: pygame.Surface | None = None
        self._panel_surface_cache_key: tuple[object, ...] | None = None
        self._layout_cache: ActionBarLayout | None = None
        self._layout_cache_key: tuple[object, ...] | None = None
        self._item_surface_cache: dict[tuple[str, str], tuple[pygame.Surface, int]] = {}

    def set_runtime_mode(self, mode: str) -> None:
        """Store the high-level runtime mode for suppression decisions."""
        self.runtime_mode = mode

    def notify_mouse_motion(
        self,
        rel: tuple[int, int] | None = None,
        *,
        now: float | None = None,
    ) -> None:
        """Refresh the bar visibility when the user meaningfully moves the mouse."""
        if rel is not None:
            dx, dy = rel
            if max(abs(dx), abs(dy)) < MIN_MOUSE_MOVEMENT_PIXELS:
                return
        self.last_mouse_motion_time = time.monotonic() if now is None else now

    def build_context(
        self,
        simulation: "Simulation",
        *,
        inspect_enabled: bool,
        settings_visible: bool,
        help_visible: bool,
        tutorial_visible: bool,
    ) -> ActionBarContext:
        """Create a filter context from renderer/runtime state."""
        return ActionBarContext(
            runtime_mode=self.runtime_mode,
            sim_mode=simulation.settings.sim_mode,
            paused=simulation.paused,
            inspect_enabled=inspect_enabled,
            settings_visible=settings_visible,
            help_visible=help_visible,
            tutorial_visible=tutorial_visible,
            game_over_visible=simulation.predator_prey_game_over_active,
        )

    def command_items(self, context: ActionBarContext) -> tuple[ShortcutHint, ...]:
        """Return the shortcut set appropriate for the current runtime context."""
        if self.is_suppressed(context):
            return ()
        if context.game_over_visible and context.sim_mode == "predator_prey":
            return _GAME_OVER_SHORTCUTS
        if context.inspect_enabled:
            return _INSPECT_SHORTCUTS
        items = list(_NORMAL_SHORTCUTS)
        if context.sim_mode == "predator_prey":
            items.extend(_PREDATOR_PREY_EXTRA)
        return tuple(items)

    def is_suppressed(self, context: ActionBarContext) -> bool:
        """Return whether the bar must be hidden regardless of timer state."""
        return context.runtime_mode != "normal" or context.overlays_visible

    def opacity(self, context: ActionBarContext, *, now: float | None = None) -> float:
        """Return the current opacity in the 0..MAX_OPACITY range."""
        if self.is_suppressed(context) or not self.command_items(context):
            return 0.0
        if self.last_mouse_motion_time is None:
            return 0.0
        current = time.monotonic() if now is None else now
        elapsed = max(0.0, current - self.last_mouse_motion_time)
        if elapsed <= VISIBLE_DURATION_SECONDS:
            return MAX_OPACITY
        fade_elapsed = elapsed - VISIBLE_DURATION_SECONDS
        if fade_elapsed >= FADE_DURATION_SECONDS:
            return 0.0
        fade_fraction = 1.0 - (fade_elapsed / FADE_DURATION_SECONDS)
        return MAX_OPACITY * max(0.0, min(1.0, fade_fraction))

    def calculate_layout(
        self,
        screen_size: tuple[int, int],
        items: tuple[ShortcutHint, ...],
    ) -> ActionBarLayout:
        """Compute the panel and row geometry for the current command set."""
        cache_key = (
            screen_size,
            tuple((item.key_label, item.action_label) for item in items),
        )
        if cache_key == self._layout_cache_key and self._layout_cache is not None:
            return self._layout_cache
        screen_width, screen_height = screen_size
        max_width = max(_BAR_MIN_WIDTH, int(screen_width * _BAR_MAX_WIDTH_RATIO))
        available_width = max(_BAR_MIN_WIDTH, max_width - (_BAR_PADDING_X * 2))

        row_height = max(
            self._font.get_height(),
            self._badge_font.get_height(),
        ) + 14

        rows: list[list[tuple[ShortcutHint, int]]] = [[]]
        row_widths = [0]
        for item in items:
            item_width = self._item_width(item)
            current_width = row_widths[-1]
            if rows[-1]:
                projected = current_width + _CHIP_GAP + item_width
                if projected > available_width:
                    rows.append([])
                    row_widths.append(0)
                    current_width = 0
            rows[-1].append((item, item_width))
            row_widths[-1] = item_width if current_width == 0 else current_width + _CHIP_GAP + item_width

        content_width = max(row_widths) if row_widths else 0
        panel_width = min(
            max_width,
            max(_BAR_MIN_WIDTH, content_width + (_BAR_PADDING_X * 2)),
        )
        panel_height = (
            (_BAR_PADDING_Y * 2)
            + len(rows) * row_height
            + max(0, len(rows) - 1) * _ROW_GAP
        )
        panel_rect = pygame.Rect(0, 0, panel_width, panel_height)
        panel_rect.midbottom = (
            screen_width // 2,
            max(panel_height + 8, screen_height - _BAR_MARGIN_BOTTOM),
        )

        row_rects: list[pygame.Rect] = []
        y = panel_rect.y + _BAR_PADDING_Y
        for row_width in row_widths:
            row_rects.append(
                pygame.Rect(
                    panel_rect.x + max(_BAR_PADDING_X, (panel_rect.width - row_width) // 2),
                    y,
                    row_width,
                    row_height,
                )
            )
            y += row_height + _ROW_GAP

        layout = ActionBarLayout(panel_rect=panel_rect, row_rects=tuple(row_rects))
        self._layout_cache_key = cache_key
        self._layout_cache = layout
        return layout

    def draw(
        self,
        surface: pygame.Surface,
        context: ActionBarContext,
        *,
        now: float | None = None,
    ) -> None:
        """Draw the action bar if it is currently visible."""
        alpha = self.opacity(context, now=now)
        items = self.command_items(context)
        if alpha <= 0.0 or not items:
            return

        layout = self.calculate_layout(surface.get_size(), items)
        panel_surface = self._get_panel_surface(layout, items)
        panel_surface.set_alpha(int(round(255 * alpha)))
        surface.blit(panel_surface, layout.panel_rect.topleft)

    def overlay_state(
        self,
        screen_size: tuple[int, int],
        context: ActionBarContext,
        *,
        now: float | None = None,
    ) -> tuple[pygame.Surface | None, pygame.Rect | None, float]:
        alpha = self.opacity(context, now=now)
        items = self.command_items(context)
        if alpha <= 0.0 or not items:
            return None, None, 0.0
        layout = self.calculate_layout(screen_size, items)
        panel_surface = self._get_panel_surface(layout, items)
        return panel_surface, layout.panel_rect, alpha

    def _get_panel_surface(
        self,
        layout: ActionBarLayout,
        items: tuple[ShortcutHint, ...],
    ) -> pygame.Surface:
        cache_key = (
            layout.panel_rect.size,
            tuple((item.key_label, item.action_label) for item in items),
        )
        if cache_key != self._panel_surface_cache_key or self._panel_surface_cache is None:
            panel_surface = pygame.Surface(layout.panel_rect.size, pygame.SRCALPHA)
            self._draw_panel(panel_surface, layout, items)
            self._panel_surface_cache = panel_surface
            self._panel_surface_cache_key = cache_key
        return self._panel_surface_cache

    def _draw_panel(
        self,
        surface: pygame.Surface,
        layout: ActionBarLayout,
        items: tuple[ShortcutHint, ...],
    ) -> None:
        pygame.draw.rect(
            surface,
            (5, 15, 24, 235),
            surface.get_rect(),
            border_radius=_PANEL_RADIUS,
        )
        pygame.draw.rect(
            surface,
            (56, 126, 142, 120),
            surface.get_rect(),
            width=1,
            border_radius=_PANEL_RADIUS,
        )
        pygame.draw.line(
            surface,
            (90, 220, 238, 160),
            (16, 1),
            (max(16, surface.get_width() - 16), 1),
            2,
        )

        row_index = 0
        row_x = layout.row_rects[row_index].x - layout.panel_rect.x
        row_y = layout.row_rects[row_index].y - layout.panel_rect.y
        row_right = row_x + layout.row_rects[row_index].width
        row_height = layout.row_rects[row_index].height

        for item in items:
            item_width = self._item_width(item)
            if row_x + item_width > row_right + 1:
                row_index += 1
                row_x = layout.row_rects[row_index].x - layout.panel_rect.x
                row_y = layout.row_rects[row_index].y - layout.panel_rect.y
                row_right = row_x + layout.row_rects[row_index].width

            self._draw_item(surface, item, pygame.Rect(row_x, row_y, item_width, row_height))
            row_x += item_width + _CHIP_GAP

    def _draw_item(
        self,
        surface: pygame.Surface,
        item: ShortcutHint,
        rect: pygame.Rect,
    ) -> None:
        item_surface, badge_width = self._get_item_surface(item)
        badge_rect = pygame.Rect(
            rect.x,
            rect.y + max(0, (rect.height - item_surface.get_height()) // 2),
            badge_width,
            item_surface.get_height(),
        )
        surface.blit(item_surface, (rect.x, badge_rect.y))

    def _get_item_surface(self, item: ShortcutHint) -> tuple[pygame.Surface, int]:
        cache_key = (item.key_label, item.action_label)
        cached = self._item_surface_cache.get(cache_key)
        if cached is not None:
            return cached
        badge_surface = self._badge_font.render(item.key_label, True, (222, 250, 255))
        label_surface = self._font.render(item.action_label, True, (214, 228, 235))
        badge_width = badge_surface.get_width() + (_BADGE_PAD_X * 2)
        item_surface = pygame.Surface(
            (
                badge_width + _ITEM_GAP + label_surface.get_width(),
                max(
                    badge_surface.get_height() + (_BADGE_PAD_Y * 2),
                    label_surface.get_height(),
                ),
            ),
            pygame.SRCALPHA,
        )
        badge_rect = pygame.Rect(
            0,
            max(0, (item_surface.get_height() - (badge_surface.get_height() + _BADGE_PAD_Y * 2)) // 2),
            badge_width,
            badge_surface.get_height() + (_BADGE_PAD_Y * 2),
        )
        pygame.draw.rect(
            item_surface,
            (28, 84, 96, 220),
            badge_rect,
            border_radius=10,
        )
        pygame.draw.rect(
            item_surface,
            (118, 236, 255, 140),
            badge_rect,
            width=1,
            border_radius=10,
        )
        item_surface.blit(
            badge_surface,
            (
                badge_rect.x + _BADGE_PAD_X,
                badge_rect.y + _BADGE_PAD_Y,
            ),
        )
        label_x = badge_rect.right + _ITEM_GAP
        label_y = max(0, (item_surface.get_height() - label_surface.get_height()) // 2)
        item_surface.blit(label_surface, (label_x, label_y))
        if len(self._item_surface_cache) >= 48:
            first_key = next(iter(self._item_surface_cache))
            self._item_surface_cache.pop(first_key)
        cached = (item_surface, badge_width)
        self._item_surface_cache[cache_key] = cached
        return cached

    def _item_width(self, item: ShortcutHint) -> int:
        badge_width = self._badge_font.size(item.key_label)[0] + (_BADGE_PAD_X * 2)
        label_width = self._font.size(item.action_label)[0]
        return badge_width + _ITEM_GAP + label_width
