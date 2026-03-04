"""Renderer module - main rendering controller."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pygame

from .hud import HUD
from .themes import AmbientParticle, Theme, get_theme

if TYPE_CHECKING:
    from ..settings import Settings
    from ..simulation.simulation import Simulation


class Renderer:
    """
    Main rendering controller for the Primordial screensaver.

    Completely decoupled from simulation logic - only reads state
    from the Simulation and renders it to the screen.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        settings: Settings,
    ) -> None:
        """
        Initialize the renderer.

        Args:
            screen: Pygame display surface.
            settings: Application settings.
        """
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
        self.frame_times: list[float] = []
        self.fps = 0.0

        # Stub mode overlay tracking
        self._is_stub_mode = settings.sim_mode != "energy"
        self._is_stub_theme = settings.visual_theme != "ocean"

    def set_theme(self, theme_name: str) -> None:
        """
        Change the visual theme.

        Args:
            theme_name: Name of the theme to use.
        """
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

        # Update FPS
        self._update_fps(current_time)

        # Clear screen with background color
        self.screen.fill(self.theme.background_color)

        # Draw ambient particles (background layer)
        self.theme.render_ambient(self.screen, self.ambient_particles, anim_time)

        # Draw food particles
        for food in simulation.food_manager:
            self.theme.render_food(self.screen, food, anim_time)

        # Draw creatures
        for creature in simulation.creatures:
            self.theme.render_creature(self.screen, creature, anim_time)

        # Draw stub mode overlay if needed
        self._draw_stub_overlay(simulation)

        # Draw HUD
        self.hud.render(self.screen, simulation, self.fps)

    def _update_fps(self, current_time: float) -> None:
        """Update FPS calculation."""
        self.frame_times.append(current_time)

        # Keep only last 60 frame times
        while len(self.frame_times) > 60:
            self.frame_times.pop(0)

        # Calculate FPS from frame times
        if len(self.frame_times) >= 2:
            elapsed = self.frame_times[-1] - self.frame_times[0]
            if elapsed > 0:
                self.fps = (len(self.frame_times) - 1) / elapsed

    def _draw_stub_overlay(self, simulation: Simulation) -> None:
        """Draw 'coming soon' overlay for stub modes/themes."""
        messages = []

        if self._is_stub_mode:
            messages.append(f"Mode '{simulation.settings.sim_mode}' coming soon")
        if self._is_stub_theme:
            messages.append(f"Theme '{simulation.settings.visual_theme}' coming soon")

        if not messages:
            return

        # Create overlay
        font = pygame.font.Font(None, 32)
        y = 50

        for message in messages:
            # Draw text with shadow
            shadow = font.render(message, True, (0, 0, 0))
            text = font.render(message, True, (200, 200, 200))

            x = self.width // 2 - text.get_width() // 2
            self.screen.blit(shadow, (x + 2, y + 2))
            self.screen.blit(text, (x, y))
            y += 40

    def toggle_hud(self) -> None:
        """Toggle HUD visibility."""
        self.hud.toggle()
        self.settings.show_hud = self.hud.visible
