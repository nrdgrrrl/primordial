"""Layout helpers for the in-app settings overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


BODY_TOP = 86
FOOTER_HEIGHT = 94
GUTTER = 18
PANEL_MARGIN = 24
ROW_HEIGHT = 64
ROW_RECT_HEIGHT = 56
LIST_HEADER_HEIGHT = 62


@dataclass(frozen=True)
class SettingsOverlayLayout:
    panel_rect: pygame.Rect
    sidebar_rect: pygame.Rect
    list_rect: pygame.Rect
    details_rect: pygame.Rect
    footer_rect: pygame.Rect


def panel_rect_for_screen(screen_size: tuple[int, int]) -> pygame.Rect:
    screen_width, screen_height = screen_size
    width = min(max(980, int(screen_width * 0.86)), screen_width - PANEL_MARGIN * 2)
    height = min(max(620, int(screen_height * 0.84)), screen_height - PANEL_MARGIN * 2)
    width = max(720, width)
    height = max(520, height)
    return pygame.Rect(
        screen_width // 2 - width // 2,
        screen_height // 2 - height // 2,
        width,
        height,
    )


def calculate_settings_layout(
    screen_size: tuple[int, int],
    *,
    categories: list[str],
    item_labels: list[str],
    category_font: pygame.font.Font,
    item_font: pygame.font.Font,
    count_font: pygame.font.Font,
) -> SettingsOverlayLayout:
    panel_rect = panel_rect_for_screen(screen_size)
    panel_width = panel_rect.width
    panel_height = panel_rect.height
    body_bottom = panel_height - FOOTER_HEIGHT
    available_width = panel_width - 36 - GUTTER * 2

    widest_category = max(
        (category_font.size(category)[0] for category in categories),
        default=0,
    )
    widest_item_label = max(
        (item_font.size(label)[0] for label in item_labels),
        default=0,
    )
    widest_count = count_font.size("999")[0]

    sidebar_desired = min(252, max(190, widest_category + widest_count + 48))
    list_desired = min(460, max(360, widest_item_label + 184))
    details_min = 240 if panel_width >= 900 else 190
    sidebar_min = 168
    list_min = 300 if panel_width >= 900 else 274

    sidebar_width = min(sidebar_desired, max(sidebar_min, int(available_width * 0.28)))
    list_width = min(list_desired, max(list_min, int(available_width * 0.46)))
    details_width = available_width - sidebar_width - list_width

    if details_width < details_min:
        deficit = details_min - details_width
        list_reduction = min(deficit, max(0, list_width - list_min))
        list_width -= list_reduction
        deficit -= list_reduction
        sidebar_width -= min(deficit, max(0, sidebar_width - sidebar_min))
        details_width = available_width - sidebar_width - list_width

    details_width = max(160, details_width)
    sidebar_rect = pygame.Rect(18, BODY_TOP, sidebar_width, body_bottom - BODY_TOP - 12)
    list_rect = pygame.Rect(sidebar_rect.right + GUTTER, BODY_TOP, list_width, sidebar_rect.height)
    details_rect = pygame.Rect(
        list_rect.right + GUTTER,
        BODY_TOP,
        details_width,
        sidebar_rect.height,
    )
    footer_rect = pygame.Rect(
        18,
        panel_height - FOOTER_HEIGHT,
        panel_width - 36,
        FOOTER_HEIGHT - 14,
    )
    return SettingsOverlayLayout(
        panel_rect=panel_rect,
        sidebar_rect=sidebar_rect,
        list_rect=list_rect,
        details_rect=details_rect,
        footer_rect=footer_rect,
    )
