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
    mode_param_mode: str | None = None
    mode_param_key: str | None = None
    visible_modes: list[str] | None = None


class SettingsOverlay:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.visible = False
        self.selected = 0
        self.fade = 0
        self.fade_dir = 0
        self.confirm_reset = False
        self.confirm_reset_predator_prey_dials = False
        self.pending: dict[str, object] = {}
        self.snapshot_path = ""
        self.snapshot_status = ""
        self.snapshot_status_is_error = False

        self.fields = [
            Field("Mode", "sim_mode", "enum", options=["energy", "predator_prey", "boids", "drift"], section="Simulation", requires_reset=True),
            Field("Initial Population", "initial_population", "int", 0, 500, 5, section="Simulation", requires_reset=True),
            Field(
                "Starting Predators",
                "",
                "float",
                0.0,
                1.0,
                0.01,
                section="Simulation",
                requires_reset=True,
                mode_param_mode="predator_prey",
                mode_param_key="predator_fraction",
                visible_modes=["predator_prey"],
            ),
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
        self._panel = pygame.Surface((600, 650), pygame.SRCALPHA)
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
        self.confirm_reset_predator_prey_dials = False
        self.snapshot_status = ""
        self.snapshot_status_is_error = False

    def sync_from_settings(self) -> None:
        self.pending = {
            self._pending_key(f): self._get_field_value(f)
            for f in self.fields
        }
        self.confirm_reset = False
        self.confirm_reset_predator_prey_dials = False
        self._clamp_selected()

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
            self.confirm_reset_predator_prey_dials = False
            return "save_snapshot"
        if event.key == pygame.K_l:
            self.confirm_reset = False
            self.confirm_reset_predator_prey_dials = False
            return "load_snapshot"
        if event.key == pygame.K_h:
            self.confirm_reset = False
            self.confirm_reset_predator_prey_dials = False
            return "help"
        if event.key == pygame.K_d and self.settings.sim_mode == "predator_prey":
            self.confirm_reset = False
            if self.confirm_reset_predator_prey_dials:
                self.confirm_reset_predator_prey_dials = False
                return "reset_predator_prey_dials"
            self.confirm_reset_predator_prey_dials = True
            return None
        visible_fields = self._visible_fields()
        if not visible_fields:
            return None
        if event.key == pygame.K_UP:
            self.selected = (self.selected - 1) % len(visible_fields)
        elif event.key == pygame.K_DOWN:
            self.selected = (self.selected + 1) % len(visible_fields)
        elif event.key == pygame.K_LEFT:
            self._adjust(-1)
        elif event.key == pygame.K_RIGHT:
            self._adjust(1)
        elif event.key == pygame.K_RETURN:
            for field in self.fields:
                self._set_field_value(field, self.pending[self._pending_key(field)])
            self.settings.save()
            self.close()
            return "apply"
        elif event.key == pygame.K_r:
            self.confirm_reset_predator_prey_dials = False
            if self.confirm_reset:
                self.settings.reset_to_defaults()
                self.sync_from_settings()
                self.confirm_reset = False
                return "reset"
            self.confirm_reset = True
        return None

    def _adjust(self, direction: int) -> None:
        field = self._selected_field()
        if field is None:
            return
        pending_key = self._pending_key(field)
        value = self.pending[pending_key]
        self.confirm_reset = False
        self.confirm_reset_predator_prey_dials = False
        if field.kind == "bool":
            self.pending[pending_key] = not bool(value)
        elif field.kind == "enum" and field.options:
            idx = field.options.index(str(value))
            self.pending[pending_key] = field.options[(idx + direction) % len(field.options)]
        elif field.kind == "int":
            new_val = int(value) + int(field.step) * direction
            self.pending[pending_key] = max(
                int(field.min_value),
                min(int(field.max_value), new_val),
            )
        else:
            new_val = float(value) + float(field.step) * direction
            bounded = max(float(field.min_value), min(float(field.max_value), new_val))
            self.pending[pending_key] = round(bounded, 4)
        self._clamp_selected()

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
        visible_fields = self._visible_fields()
        self._clamp_selected()
        for idx, field in enumerate(visible_fields):
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
        if self.settings.sim_mode == "predator_prey":
            dial_action = self._small.render(
                "D = Reset predator-prey dials + max ticks",
                True,
                (185, 225, 255),
            )
            self._panel.blit(dial_action, (20, action_y + 26))

        path_text = self.snapshot_path or "(default path pending)"
        path = self._small.render(f"Path: {path_text}", True, (120, 165, 220))
        path_y = action_y + (52 if self.settings.sim_mode == "predator_prey" else 26)
        self._panel.blit(path, (20, path_y))

        if self.snapshot_status:
            status_color = (240, 140, 140) if self.snapshot_status_is_error else (170, 225, 180)
            status = self._small.render(self.snapshot_status, True, status_color)
            self._panel.blit(status, (20, path_y + 26))

        hint = "Enter=Apply  Esc/S=Discard  R=Reset defaults"
        if self.confirm_reset:
            hint = "Press R again to confirm reset"
        elif self.confirm_reset_predator_prey_dials:
            hint = "Press D again to reset predator-prey dials"
        hint_y = self._panel.get_height() - 30
        self._panel.blit(self._small.render(hint, True, (180, 205, 230)), (20, hint_y))

        x = screen.get_width() // 2 - self._panel.get_width() // 2
        y = screen.get_height() // 2 - self._panel.get_height() // 2
        screen.blit(self._panel, (x, y))

    def _format_value(self, field: Field) -> str:
        value = self.pending[self._pending_key(field)]
        if field.kind == "bool":
            return "[ ON ]" if value else "[ OFF ]"
        if field.kind == "enum":
            return f"< {value} >"
        if field.mode_param_mode == "predator_prey" and field.mode_param_key == "predator_fraction":
            return f"< {int(round(float(value) * 100.0))}% >"
        if field.attr == "food_cycle_period":
            frames = int(value)
            seconds = frames / _SIMULATION_FRAMES_PER_SECOND
            return f"< {frames}f / {seconds:.1f}s >"
        if field.kind == "int":
            return f"< {int(value)} >"
        return f"{float(value):.3f}"

    def _pending_key(self, field: Field) -> str:
        if field.mode_param_mode is not None and field.mode_param_key is not None:
            return f"mode_param:{field.mode_param_mode}:{field.mode_param_key}"
        return field.attr

    def _get_field_value(self, field: Field) -> object:
        if field.mode_param_mode is not None and field.mode_param_key is not None:
            return self.settings.mode_params[field.mode_param_mode][field.mode_param_key]
        return getattr(self.settings, field.attr)

    def _set_field_value(self, field: Field, value: object) -> None:
        if field.mode_param_mode is not None and field.mode_param_key is not None:
            self.settings.mode_params[field.mode_param_mode][field.mode_param_key] = value
            return
        setattr(self.settings, field.attr, value)

    def _current_mode_for_visibility(self) -> str:
        return str(self.pending.get("sim_mode", self.settings.sim_mode))

    def _visible_fields(self) -> list[Field]:
        active_mode = self._current_mode_for_visibility()
        return [
            field
            for field in self.fields
            if field.visible_modes is None or active_mode in field.visible_modes
        ]

    def _clamp_selected(self) -> None:
        visible_count = len(self._visible_fields())
        if visible_count == 0:
            self.selected = 0
            return
        self.selected %= visible_count

    def _selected_field(self) -> Field | None:
        visible_fields = self._visible_fields()
        if not visible_fields:
            return None
        self._clamp_selected()
        return visible_fields[self.selected]
