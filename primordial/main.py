#!/usr/bin/env python3
"""
Primordial - A cellular evolution screensaver simulation.

Main entry point with game loop, event handling, and controls.
"""

from __future__ import annotations

import sys

import pygame

from .rendering import Renderer
from .settings import Settings
from .simulation import Simulation


def main() -> None:
    """Main entry point for Primordial."""
    # Initialize pygame
    pygame.init()

    # Load settings
    settings = Settings()

    # Set up display
    if settings.fullscreen:
        # Get display info for fullscreen
        display_info = pygame.display.Info()
        width = display_info.current_w
        height = display_info.current_h
        screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    else:
        width = 1280
        height = 720
        screen = pygame.display.set_mode((width, height))

    pygame.display.set_caption("Primordial")

    # Hide mouse cursor for screensaver feel
    pygame.mouse.set_visible(False)

    # Initialize simulation and renderer
    simulation = Simulation(width, height, settings)
    renderer = Renderer(screen, settings)

    # Set up clock for FPS limiting
    clock = pygame.time.Clock()

    # Main game loop
    running = True
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                running = handle_keydown(event, simulation, renderer, settings, screen)

        # Update simulation
        simulation.step()

        # Render
        renderer.draw(simulation)
        pygame.display.flip()

        # Limit FPS
        clock.tick(settings.target_fps)

    # Cleanup
    pygame.quit()
    sys.exit(0)


def handle_keydown(
    event: pygame.event.Event,
    simulation: Simulation,
    renderer: Renderer,
    settings: Settings,
    screen: pygame.Surface,
) -> bool:
    """
    Handle keyboard input.

    Args:
        event: Pygame key event.
        simulation: Simulation instance.
        renderer: Renderer instance.
        settings: Settings instance.
        screen: Pygame screen surface.

    Returns:
        True to continue running, False to quit.
    """
    key = event.key

    # Quit: ESC or Q
    if key in (pygame.K_ESCAPE, pygame.K_q):
        return False

    # Toggle HUD: H
    elif key == pygame.K_h:
        renderer.toggle_hud()

    # Pause/unpause: Space
    elif key == pygame.K_SPACE:
        simulation.paused = not simulation.paused

    # Toggle fullscreen: F
    elif key == pygame.K_f:
        toggle_fullscreen(settings, simulation, renderer)

    # Reset simulation: R
    elif key == pygame.K_r:
        simulation.reset()

    # Increase food spawn rate: + or =
    elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
        settings.food_spawn_rate = min(2.0, settings.food_spawn_rate + 0.1)

    # Decrease food spawn rate: - or _
    elif key in (pygame.K_MINUS, pygame.K_UNDERSCORE, pygame.K_KP_MINUS):
        settings.food_spawn_rate = max(0.1, settings.food_spawn_rate - 0.1)

    return True


def toggle_fullscreen(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """
    Toggle between fullscreen and windowed mode.

    Args:
        settings: Settings instance.
        simulation: Simulation instance.
        renderer: Renderer instance.
    """
    settings.fullscreen = not settings.fullscreen

    if settings.fullscreen:
        display_info = pygame.display.Info()
        width = display_info.current_w
        height = display_info.current_h
        screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    else:
        width = 1280
        height = 720
        screen = pygame.display.set_mode((width, height))

    pygame.mouse.set_visible(not settings.fullscreen)

    # Update renderer with new screen
    renderer.screen = screen
    renderer.width = width
    renderer.height = height

    # Update simulation world size
    simulation.width = width
    simulation.height = height
    simulation.food_manager.world_width = width
    simulation.food_manager.world_height = height


if __name__ == "__main__":
    main()
