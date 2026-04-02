"""Renderer module - main rendering controller."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

from .animations import AnimationManager
from .hud import HUD
from .settings_overlay import SettingsOverlay
from .themes import AmbientParticle, OceanTheme, Theme, get_theme

# Zone type → background RGB (same palette as zones.py, duplicated here
# so renderer has no import from simulation/)
_ZONE_BG_COLORS: dict[str, tuple[int, int, int]] = {
    "warm_vent":      (214, 116, 34),
    "open_water":     (56, 156, 224),
    "kelp_forest":    (36, 132, 92),
    "hunting_ground": (172, 44, 52),
    "deep_trench":    (64, 60, 156),
}

_ZONE_LABELS: dict[str, str] = {
    "warm_vent": "Warm Vent",
    "open_water": "Open Water",
    "kelp_forest": "Kelp Forest",
    "hunting_ground": "Hunting Ground",
    "deep_trench": "Deep Trench",
}

_PREDATOR_PREY_DIAL_LABELS: dict[str, str] = {
    "predator_contact_kill_distance_scale": "Kill distance",
    "predator_kill_energy_gain_cap": "Kill reward",
    "predator_hunt_sense_multiplier": "Pred sense",
    "prey_flee_sense_multiplier": "Prey flee",
    "predator_prey_scarcity_penalty_multiplier": "Scarcity cost",
    "food_cycle_amplitude": "Food cycle",
}

if TYPE_CHECKING:
    from ..simulation.simulation import Simulation
    from ..settings import Settings


# ---------------------------------------------------------------------------
# Territory shimmer state
# ---------------------------------------------------------------------------


@dataclass
class ShimmerState:
    """Persistent per-lineage shimmer state for smooth animation."""

    lineage_id: int
    centroid_x: float
    centroid_y: float
    spread_x: float           # std-dev of x positions
    spread_y: float
    hue: float                # representative hue from this lineage
    phase_offset: float       # randomised sine phase
    sine_period: float        # 4-6s
    alpha_mult: float = 1.0   # fade multiplier (1.0 = full, 0.0 = invisible)
    fading_out: bool = False  # True when lineage left top-N


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class Renderer:
    """
    Main rendering controller for the Primordial screensaver.

    Completely decoupled from simulation logic - only reads state
    from the Simulation and renders it to the screen.

    Systems managed here:
    - OceanTheme glyph rendering
    - Kin connection lines (lineage-bucketed)
    - Territory shimmer for dominant lineages
    - AnimationManager (death/birth effects)
    """

    def __init__(
        self,
        screen: pygame.Surface,
        settings: Settings,
        debug: bool = False,
    ) -> None:
        self.screen = screen
        self.settings = settings
        self.debug_enabled = debug
        self.display_width = screen.get_width()
        self.display_height = screen.get_height()
        self.width = self.display_width
        self.height = self.display_height
        self._frame_surf = pygame.Surface((self.width, self.height))
        self._target_surface = self._frame_surf

        # Initialize theme
        self.theme: Theme = get_theme(settings.visual_theme)

        # Create ambient particles
        self.ambient_particles: list[AmbientParticle] = (
            self.theme.create_ambient_particles(self.width, self.height, 30)
        )

        # Initialize HUD
        self.hud = HUD(font_size=16)
        self.hud.visible = settings.show_hud

        # Time tracking for animations
        self.start_time = time.time()

        # FPS tracking
        self.frame_times: deque[float] = deque(maxlen=60)
        self.fps = 0.0
        self._fps_history: deque[float] = deque(maxlen=240)
        self._population_history: deque[int] = deque(maxlen=240)
        self._debug_font = pygame.font.Font(None, 18)
        self._overlay_title_font = pygame.font.Font(None, 72)
        self._overlay_body_font = pygame.font.Font(None, 32)
        self._overlay_small_font = pygame.font.Font(None, 24)
        self._debug_timing: dict[str, float] = {}
        self._external_debug_metrics: dict[str, float] = {}

        # Stub mode/theme detection — all four sim modes are now implemented
        _IMPLEMENTED_MODES = {"energy", "predator_prey", "boids", "drift"}
        self._is_stub_mode = settings.sim_mode not in _IMPLEMENTED_MODES
        self._is_stub_theme = settings.visual_theme != "ocean"

        # Animation manager
        self.animation_manager = AnimationManager(
            num_particles=settings.death_particle_count
        )

        # Territory shimmer state: lineage_id → ShimmerState
        self._shimmer_states: dict[int, ShimmerState] = {}

        # Pre-allocated full-screen overlay surfaces (cleared each frame, not recreated)
        self._line_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._attack_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._shimmer_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._predator_highlight_surf = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA
        )

        # Cached static composition layers.
        self._zone_surf_cached: pygame.Surface | None = None
        self._zone_label_surf_cached: pygame.Surface | None = None
        self._frozen_link_surf_cached: pygame.Surface | None = None
        self._game_over_overlay_cache_key: tuple[object, ...] | None = None
        self._game_over_overlay_cache: pygame.Surface | None = None
        self.show_predator_highlight = False

        self.settings_overlay = SettingsOverlay(settings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_theme(self, theme_name: str) -> None:
        """Change the visual theme."""
        self.theme = get_theme(theme_name)
        self.ambient_particles = self.theme.create_ambient_particles(
            self.width, self.height, 30
        )
        self._is_stub_theme = theme_name != "ocean"
        self._invalidate_static_caches()

    def set_mode(self, mode_name: str) -> None:
        """Update stub detection when sim mode changes."""
        _IMPLEMENTED_MODES = {"energy", "predator_prey", "boids", "drift"}
        self._is_stub_mode = mode_name not in _IMPLEMENTED_MODES
        self._invalidate_static_caches()

    def set_external_debug_metrics(self, metrics: dict[str, float]) -> None:
        """Attach outer-loop timing metrics for debug and summary consumers."""
        self._external_debug_metrics = metrics

    def resize(
        self, width: int, height: int, screen: pygame.Surface | None = None
    ) -> None:
        """Resize logical world-space surfaces and refresh display presentation."""
        self.width = width
        self.height = height
        if screen is not None:
            self.screen = screen
        self.display_width, self.display_height = self.screen.get_size()
        self._frame_surf = pygame.Surface((self.width, self.height))
        self._target_surface = self._frame_surf

        self._line_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._attack_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._shimmer_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        self._predator_highlight_surf = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA
        )
        self._shimmer_states.clear()
        self._invalidate_static_caches()
        self.ambient_particles = self.theme.create_ambient_particles(
            self.width, self.height, 30
        )
        if isinstance(self.theme, OceanTheme):
            self.theme.invalidate_runtime_caches()
            self.theme._trail_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

    def reset_runtime_state(self) -> None:
        """Clear renderer-only transient state after an in-process world swap."""
        self.animation_manager = AnimationManager(
            num_particles=self.settings.death_particle_count
        )
        self._shimmer_states.clear()
        self.frame_times.clear()
        self.fps = 0.0
        self._fps_history.clear()
        self._population_history.clear()
        self._external_debug_metrics = {}
        self._invalidate_static_caches()
        if isinstance(self.theme, OceanTheme):
            self.theme.invalidate_runtime_caches()
            self.theme._trail_surf = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

    def _invalidate_static_caches(self) -> None:
        """Clear cached surfaces tied to world geometry or presentation state."""
        self._zone_surf_cached = None
        self._zone_label_surf_cached = None
        self._frozen_link_surf_cached = None
        self._game_over_overlay_cache_key = None
        self._game_over_overlay_cache = None

    def blit_presentation_overlay(self, overlay: pygame.Surface) -> None:
        """Composite a logical-space overlay onto the active display surface."""
        if overlay.get_size() != (self.width, self.height):
            raise ValueError(
                "Presentation overlay must match renderer logical size "
                f"{self.width}x{self.height}, got {overlay.get_width()}x{overlay.get_height()}."
            )
        if (self.display_width, self.display_height) == (self.width, self.height):
            self.screen.blit(overlay, (0, 0))
            return
        scaled = pygame.transform.scale(
            overlay, (self.display_width, self.display_height)
        )
        self.screen.blit(scaled, (0, 0))

    def draw(self, simulation: Simulation) -> dict[str, float]:
        """
        Render the current simulation state.

        Args:
            simulation: Simulation instance to render.
        """
        frame_t0 = time.perf_counter()
        timings: dict[str, float] = {}
        target = self._frame_surf
        self._target_surface = target

        current_time = time.time()
        anim_time = current_time - self.start_time
        dt_real = self._update_fps(current_time)
        self._fps_history.append(self.fps)
        self._population_history.append(simulation.population)
        is_frozen_world = simulation.paused or simulation.predator_prey_game_over_active
        if not is_frozen_world:
            self._frozen_link_surf_cached = None

        # --- Process simulation events → create animations ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme):
            get_color = lambda g: self.theme.get_creature_color(g.hue, g.saturation)
        else:
            get_color = lambda g: (150, 150, 200)

        self.animation_manager.process_events(
            simulation.death_events,
            simulation.birth_events,
            get_color,
        )

        # Cosmic ray visual effects
        for cx, cy in simulation.cosmic_ray_events:
            self.animation_manager.add_cosmic_ray(cx, cy)
        simulation.cosmic_ray_events.clear()

        simulation.death_events.clear()
        simulation.birth_events.clear()
        timings["events_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Clear screen ---
        t0 = time.perf_counter()
        target.fill(self.theme.background_color)
        timings["clear_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Ambient particles ---
        t0 = time.perf_counter()
        self.theme.render_ambient(target, self.ambient_particles, anim_time)
        timings["ambient_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Zone backgrounds (very faint atmospheric gradient circles) ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme):
            self._draw_zone_backgrounds(simulation)
            if self.hud.visible:
                self._draw_zone_labels(simulation)
        timings["zones_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Territory shimmer (beneath creatures) ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme):
            self._draw_territory_shimmer(simulation, anim_time, dt_real)
        timings["territory_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Food particles ---
        t0 = time.perf_counter()
        for food in simulation.food_manager:
            self.theme.render_food(target, food, anim_time)
        timings["food_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Kin/flock connection lines (beneath creatures) ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme):
            if simulation.settings.sim_mode == "boids":
                self._draw_flock_lines(simulation, use_cached=is_frozen_world)
            else:
                self._draw_kin_lines(simulation, use_cached=is_frozen_world)
        timings["links_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Creature trails (batched onto shared surface, then blitted once) ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme):
            if (self.theme._trail_surf is None or
                    self.theme._trail_surf.get_size() != (self.width, self.height)):
                self.theme._trail_surf = pygame.Surface(
                    (self.width, self.height), pygame.SRCALPHA
                )
            self.theme._trail_surf.fill((0, 0, 0, 0))
            for creature in simulation.creatures:
                birth_scale = self.animation_manager.get_birth_scale(creature)
                scale = birth_scale if birth_scale is not None else 1.0
                self.theme.render_creature_trail(creature, anim_time, scale=scale)
            target.blit(self.theme._trail_surf, (0, 0))
        timings["trails_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Creatures ---
        t0 = time.perf_counter()
        for creature in simulation.creatures:
            birth_scale = self.animation_manager.get_birth_scale(creature)
            scale = birth_scale if birth_scale is not None else 1.0
            self.theme.render_creature(target, creature, anim_time, scale=scale)
        timings["creatures_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Predator locator highlight (hold P) ---
        t0 = time.perf_counter()
        self._draw_predator_highlights(simulation, anim_time)
        timings["predator_highlights_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Attack lines (drawn above creatures, very faint) ---
        t0 = time.perf_counter()
        if isinstance(self.theme, OceanTheme) and simulation.active_attacks:
            self._draw_attack_lines(simulation)
        timings["attacks_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Animation effects (death bursts etc.) ---
        t0 = time.perf_counter()
        self.animation_manager.tick_and_draw(target)
        timings["anim_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- Stub overlay ---
        t0 = time.perf_counter()
        self._draw_stub_overlay(simulation)
        timings["stub_ms"] = (time.perf_counter() - t0) * 1000.0

        # --- HUD ---
        t0 = time.perf_counter()
        debug_lines = self._build_debug_lines(timings) if self.debug_enabled else None
        self.hud.render(target, simulation, self.fps, debug_lines=debug_lines)
        timings["hud_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        self._draw_predator_prey_game_over_overlay(simulation)
        timings["overlay_ms"] = (time.perf_counter() - t0) * 1000.0

        t0 = time.perf_counter()
        if self.settings_overlay.visible or self.settings_overlay.fade > 0:
            self.settings_overlay.update()
            self.settings_overlay.draw(target)
        timings["settings_ms"] = (time.perf_counter() - t0) * 1000.0

        timings["draw_total_ms"] = (time.perf_counter() - frame_t0) * 1000.0
        if self.debug_enabled:
            self._debug_timing = timings
            self._draw_debug_graph_overlay(simulation)
        if (self.display_width, self.display_height) == (self.width, self.height):
            self.screen.blit(target, (0, 0))
        else:
            pygame.transform.scale(
                target,
                (self.display_width, self.display_height),
                self.screen,
            )
        return dict(timings)

    def toggle_hud(self) -> None:
        """Toggle HUD visibility."""
        self.hud.toggle()
        self.settings.show_hud = self.hud.visible
        self._zone_label_surf_cached = None

    def toggle_settings_overlay(self) -> None:
        """Open/close settings overlay."""
        if self.settings_overlay.visible:
            self.settings_overlay.close()
        else:
            self.settings_overlay.open()

    def set_predator_highlight(self, active: bool) -> None:
        """Toggle the temporary predator locator overlay."""
        self.show_predator_highlight = active

    def _draw_predator_prey_game_over_overlay(self, simulation: "Simulation") -> None:
        """Tint the screen red and present restart details after ecological collapse."""
        if not simulation.predator_prey_game_over_active:
            self._game_over_overlay_cache_key = None
            self._game_over_overlay_cache = None
            return

        stats = simulation.get_predator_prey_stability_stats()
        lines = self._build_predator_prey_game_over_summary_lines(stats)
        dial_values = stats["collapse_dial_values"] or {}
        changed_key = stats["collapse_trial_dial"]
        changed_delta = float(stats["collapse_trial_delta"])
        keys = [key for key in _PREDATOR_PREY_DIAL_LABELS if key in dial_values]
        dial_lines = []
        for key in keys:
            value = float(dial_values[key])
            label = _PREDATOR_PREY_DIAL_LABELS.get(key, key)
            line = f"{label}: {value:.2f}"
            color = (255, 228, 228)
            if key == changed_key and not math.isclose(changed_delta, 0.0, abs_tol=1e-9):
                line = f"{line}  ({changed_delta:+.2f} this run)"
                color = (255, 242, 176)
            dial_lines.append((line, color))

        cache_key = (
            self.width,
            self.height,
            tuple(lines),
            tuple(dial_lines),
        )
        if cache_key != self._game_over_overlay_cache_key:
            self._game_over_overlay_cache_key = cache_key
            self._game_over_overlay_cache = self._build_predator_prey_game_over_overlay_surface(
                lines=lines,
                dial_lines=dial_lines,
            )

        if self._game_over_overlay_cache is not None:
            self._target_surface.blit(self._game_over_overlay_cache, (0, 0))

    def _build_predator_prey_game_over_overlay_surface(
        self,
        *,
        lines: list[tuple[str, tuple[int, int, int]]],
        dial_lines: list[tuple[str, tuple[int, int, int]]],
    ) -> pygame.Surface:
        """Build the cached game-over overlay for the current collapse snapshot."""
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((160, 12, 18, 120))

        title = self._overlay_title_font.render("GAME OVER", True, (255, 236, 236))
        title_pos = (
            (self.width - title.get_width()) // 2,
            max(40, self.height // 5),
        )
        overlay.blit(title, title_pos)

        y = title_pos[1] + title.get_height() + 20
        summary_font = self._overlay_small_font
        panel_width = min(self.width - 80, 760)
        for line, color in lines:
            text = summary_font.render(line, True, color)
            panel = pygame.Surface(
                (panel_width, text.get_height() + 10),
                pygame.SRCALPHA,
            )
            panel.fill((24, 4, 6, 150))
            text_x = max(12, (panel_width - text.get_width()) // 2)
            panel.blit(text, (text_x, 5))
            overlay.blit(panel, ((self.width - panel_width) // 2, y - 5))
            y += text.get_height() + 12

        if not dial_lines:
            return overlay

        dial_title = self._overlay_small_font.render(
            "Run dials",
            True,
            (255, 236, 236),
        )
        dial_title_y = y + 4
        overlay.blit(
            dial_title,
            ((self.width - dial_title.get_width()) // 2, dial_title_y),
        )

        columns = 2
        rows = math.ceil(len(dial_lines) / columns)
        cell_width = min(320, max(220, (self.width - 120) // columns))
        start_x = (self.width - (cell_width * columns)) // 2
        start_y = dial_title_y + dial_title.get_height() + 12

        for index, (line, color) in enumerate(dial_lines):
            row = index % rows
            col = index // rows
            x = start_x + (col * cell_width)
            y = start_y + (row * 28)
            text = self._overlay_small_font.render(line, True, color)
            panel = pygame.Surface(
                (cell_width - 10, text.get_height() + 8),
                pygame.SRCALPHA,
            )
            panel.fill((24, 4, 6, 150))
            panel.blit(text, (8, 4))
            overlay.blit(panel, (x, y))

        return overlay

    def _build_predator_prey_game_over_summary_lines(
        self,
        stats: dict[str, object],
    ) -> list[tuple[str, tuple[int, int, int]]]:
        record_suffix = "  NEW BEST" if stats["collapse_was_new_highest"] else ""
        survival_color = (
            (255, 242, 176)
            if stats["collapse_beat_average"]
            else (255, 228, 228)
        )
        beat_suffix = "  BEAT AVG" if stats["collapse_beat_average"] else ""
        modifier_line = (
            "Adjustment step: "
            f"{float(stats['adjustment_step_multiplier']):.2f}x "
            f"(+{float(stats['adjustment_step_increase_percent']):.0f}%)"
            f"   Streak: {int(stats['non_improving_run_streak'])}"
        )
        return [
            (
                f"Cause: {stats['collapse_cause'] or 'Unknown'}",
                (255, 228, 228),
            ),
            (
                "Seed: "
                f"{stats['current_seed'] if stats['current_seed'] is not None else '—'}"
                f"   Predators: {stats['collapse_predators']}   Prey: {stats['collapse_prey']}",
                (255, 228, 228),
            ),
            (
                f"Survival ticks: {stats['survival_ticks']}   "
                f"Rolling median: {float(stats['collapse_rolling_average']):.0f}{beat_suffix}",
                survival_color,
            ),
            (
                f"Highest ticks: {stats['highest_survival_ticks']}{record_suffix}",
                (255, 228, 228),
            ),
            (
                modifier_line,
                (255, 228, 228),
            ),
            (
                f"Restart in: {math.ceil(float(stats['restart_countdown_seconds']))}s   Space: skip",
                (255, 228, 228),
            ),
        ]

    # ------------------------------------------------------------------
    # Zone backgrounds
    # ------------------------------------------------------------------

    def _draw_zone_backgrounds(self, simulation: "Simulation") -> None:
        """
        Draw atmospheric radial gradient circles for each environmental zone.

        Zones never move, so the surface is rendered once and cached.
        """
        if self._zone_surf_cached is None:
            self._zone_surf_cached = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            for zone in simulation.zone_manager.zones:
                color = _ZONE_BG_COLORS.get(zone.zone_type, (60, 60, 60))
                radius = int(zone.radius)
                cx = int(zone.x)
                cy = int(zone.y)

                layers = 8
                intensity = self.settings.zone_background_intensity
                for i in range(layers, 0, -1):
                    t = i / layers
                    layer_radius = int(radius * t)
                    layer_alpha = int(22 * intensity * (0.35 + 0.65 * (t ** 1.8)))
                    if layer_alpha <= 0 or layer_radius <= 0:
                        continue
                    pygame.draw.circle(
                        self._zone_surf_cached,
                        (*color, layer_alpha),
                        (cx, cy),
                        layer_radius,
                    )

        self._target_surface.blit(self._zone_surf_cached, (0, 0))

    def _draw_predator_highlights(
        self, simulation: "Simulation", anim_time: float
    ) -> None:
        """Draw a cheap hold-to-locate overlay around current predators."""
        if (
            not self.show_predator_highlight
            or simulation.settings.sim_mode != "predator_prey"
        ):
            return

        predators = [
            creature for creature in simulation.creatures if creature.species == "predator"
        ]
        if not predators:
            return

        self._predator_highlight_surf.fill((0, 0, 0, 0))
        pulse_seconds = self.settings.predator_highlight_pulse_seconds
        alpha = self.settings.predator_highlight_alpha
        radius_scale = self.settings.predator_highlight_radius_scale

        for creature in predators:
            if isinstance(self.theme, OceanTheme):
                base_color = self.theme.get_creature_color(
                    creature.genome.hue, creature.genome.saturation
                )
            else:
                base_color = (255, 220, 180)
            accent_color = tuple(
                min(255, int(channel + (255 - channel) * 0.55)) for channel in base_color
            )
            pulse = 0.5 + 0.5 * math.sin(
                (2 * math.pi * anim_time / pulse_seconds) + creature._glyph_phase
            )
            ring_radius = max(
                10, int(creature.get_radius() * radius_scale + 6.0 * pulse)
            )
            outer_radius = ring_radius + max(3, int(4.0 * pulse))
            ring_width = max(2, int(ring_radius * 0.18))
            tick_length = max(6, int(ring_radius * 0.55))
            center = (int(creature.x), int(creature.y))

            pygame.draw.circle(
                self._predator_highlight_surf,
                (*accent_color, int(alpha * 0.35)),
                center,
                outer_radius,
                ring_width + 1,
            )
            pygame.draw.circle(
                self._predator_highlight_surf,
                (*accent_color, alpha),
                center,
                ring_radius,
                ring_width,
            )

            cx, cy = center
            tick_gap = ring_radius + 2
            pygame.draw.line(
                self._predator_highlight_surf,
                (*accent_color, int(alpha * 0.80)),
                (cx, cy - tick_gap),
                (cx, cy - tick_gap - tick_length),
                2,
            )
            pygame.draw.line(
                self._predator_highlight_surf,
                (*accent_color, int(alpha * 0.80)),
                (cx + tick_gap, cy),
                (cx + tick_gap + tick_length, cy),
                2,
            )
            pygame.draw.line(
                self._predator_highlight_surf,
                (*accent_color, int(alpha * 0.80)),
                (cx, cy + tick_gap),
                (cx, cy + tick_gap + tick_length),
                2,
            )
            pygame.draw.line(
                self._predator_highlight_surf,
                (*accent_color, int(alpha * 0.80)),
                (cx - tick_gap, cy),
                (cx - tick_gap - tick_length, cy),
                2,
            )

        self._target_surface.blit(self._predator_highlight_surf, (0, 0))

    def _draw_zone_labels(self, simulation: "Simulation") -> None:
        """Draw subtle zone labels to support ecological review."""
        if self._zone_label_surf_cached is None:
            self._zone_label_surf_cached = pygame.Surface(
                (self.width, self.height), pygame.SRCALPHA
            )
            for zone in simulation.zone_manager.zones:
                label = _ZONE_LABELS.get(zone.zone_type)
                if not label:
                    continue
                text_surface = self._debug_font.render(label, True, (220, 235, 245))
                panel = pygame.Surface(
                    (text_surface.get_width() + 10, text_surface.get_height() + 6),
                    pygame.SRCALPHA,
                )
                panel.fill((8, 16, 26, 120))
                panel.blit(text_surface, (5, 3))
                pos = (
                    int(zone.x - panel.get_width() / 2),
                    int(zone.y - panel.get_height() / 2),
                )
                self._zone_label_surf_cached.blit(panel, pos)
        self._target_surface.blit(self._zone_label_surf_cached, (0, 0))

    # ------------------------------------------------------------------
    # Attack lines
    # ------------------------------------------------------------------

    def _draw_attack_lines(self, simulation: "Simulation") -> None:
        """
        Draw very faint thin lines between predator and prey during attacks.
        """
        if not simulation.active_attacks:
            return

        self._attack_surf.fill((0, 0, 0, 0))

        for ax, ay, tx, ty, hue in simulation.active_attacks:
            if isinstance(self.theme, OceanTheme):
                color = self.theme.get_creature_color(hue, 0.8)
            else:
                color = (200, 200, 200)

            pygame.draw.line(
                self._attack_surf,
                (*color, 40),
                (int(ax), int(ay)),
                (int(tx), int(ty)),
                1,
            )

        self._target_surface.blit(self._attack_surf, (0, 0))

    # ------------------------------------------------------------------
    # Kin connection lines
    # ------------------------------------------------------------------

    def _draw_kin_lines(self, simulation: Simulation, *, use_cached: bool = False) -> None:
        """
        Draw faint connection lines between creatures of the same lineage.

        Uses lineage buckets plus a local spatial grid to avoid dense O(n²)
        comparisons for widely spread groups.
        Only draws if lineage has 3+ members on screen.
        Alpha is inversely proportional to distance.
        """
        if use_cached and self._frozen_link_surf_cached is not None:
            self._target_surface.blit(self._frozen_link_surf_cached, (0, 0))
            return

        settings = self.settings
        max_dist = settings.kin_line_max_distance

        # Bucket creatures by lineage_id
        lineage_buckets: dict[int, list] = defaultdict(list)
        for c in simulation.creatures:
            lineage_buckets[c.lineage_id].append(c)

        # Clear the pre-allocated line surface
        self._line_surf.fill((0, 0, 0, 0))
        has_lines = False

        for lineage_id, members in lineage_buckets.items():
            if len(members) < settings.kin_line_min_group:
                continue
            has_lines = True

            # Compute representative hue from first member
            hue = members[0].genome.hue
            if isinstance(self.theme, OceanTheme):
                base_color = self.theme.get_creature_color(hue, members[0].genome.saturation)
            else:
                base_color = (200, 200, 200)
            self._draw_connection_group(
                members,
                base_color=base_color,
                max_dist=max_dist,
                alpha_min=15,
                alpha_max=30,
            )

        if not has_lines:
            self._frozen_link_surf_cached = None
            return

        if use_cached:
            self._frozen_link_surf_cached = self._line_surf.copy()
        self._target_surface.blit(self._line_surf, (0, 0))

    # ------------------------------------------------------------------
    # Flock connection lines (boids mode)
    # ------------------------------------------------------------------

    def _draw_flock_lines(self, simulation: "Simulation", *, use_cached: bool = False) -> None:
        """
        Draw faint lines between creatures in the same flock (boids mode).

        Same visual treatment as kin lines but grouped by flock_id.
        Lone creatures outside any flock are not connected.
        """
        if use_cached and self._frozen_link_surf_cached is not None:
            self._target_surface.blit(self._frozen_link_surf_cached, (0, 0))
            return

        settings = self.settings
        max_dist = settings.kin_line_max_distance * 1.5

        # Bucket by flock_id
        flock_buckets: dict[int, list] = defaultdict(list)
        for c in simulation.creatures:
            if c.flock_id != -1:
                flock_buckets[c.flock_id].append(c)

        self._line_surf.fill((0, 0, 0, 0))
        has_lines = False

        for flock_id, members in flock_buckets.items():
            if len(members) < 2:
                continue
            has_lines = True

            hue = members[0].genome.hue
            if isinstance(self.theme, OceanTheme):
                base_color = self.theme.get_creature_color(hue, 0.6)
            else:
                base_color = (200, 200, 200)
            self._draw_connection_group(
                members,
                base_color=base_color,
                max_dist=max_dist,
                alpha_min=10,
                alpha_max=25,
            )

        if not has_lines:
            self._frozen_link_surf_cached = None
            return

        if use_cached:
            self._frozen_link_surf_cached = self._line_surf.copy()
        self._target_surface.blit(self._line_surf, (0, 0))

    def _draw_connection_group(
        self,
        members: list,
        *,
        base_color: tuple[int, int, int],
        max_dist: float,
        alpha_min: int,
        alpha_max: int,
    ) -> None:
        """Draw near-neighbour lines for one lineage/flock group."""
        max_dist_sq = max_dist * max_dist
        cell_size = max(1.0, max_dist)
        grid_w = max(1, int(math.ceil(self.width / cell_size)))
        grid_h = max(1, int(math.ceil(self.height / cell_size)))
        cell_buckets: dict[tuple[int, int], list] = defaultdict(list)

        for creature in members:
            key = (
                int(creature.x // cell_size) % grid_w,
                int(creature.y // cell_size) % grid_h,
            )
            cell_buckets[key].append(creature)

        for key, bucket_members in cell_buckets.items():
            self._draw_connection_pairs(
                bucket_members,
                bucket_members,
                same_bucket=True,
                base_color=base_color,
                max_dist=max_dist,
                max_dist_sq=max_dist_sq,
                alpha_min=alpha_min,
                alpha_max=alpha_max,
            )
            for off_x, off_y in ((1, -1), (1, 0), (1, 1), (0, 1)):
                neighbor_key = ((key[0] + off_x) % grid_w, (key[1] + off_y) % grid_h)
                if neighbor_key == key:
                    continue
                neighbor_members = cell_buckets.get(neighbor_key)
                if not neighbor_members:
                    continue
                self._draw_connection_pairs(
                    bucket_members,
                    neighbor_members,
                    same_bucket=False,
                    base_color=base_color,
                    max_dist=max_dist,
                    max_dist_sq=max_dist_sq,
                    alpha_min=alpha_min,
                    alpha_max=alpha_max,
                )

    def _draw_connection_pairs(
        self,
        left_members: list,
        right_members: list,
        *,
        same_bucket: bool,
        base_color: tuple[int, int, int],
        max_dist: float,
        max_dist_sq: float,
        alpha_min: int,
        alpha_max: int,
    ) -> None:
        """Draw qualifying line pairs between one or two cell buckets."""
        for left_index, left in enumerate(left_members):
            start_index = left_index + 1 if same_bucket else 0
            for right in right_members[start_index:]:
                dx = right.x - left.x
                dy = right.y - left.y
                if abs(dx) > self.width / 2:
                    dx -= math.copysign(self.width, dx)
                if abs(dy) > self.height / 2:
                    dy -= math.copysign(self.height, dy)
                dist_sq = dx * dx + dy * dy
                if dist_sq > max_dist_sq:
                    continue
                dist = math.sqrt(dist_sq)
                alpha = int(alpha_max * (1.0 - dist / max_dist))
                alpha = max(alpha_min, min(alpha_max, alpha))
                pygame.draw.line(
                    self._line_surf,
                    (*base_color, alpha),
                    (int(left.x), int(left.y)),
                    (int(right.x), int(right.y)),
                    1,
                )

    # ------------------------------------------------------------------
    # Territory shimmer
    # ------------------------------------------------------------------

    def _draw_territory_shimmer(
        self, simulation: Simulation, anim_time: float, dt_real: float
    ) -> None:
        """
        Render soft shimmer regions for the top N most populous lineages.

        Each dominant lineage gets a pulsing radial gradient ellipse at
        its centroid. Shimmers lerp their centroid toward the true centroid
        and fade out gracefully when lineages drop out of the top N.
        """
        settings = self.settings
        top_n = settings.territory_top_n
        lerp = settings.territory_shimmer_lerp
        fade_frames = settings.territory_fade_seconds * 60

        lineage_stats: dict[int, dict[str, float]] = {}
        for creature in simulation.creatures:
            stats = lineage_stats.get(creature.lineage_id)
            if stats is None:
                stats = {
                    "count": 0.0,
                    "sum_x": 0.0,
                    "sum_y": 0.0,
                    "sum_x2": 0.0,
                    "sum_y2": 0.0,
                    "hue": creature.genome.hue,
                }
                lineage_stats[creature.lineage_id] = stats
            stats["count"] += 1.0
            stats["sum_x"] += creature.x
            stats["sum_y"] += creature.y
            stats["sum_x2"] += creature.x * creature.x
            stats["sum_y2"] += creature.y * creature.y

        top_ids = set(
            sorted(
                lineage_stats.keys(),
                key=lambda lid: -lineage_stats[lid]["count"],
            )[:top_n]
        )

        # Update or create shimmer states for dominant lineages
        for lid in top_ids:
            stats = lineage_stats.get(lid)
            if not stats:
                continue

            count = max(1.0, stats["count"])
            cx = stats["sum_x"] / count
            cy = stats["sum_y"] / count
            sx = math.sqrt(max(0.0, (stats["sum_x2"] / count) - (cx * cx))) + 30
            sy = math.sqrt(max(0.0, (stats["sum_y2"] / count) - (cy * cy))) + 30
            hue = stats["hue"]

            if lid in self._shimmer_states:
                state = self._shimmer_states[lid]
                # Lerp centroid
                state.centroid_x += (cx - state.centroid_x) * lerp
                state.centroid_y += (cy - state.centroid_y) * lerp
                state.spread_x += (sx - state.spread_x) * lerp
                state.spread_y += (sy - state.spread_y) * lerp
                state.hue = hue
                state.fading_out = False
                state.alpha_mult = min(1.0, state.alpha_mult + 2.0 / fade_frames)
            else:
                from .animations import _render_rng
                self._shimmer_states[lid] = ShimmerState(
                    lineage_id=lid,
                    centroid_x=cx,
                    centroid_y=cy,
                    spread_x=sx,
                    spread_y=sy,
                    hue=hue,
                    phase_offset=_render_rng.uniform(0, math.pi * 2),
                    sine_period=_render_rng.uniform(4.0, 6.0),
                    alpha_mult=0.0,
                )

        # Mark out-of-top lineages for fade-out
        for lid, state in list(self._shimmer_states.items()):
            if lid not in top_ids:
                state.fading_out = True
                state.alpha_mult -= 1.0 / fade_frames
                if state.alpha_mult <= 0.0:
                    del self._shimmer_states[lid]

        # Render shimmer ellipses
        if not self._shimmer_states:
            return

        self._shimmer_surf.fill((0, 0, 0, 0))

        for lid, state in self._shimmer_states.items():
            if state.alpha_mult <= 0.0:
                continue

            # Pulsing alpha: base 12-25, sine wave at ~1/period Hz
            pulse = math.sin(anim_time * (2 * math.pi / state.sine_period) + state.phase_offset)
            base_alpha = int((12 + pulse * 6) * state.alpha_mult)
            base_alpha = max(0, min(30, base_alpha))

            if base_alpha == 0:
                continue

            # Color from lineage hue
            if isinstance(self.theme, OceanTheme):
                color = self.theme.get_creature_color(state.hue, 0.8)
            else:
                color = (150, 150, 220)

            rx = int(state.spread_x * 2.5)
            ry = int(state.spread_y * 2.5)
            cx = int(state.centroid_x)
            cy = int(state.centroid_y)
            if rx < 2 or ry < 2:
                continue

            layers = 5
            for i in range(layers, 0, -1):
                t = i / layers
                layer_alpha = int(base_alpha * t * t)
                layer_rx = int(rx * (layers - i + 1) / layers)
                layer_ry = int(ry * (layers - i + 1) / layers)
                if layer_rx < 2 or layer_ry < 2:
                    continue
                rect = pygame.Rect(
                    cx - layer_rx,
                    cy - layer_ry,
                    layer_rx * 2,
                    layer_ry * 2,
                )
                pygame.draw.ellipse(self._shimmer_surf, (*color, layer_alpha), rect)

        self._target_surface.blit(self._shimmer_surf, (0, 0))

    # ------------------------------------------------------------------
    # FPS and stub overlay helpers
    # ------------------------------------------------------------------

    def _build_debug_lines(self, timings: dict[str, float]) -> list[str]:
        """Build compact debug timing lines for the HUD."""
        event_ms = self._external_debug_metrics.get("event_ms", 0.0)
        sim_ms = self._external_debug_metrics.get("sim_ms", 0.0)
        draw_ms = timings.get("draw_total_ms", self._debug_timing.get("draw_total_ms", 0.0))
        present_ms = self._external_debug_metrics.get("present_ms", 0.0)
        pacing_ms = self._external_debug_metrics.get("pacing_ms", 0.0)
        frame_ms = self._external_debug_metrics.get("frame_ms", 0.0)
        eff_fps = self._external_debug_metrics.get("effective_fps", 0.0)
        sim_steps = int(self._external_debug_metrics.get("sim_steps", 0.0))
        clamp_frames = int(self._external_debug_metrics.get("clamp_frames", 0.0))
        dropped_ms = self._external_debug_metrics.get("dropped_ms", 0.0)
        display_width = int(self._external_debug_metrics.get("display_width", 0.0))
        display_height = int(self._external_debug_metrics.get("display_height", 0.0))
        world_width = int(self._external_debug_metrics.get("world_width", 0.0))
        world_height = int(self._external_debug_metrics.get("world_height", 0.0))
        return [
            "Dbg frame: evt {evt:.2f}ms  sim {sim:.2f}ms  draw {draw:.2f}ms  "
            "flip {flip:.2f}ms".format(
                evt=event_ms,
                sim=sim_ms,
                draw=draw_ms,
                flip=present_ms,
            ),
            "Dbg loop: frame {frame:.2f}ms  pace {pace:.2f}ms  fps {fps:.1f}  "
            "steps {steps}  drops {drops}".format(
                frame=frame_ms,
                pace=pacing_ms,
                fps=eff_fps,
                steps=sim_steps,
                drops=clamp_frames,
            ),
            f"Dbg debt: dropped {dropped_ms:.2f}ms",
            "Dbg sizes: display {dw}x{dh}  world {ww}x{wh}".format(
                dw=display_width,
                dh=display_height,
                ww=world_width,
                wh=world_height,
            ),
            "Dbg render: clear {clear:.2f}  amb {amb:.2f}  zones {zones:.2f}  "
            "terr {terr:.2f}  food {food:.2f}  links {links:.2f}".format(
                clear=timings.get("clear_ms", 0.0),
                amb=timings.get("ambient_ms", 0.0),
                zones=timings.get("zones_ms", 0.0),
                terr=timings.get("territory_ms", 0.0),
                food=timings.get("food_ms", 0.0),
                links=timings.get("links_ms", 0.0),
            ),
            "Dbg render: trails {trails:.2f}  creatures {creatures:.2f}  "
            "attacks {attacks:.2f}  anim {anim:.2f}  hud {hud:.2f}".format(
                trails=timings.get("trails_ms", 0.0),
                creatures=timings.get("creatures_ms", 0.0),
                attacks=timings.get("attacks_ms", 0.0),
                anim=timings.get("anim_ms", 0.0),
                hud=timings.get("hud_ms", 0.0),
            ),
        ]

    def _draw_debug_graph_overlay(self, simulation: "Simulation") -> None:
        """Draw FPS and population history graphs in debug mode."""
        panel_w = 320
        panel_h = 170
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((5, 10, 20, 190))
        pygame.draw.rect(panel, (90, 150, 210), panel.get_rect(), 1)

        label = self._debug_font.render("DEBUG", True, (180, 230, 255))
        panel.blit(label, (8, 6))

        fps_rect = pygame.Rect(10, 26, 300, 56)
        pop_rect = pygame.Rect(10, 98, 300, 56)
        pygame.draw.rect(panel, (30, 40, 60), fps_rect, 1)
        pygame.draw.rect(panel, (30, 40, 60), pop_rect, 1)

        if len(self._fps_history) > 1:
            points: list[tuple[int, int]] = []
            target = max(1.0, float(self.settings.target_fps))
            max_fps = max(target * 1.2, max(self._fps_history))
            for i, v in enumerate(self._fps_history):
                x = fps_rect.left + int(i * (fps_rect.width - 1) / (len(self._fps_history) - 1))
                y = fps_rect.bottom - int((v / max_fps) * (fps_rect.height - 2))
                points.append((x, y))
            if len(points) > 1:
                pygame.draw.lines(panel, (120, 230, 170), False, points, 1)

            target_y = fps_rect.bottom - int((target / max_fps) * (fps_rect.height - 2))
            pygame.draw.line(panel, (230, 200, 120), (fps_rect.left, target_y), (fps_rect.right, target_y), 1)

        if len(self._population_history) > 1:
            points = []
            max_pop = max(1, max(self._population_history), self.settings.max_population)
            for i, v in enumerate(self._population_history):
                x = pop_rect.left + int(i * (pop_rect.width - 1) / (len(self._population_history) - 1))
                y = pop_rect.bottom - int((v / max_pop) * (pop_rect.height - 2))
                points.append((x, y))
            if len(points) > 1:
                pygame.draw.lines(panel, (140, 180, 255), False, points, 1)

        fps_text = self._debug_font.render(
            f"FPS {self.fps:5.1f} / {self.settings.target_fps}",
            True,
            (220, 245, 255),
        )
        pop_text = self._debug_font.render(
            f"Pop {simulation.population:4d}",
            True,
            (220, 245, 255),
        )
        panel.blit(fps_text, (14, 28))
        panel.blit(pop_text, (14, 100))
        self._target_surface.blit(panel, (10, 10))

    def _update_fps(self, current_time: float) -> float:
        """Update FPS calculation. Returns dt in seconds."""
        self.frame_times.append(current_time)

        if len(self.frame_times) >= 2:
            elapsed = self.frame_times[-1] - self.frame_times[0]
            if elapsed > 0:
                self.fps = (len(self.frame_times) - 1) / elapsed
            return self.frame_times[-1] - self.frame_times[-2]
        return 1.0 / 60.0

    def _draw_stub_overlay(self, simulation: Simulation) -> None:
        """Draw 'coming soon' overlay for stub modes/themes."""
        messages = []

        if self._is_stub_mode:
            messages.append(f"Mode '{simulation.settings.sim_mode}' coming soon")
        if self._is_stub_theme:
            messages.append(f"Theme '{simulation.settings.visual_theme}' coming soon")

        if not messages:
            return

        font = pygame.font.Font(None, 32)
        y = 50

        for message in messages:
            shadow = font.render(message, True, (0, 0, 0))
            text = font.render(message, True, (200, 200, 200))

            x = self.width // 2 - text.get_width() // 2
            self._target_surface.blit(shadow, (x + 2, y + 2))
            self._target_surface.blit(text, (x, y))
            y += 40
