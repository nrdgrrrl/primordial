"""Layout helpers for the in-app help overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


PANEL_MARGIN = 24
HEADER_HEIGHT = 72
FOOTER_HEIGHT = 72
GUTTER = 18
SEARCH_HEIGHT = 38
SCROLLBAR_WIDTH = 10
SCROLLBAR_TRACK_PAD = 2
SIDEBAR_ROW_HEIGHT = 42
GROUP_ROW_HEIGHT = 36


@dataclass(frozen=True)
class HelpOverlayLayout:
    panel_rect: pygame.Rect
    header_rect: pygame.Rect
    search_rect: pygame.Rect
    sidebar_rect: pygame.Rect
    content_rect: pygame.Rect
    footer_rect: pygame.Rect
    close_rect: pygame.Rect
    sidebar_scrollbar_rect: pygame.Rect
    content_scrollbar_rect: pygame.Rect


def panel_rect_for_screen(screen_size: tuple[int, int]) -> pygame.Rect:
    screen_width, screen_height = screen_size
    width = min(max(940, int(screen_width * 0.84)), screen_width - PANEL_MARGIN * 2)
    height = min(max(610, int(screen_height * 0.84)), screen_height - PANEL_MARGIN * 2)
    width = max(700, width)
    height = max(500, height)
    return pygame.Rect(
        screen_width // 2 - width // 2,
        screen_height // 2 - height // 2,
        width,
        height,
    )


def calculate_help_layout(
    screen_size: tuple[int, int],
    *,
    title_font: pygame.font.Font | None = None,
) -> HelpOverlayLayout:
    panel_rect = panel_rect_for_screen(screen_size)
    panel_width = panel_rect.width
    panel_height = panel_rect.height

    body_top = HEADER_HEIGHT
    footer_y = panel_height - FOOTER_HEIGHT
    available_width = panel_width - 36 - GUTTER
    sidebar_width = min(280, max(220, int(available_width * 0.34)))
    content_width = available_width - sidebar_width
    if content_width < 360:
        deficit = 360 - content_width
        sidebar_width = max(206, sidebar_width - deficit)
        content_width = available_width - sidebar_width

    search_rect = pygame.Rect(18, body_top, sidebar_width, SEARCH_HEIGHT)
    sidebar_top = search_rect.bottom + 8
    sidebar_rect = pygame.Rect(
        18,
        sidebar_top,
        sidebar_width - SCROLLBAR_WIDTH - SCROLLBAR_TRACK_PAD,
        footer_y - sidebar_top - 12,
    )
    sidebar_scrollbar_rect = pygame.Rect(
        sidebar_rect.right + SCROLLBAR_TRACK_PAD,
        sidebar_top,
        SCROLLBAR_WIDTH,
        footer_y - sidebar_top - 12,
    )
    content_rect = pygame.Rect(
        sidebar_rect.right + SCROLLBAR_WIDTH + SCROLLBAR_TRACK_PAD + GUTTER,
        body_top,
        content_width,
        footer_y - body_top - 12,
    )
    content_scrollbar_rect = pygame.Rect(
        content_rect.right + SCROLLBAR_TRACK_PAD,
        content_rect.y,
        SCROLLBAR_WIDTH,
        content_rect.height,
    )
    footer_rect = pygame.Rect(18, footer_y, panel_width - 36, FOOTER_HEIGHT - 14)
    close_rect = pygame.Rect(panel_width - 92, 16, 66, 30)
    return HelpOverlayLayout(
        panel_rect=panel_rect,
        header_rect=pygame.Rect(18, 8, panel_width - 36, HEADER_HEIGHT - 14),
        search_rect=search_rect,
        sidebar_rect=sidebar_rect,
        content_rect=content_rect,
        footer_rect=footer_rect,
        close_rect=close_rect,
        sidebar_scrollbar_rect=sidebar_scrollbar_rect,
        content_scrollbar_rect=content_scrollbar_rect,
    )