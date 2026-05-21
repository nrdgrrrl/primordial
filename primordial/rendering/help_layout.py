"""Layout helpers for the in-app help overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


PANEL_MARGIN = 24
HEADER_HEIGHT = 82
FOOTER_HEIGHT = 72
GUTTER = 18
SEARCH_HEIGHT = 38
NAV_ROW_HEIGHT = 50


@dataclass(frozen=True)
class HelpOverlayLayout:
    panel_rect: pygame.Rect
    header_rect: pygame.Rect
    search_rect: pygame.Rect
    nav_rect: pygame.Rect
    content_rect: pygame.Rect
    footer_rect: pygame.Rect
    close_rect: pygame.Rect


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
    section_titles: list[str],
    title_font: pygame.font.Font,
) -> HelpOverlayLayout:
    panel_rect = panel_rect_for_screen(screen_size)
    panel_width = panel_rect.width
    panel_height = panel_rect.height

    widest_title = max((title_font.size(title)[0] for title in section_titles), default=0)
    body_top = HEADER_HEIGHT
    footer_y = panel_height - FOOTER_HEIGHT
    available_width = panel_width - 36 - GUTTER
    nav_width = min(310, max(232, widest_title + 42))
    max_nav_width = max(220, int(available_width * 0.38))
    nav_width = min(nav_width, max_nav_width)
    content_width = available_width - nav_width
    if content_width < 360:
        deficit = 360 - content_width
        nav_width = max(206, nav_width - deficit)
        content_width = available_width - nav_width

    search_rect = pygame.Rect(18, body_top, nav_width, SEARCH_HEIGHT)
    nav_rect = pygame.Rect(
        18,
        search_rect.bottom + 10,
        nav_width,
        footer_y - search_rect.bottom - 22,
    )
    content_rect = pygame.Rect(
        nav_rect.right + GUTTER,
        body_top,
        content_width,
        footer_y - body_top - 12,
    )
    footer_rect = pygame.Rect(18, footer_y, panel_width - 36, FOOTER_HEIGHT - 14)
    close_rect = pygame.Rect(panel_width - 92, 24, 66, 30)
    return HelpOverlayLayout(
        panel_rect=panel_rect,
        header_rect=pygame.Rect(18, 12, panel_width - 36, HEADER_HEIGHT - 18),
        search_rect=search_rect,
        nav_rect=nav_rect,
        content_rect=content_rect,
        footer_rect=footer_rect,
        close_rect=close_rect,
    )
