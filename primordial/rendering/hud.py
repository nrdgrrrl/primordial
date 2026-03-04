"""HUD module - heads-up display for simulation info."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ..simulation.simulation import Simulation


class HUD:
    """
    Heads-up display for simulation information.

    Shows generation count, population, oldest creature age (% lifespan),
    hunter/grazer ratio, food cycle bar, dominant zone, average lifespan,
    current mode/theme, and FPS in a semi-transparent panel.
    """

    def __init__(self, font_size: int = 16) -> None:
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
        if not self.visible:
            return

        # ------------------------------------------------------------------
        # Oldest as % of max lifespan
        # ------------------------------------------------------------------
        oldest_str = "—"
        if simulation.creatures:
            oldest = max(simulation.creatures, key=lambda c: c.age)
            pct = oldest.get_age_fraction() * 100
            oldest_str = f"{pct:.0f}%"

        # ------------------------------------------------------------------
        # Hunter / Grazer counts
        # ------------------------------------------------------------------
        hunters, grazers, opps = simulation.get_hunter_grazer_counts()

        # ------------------------------------------------------------------
        # Dominant zone
        # ------------------------------------------------------------------
        dom_zone = simulation.zone_manager.get_dominant_zone(simulation.creatures)

        # ------------------------------------------------------------------
        # Average old-age lifespan
        # ------------------------------------------------------------------
        avg_ls = simulation.avg_old_age_lifespan_seconds
        avg_ls_str = f"{avg_ls:.0f}s" if avg_ls > 0 else "—"

        # ------------------------------------------------------------------
        # Text lines
        # ------------------------------------------------------------------
        lines = [
            f"Generation: {simulation.generation}",
            f"Population: {simulation.population}",
            f"Oldest: {oldest_str} lifespan",
            f"H:{hunters} G:{grazers} O:{opps}",
            f"Avg lifespan: {avg_ls_str}",
            f"Zone: {dom_zone}",
            f"Food: {simulation.food_count}",
            f"Mode: {simulation.settings.sim_mode}",
            f"Theme: {simulation.settings.visual_theme}",
            f"FPS: {fps:.0f}",
        ]

        if simulation.paused:
            lines.insert(0, "[PAUSED]")

        # ------------------------------------------------------------------
        # Calculate panel dimensions
        # ------------------------------------------------------------------
        # Extra height for the food bar row
        food_bar_height = 12
        food_bar_margin = 6

        max_width = 0
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            max_width = max(max_width, text_surface.get_width())

        # Food bar width: 80px label "Feast/Famine" takes some space too
        feast_label = self.font.render("Feast", True, (255, 255, 255))
        famine_label = self.font.render("Famine", True, (255, 255, 255))
        bar_label_w = max(feast_label.get_width(), famine_label.get_width())
        bar_row_width = 80 + bar_label_w * 2 + 8
        max_width = max(max_width, bar_row_width)

        panel_width = max_width + self.padding * 2
        panel_height = (
            len(lines) * self.line_height
            + food_bar_height + food_bar_margin
            + self.padding * 2
        )

        # ------------------------------------------------------------------
        # Draw panel
        # ------------------------------------------------------------------
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 102))  # 40% alpha black

        y = self.padding

        # Text lines
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            panel.blit(text_surface, (self.padding, y))
            y += self.line_height

        # ------------------------------------------------------------------
        # Food cycle bar
        # ------------------------------------------------------------------
        y += food_bar_margin // 2

        phase = simulation.food_cycle_phase  # 0.0=famine, 1.0=feast

        # Label "Famine" on left, "Feast" on right
        famine_surf = self.font.render("Famine", True, (160, 120, 80))
        feast_surf = self.font.render("Feast", True, (120, 220, 140))

        bar_x = self.padding + famine_surf.get_width() + 4
        bar_w = 80
        bar_y = y + (food_bar_height - food_bar_height) // 2

        # Background track
        pygame.draw.rect(panel, (60, 60, 80, 180), (bar_x, bar_y, bar_w, food_bar_height), border_radius=3)

        # Fill based on phase
        fill_w = max(2, int(bar_w * phase))
        # Color gradient: red at famine, green at feast
        fill_r = int(180 * (1 - phase) + 40 * phase)
        fill_g = int(60 * (1 - phase) + 180 * phase)
        fill_b = int(40 * (1 - phase) + 80 * phase)
        pygame.draw.rect(panel, (fill_r, fill_g, fill_b, 220),
                         (bar_x, bar_y, fill_w, food_bar_height), border_radius=3)

        # Labels centred vertically with bar
        label_y = bar_y + (food_bar_height - famine_surf.get_height()) // 2
        panel.blit(famine_surf, (self.padding, label_y))
        panel.blit(feast_surf, (bar_x + bar_w + 4, label_y))

        # ------------------------------------------------------------------
        # Blit panel to screen (bottom-left)
        # ------------------------------------------------------------------
        screen_height = surface.get_height()
        pos = (10, screen_height - panel_height - 10)
        surface.blit(panel, pos)

    def toggle(self) -> None:
        """Toggle HUD visibility."""
        self.visible = not self.visible
