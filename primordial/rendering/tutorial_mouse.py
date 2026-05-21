"""Mouse hit regions for the tutorial overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class TutorialHitRegion:
    kind: str
    rect: pygame.Rect
    action: str | None = None
