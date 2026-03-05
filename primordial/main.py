#!/usr/bin/env python3
"""
Primordial - A cellular evolution screensaver simulation.

Main entry point with game loop, event handling, and controls.
Supports Windows screensaver modes: /s (screensaver), /p HWND (preview), /c (config).
"""

from __future__ import annotations

import platform
import sys
import time

import pygame

# Fix blurry rendering on Windows high-DPI displays.
# Must run before pygame.init(); silently ignored on non-Windows and older Windows.
try:
    if platform.system() == "Windows":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
except Exception:
    pass

from .rendering import Renderer
from .settings import Settings
from .simulation import Simulation
from .utils.screensaver import ScreensaverArgs


def main(scr_args: ScreensaverArgs | None = None) -> None:
    """Main entry point for Primordial."""
    if scr_args is None:
        scr_args = ScreensaverArgs(mode="normal")

    # Config mode: show a simple settings dialog without running the simulation.
    if scr_args.mode == "config":
        _run_config_dialog()
        return

    # Initialize pygame
    pygame.init()

    # Load settings
    settings = Settings()

    # Set up display based on mode
    if scr_args.mode == "screensaver":
        display_info = pygame.display.Info()
        width = display_info.current_w
        height = display_info.current_h
        screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
        pygame.mouse.set_visible(False)

    elif scr_args.mode == "preview":
        # SDL_WINDOWID was already set by root main.py; just create a surface
        # that fits into the preview pane (typically ~152×112 px).
        width, height = 152, 112
        screen = pygame.display.set_mode((width, height))
        pygame.mouse.set_visible(False)

    else:
        # Normal mode — existing behaviour unchanged.
        if settings.fullscreen:
            display_info = pygame.display.Info()
            width = display_info.current_w
            height = display_info.current_h
            screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
        else:
            width = 1280
            height = 720
            screen = pygame.display.set_mode((width, height))
        pygame.mouse.set_visible(False)

    pygame.display.set_caption("Primordial")

    # Initialize simulation and renderer
    simulation = Simulation(width, height, settings)
    renderer = Renderer(screen, settings)

    # Clock for FPS limiting
    clock = pygame.time.Clock()

    # Grace period for screensaver mode: ignore all input for 2 seconds after
    # launch to absorb any spurious mouse events some systems emit at startup.
    grace_until: float = time.time() + 2.0 if scr_args.mode == "screensaver" else 0.0

    # Mode transition fade state — 2-second (120-frame) cross-fade on mode change
    _prev_mode: str = settings.sim_mode   # mode saved when overlay is opened
    _transition_alpha: int = 0            # 0=transparent, 255=opaque
    _transition_dir: int = 0              # +1=fading out, -1=fading in, 0=idle
    _transition_surf: pygame.Surface | None = None

    def _begin_mode_transition() -> None:
        """Start the 2-second mode-change fade."""
        nonlocal _transition_alpha, _transition_dir, _transition_surf
        _transition_alpha = 0
        _transition_dir = 1  # start fading to black
        _transition_surf = pygame.Surface((width, height), pygame.SRCALPHA)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif scr_args.mode == "screensaver":
                # Quit on any real user input after the grace period.
                if time.time() > grace_until:
                    if event.type == pygame.KEYDOWN:
                        running = False
                    elif event.type == pygame.MOUSEBUTTONDOWN:
                        running = False
                    elif event.type == pygame.MOUSEMOTION:
                        # Only quit if movement exceeds threshold (avoids
                        # triggering on tiny cursor settling jitter at startup).
                        dx, dy = event.rel
                        if abs(dx) > 4 or abs(dy) > 4:
                            running = False

            elif scr_args.mode == "preview":
                # Preview pane: no input handling except QUIT (already handled above).
                pass

            elif event.type == pygame.KEYDOWN:
                if renderer.settings_overlay.visible:
                    action = renderer.settings_overlay.handle_event(event)
                    if action == "apply":
                        if settings.fullscreen != bool(screen.get_flags() & pygame.FULLSCREEN):
                            toggle_fullscreen(settings, simulation, renderer)
                        renderer.set_theme(settings.visual_theme)
                        renderer.set_mode(settings.sim_mode)
                        # Trigger fade transition if mode changed
                        if settings.sim_mode != _prev_mode:
                            _begin_mode_transition()
                        else:
                            simulation.paused = False
                    elif action == "discard" and renderer.settings_overlay.fade_dir < 0:
                        simulation.paused = False
                else:
                    running = handle_keydown(event, simulation, renderer, settings, screen, scr_args.mode)
                    if renderer.settings_overlay.visible:
                        # Save current mode so we can detect a change on apply
                        _prev_mode = settings.sim_mode
                        simulation.paused = True

        # Mode transition: fade out → reset sim → fade in
        if _transition_dir != 0 and _transition_surf is not None:
            step = 4  # ~60 frames total (30 out, 30 in) at 60fps ≈ 1s each way
            if _transition_dir == 1:
                _transition_alpha = min(200, _transition_alpha + step)
                if _transition_alpha >= 200:
                    # Mid-point: reinitialise simulation
                    simulation.reset()
                    simulation.paused = False
                    _transition_dir = -1
            else:
                _transition_alpha = max(0, _transition_alpha - step)
                if _transition_alpha <= 0:
                    _transition_dir = 0

        # Update simulation (paused during full fade-out)
        if _transition_dir != 1 or _transition_alpha < 200:
            simulation.step()

        # Render
        renderer.draw(simulation)

        # Overlay the transition fade
        if _transition_dir != 0 and _transition_surf is not None and _transition_alpha > 0:
            _transition_surf.fill((0, 0, 0, _transition_alpha))
            screen.blit(_transition_surf, (0, 0))

        pygame.display.flip()

        # Preview runs at half speed to save CPU
        target_fps = settings.target_fps // 2 if scr_args.mode == "preview" else settings.target_fps
        clock.tick(target_fps)

    pygame.quit()
    sys.exit(0)


