"""HUD module - heads-up display for simulation info."""

from __future__ import annotations

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
        self._panel_surface_cache: pygame.Surface | None = None
        self._panel_cache_key: tuple[object, ...] | None = None
        self._panel_position_cache: tuple[int, int] = (10, 10)
        self._refresh_token: object | None = None
        self._last_fps_display: str = "0"

    def invalidate_cache(self) -> None:
        self._panel_surface_cache = None
        self._panel_cache_key = None
        self._refresh_token = None

    def render(
        self,
        surface: pygame.Surface,
        simulation: "Simulation",
        fps: float,
        debug_lines: list[str] | None = None,
        *,
        refresh_token: object | None = None,
    ) -> None:
        if not self.visible:
            return
        panel_surface, panel_pos = self.build_panel_surface(
            surface.get_size(),
            simulation,
            fps,
            debug_lines=debug_lines,
            refresh_token=refresh_token,
        )
        surface.blit(panel_surface, panel_pos)

    def build_panel_surface(
        self,
        target_size: tuple[int, int],
        simulation: "Simulation",
        fps: float,
        *,
        debug_lines: list[str] | None = None,
        refresh_token: object | None = None,
        docked: bool = False,
    ) -> tuple[pygame.Surface, tuple[int, int]]:
        if not self.visible:
            empty = pygame.Surface((1, 1), pygame.SRCALPHA)
            return empty, (0, 0)
        effective_refresh_token = (
            refresh_token
            if refresh_token is not None
            else (
                int(getattr(simulation, "_frame", 0)),
                int(round(fps)),
                tuple(debug_lines or ()),
            )
        )
        if (
            self._panel_surface_cache is not None
            and self._refresh_token == effective_refresh_token
            and self._panel_cache_key == (target_size, simulation.settings.sim_mode, simulation.paused, bool(debug_lines))
        ):
            return self._panel_surface_cache, self._panel_position_cache

        mode = simulation.settings.sim_mode
        if mode == "predator_prey":
            lines = self._lines_predator_prey(simulation)
            show_food_bar = True
        elif mode == "boids":
            lines = self._lines_boids(simulation)
            show_food_bar = False
        elif mode == "drift":
            lines = self._lines_drift(simulation)
            show_food_bar = False
        else:
            lines = self._lines_energy(simulation)
            show_food_bar = True
        panel_surface, panel_pos = self._build_panel_surface(
            target_size,
            simulation,
            fps,
            lines=lines,
            show_food_bar=show_food_bar,
            debug_lines=debug_lines,
            docked=docked,
        )
        self._panel_cache_key = (target_size, simulation.settings.sim_mode, simulation.paused, bool(debug_lines))
        self._panel_surface_cache = panel_surface
        self._panel_position_cache = panel_pos
        self._refresh_token = effective_refresh_token
        return panel_surface, panel_pos

    # ------------------------------------------------------------------
    # Mode-specific line builders
    # ------------------------------------------------------------------

    def _observability_lines(self, simulation: "Simulation") -> list[str]:
        pop = simulation.get_population_observability_summary()
        evo = simulation.get_evolution_summary()
        tick_hz = simulation.get_simulation_tick_hz()
        avg_age = pop["average_age_ticks"] / tick_hz
        avg_lin = pop["average_lineage_age_ticks"] / tick_hz
        old_lin = pop["oldest_lineage_age_ticks"] / tick_hz
        directions = ", ".join(evo["top_directions"][:3]) if evo["top_directions"] else "stable"
        return [
            f"Age avg {avg_age:.0f}s | Lin {int(pop['active_lineage_count'])} avg {avg_lin:.0f}s old {old_lin:.0f}s",
            f"Evo Δ{float(evo['distance']):.3f}: {directions}",
        ]


    def _epistasis_lines(self, simulation: "Simulation") -> list[str]:
        summary = simulation.get_epistasis_summary()
        if not summary["enabled"] or simulation.population <= 0:
            return []
        avg = summary["average_modifiers"]
        strategy = str(summary["top_strategy"]).replace("-", " ")
        share = summary["top_strategy_share"] * 100.0
        return [
            f"Body plan: {strategy} {share:.0f}%",
            "Mods Sp:{speed:.2f} Se:{sense:.2f} Cost:{cost:.2f}".format(
                speed=avg["speed_mult"],
                sense=avg["sense_radius_mult"],
                cost=avg["movement_cost_mult"],
            ),
        ]

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
            *self._observability_lines(simulation),
            *self._epistasis_lines(simulation),
            f"Mode: {simulation.settings.sim_mode}",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    def _lines_predator_prey(self, simulation: "Simulation") -> list[str]:
        pred_count, prey_count = simulation.get_species_counts()
        pred_speed, prey_speed = simulation.get_species_avg_actual_speeds()
        predation = simulation.get_recent_predation_stats()
        stability = simulation.get_predator_prey_stability_stats()
        dom_zone = simulation.zone_manager.get_dominant_zone(simulation.creatures)
        seed = stability["current_seed"]
        seed_str = str(seed) if seed is not None else "—"

        trial_line = "Trial: none"
        if stability["trial_active"] and stability["trial_dial"]:
            trial_line = (
                f"Trial: {stability['trial_dial']} {stability['trial_direction']}"
            )
        danger_line = "Danger: none"
        if stability["extinction_grace_active"]:
            if stability["extinction_grace_role"] == "both":
                remaining = min(
                    stability["predator_grace_remaining_ticks"],
                    stability["prey_grace_remaining_ticks"],
                )
            elif stability["extinction_grace_role"] == "predators":
                remaining = stability["predator_grace_remaining_ticks"]
            else:
                remaining = stability["prey_grace_remaining_ticks"]
            danger_line = (
                f"Danger: {stability['extinction_grace_role']} zero "
                f"({remaining}t grace)"
            )
        history_window = stability["history_window_size"]

        return [
            f"Predators: {pred_count}  /  Prey: {prey_count}",
            f"Actual speed P:{pred_speed:.2f}  Q:{prey_speed:.2f}",
            f"Kills (3s): {predation['recent_kills']}  Cross-miss: {predation['recent_cross_band_misses']}",
            f"sim_ticks: {stability['sim_ticks']}  Seed: {seed_str}",
            (
                "Survival: {current}  Med{window}: {average:.0f}  Best{window}: {best}".format(
                    current=stability["survival_ticks"],
                    window=history_window,
                    average=stability["rolling_average_survival_ticks"],
                    best=stability["best_recent_survival_ticks"],
                )
            ),
            danger_line,
            trial_line,
            *self._observability_lines(simulation),
            *self._epistasis_lines(simulation),
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
            *self._observability_lines(simulation),
            *self._epistasis_lines(simulation),
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
            *self._observability_lines(simulation),
            *self._epistasis_lines(simulation),
            f"Mode: drift",
            f"Theme: {simulation.settings.visual_theme}",
        ]

    # ------------------------------------------------------------------
    # Shared panel renderer
    # ------------------------------------------------------------------

    def _build_panel_surface(
        self,
        target_size: tuple[int, int],
        simulation: "Simulation",
        fps: float,
        *,
        lines: list[str],
        show_food_bar: bool,
        debug_lines: list[str] | None = None,
        docked: bool = False,
    ) -> tuple[pygame.Surface, tuple[int, int]]:
        if simulation.paused:
            lines = ["[PAUSED]"] + lines
        fps_display = f"{fps:.0f}"
        self._last_fps_display = fps_display
        fps_line = f"FPS: {fps_display}"
        lines.append(fps_line)
        if debug_lines:
            lines.extend(debug_lines)

        if docked:
            return self._build_docked_panel(target_size, lines, fps_line, show_food_bar, simulation)

        max_panel_width = max(220, target_size[0] - 20)
        lines = self._fit_lines(lines, max_panel_width - self.padding * 2)

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

        panel_width = min(max_panel_width, max_width + self.padding * 2)
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

        screen_height = target_size[1]
        pos = (10, screen_height - panel_height - 10)
        return panel, pos

    _PRIORITY_CRITICAL = 0
    _PRIORITY_HIGH = 1
    _PRIORITY_MEDIUM = 2
    _PRIORITY_LOW = 3

    _PREDATOR_PREY_PREFIXES_CRITICAL = (
        "Predators:", "Prey:", "Kills", "Danger:", "Survival:",
    )
    _PREDATOR_PREY_PREFIXES_HIGH = (
        "Actual speed", "sim_ticks:", "Seed:", "Trial:",
    )
    _GENERAL_PREFIXES_HIGH = (
        "Generation:", "Population:", "Food:",
    )

    @classmethod
    def _line_priority(cls, line: str) -> int:
        if line.startswith("[PAUSED]") or line.startswith("FPS:"):
            return cls._PRIORITY_CRITICAL
        if line.startswith("Dbg "):
            return cls._PRIORITY_LOW
        for prefix in cls._PREDATOR_PREY_PREFIXES_CRITICAL:
            if line.startswith(prefix):
                return cls._PRIORITY_CRITICAL
        for prefix in cls._PREDATOR_PREY_PREFIXES_HIGH:
            if line.startswith(prefix):
                return cls._PRIORITY_HIGH
        for prefix in cls._GENERAL_PREFIXES_HIGH:
            if line.startswith(prefix):
                return cls._PRIORITY_HIGH
        if line.startswith("Zone:") or line.startswith("Mode:") or line.startswith("Theme:"):
            return cls._PRIORITY_LOW
        if line.startswith("Age ") or line.startswith("Evo ") or line.startswith("Body ") or line.startswith("Mods "):
            return cls._PRIORITY_MEDIUM
        return cls._PRIORITY_MEDIUM

    @classmethod
    def _classify_column(cls, line: str) -> int:
        for prefix in (
            "Predators:", "Prey:", "Kills", "Survival:", "Danger:",
            "Actual speed", "sim_ticks:", "Seed:", "Trial:",
            "Generation:", "Population:", "Food:", "[PAUSED]",
        ):
            if line.startswith(prefix):
                return 0
        return 1

    def _build_docked_panel(
        self,
        target_size: tuple[int, int],
        lines: list[str],
        fps_line: str,
        show_food_bar: bool,
        simulation: "Simulation",
    ) -> tuple[pygame.Surface, tuple[int, int]]:
        avail_w, avail_h = target_size
        if avail_w < 40 or avail_h < 20:
            empty = pygame.Surface((1, 1), pygame.SRCALPHA)
            return empty, (0, 0)

        col_gap = 8
        col_width = max(80, (avail_w - self.padding * 2 - col_gap) // 2)
        max_text_width = col_width - 8
        fitted = self._fit_lines(lines, max_text_width)

        header_lines = [l for l in fitted if l.startswith("FPS:") or l.startswith("[PAUSED]")]
        body_lines = [l for l in fitted if l not in header_lines]

        body_with_priority = [(l, self._line_priority(l)) for l in body_lines]
        body_with_priority.sort(key=lambda t: t[1])

        col_lines: list[list[str]] = [[], []]
        for line, _ in body_with_priority:
            col_idx = len(col_lines[0]) <= len(col_lines[1]) and 0 or 1
            col_idx = self._classify_column(line)
            col_lines[col_idx].append(line)

        row_height = self.line_height
        header_rows = len(header_lines)
        header_height = header_rows * row_height

        food_bar_h = 14
        food_bar_gap = 4
        food_bar_total = food_bar_h + food_bar_gap if show_food_bar else 0

        body_avail_h = avail_h - self.padding * 2 - header_height - food_bar_total

        col0_dropped = 0
        while col0_dropped < len(col_lines[0]):
            needed = (len(col_lines[0]) - col0_dropped) * row_height
            if needed <= body_avail_h:
                break
            col0_dropped += 1
        col1_dropped = 0
        while col1_dropped < len(col_lines[1]):
            needed = (len(col_lines[1]) - col1_dropped) * row_height
            if needed <= body_avail_h:
                break
            col1_dropped += 1

        if col0_dropped > 0 or col1_dropped > 0:
            for i in range(len(col_lines[0]) - 1, -1, -1):
                if col0_dropped <= 0:
                    break
                pri = self._line_priority(col_lines[0][i])
                if pri >= self._PRIORITY_LOW:
                    col_lines[0].pop(i)
                    col0_dropped -= 1
            for i in range(len(col_lines[1]) - 1, -1, -1):
                if col1_dropped <= 0:
                    break
                pri = self._line_priority(col_lines[1][i])
                if pri >= self._PRIORITY_LOW:
                    col_lines[1].pop(i)
                    col1_dropped -= 1

        max_rows = max(len(col_lines[0]), len(col_lines[1]), 0)
        panel_height = self.padding + header_height + max_rows * row_height + food_bar_total + self.padding
        panel_height = min(panel_height, avail_h)

        panel = pygame.Surface((avail_w, panel_height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 80))

        y = self.padding
        for line in header_lines:
            text_surface = self.font.render(line, True, (200, 230, 255))
            panel.blit(text_surface, (self.padding, y))
            y += row_height

        body_y = y
        for col_idx, col in enumerate(col_lines):
            x = self.padding + col_idx * (col_width + col_gap)
            row_y = body_y
            for line in col:
                if row_y + row_height > panel_height - self.padding - food_bar_total:
                    break
                text_surface = self.font.render(line, True, (255, 255, 255))
                panel.blit(text_surface, (x, row_y))
                row_y += row_height

        if show_food_bar:
            bar_y = panel_height - self.padding - food_bar_h
            phase = simulation.food_cycle_phase
            bar_x = self.padding
            bar_w = min(col_width, avail_w - self.padding * 2)
            pygame.draw.rect(panel, (60, 60, 80, 180),
                             (bar_x, bar_y, bar_w, food_bar_h), border_radius=3)
            fill_w = max(2, int(bar_w * phase))
            fill_r = int(180 * (1 - phase) + 40 * phase)
            fill_g = int(60 * (1 - phase) + 180 * phase)
            fill_b = int(40 * (1 - phase) + 80 * phase)
            pygame.draw.rect(panel, (fill_r, fill_g, fill_b, 220),
                             (bar_x, bar_y, fill_w, food_bar_h), border_radius=3)
            famine_surf = self.font.render("F", True, (160, 120, 80))
            feast_surf = self.font.render("E", True, (120, 220, 140))
            label_y = bar_y + (food_bar_h - famine_surf.get_height()) // 2
            panel.blit(famine_surf, (bar_x + 2, label_y))
            panel.blit(feast_surf, (bar_x + bar_w - feast_surf.get_width() - 2, label_y))

        return panel, (0, 0)

    def _fit_lines(self, lines: list[str], max_text_width: int) -> list[str]:
        fitted: list[str] = []
        for line in lines:
            if self.font.size(line)[0] <= max_text_width:
                fitted.append(line)
                continue
            words = line.split(" ")
            if not words:
                fitted.append("...")
                continue
            current = words[0]
            for word in words[1:]:
                candidate = f"{current} {word}"
                if self.font.size(candidate)[0] <= max_text_width:
                    current = candidate
                    continue
                fitted.append(self._truncate(current, max_text_width))
                current = word
            fitted.append(self._truncate(current, max_text_width))
        return fitted

    def _truncate(self, text: str, max_width: int) -> str:
        if self.font.size(text)[0] <= max_width:
            return text
        trimmed = text
        ellipsis = "..."
        while trimmed and self.font.size(trimmed + ellipsis)[0] > max_width:
            trimmed = trimmed[:-1]
        return (trimmed + ellipsis) if trimmed else ellipsis

    def toggle(self) -> None:
        """Toggle HUD visibility."""
        self.visible = not self.visible
