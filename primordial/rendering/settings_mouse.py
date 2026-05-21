"""Mouse hit regions for the settings overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class SettingsHitRegion:
    kind: str
    rect: pygame.Rect
    category: str | None = None
    row_index: int | None = None
    direction: int = 0
    action: str | None = None
