"""Mouse hit regions for the in-app help overlay."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class HelpHitRegion:
    kind: str
    rect: pygame.Rect
    section_index: int | None = None
    action: str | None = None
    doc_id: str | None = None
