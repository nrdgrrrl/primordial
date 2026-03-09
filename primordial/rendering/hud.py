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

    Shows mode-specific stats in a semi-transparent panel.
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
        simulation: "Simulation",
        fps: float,
        debug_lines: list[str] | None = None,
    ) -> None:
        if not self.visible:
            return

        mode = simulation.settings.sim_mode

        if mode == "predator_prey":
            self._render_panel(surface, simulation, fps,
                               self._lines_predator_prey(simulation),
                               show_food_bar=True,
                               debug_lines=debug_lines)
        elif mode == "boids":
            self._render_panel(surface, simulation, fps,
                               self._lines_boids(simulation),
                               show_food_bar=False,
                               debug_lines=debug_lines)
        elif mode == "drift":
            self._render_panel(surface, simulation, fps,
                               self._lines_drift(simulation),
                               show_food_bar=False,
                               debug_lines=debug_lines)
        else:
            self._render_panel(surface, simulation, fps,
                               self._lines_energy(simulation),
                               show_food_bar=True,
                               debug_lines=debug_lines)

    # ------------------------------------------------------------------
    # Mode-specific line builders
    # ------------------------------------------------------------------

    def _lines_energy(self, simulation: "Simulation") -> list[str]:
        oldest_str = "—"
        if simulation.creatures:
            oldest = max(simulation.creatures, key=lambda c: c.age)
            pct = oldest.get_age_fraction() * 100
            oldest_str = f"{pct:.0f}%"

        hunters, grazers, opps = simulation.get_hunter_grazer_counts()
        dom_zone = simulation.zone_manager.get_dominant_zone(simulation.creatures)
        avg_ls = simulation.avg_old_age_lifespan_seconds
        avg_ls_str = f"{avg_ls:.0f}s" if avg_ls > 0 else "—"

        return [
            f"Generation: {simulation.generation}",
            f"Population: {simulation.population}",
            f"Oldest: {oldest_str} lifespan",
            f"H:{hunters} G:{grazers} O:{opps}",
            f"Avg lifespan: {avg_ls_str}",
            f"Zone: {dom_zone}",
            f"Food: {simulation.food_count}",
            f"Mode: {simulation.settings.sim_mode}",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    def _lines_predator_prey(self, simulation: "Simulation") -> list[str]:
        pred_count, prey_count = simulation.get_species_counts()
        pred_speed, prey_speed = simulation.get_species_avg_actual_speeds()
        predation = simulation.get_recent_predation_stats()
        dom_zone = simulation.zone_manager.get_dominant_zone(simulation.creatures)

        return [
            f"Predators: {pred_count}  /  Prey: {prey_count}",
            f"Actual speed P:{pred_speed:.2f}  Q:{prey_speed:.2f}",
            f"Kills (3s): {predation['recent_kills']}  Cross-miss: {predation['recent_cross_band_misses']}",
            f"Generation: {simulation.generation}",
            f"Zone: {dom_zone}",
            f"Mode: predator_prey",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    def _lines_boids(self, simulation: "Simulation") -> list[str]:
        flock_count, avg_size, largest = simulation.get_flock_stats()
        avg_conformity = simulation.get_avg_conformity()
        loners = sum(1 for c in simulation.creatures if c.flock_id == -1)

        return [
            f"Population: {simulation.population}",
            f"Flocks: {flock_count}  Avg size: {avg_size:.1f}",
            f"Largest flock: {largest}  Loners: {loners}",
            f"Avg conformity: {avg_conformity:.2f}",
            f"Generation: {simulation.generation}",
            f"Mode: boids",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    def _lines_drift(self, simulation: "Simulation") -> list[str]:
        lineage_count = simulation.get_lineage_count()
        most_var = simulation.get_most_variable_trait()

        return [
            f"Population: {simulation.population}",
            f"Generation: {simulation.generation}",
            f"Lineages: {lineage_count}",
            f"Most variable: {most_var}",
            f"Mode: drift",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    # ------------------------------------------------------------------
    # Shared panel renderer
    # ------------------------------------------------------------------

    def _render_panel(
        self,
        surface: pygame.Surface,
        simulation: "Simulation",
        fps: float,
        lines: list[str],
        show_food_bar: bool,
        debug_lines: list[str] | None = None,
    ) -> None:
        if simulation.paused:
            lines = ["[PAUSED]"] + lines
        lines.append(f"FPS: {fps:.0f}")
        if debug_lines:
            lines.extend(debug_lines)

        food_bar_height = 12
        food_bar_margin = 6

        max_width = 0
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            max_width = max(max_width, text_surface.get_width())

        if show_food_bar:
            feast_label = self.font.render("Feast", True, (255, 255, 255))
            famine_label = self.font.render("Famine", True, (255, 255, 255))
            bar_label_w = max(feast_label.get_width(), famine_label.get_width())
            bar_row_width = 80 + bar_label_w * 2 + 8
            max_width = max(max_width, bar_row_width)

        panel_width = max_width + self.padding * 2
        panel_height = (
            len(lines) * self.line_height
            + (food_bar_height + food_bar_margin if show_food_bar else 0)
            + self.padding * 2
        )

        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 102))

        y = self.padding
        for line in lines:
            text_surface = self.font.render(line, True, (255, 255, 255))
            panel.blit(text_surface, (self.padding, y))
            y += self.line_height

        if show_food_bar:
            y += food_bar_margin // 2
            phase = simulation.food_cycle_phase

            famine_surf = self.font.render("Famine", True, (160, 120, 80))
            feast_surf = self.font.render("Feast", True, (120, 220, 140))

            bar_x = self.padding + famine_surf.get_width() + 4
            bar_w = 80
            bar_y = y

            pygame.draw.rect(panel, (60, 60, 80, 180),
                             (bar_x, bar_y, bar_w, food_bar_height), border_radius=3)

            fill_w = max(2, int(bar_w * phase))
            fill_r = int(180 * (1 - phase) + 40 * phase)
            fill_g = int(60 * (1 - phase) + 180 * phase)
            fill_b = int(40 * (1 - phase) + 80 * phase)
            pygame.draw.rect(panel, (fill_r, fill_g, fill_b, 220),
                             (bar_x, bar_y, fill_w, food_bar_height), border_radius=3)

            label_y = bar_y + (food_bar_height - famine_surf.get_height()) // 2
            panel.blit(famine_surf, (self.padding, label_y))
            panel.blit(feast_surf, (bar_x + bar_w + 4, label_y))

        screen_height = surface.get_height()
        pos = (10, screen_height - panel_height - 10)
        surface.blit(panel, pos)

    def toggle(self) -> None:
        """Toggle HUD visibility."""
        self.visible = not self.visible