def _run_config_dialog() -> None:
    """Show a minimal config/about dialog when launched with /c."""
    pygame.init()

    width, height = 400, 300
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Primordial Screensaver")
    pygame.mouse.set_visible(True)

    settings = Settings()

    settings_path = str(settings.config_path)

    font_title = pygame.font.Font(None, 28)
    font_body = pygame.font.Font(None, 20)
    font_small = pygame.font.Font(None, 17)

    BG = (10, 15, 30)
    TITLE_COLOR = (120, 200, 255)
    TEXT_COLOR = (180, 210, 240)
    DIM_COLOR = (100, 130, 160)
    BTN_COLOR = (40, 80, 140)
    BTN_HOVER = (60, 110, 180)
    BTN_TEXT = (220, 240, 255)

    btn_rect = pygame.Rect(width // 2 - 50, height - 55, 100, 36)

    clock = pygame.time.Clock()
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_ESCAPE, pygame.K_SPACE):
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_rect.collidepoint(mouse_pos):
                    running = False

        screen.fill(BG)

        # Title
        title_surf = font_title.render("Primordial Screensaver", True, TITLE_COLOR)
        screen.blit(title_surf, (width // 2 - title_surf.get_width() // 2, 24))

        # Divider
        pygame.draw.line(screen, (40, 60, 100), (30, 58), (width - 30, 58), 1)

        # Current settings
        lines = [
            ("Sim Mode", settings.sim_mode),
            ("Visual Theme", settings.visual_theme),
            ("Population", str(settings.initial_population)),
            ("Target FPS", str(settings.target_fps)),
        ]
        y = 72
        for label, value in lines:
            label_surf = font_body.render(f"{label}:", True, DIM_COLOR)
            value_surf = font_body.render(value, True, TEXT_COLOR)
            screen.blit(label_surf, (40, y))
            screen.blit(value_surf, (180, y))
            y += 26

        # Divider
        pygame.draw.line(screen, (40, 60, 100), (30, y + 4), (width - 30, y + 4), 1)
        y += 14

        # Edit instructions
        edit_surf = font_small.render("Edit config.toml to configure:", True, DIM_COLOR)
        screen.blit(edit_surf, (40, y))
        y += 18
        path_surf = font_small.render(settings_path, True, TEXT_COLOR)
        screen.blit(path_surf, (40, y))

        # OK button
        hover = btn_rect.collidepoint(mouse_pos)
        pygame.draw.rect(screen, BTN_HOVER if hover else BTN_COLOR, btn_rect, border_radius=6)
        ok_surf = font_body.render("OK", True, BTN_TEXT)
        screen.blit(ok_surf, (btn_rect.centerx - ok_surf.get_width() // 2,
                               btn_rect.centery - ok_surf.get_height() // 2))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit(0)


def handle_keydown(
    event: pygame.event.Event,
    simulation: Simulation,
    renderer: Renderer,
    settings: Settings,
    screen: pygame.Surface,
    mode: str,
) -> bool:
    """
    Handle keyboard input.

    Returns:
        True to continue running, False to quit.
    """
    key = event.key

    if key in (pygame.K_ESCAPE, pygame.K_q):
        return False
    elif key == pygame.K_h:
        renderer.toggle_hud()
    elif key == pygame.K_s and mode != "screensaver":
        renderer.toggle_settings_overlay()
    elif key == pygame.K_SPACE:
        simulation.paused = not simulation.paused
    elif key == pygame.K_f:
        toggle_fullscreen(settings, simulation, renderer)
    elif key == pygame.K_r:
        simulation.reset()
    elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
        settings.food_spawn_rate = min(2.0, settings.food_spawn_rate + 0.1)
    elif key in (pygame.K_MINUS, pygame.K_UNDERSCORE, pygame.K_KP_MINUS):
        settings.food_spawn_rate = max(0.1, settings.food_spawn_rate - 0.1)

    return True


def toggle_fullscreen(
    settings: Settings,
    simulation: Simulation,
    renderer: Renderer,
) -> None:
    """Toggle between fullscreen and windowed mode."""
    settings.fullscreen = not settings.fullscreen

    try:
        pygame.display.toggle_fullscreen()
        screen = pygame.display.get_surface()
        if screen is None:
            raise pygame.error("No display surface")
        width = screen.get_width()
        height = screen.get_height()
    except pygame.error:
        if settings.fullscreen:
            display_info = pygame.display.Info()
            width = display_info.current_w
            height = display_info.current_h
            screen = pygame.display.set_mode((width, height), pygame.FULLSCREEN | pygame.SCALED)
        else:
            width = 1280
            height = 720
            screen = pygame.display.set_mode((width, height))

    pygame.mouse.set_visible(not settings.fullscreen)

    renderer.screen = screen
    renderer.width = width
    renderer.height = height

    simulation.width = width
    simulation.height = height
    simulation.food_manager.world_width = width
    simulation.food_manager.world_height = height


if __name__ == "__main__":
    main()
