"""Layout helpers for the in-game tutorial overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


PANEL_MARGIN = 24
HEADER_HEIGHT = 76
FOOTER_HEIGHT = 64
BUTTON_HEIGHT = 36
BUTTON_GAP = 12


@dataclass(frozen=True)
class TutorialLayout:
    panel_rect: pygame.Rect
    header_rect: pygame.Rect
    body_rect: pygame.Rect
    footer_rect: pygame.Rect
    back_rect: pygame.Rect
    skip_rect: pygame.Rect
    next_rect: pygame.Rect
    highlight_rect: pygame.Rect | None


def calculate_tutorial_layout(
    screen_size: tuple[int, int],
    *,
    highlight: str,
) -> TutorialLayout:
    screen_width, screen_height = screen_size
    max_width = max(320, screen_width - PANEL_MARGIN * 2)
    max_height = max(260, screen_height - PANEL_MARGIN * 2)
    panel_width = min(max(620, int(screen_width * 0.46)), max_width)
    panel_height = min(max(360, int(screen_height * 0.48)), max_height)
    panel_width = min(max_width, max(320, panel_width))
    panel_height = min(max_height, max(260, panel_height))

    panel_x = screen_width - panel_width - max(PANEL_MARGIN, int(screen_width * 0.04))
    panel_y = screen_height // 2 - panel_height // 2
    if highlight in {"hud", "settings", "help"}:
        panel_x = max(PANEL_MARGIN, int(screen_width * 0.06))
    panel_x = max(PANEL_MARGIN, min(screen_width - panel_width - PANEL_MARGIN, panel_x))
    panel_y = max(PANEL_MARGIN, min(screen_height - panel_height - PANEL_MARGIN, panel_y))

    panel_rect = pygame.Rect(panel_x, panel_y, panel_width, panel_height)
    header_rect = pygame.Rect(22, 16, panel_width - 44, HEADER_HEIGHT - 18)
    footer_rect = pygame.Rect(22, panel_height - FOOTER_HEIGHT, panel_width - 44, FOOTER_HEIGHT - 14)
    body_rect = pygame.Rect(
        22,
        HEADER_HEIGHT + 8,
        panel_width - 44,
        footer_rect.y - HEADER_HEIGHT - 18,
    )

    next_width = 106
    back_width = 96
    skip_width = 96
    next_rect = pygame.Rect(
        footer_rect.right - next_width,
        footer_rect.y + 8,
        next_width,
        BUTTON_HEIGHT,
    )
    skip_rect = pygame.Rect(
        next_rect.x - BUTTON_GAP - skip_width,
        next_rect.y,
        skip_width,
        BUTTON_HEIGHT,
    )
    back_rect = pygame.Rect(
        footer_rect.x,
        next_rect.y,
        back_width,
        BUTTON_HEIGHT,
    )

    return TutorialLayout(
        panel_rect=panel_rect,
        header_rect=header_rect,
        body_rect=body_rect,
        footer_rect=footer_rect,
        back_rect=back_rect,
        skip_rect=skip_rect,
        next_rect=next_rect,
        highlight_rect=highlight_rect_for_screen(screen_size, highlight, panel_rect),
    )


def highlight_rect_for_screen(
    screen_size: tuple[int, int],
    highlight: str,
    panel_rect: pygame.Rect,
) -> pygame.Rect | None:
    width, height = screen_size
    if highlight == "none":
        return None
    if highlight == "hud":
        return pygame.Rect(16, 16, min(420, width - 32), min(190, height - 32))
    if highlight == "settings":
        return pygame.Rect(18, height - 92, min(380, width - 36), 58)
    if highlight == "help":
        return pygame.Rect(18, height - 150, min(420, width - 36), 58)
    if highlight == "food":
        return pygame.Rect(width // 2 - 180, height // 2 - 110, 360, 220)
    if highlight == "creatures":
        return pygame.Rect(width // 2 - 240, height // 2 - 150, 480, 300)
    if highlight == "predators":
        return pygame.Rect(width // 2 - 270, height // 2 - 150, 540, 300)
    if highlight == "lineages":
        return pygame.Rect(width // 2 - 300, height // 2 - 190, 600, 380)
    if highlight == "zones":
        return pygame.Rect(60, 60, max(280, width - 120), max(220, height - 120))
    if highlight == "depth":
        return pygame.Rect(70, height // 2 - 95, max(280, width - 140), 190)
    if highlight == "game_over":
        return pygame.Rect(width // 2 - 260, height // 2 - 120, 520, 240)
    if highlight == "world":
        margin = 54
        rect = pygame.Rect(margin, margin, width - margin * 2, height - margin * 2)
        if rect.colliderect(panel_rect):
            rect.width = max(220, panel_rect.x - margin * 2)
        return rect
    return None
