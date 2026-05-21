"""In-app settings overlay widgets."""

from __future__ import annotations

import pygame

from .settings_metadata import (
    CATEGORY_ACTIONS,
    SETTING_CATEGORIES,
    ActionItem,
    Field,
    build_action_items,
    build_settings_fields,
)
from .settings_navigation import SettingsNavigation


class SettingsOverlay:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.visible = False
        self.fade = 0
        self.fade_dir = 0
        self.confirm_reset = False
        self.confirm_reset_predator_prey_dials = False
        self.pending: dict[str, object] = {}
        self.snapshot_path = ""
        self.snapshot_status = ""
        self.snapshot_status_is_error = False

        self.fields = build_settings_fields()
        self.actions = build_action_items()
        self.navigation = SettingsNavigation(SETTING_CATEGORIES)
        self._first_visible_row = 0

        self._shade: pygame.Surface | None = None
        self._title_font = pygame.font.Font(None, 34)
        self._section_font = pygame.font.Font(None, 25)
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 20)
        self._tiny = pygame.font.Font(None, 18)

    @property
    def selected(self) -> int:
        return self.navigation.selected

    @selected.setter
    def selected(self, value: int) -> None:
        self.navigation.selected = value

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
        self.pending = {}
        for field in self.fields:
            self.pending[self._pending_key(field)] = self._get_field_value(field)
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
            self._clear_confirmations()
            return "save_snapshot"
        if event.key == pygame.K_l:
            self._clear_confirmations()
            return "load_snapshot"
        if event.key == pygame.K_h:
            self._clear_confirmations()
            return "help"
        if event.key == pygame.K_d and self.settings.sim_mode == "predator_prey":
            self.confirm_reset = False
            if self.confirm_reset_predator_prey_dials:
                self.confirm_reset_predator_prey_dials = False
                return "reset_predator_prey_dials"
            self.confirm_reset_predator_prey_dials = True
            return None
        if event.key in (pygame.K_TAB, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
            direction = -1 if (
                event.key == pygame.K_PAGEUP
                or (event.key == pygame.K_TAB and getattr(event, "mod", 0) & pygame.KMOD_SHIFT)
            ) else 1
            self.navigation.move_category(direction, self._item_count_for_category)
            self._first_visible_row = 0
            self._clear_confirmations()
            return None

        items = self._visible_items_for_active_category()
        if not items:
            return None
        if event.key == pygame.K_UP:
            self.navigation.move_selection(-1, len(items))
            self._clear_confirmations()
        elif event.key == pygame.K_DOWN:
            self.navigation.move_selection(1, len(items))
            self._clear_confirmations()
        elif event.key == pygame.K_LEFT:
            self._adjust(-1)
        elif event.key == pygame.K_RIGHT:
            self._adjust(1)
        elif event.key == pygame.K_SPACE:
            return self._run_selected_action()
        elif event.key == pygame.K_RETURN:
            for field in self.fields:
                pending_key = self._ensure_pending_value(field)
                self._set_field_value(field, self.pending[pending_key])
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

    def _run_selected_action(self) -> str | None:
        item = self._selected_item()
        if not isinstance(item, ActionItem):
            return None
        if not self._action_enabled(item):
            self.set_snapshot_status(
                f"{item.label} is only available in predator_prey mode.",
                is_error=True,
            )
            return None
        if item.action == "reset_predator_prey_dials":
            if self.confirm_reset_predator_prey_dials:
                self.confirm_reset_predator_prey_dials = False
                return "reset_predator_prey_dials"
            self.confirm_reset = False
            self.confirm_reset_predator_prey_dials = True
            return None
        if item.action == "reset":
            if self.confirm_reset:
                self.settings.reset_to_defaults()
                self.sync_from_settings()
                self.confirm_reset = False
                return "reset"
            self.confirm_reset_predator_prey_dials = False
            self.confirm_reset = True
            return None
        self._clear_confirmations()
        return item.action

    def _clear_confirmations(self) -> None:
        self.confirm_reset = False
        self.confirm_reset_predator_prey_dials = False

    def _adjust(self, direction: int) -> None:
        field = self._selected_field()
        if field is None:
            return
        pending_key = self._ensure_pending_value(field)
        value = self.pending[pending_key]
        self._clear_confirmations()
        if field.kind == "bool":
            self.pending[pending_key] = not bool(value)
        elif field.kind == "enum" and field.options:
            idx = field.options.index(str(value))
            self.pending[pending_key] = field.options[(idx + direction) % len(field.options)]
            if field.attr == "sim_mode":
                self._clamp_selected()
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
        fade_ratio = self.fade / 20
        alpha = int(185 * fade_ratio)
        if self._shade is None or self._shade.get_size() != screen.get_size():
            self._shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._shade.fill((0, 6, 16, alpha))
        screen.blit(self._shade, (0, 0))

        panel_rect = self._panel_rect(screen)
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((6, 18, 34, int(244 * fade_ratio)))
        self._draw_panel_glow(panel, fade_ratio)
        self._draw_header(panel)

        body_top = 86
        footer_height = 64
        body_bottom = panel.get_height() - footer_height
        sidebar_rect = pygame.Rect(18, body_top, 184, body_bottom - body_top - 12)
        list_rect = pygame.Rect(sidebar_rect.right + 18, body_top, 360, sidebar_rect.height)
        details_rect = pygame.Rect(list_rect.right + 18, body_top, panel.get_width() - list_rect.right - 36, sidebar_rect.height)
        footer_rect = pygame.Rect(18, panel.get_height() - footer_height, panel.get_width() - 36, footer_height - 14)

        self._draw_sidebar(panel, sidebar_rect)
        self._draw_item_list(panel, list_rect)
        self._draw_details(panel, details_rect)
        self._draw_footer(panel, footer_rect)

        screen.blit(panel, panel_rect.topleft)

    def _panel_rect(self, screen: pygame.Surface) -> pygame.Rect:
        margin = 24
        width = min(max(980, int(screen.get_width() * 0.86)), screen.get_width() - margin * 2)
        height = min(max(620, int(screen.get_height() * 0.84)), screen.get_height() - margin * 2)
        width = max(720, width)
        height = max(520, height)
        return pygame.Rect(
            screen.get_width() // 2 - width // 2,
            screen.get_height() // 2 - height // 2,
            width,
            height,
        )

    def _draw_panel_glow(self, panel: pygame.Surface, fade_ratio: float) -> None:
        rect = panel.get_rect()
        pygame.draw.rect(panel, (11, 38, 62, int(190 * fade_ratio)), rect, border_radius=10)
        pygame.draw.rect(panel, (78, 194, 224, int(190 * fade_ratio)), rect, 2, border_radius=10)
        inner = rect.inflate(-8, -8)
        pygame.draw.rect(panel, (22, 74, 102, int(120 * fade_ratio)), inner, 1, border_radius=8)

    def _draw_header(self, panel: pygame.Surface) -> None:
        title = self._title_font.render("PRIMORDIAL SETTINGS", True, (218, 247, 255))
        panel.blit(title, (24, 22))
        subtitle = self._small.render(
            self._status_summary(),
            True,
            (134, 202, 226),
        )
        panel.blit(subtitle, (24, 55))
        badge_text = "UNAPPLIED CHANGES" if self.has_unapplied_changes() else "SAVED STATE"
        badge_color = (248, 190, 108) if self.has_unapplied_changes() else (106, 218, 190)
        badge = self._small.render(badge_text, True, badge_color)
        badge_rect = pygame.Rect(panel.get_width() - badge.get_width() - 34, 25, badge.get_width() + 18, 28)
        pygame.draw.rect(panel, (10, 34, 50), badge_rect, border_radius=6)
        pygame.draw.rect(panel, badge_color, badge_rect, 1, border_radius=6)
        panel.blit(badge, (badge_rect.x + 9, badge_rect.y + 6))
        pygame.draw.line(panel, (38, 96, 122), (18, 76), (panel.get_width() - 18, 76), 1)

    def _draw_sidebar(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (7, 25, 42), (42, 106, 136))
        y = rect.y + 12
        for index, category in enumerate(SETTING_CATEGORIES):
            count = self._item_count_for_category(category)
            selected = index == self.navigation.category_index
            item_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, 34)
            if selected:
                pygame.draw.rect(panel, (18, 76, 98), item_rect, border_radius=6)
                pygame.draw.rect(panel, (91, 221, 236), item_rect, 1, border_radius=6)
            label_color = (226, 250, 255) if selected else (142, 184, 204)
            count_color = (116, 210, 210) if count else (88, 116, 132)
            panel.blit(self._font.render(category, True, label_color), (item_rect.x + 9, item_rect.y + 7))
            count_surf = self._tiny.render(str(count), True, count_color)
            panel.blit(count_surf, (item_rect.right - count_surf.get_width() - 10, item_rect.y + 9))
            y += 39

    def _draw_item_list(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (5, 20, 34), (37, 89, 116))
        items = self._visible_items_for_active_category()
        self.navigation.clamp_selected(len(items))
        header = f"{self.navigation.category} {self.navigation.selected + 1 if items else 0} / {len(items)}"
        panel.blit(self._section_font.render(header, True, (219, 246, 252)), (rect.x + 14, rect.y + 12))
        pygame.draw.line(panel, (35, 88, 112), (rect.x + 12, rect.y + 46), (rect.right - 12, rect.y + 46), 1)
        if not items:
            message = "No settings in this category for the selected mode."
            for line in self._wrap_text(message, self._font, rect.width - 28):
                panel.blit(self._font.render(line, True, (156, 190, 208)), (rect.x + 14, rect.y + 64))
            return

        row_height = 40
        max_rows = max(1, (rect.height - 62) // row_height)
        if self.navigation.selected < self._first_visible_row:
            self._first_visible_row = self.navigation.selected
        if self.navigation.selected >= self._first_visible_row + max_rows:
            self._first_visible_row = self.navigation.selected - max_rows + 1
        self._first_visible_row = min(self._first_visible_row, max(0, len(items) - max_rows))

        y = rect.y + 56
        for row_index, item in enumerate(items[self._first_visible_row:self._first_visible_row + max_rows], start=self._first_visible_row):
            selected = row_index == self.navigation.selected
            row_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, 34)
            if selected:
                pygame.draw.rect(panel, (20, 82, 103), row_rect, border_radius=7)
                pygame.draw.rect(panel, (103, 236, 239), row_rect, 1, border_radius=7)
            elif isinstance(item, ActionItem) and item.destructive:
                pygame.draw.rect(panel, (31, 24, 36), row_rect, border_radius=7)
            label_color = (238, 253, 255) if selected else (180, 211, 225)
            if isinstance(item, ActionItem) and not self._action_enabled(item):
                label_color = (94, 119, 132)
            panel.blit(self._font.render(item.label, True, label_color), (row_rect.x + 9, row_rect.y + 7))
            if isinstance(item, Field):
                value_text = self._format_value(item)
                value_color = (123, 241, 220) if selected else (104, 197, 196)
                value = self._font.render(value_text, True, value_color)
                value_right_padding = 88 if item.requires_reset else 10
                panel.blit(value, (row_rect.right - value.get_width() - value_right_padding, row_rect.y + 7))
                if item.requires_reset:
                    self._draw_badge(panel, "RESET", row_rect.right - 78, row_rect.y + 8, (232, 170, 91))
                if self._field_changed(item):
                    self._draw_badge(panel, "CHANGED", row_rect.x + 9, row_rect.y + 24, (248, 190, 108), tiny=True)
            else:
                shortcut = self._tiny.render(item.shortcut, True, (133, 220, 218))
                panel.blit(shortcut, (row_rect.right - shortcut.get_width() - 10, row_rect.y + 10))
            y += row_height

        if self._first_visible_row > 0:
            panel.blit(self._tiny.render("more above", True, (108, 152, 174)), (rect.right - 80, rect.y + 50))
        if self._first_visible_row + max_rows < len(items):
            panel.blit(self._tiny.render("more below", True, (108, 152, 174)), (rect.right - 80, rect.bottom - 22))

    def _draw_details(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (7, 24, 39), (42, 104, 132))
        item = self._selected_item()
        title = item.label if item is not None else self.navigation.category
        panel.blit(self._section_font.render(title, True, (231, 250, 255)), (rect.x + 16, rect.y + 14))
        y = rect.y + 50
        if item is None:
            text = "Choose another category with Tab. Mode-specific settings appear when their mode is selected."
            for line in self._wrap_text(text, self._font, rect.width - 32):
                panel.blit(self._font.render(line, True, (178, 210, 224)), (rect.x + 16, y))
                y += 25
            return

        description = item.description
        for line in self._wrap_text(description, self._font, rect.width - 32):
            panel.blit(self._font.render(line, True, (203, 231, 239)), (rect.x + 16, y))
            y += 25
        y += 8

        if isinstance(item, Field):
            details = self._field_details(item)
            for label, value, color in details:
                label_surf = self._small.render(label, True, (120, 170, 194))
                value_surf = self._small.render(value, True, color)
                panel.blit(label_surf, (rect.x + 16, y))
                panel.blit(value_surf, (rect.x + 132, y))
                y += 24
            if item.guidance:
                y += 6
                for line in self._wrap_text(item.guidance, self._small, rect.width - 32):
                    panel.blit(self._small.render(line, True, (155, 196, 211)), (rect.x + 16, y))
                    y += 22
        else:
            enabled = self._action_enabled(item)
            mode_line = "Available now" if enabled else "Only available in predator_prey mode"
            mode_color = (117, 227, 191) if enabled else (232, 170, 91)
            self._draw_detail_row(panel, rect.x + 16, y, "Shortcut", item.shortcut, (130, 232, 221))
            y += 24
            self._draw_detail_row(panel, rect.x + 16, y, "Status", mode_line, mode_color)
            y += 32
            if item.destructive:
                for line in self._wrap_text("This action asks for a second key press before it runs.", self._small, rect.width - 32):
                    panel.blit(self._small.render(line, True, (232, 170, 91)), (rect.x + 16, y))
                    y += 22

        if self.snapshot_status:
            status_color = (244, 139, 139) if self.snapshot_status_is_error else (129, 226, 173)
            y = max(y + 10, rect.bottom - 58)
            for line in self._wrap_text(self.snapshot_status, self._small, rect.width - 32):
                panel.blit(self._small.render(line, True, status_color), (rect.x + 16, y))
                y += 22

    def _draw_footer(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (5, 20, 32), (34, 88, 112))
        hint = "Enter Apply   Esc/S Discard   Up/Down Select   Left/Right Change   Tab Category   V Save   L Load   H Guide   R R Defaults"
        if self.navigation.category == CATEGORY_ACTIONS:
            hint = "Space Run Action   Enter Apply Settings   Esc/S Discard   Up/Down Select   Tab Category   R R Defaults"
        if self.settings.sim_mode == "predator_prey":
            hint += "   D D Reset Dials"
        if self.confirm_reset:
            hint = "Press R again, or Space on Reset Settings Defaults, to restore canonical defaults."
        elif self.confirm_reset_predator_prey_dials:
            hint = "Press D again, or Space on Reset Predator-Prey Dials, to reset adaptive ecological dials and restart the run."
        lines = self._wrap_text(hint, self._small, rect.width - 24)
        y = rect.y + 11
        for line in lines[:2]:
            panel.blit(self._small.render(line, True, (189, 225, 235)), (rect.x + 12, y))
            y += 22
        path = self.snapshot_path or "(default path pending)"
        path_line = self._tiny.render(f"Snapshot: {path}", True, (99, 151, 176))
        panel.blit(path_line, (rect.x + 12, rect.bottom - 19))

    def _draw_box(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int],
        border: tuple[int, int, int],
    ) -> None:
        pygame.draw.rect(panel, fill, rect, border_radius=8)
        pygame.draw.rect(panel, border, rect, 1, border_radius=8)

    def _draw_badge(
        self,
        panel: pygame.Surface,
        text: str,
        x: int,
        y: int,
        color: tuple[int, int, int],
        *,
        tiny: bool = False,
    ) -> None:
        font = self._tiny if tiny else self._small
        surf = font.render(text, True, color)
        rect = pygame.Rect(x, y, surf.get_width() + 10, surf.get_height() + 4)
        pygame.draw.rect(panel, (24, 38, 42), rect, border_radius=5)
        pygame.draw.rect(panel, color, rect, 1, border_radius=5)
        panel.blit(surf, (rect.x + 5, rect.y + 2))

    def _draw_detail_row(
        self,
        panel: pygame.Surface,
        x: int,
        y: int,
        label: str,
        value: str,
        color: tuple[int, int, int],
    ) -> None:
        panel.blit(self._small.render(label, True, (120, 170, 194)), (x, y))
        panel.blit(self._small.render(value, True, color), (x + 116, y))

    def _status_summary(self) -> str:
        active_mode = self._current_mode_for_visibility()
        count = self._item_count_for_category(self.navigation.category)
        return f"{self.navigation.category} · {count} item{'s' if count != 1 else ''} · Active mode: {active_mode}"

    def _field_details(self, field: Field) -> list[tuple[str, str, tuple[int, int, int]]]:
        effect = "Requires reset" if field.requires_reset else "Applies on save"
        rows = [
            ("Value", self._format_value(field), (125, 241, 220)),
            ("Effect", effect, (232, 170, 91) if field.requires_reset else (122, 225, 186)),
        ]
        if field.kind in {"int", "float"} and field.min_value is not None and field.max_value is not None:
            rows.append(("Range", f"{field.min_value} to {field.max_value}  step {field.step}", (185, 215, 226)))
        elif field.kind == "enum" and field.options:
            rows.append(("Choices", ", ".join(field.options), (185, 215, 226)))
        elif field.kind == "bool":
            rows.append(("Choices", "on, off", (185, 215, 226)))
        rows.append(("Key", field.internal_key, (113, 153, 172)))
        return rows

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _format_value(self, field: Field) -> str:
        value = self.pending[self._ensure_pending_value(field)]
        if field.kind == "bool":
            return "ON" if value else "OFF"
        if field.kind == "enum":
            return str(value)
        if field.mode_param_mode == "predator_prey" and field.mode_param_key == "predator_fraction":
            return f"{int(round(float(value) * 100.0))}%"
        if field.attr == "food_cycle_period":
            frames = int(value)
            seconds = frames / self._simulation_frames_per_second()
            return f"{frames}f / {seconds:.1f}s"
        if field.kind == "int":
            return str(int(value))
        return f"{float(value):.3f}"

    def _pending_key(self, field: Field) -> str:
        mode_target = self._resolve_mode_target(field)
        if mode_target is not None:
            mode_name, mode_key = mode_target
            return f"mode_param:{mode_name}:{mode_key}"
        return field.attr

    def _get_field_value(self, field: Field) -> object:
        mode_target = self._resolve_mode_target(field)
        if mode_target is not None:
            mode_name, mode_key = mode_target
            return self.settings.mode_params[mode_name][mode_key]
        return getattr(self.settings, field.attr)

    def _set_field_value(self, field: Field, value: object) -> None:
        mode_target = self._resolve_mode_target(field)
        if mode_target is not None:
            mode_name, mode_key = mode_target
            self.settings.mode_params[mode_name][mode_key] = value
            return
        setattr(self.settings, field.attr, value)

    def _resolve_mode_target(self, field: Field) -> tuple[str, str] | None:
        if field.mode_param_mode is not None and field.mode_param_key is not None:
            return (field.mode_param_mode, field.mode_param_key)
        if not field.use_active_mode_param:
            return None
        active_mode = self._current_mode_for_visibility()
        mode_values = self.settings.mode_params.get(active_mode)
        if mode_values is None or field.attr not in mode_values:
            return None
        return (active_mode, field.attr)

    def _ensure_pending_value(self, field: Field) -> str:
        pending_key = self._pending_key(field)
        if pending_key not in self.pending:
            self.pending[pending_key] = self._get_field_value(field)
        return pending_key

    def _current_mode_for_visibility(self) -> str:
        return str(self.pending.get("sim_mode", self.settings.sim_mode))

    def _simulation_frames_per_second(self) -> float:
        active_mode = self._current_mode_for_visibility()
        mode_values = self.settings.mode_params.get(active_mode, {})
        if isinstance(mode_values, dict) and "simulation_tick_hz" in mode_values:
            return max(1.0, float(mode_values["simulation_tick_hz"]))
        return 60.0

    def _visible_fields(self) -> list[Field]:
        active_mode = self._current_mode_for_visibility()
        return [
            field
            for field in self.fields
            if field.visible_modes is None or active_mode in field.visible_modes
        ]

    def _visible_fields_for_category(self, category: str) -> list[Field]:
        return [field for field in self._visible_fields() if field.section == category]

    def _visible_actions(self) -> list[ActionItem]:
        return self.actions

    def _visible_items_for_active_category(self) -> list[Field | ActionItem]:
        category = self.navigation.category
        if category == CATEGORY_ACTIONS:
            return list(self._visible_actions())
        return list(self._visible_fields_for_category(category))

    def _item_count_for_category(self, category: str) -> int:
        if category == CATEGORY_ACTIONS:
            return len(self._visible_actions())
        return len(self._visible_fields_for_category(category))

    def _clamp_selected(self) -> None:
        self.navigation.clamp_selected(len(self._visible_items_for_active_category()))

    def _selected_item(self) -> Field | ActionItem | None:
        items = self._visible_items_for_active_category()
        if not items:
            return None
        self._clamp_selected()
        return items[self.navigation.selected]

    def _selected_field(self) -> Field | None:
        item = self._selected_item()
        return item if isinstance(item, Field) else None

    def _field_changed(self, field: Field) -> bool:
        pending_key = self._ensure_pending_value(field)
        return self.pending[pending_key] != self._get_field_value(field)

    def has_unapplied_changes(self) -> bool:
        return any(self._field_changed(field) for field in self.fields)

    def _action_enabled(self, item: ActionItem) -> bool:
        return item.enabled_modes is None or self.settings.sim_mode in item.enabled_modes
