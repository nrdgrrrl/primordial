"""Mouse cursor visibility helpers for runtime UI states."""

from __future__ import annotations

import pygame


def show_interactive_cursor() -> None:
    """Show the OS cursor while an interactive overlay is active."""
    pygame.mouse.set_visible(True)


def hide_runtime_cursor() -> None:
    """Hide the OS cursor during normal simulation playback."""
    pygame.mouse.set_visible(False)


def restore_system_cursor() -> None:
    """Restore the OS cursor before leaving pygame-controlled UI."""
    pygame.mouse.set_visible(True)
