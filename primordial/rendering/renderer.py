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
from .themes import AmbientParticle, OceanTheme, Theme, get_theme

# Zone type → background RGB (same palette as zones.py, duplicated here
# so renderer has no import from simulation/)
_ZONE_BG_COLORS: dict[str, tuple[int, int, int]] = {
    "warm_vent":      (180, 90, 10),
    "open_water":     (60, 120, 200),
    "kelp_forest":    (0, 80, 40),
    "hunting_ground": (100, 0, 10),
    "deep_trench":    (15, 5, 80),
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
    ) -> None:
        self.screen = screen
        self.settings = settings
        self.width = screen.get_width()
        self.height = screen.get_height()

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

        # Stub mode/theme detection
        self._is_stub_mode = settings.sim_mode != "energy"
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

        # Cached zone background (zones never move; render once)
        self._zone_surf_cached: pygame.Surface | None = None

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

    def draw(self, simulation: Simulation) -> None:
        """
        Render the current simulation state.

        Args:
            simulation: Simulation instance to render.
        """
        current_time = time.time()
        anim_time = current_time - self.start_time
        dt_real = self._update_fps(current_time)

        # --- Process simulation events → create animations ---
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

        # --- Clear screen ---
        self.screen.fill(self.theme.background_color)

        # --- Ambient particles ---
        self.theme.render_ambient(self.screen, self.ambient_particles, anim_time)

        # --- Zone backgrounds (very faint atmospheric gradient circles) ---
        if isinstance(self.theme, OceanTheme):
            self._draw_zone_backgrounds(simulation)

        # --- Territory shimmer (beneath creatures) ---
        if isinstance(self.theme, OceanTheme):
            self._draw_territory_shimmer(simulation, anim_time, dt_real)

        # --- Food particles ---
        for food in simulation.food_manager:
            self.theme.render_food(self.screen, food, anim_time)

        # --- Kin connection lines (beneath creatures) ---
        if isinstance(self.theme, OceanTheme):
            self._draw_kin_lines(simulation)

        # --- Creature trails (batched onto shared surface, then blitted once) ---
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
            self.screen.blit(self.theme._trail_surf, (0, 0))

        # --- Creatures ---
        for creature in simulation.creatures:
            birth_scale = self.animation_manager.get_birth_scale(creature)
            scale = birth_scale if birth_scale is not None else 1.0
            self.theme.render_creature(self.screen, creature, anim_time, scale=scale)

        # --- Attack lines (drawn above creatures, very faint) ---
        if isinstance(self.theme, OceanTheme) and simulation.active_attacks:
            self._draw_attack_lines(simulation)

        # --- Animation effects (death bursts etc.) ---
        self.animation_manager.tick_and_draw(self.screen)

        # --- Stub overlay ---
        self._draw_stub_overlay(simulation)

        # --- HUD ---
        self.hud.render(self.screen, simulation, self.fps)

    def toggle_hud(self) -> None:
        """Toggle HUD visibility."""
        self.hud.toggle()
        self.settings.show_hud = self.hud.visible

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

                layers = 6
                for i in range(layers, 0, -1):
                    t = i / layers
                    layer_radius = int(radius * t)
                    layer_alpha = int(20 * (t ** 2))
                    if layer_alpha <= 0 or layer_radius <= 0:
                        continue
                    pygame.draw.circle(
                        self._zone_surf_cached,
                        (*color, layer_alpha),
                        (cx, cy),
                        layer_radius,
                    )

        self.screen.blit(self._zone_surf_cached, (0, 0))

    # ------------------------------------------------------------------
    # Attack lines
    # ------------------------------------------------------------------

    def _draw_attack_lines(self, simulation: "Simulation") -> None:
        """
        Draw very faint thin lines between hunter and target during attacks.

        Alpha ~40, coloured by the attacker's hue.  Subtle — just enough to
        feel like energy is flowing between them.
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

        self.screen.blit(self._attack_surf, (0, 0))

    # ------------------------------------------------------------------
    # Kin connection lines
    # ------------------------------------------------------------------

    def _draw_kin_lines(self, simulation: Simulation) -> None:
        """
        Draw faint connection lines between creatures of the same lineage.

        Uses lineage buckets to avoid O(n²) comparisons.
        Only draws if lineage has 3+ members on screen.
        Alpha is inversely proportional to distance.
        """
        settings = self.settings
        max_dist = settings.kin_line_max_distance
        min_group = settings.kin_line_min_group
        max_dist_sq = max_dist * max_dist

        # Bucket creatures by lineage_id
        lineage_buckets: dict[int, list] = defaultdict(list)
        for c in simulation.creatures:
            lineage_buckets[c.lineage_id].append(c)

        # Clear the pre-allocated line surface
        self._line_surf.fill((0, 0, 0, 0))

        for lineage_id, members in lineage_buckets.items():
            if len(members) < min_group:
                continue

            # Compute representative hue from first member
            hue = members[0].genome.hue
            if isinstance(self.theme, OceanTheme):
                base_color = self.theme.get_creature_color(hue, members[0].genome.saturation)
            else:
                base_color = (200, 200, 200)

            # Draw lines for all pairs within max_dist
            n = len(members)
            for i in range(n):
                a = members[i]
                for j in range(i + 1, n):
                    b = members[j]
                    dx = b.x - a.x
                    dy = b.y - a.y
                    # Toroidal shortest path
                    if abs(dx) > self.width / 2:
                        dx -= math.copysign(self.width, dx)
                    if abs(dy) > self.height / 2:
                        dy -= math.copysign(self.height, dy)
                    dist_sq = dx * dx + dy * dy
                    if dist_sq > max_dist_sq:
                        continue

                    dist = math.sqrt(dist_sq)
                    # Alpha inversely proportional to distance (15-30)
                    alpha = int(30 * (1.0 - dist / max_dist))
                    alpha = max(15, min(30, alpha))

                    pygame.draw.line(
                        self._line_surf,
                        (*base_color, alpha),
                        (int(a.x), int(a.y)),
                        (int(b.x), int(b.y)),
                        1,
                    )

        self.screen.blit(self._line_surf, (0, 0))

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

        # Get lineage counts and find top-N
        lineage_counts = simulation.get_lineage_counts()
        top_ids = set(
            sorted(lineage_counts.keys(), key=lambda lid: -lineage_counts[lid])[:top_n]
        )

        # Bucket creatures by lineage
        lineage_creatures: dict[int, list] = defaultdict(list)
        for c in simulation.creatures:
            lineage_creatures[c.lineage_id].append(c)

        # Update or create shimmer states for dominant lineages
        for lid in top_ids:
            members = lineage_creatures.get(lid, [])
            if not members:
                continue

            xs = [c.x for c in members]
            ys = [c.y for c in members]
            cx = sum(xs) / len(xs)
            cy = sum(ys) / len(ys)

            # Spread = std-dev of positions
            sx = math.sqrt(sum((x - cx) ** 2 for x in xs) / len(xs)) + 30
            sy = math.sqrt(sum((y - cy) ** 2 for y in ys) / len(ys)) + 30
            hue = members[0].genome.hue

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
                import random as _random
                self._shimmer_states[lid] = ShimmerState(
                    lineage_id=lid,
                    centroid_x=cx,
                    centroid_y=cy,
                    spread_x=sx,
                    spread_y=sy,
                    hue=hue,
                    phase_offset=_random.uniform(0, math.pi * 2),
                    sine_period=_random.uniform(4.0, 6.0),
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

            # Draw a soft radial gradient ellipse using concentric scaled rects
            rx = int(state.spread_x * 2.5)
            ry = int(state.spread_y * 2.5)
            cx = int(state.centroid_x)
            cy = int(state.centroid_y)

            layers = 5
            for i in range(layers, 0, -1):
                t = i / layers
                layer_alpha = int(base_alpha * t * t)
                layer_rx = int(rx * (layers - i + 1) / layers)
                layer_ry = int(ry * (layers - i + 1) / layers)
                if layer_rx < 2 or layer_ry < 2:
                    continue
                rect = pygame.Rect(cx - layer_rx, cy - layer_ry,
                                   layer_rx * 2, layer_ry * 2)
                pygame.draw.ellipse(self._shimmer_surf, (*color, layer_alpha), rect)

        self.screen.blit(self._shimmer_surf, (0, 0))

    # ------------------------------------------------------------------
    # FPS and stub overlay helpers
    # ------------------------------------------------------------------

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
            self.screen.blit(shadow, (x + 2, y + 2))
            self.screen.blit(text, (x, y))
            y += 40
