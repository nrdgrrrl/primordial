"""In-app settings overlay widgets."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

_SIMULATION_FRAMES_PER_SECOND = 60.0


@dataclass
class Field:
    label: str
    attr: str
    kind: str
    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int = 1
    options: list[str] | None = None
    section: str = ""
    requires_reset: bool = False


class SettingsOverlay:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.visible = False
        self.selected = 0
        self.fade = 0
        self.fade_dir = 0
        self.confirm_reset = False
        self.pending: dict[str, object] = {}
        self.snapshot_path = ""
        self.snapshot_status = ""
        self.snapshot_status_is_error = False

        self.fields = [
            Field("Mode", "sim_mode", "enum", options=["energy", "predator_prey", "boids", "drift"], section="Simulation", requires_reset=True),
            Field("Initial Population", "initial_population", "int", 0, 500, 5, section="Simulation", requires_reset=True),
            Field("Max Population", "max_population", "int", 1, 600, 5, section="Simulation"),
            Field("Food Spawn Rate", "food_spawn_rate", "float", 0.0, 2.0, 0.05, section="Simulation"),
            Field("Creature Speed", "creature_speed_base", "float", 0.5, 3.0, 0.05, section="Simulation"),
            Field("Visual Theme", "visual_theme", "enum", options=["ocean", "petri", "geometric", "chaotic"], section="Display"),
            Field("Fullscreen", "fullscreen", "bool", section="Display"),
            Field("Target FPS", "target_fps", "int", 15, 240, 5, section="Display"),
            Field("Show HUD", "show_hud", "bool", section="Display"),
            Field("Mutation Rate", "mutation_rate", "float", 0.0, 1.0, 0.01, section="Evolution"),
            Field("Cosmic Ray Rate", "cosmic_ray_rate", "float", 0.0, 0.01, 0.0001, section="Evolution"),
            Field("Food Cycle", "food_cycle_enabled", "bool", section="Evolution"),
            Field("Food Cycle Length", "food_cycle_period", "int", 60, 5000, 30, section="Evolution"),
            Field("Zone Count", "zone_count", "int", 0, 12, 1, section="Evolution"),
            Field("Zone Strength", "zone_strength", "float", 0.0, 1.0, 0.05, section="Evolution"),
        ]
        self._panel = pygame.Surface((600, 620), pygame.SRCALPHA)
        self._shade: pygame.Surface | None = None
        self._font = pygame.font.Font(None, 26)
        self._small = pygame.font.Font(None, 22)

    def open(self) -> None:
        self.visible = True
        self.fade_dir = 1
        self.sync_from_settings()

    def close(self) -> None:
        self.fade_dir = -1
        self.confirm_reset = False
        self.snapshot_status = ""
        self.snapshot_status_is_error = False

    def sync_from_settings(self) -> None:
        self.pending = {f.attr: getattr(self.settings, f.attr) for f in self.fields}
        self.confirm_reset = False

    def set_snapshot_path(self, path: str) -> None:
        self.snapshot_path = path

    def set_snapshot_status(self, message: str, *, is_error: bool = False) -> None:
        self.snapshot_status = message
        self.snapshot_status_is_error = is_error

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type != pygame.KEYDOWN:
            return None
        if event.key in (pygame.K_ESCAPE, pygame.K_s):
            self.close()
            return "discard"
        if event.key == pygame.K_v:
            self.confirm_reset = False
            return "save_snapshot"
        if event.key == pygame.K_l:
            self.confirm_reset = False
            return "load_snapshot"
        if event.key == pygame.K_h:
            self.confirm_reset = False
            return "help"
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(self.fields)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(self.fields)
        elif event.key == pygame.K_LEFT:
            self._adjust(-1)
        elif event.key == pygame.K_RIGHT:
            self._adjust(1)
        elif event.key == pygame.K_RETURN:
            for k, v in self.pending.items():
                setattr(self.settings, k, v)
            self.settings.save()
            self.close()
            return "apply"
        elif event.key == pygame.K_r:
            if self.confirm_reset:
                self.settings.reset_to_defaults()
                self.pending = {f.attr: getattr(self.settings, f.attr) for f in self.fields}
                self.confirm_reset = False
                return "reset"
            self.confirm_reset = True
        return None

    def _adjust(self, direction: int) -> None:
        field = self.fields[self.selected]
        value = self.pending[field.attr]
        self.confirm_reset = False
        if field.kind == "bool":
            self.pending[field.attr] = not bool(value)
        elif field.kind == "enum" and field.options:
            idx = field.options.index(str(value))
            self.pending[field.attr] = field.options[(idx + direction) % len(field.options)]
        elif field.kind == "int":
            new_val = int(value) + int(field.step) * direction
            self.pending[field.attr] = max(int(field.min_value), min(int(field.max_value), new_val))
        else:
            new_val = float(value) + float(field.step) * direction
            bounded = max(float(field.min_value), min(float(field.max_value), new_val))
            self.pending[field.attr] = round(bounded, 4)

    def update(self) -> None:
        if self.fade_dir > 0:
            self.fade = min(20, self.fade + 1)
        elif self.fade_dir < 0:
            self.fade = max(0, self.fade - 1)
            if self.fade == 0:
                self.visible = False
                self.fade_dir = 0

    def draw(self, screen: pygame.Surface) -> None:
        if not self.visible and self.fade == 0:
            return
        alpha = int(170 * (self.fade / 20))
        if self._shade is None or self._shade.get_size() != screen.get_size():
            self._shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._shade.fill((0, 0, 0, alpha))
        screen.blit(self._shade, (0, 0))

        self._panel.fill((10, 22, 40, int(235 * (self.fade / 20))))
        pygame.draw.rect(self._panel, (70, 130, 190), self._panel.get_rect(), 2, border_radius=8)
        title = self._font.render("PRIMORDIAL SETTINGS", True, (185, 225, 255))
        self._panel.blit(title, (20, 18))

        y = 56
        last_section = ""
        for idx, field in enumerate(self.fields):
            if field.section != last_section:
                sec = self._small.render(field.section, True, (120, 165, 220))
                self._panel.blit(sec, (20, y))
                y += 24
                last_section = field.section
            color = (240, 245, 255) if idx == self.selected else (165, 190, 220)
            self._panel.blit(self._small.render(field.label, True, color), (32, y))
            self._panel.blit(self._small.render(self._format_value(field), True, color), (350, y))
            if field.requires_reset:
                note = self._small.render("*requires reset (R)", True, (210, 160, 120))
                self._panel.blit(note, (440, y))
            y += 24

        action_y = y + 8
        action = self._small.render(
            "V = Save Snapshot    L = Load Snapshot    H = Help",
            True,
            (185, 225, 255),
        )
        self._panel.blit(action, (20, action_y))

        path_text = self.snapshot_path or "(default path pending)"
        path = self._small.render(f"Path: {path_text}", True, (120, 165, 220))
        self._panel.blit(path, (20, action_y + 26))

        if self.snapshot_status:
            status_color = (240, 140, 140) if self.snapshot_status_is_error else (170, 225, 180)
            status = self._small.render(self.snapshot_status, True, status_color)
            self._panel.blit(status, (20, action_y + 52))

        hint = "Enter=Apply  Esc/S=Discard  R=Reset defaults"
        if self.confirm_reset:
            hint = "Press R again to confirm reset"
        self._panel.blit(self._small.render(hint, True, (180, 205, 230)), (20, 590))

        x = screen.get_width() // 2 - self._panel.get_width() // 2
        y = screen.get_height() // 2 - self._panel.get_height() // 2
        screen.blit(self._panel, (x, y))

    def _format_value(self, field: Field) -> str:
        value = self.pending[field.attr]
        if field.kind == "bool":
            return "[ ON ]" if value else "[ OFF ]"
        if field.kind == "enum":
            return f"< {value} >"
        if field.attr == "food_cycle_period":
            frames = int(value)
            seconds = frames / _SIMULATION_FRAMES_PER_SECOND
            return f"< {frames}f / {seconds:.1f}s >"
        if field.kind == "int":
            return f"< {int(value)} >"
        return f"{float(value):.3f}"
