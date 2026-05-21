"""Renderer-owned in-game tutorial/onboarding overlay."""

from __future__ import annotations

import pygame

from primordial.tutorial import TutorialState, TutorialStep, build_default_tutorial_steps

from .tutorial_layout import TutorialHighlightContext, calculate_tutorial_layout
from .tutorial_mouse import TutorialHitRegion


class TutorialOverlay:
    """Draw and operate the first-version tutorial flow."""

    def __init__(self, steps: tuple[TutorialStep, ...] | None = None) -> None:
        self.state = TutorialState(steps or build_default_tutorial_steps())
        self.visible = False
        self.fade = 0
        self.fade_dir = 0
        self._shade: pygame.Surface | None = None
        self._hit_regions: list[TutorialHitRegion] = []
        self._hover_region: TutorialHitRegion | None = None
        self._last_panel_rect = pygame.Rect(0, 0, 0, 0)
        self._highlight_context = TutorialHighlightContext()

        self._title_font = pygame.font.Font(None, 36)
        self._phase_font = pygame.font.Font(None, 22)
        self._font = pygame.font.Font(None, 25)
        self._small = pygame.font.Font(None, 20)
        self._tiny = pygame.font.Font(None, 18)

    def open(self, *, forced: bool = False, previous_paused: bool | None = None) -> None:
        self.state.start(forced=forced, previous_paused=previous_paused)
        self.visible = True
        self.fade_dir = 1

    def close(self) -> str:
        action = self.state.close()
        self.fade_dir = -1
        return action

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.MOUSEMOTION:
            self._hover_region = self._hit_region_at(event.pos)
            self.state.hover_action = self._hover_region.action if self._hover_region else None
            return None
        if event.type == pygame.MOUSEWHEEL:
            self._handle_wheel(event)
            return None
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_mouse_button(event)
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            return self._close_with_action(self.state.close())
        if event.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_SPACE):
            return self._advance()
        if event.key in (pygame.K_LEFT, pygame.K_BACKSPACE):
            self.state.back()
            return None
        if event.key == pygame.K_PAGEUP:
            self.state.scroll_text(-5)
            return None
        if event.key == pygame.K_PAGEDOWN:
            self.state.scroll_text(5)
            return None
        return None

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
        layout = calculate_tutorial_layout(
            screen.get_size(),
            highlight=self.state.current_step.highlight,
            highlight_context=self._highlight_context,
        )
        self._last_panel_rect = layout.panel_rect
        self._hit_regions = []

        if self._shade is None or self._shade.get_size() != screen.get_size():
            self._shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._shade.fill((0, 8, 18, int(126 * fade_ratio)))
        screen.blit(self._shade, (0, 0))
        self._draw_highlight(
            screen,
            layout.highlight_rect,
            self.state.current_step.highlight,
            fade_ratio,
        )

        panel = pygame.Surface(layout.panel_rect.size, pygame.SRCALPHA)
        panel.fill((5, 18, 34, int(244 * fade_ratio)))
        self._draw_panel_frame(panel, fade_ratio)
        self._draw_header(panel, layout.header_rect)
        self._draw_body(panel, layout.body_rect)
        self._draw_footer(panel, layout)
        screen.blit(panel, layout.panel_rect.topleft)

    def restore_pause_value(self) -> bool | None:
        return self.state.previous_paused

    def wants_simulation_paused(self) -> bool:
        # v1 onboarding keeps the simulation frozen for the full tutorial so
        # the scene does not drift while the user reads or interacts.
        return self.visible

    def set_runtime_context(
        self,
        *,
        hud_visible: bool,
        settings_visible: bool = False,
        help_visible: bool = False,
        game_over_visible: bool = False,
    ) -> None:
        self._highlight_context = TutorialHighlightContext(
            hud_visible=hud_visible,
            settings_visible=settings_visible,
            help_visible=help_visible,
            game_over_visible=game_over_visible,
        )

    def _handle_mouse_button(self, event: pygame.event.Event) -> str | None:
        if event.button in (4, 5):
            self.state.scroll_text(-1 if event.button == 4 else 1)
            return None
        if event.button != 1:
            return None
        region = self._hit_region_at(event.pos)
        self._hover_region = region
        if region is None or region.action is None:
            return None
        if region.action == "next":
            return self._advance()
        if region.action == "back":
            self.state.back()
            return None
        if region.action == "skip":
            return self._close_with_action(self.state.skip())
        return None

    def _handle_wheel(self, event: pygame.event.Event) -> None:
        y = int(getattr(event, "y", 0))
        if y == 0 and getattr(event, "button", None) in (4, 5):
            y = 1 if event.button == 4 else -1
        self.state.scroll_text(-y)

    def _advance(self) -> str | None:
        action = self.state.next()
        if action is not None:
            return self._close_with_action(action)
        return None

    def _close_with_action(self, action: str) -> str:
        self.fade_dir = -1
        return action

    def _draw_highlight(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect | None,
        highlight: str,
        fade_ratio: float,
    ) -> None:
        if rect is None:
            return
        glow = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        outer = rect.inflate(18, 18)
        pygame.draw.rect(glow, (40, 140, 154, int(22 * fade_ratio)), outer, border_radius=18)
        pygame.draw.rect(glow, (90, 234, 229, int(126 * fade_ratio)), rect, 2, border_radius=14)
        pygame.draw.rect(glow, (160, 244, 248, int(54 * fade_ratio)), rect, border_radius=14)
        label = self._highlight_label(highlight)
        if label:
            self._draw_highlight_label(glow, rect, label, fade_ratio)
        screen.blit(glow, (0, 0))

    def _highlight_label(
        self,
        highlight: str,
    ) -> str | None:
        labels = {
            "hud": "HUD",
            "creatures": "Creature Field",
            "food": "Food Field",
            "predators": "Predator / Prey Field",
            "lineages": "Lineage Activity",
            "zones": "Simulation World",
        }
        return labels.get(highlight)

    def _draw_highlight_label(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        fade_ratio: float,
    ) -> None:
        text = self._small.render(label, True, (231, 252, 255))
        pill = pygame.Rect(0, 0, text.get_width() + 18, text.get_height() + 10)
        pill.x = max(12, min(surface.get_width() - pill.width - 12, rect.x + 8))
        pill.y = max(12, rect.y - pill.height - 8)
        pygame.draw.rect(surface, (9, 34, 46, int(220 * fade_ratio)), pill, border_radius=8)
        pygame.draw.rect(surface, (96, 236, 232, int(190 * fade_ratio)), pill, 1, border_radius=8)
        surface.blit(text, (pill.x + 9, pill.y + 5))

    def _draw_panel_frame(self, panel: pygame.Surface, fade_ratio: float) -> None:
        rect = panel.get_rect()
        pygame.draw.rect(panel, (9, 38, 59, int(200 * fade_ratio)), rect, border_radius=10)
        pygame.draw.rect(panel, (90, 220, 229, int(185 * fade_ratio)), rect, 2, border_radius=10)
        pygame.draw.rect(panel, (22, 78, 104, int(120 * fade_ratio)), rect.inflate(-8, -8), 1, border_radius=8)

    def _draw_header(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        step = self.state.current_step
        progress = f"{self.state.current_index + 1} / {len(self.state.steps)}"
        phase = self._phase_font.render(f"{step.phase} · {progress}", True, (126, 209, 225))
        panel.blit(phase, (rect.x + 2, rect.y + 4))
        title = self._title_font.render(step.title, True, (232, 252, 255))
        panel.blit(title, (rect.x + 2, rect.y + 28))
        pygame.draw.line(panel, (38, 96, 122), (22, rect.bottom), (panel.get_width() - 22, rect.bottom), 1)

    def _draw_body(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (7, 25, 40), (39, 100, 128))
        body_rect = rect.inflate(-24, -24)
        lines = self._wrap_paragraphs(self.state.current_step.body, self._font, body_rect.width)
        visible_lines = max(1, body_rect.height // 25)
        self.state.set_text_bounds(line_count=len(lines), visible_lines=visible_lines)
        y = body_rect.y
        for line in lines[self.state.text_scroll:self.state.text_scroll + visible_lines]:
            panel.blit(self._font.render(line, True, (210, 238, 246)), (body_rect.x, y))
            y += 25
        if self.state.text_line_count > visible_lines:
            self._draw_scrollbar(panel, rect, self.state.text_scroll, self.state.text_line_count, visible_lines)

    def _draw_footer(self, panel: pygame.Surface, layout) -> None:
        rect = layout.footer_rect
        pygame.draw.line(panel, (38, 96, 122), (rect.x, rect.y), (rect.right, rect.y), 1)
        self._draw_button(
            panel,
            layout.back_rect,
            "Back",
            action="back",
            disabled=self.state.is_first_step,
        )
        self._draw_button(panel, layout.skip_rect, "Skip", action="skip", destructive=True)
        self._draw_button(
            panel,
            layout.next_rect,
            "Finish" if self.state.is_last_step else "Next",
            action="next",
            primary=True,
        )
        hint = "Keyboard: Enter/Space/Right next · Left/Backspace back · PageUp/PageDown scroll · Esc skip"
        panel.blit(self._tiny.render(hint, True, (134, 184, 205)), (rect.x, rect.bottom - 16))

    def _draw_button(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        *,
        action: str,
        primary: bool = False,
        destructive: bool = False,
        disabled: bool = False,
    ) -> None:
        hovered = self._region_hovered(action) and not disabled
        if disabled:
            fill, border, color = (8, 29, 43), (35, 70, 87), (91, 126, 140)
        elif destructive:
            fill = (83, 39, 48) if hovered else (53, 28, 39)
            border = (244, 133, 130) if hovered else (151, 82, 91)
            color = (255, 226, 222)
        elif primary:
            fill = (20, 88, 105) if hovered else (14, 63, 84)
            border = (124, 247, 239) if hovered else (82, 190, 206)
            color = (235, 254, 255)
        else:
            fill = (17, 62, 82) if hovered else (10, 42, 61)
            border = (88, 189, 205) if hovered else (54, 132, 156)
            color = (223, 247, 251)
        pygame.draw.rect(panel, fill, rect, border_radius=7)
        pygame.draw.rect(panel, border, rect, 1, border_radius=7)
        surf = self._small.render(text, True, color)
        panel.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))
        if not disabled:
            self._register_hit_region("button", rect, action=action)

    def _draw_box(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int],
        border: tuple[int, int, int],
    ) -> None:
        pygame.draw.rect(panel, fill, rect, border_radius=8)
        pygame.draw.rect(panel, border, rect, 1, border_radius=8)

    def _draw_scrollbar(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        scroll: int,
        total_lines: int,
        visible_lines: int,
    ) -> None:
        track = pygame.Rect(rect.right - 10, rect.y + 16, 4, rect.height - 32)
        pygame.draw.rect(panel, (18, 55, 72), track, border_radius=2)
        ratio = visible_lines / max(1, total_lines)
        thumb_h = max(24, int(track.height * ratio))
        max_scroll = max(1, total_lines - visible_lines)
        thumb_y = track.y + int((track.height - thumb_h) * (scroll / max_scroll))
        pygame.draw.rect(panel, (86, 206, 218), pygame.Rect(track.x, thumb_y, track.width, thumb_h), border_radius=2)

    def _register_hit_region(self, kind: str, rect: pygame.Rect, *, action: str | None = None) -> None:
        self._hit_regions.append(
            TutorialHitRegion(kind=kind, rect=rect.move(self._last_panel_rect.topleft), action=action)
        )

    def _hit_region_at(self, pos: tuple[int, int]) -> TutorialHitRegion | None:
        for region in reversed(self._hit_regions):
            if region.rect.collidepoint(pos):
                return region
        return None

    def _region_hovered(self, action: str) -> bool:
        return self._hover_region is not None and self._hover_region.action == action

    def _wrap_paragraphs(
        self,
        text: str,
        font: pygame.font.Font,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        for paragraph in text.split("\n"):
            wrapped = self._wrap_text(paragraph, font, max_width)
            lines.extend(wrapped)
            lines.append("")
        return lines[:-1] or [""]

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
