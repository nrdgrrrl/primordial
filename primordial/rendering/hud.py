"""HUD module - heads-up display for simulation info."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.simulation import Simulation


class HUD:
    """
    Heads-up display for simulation information.

    Shows generation count, population, oldest creature age,
    current mode/theme, and FPS in a semi-transparent panel.
    """

    def __init__(self, font_size: int = 16) -> None:
        """
        Initialize the HUD.

        Args:
            font_size: Font size in pixels.
        """
        pygame.font.init()
        self.font = pygame.font.Font(None, font_size)
        self.font_size = font_size
        self.padding = 10
        self.line_height = font_size + 4
        self.visible = True

    def render(
        self,
        surface: pygame.Surface,
        simulation: Simulation,
        fps: float,
    ) -> None:
        """
        Render the HUD to the surface.

        Args:
            surface: Pygame surface to draw on.
            simulation: Simulation instance for data.
            fps: Current frames per second.
        """
        if not self.visible:
            return

        # Prepare text lines
        lines = [
            f"Generation: {simulation.generation}",
            f"Population: {simulation.population}",
            f"Oldest: {simulation.oldest_age} frames",
            f"Food: {simulation.food_count}",
            f"Mode: {simulation.settings.sim_mode}",
            f"Theme: {simulation.settings.visual_theme}",
            f"FPS: {fps:.0f}",
        ]

        if simulation.paused:
            lines.insert(0, "[PAUSED]")

        # Calculate panel size
        max_width = 0
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            max_width = max(max_width, text_surface.get_width())

        panel_width = max_width + self.padding * 2
        panel_height = len(lines) * self.line_height + self.padding * 2

        # Create semi-transparent panel
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 102))  # 40% alpha black

        # Render text lines
        y = self.padding
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            panel.blit(text_surface, (self.padding, y))
            y += self.line_height

        # Position in bottom-left corner
        screen_height = surface.get_height()
        pos = (10, screen_height - panel_height - 10)
        surface.blit(panel, pos)

    def toggle(self) -> None:
        """Toggle HUD visibility."""
        self.visible = not self.visible
