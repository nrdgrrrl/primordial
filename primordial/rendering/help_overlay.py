"""In-app documentation browser overlay."""

from __future__ import annotations

import pygame

from primordial.help import HelpDocument, HelpSection, load_help_document

from .help_layout import (
    NAV_ROW_HEIGHT,
    calculate_help_layout,
    panel_rect_for_screen,
)
from .help_mouse import HelpHitRegion
from .help_navigation import HelpNavigation


class HelpOverlay:
    """Render and operate the in-app help/documentation browser."""

    def __init__(self, document: HelpDocument | None = None) -> None:
        self.document = document or load_help_document()
        self.navigation = HelpNavigation(self.document)
        self.visible = False
        self.fade = 0
        self.fade_dir = 0
        self.status_message = ""
        self._shade: pygame.Surface | None = None
        self._hit_regions: list[HelpHitRegion] = []
        self._hover_region: HelpHitRegion | None = None
        self._last_panel_rect = pygame.Rect(0, 0, 0, 0)
        self._last_nav_rect = pygame.Rect(0, 0, 0, 0)
        self._last_content_rect = pygame.Rect(0, 0, 0, 0)

        self._title_font = pygame.font.Font(None, 34)
        self._section_font = pygame.font.Font(None, 28)
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 20)
        self._tiny = pygame.font.Font(None, 18)

    def open(self, *, reload_document: bool = True) -> None:
        if reload_document:
            self.set_document(load_help_document())
        self.visible = True
        self.fade_dir = 1
        self.navigation.search_focused = False

    def close(self) -> None:
        self.fade_dir = -1
        self.navigation.search_focused = False

    def set_document(self, document: HelpDocument) -> None:
        self.document = document
        self.navigation.set_document(document)
        self.status_message = document.error or ""

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.MOUSEMOTION:
            self._hover_region = self._hit_region_at(event.pos)
            return None
        if event.type == pygame.MOUSEWHEEL:
            self._handle_wheel(event)
            return None
        if event.type == pygame.MOUSEBUTTONDOWN:
            return self._handle_mouse_button(event)
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_ESCAPE:
            self.close()
            return "close"
        if event.key == pygame.K_SLASH:
            self.navigation.search_focused = True
            return None
        if event.key == pygame.K_TAB:
            self.navigation.search_focused = not self.navigation.search_focused
            return None
        if event.key == pygame.K_BACKSPACE:
            if self.navigation.search_focused or self.navigation.search_query:
                self.navigation.backspace_search()
            return None
        if event.key == pygame.K_DELETE and self.navigation.search_query:
            self.navigation.clear_search()
            return None
        if event.key == pygame.K_UP:
            self.navigation.move_selection(-1)
            return None
        if event.key == pygame.K_DOWN:
            self.navigation.move_selection(1)
            return None
        if event.key == pygame.K_PAGEUP:
            self.navigation.scroll_content(-8)
            return None
        if event.key == pygame.K_PAGEDOWN:
            self.navigation.scroll_content(8)
            return None
        if event.key == pygame.K_HOME:
            self.navigation.content_scroll = 0
            return None
        if event.key == pygame.K_END:
            self.navigation.content_scroll = self.navigation.content_line_count
            self.navigation.clamp_content_scroll()
            return None

        text = getattr(event, "unicode", "")
        if text and text.isprintable() and not getattr(event, "mod", 0) & pygame.KMOD_CTRL:
            self.navigation.search_focused = True
            self.navigation.append_search_text(text)
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
        alpha = int(178 * fade_ratio)
        if self._shade is None or self._shade.get_size() != screen.get_size():
            self._shade = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._shade.fill((0, 7, 18, alpha))
        screen.blit(self._shade, (0, 0))

        layout = self._layout_for_screen(screen)
        panel_rect = layout.panel_rect
        panel = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel.fill((5, 18, 33, int(246 * fade_ratio)))
        self._hit_regions = []
        self._last_panel_rect = panel_rect
        self._last_nav_rect = layout.nav_rect
        self._last_content_rect = layout.content_rect

        self._draw_panel_glow(panel, fade_ratio)
        self._draw_header(panel, layout.header_rect, layout.close_rect)
        self._draw_search(panel, layout.search_rect)
        self._draw_nav(panel, layout.nav_rect)
        self._draw_content(panel, layout.content_rect)
        self._draw_footer(panel, layout.footer_rect)

        screen.blit(panel, panel_rect.topleft)

    def _layout_for_screen(self, screen: pygame.Surface):
        return calculate_help_layout(
            screen.get_size(),
            section_titles=[section.title for section in self.document.sections],
            title_font=self._font,
        )

    def _handle_mouse_button(self, event: pygame.event.Event) -> str | None:
        if event.button in (4, 5):
            self._handle_wheel(event)
            return None
        if event.button != 1:
            return None
        region = self._hit_region_at(event.pos)
        self._hover_region = region
        if region is None:
            self.navigation.search_focused = False
            return None
        if region.kind == "section" and region.section_index is not None:
            self.navigation.select_section(region.section_index)
            self.navigation.search_focused = False
        elif region.kind == "search":
            self.navigation.search_focused = True
        elif region.kind == "button" and region.action == "close":
            self.close()
            return "close"
        elif region.kind == "button" and region.action == "clear_search":
            self.navigation.clear_search()
            self.navigation.search_focused = True
        return None

    def _handle_wheel(self, event: pygame.event.Event) -> None:
        y = int(getattr(event, "y", 0))
        if y == 0 and getattr(event, "button", None) in (4, 5):
            y = 1 if event.button == 4 else -1
        pos = pygame.mouse.get_pos()
        amount = -y
        if self._last_nav_rect.move(self._last_panel_rect.topleft).collidepoint(pos):
            self.navigation.scroll_nav(amount, self._visible_nav_rows())
        else:
            self.navigation.scroll_content(amount * 3)

    def _draw_panel_glow(self, panel: pygame.Surface, fade_ratio: float) -> None:
        rect = panel.get_rect()
        pygame.draw.rect(panel, (10, 40, 62, int(190 * fade_ratio)), rect, border_radius=10)
        pygame.draw.rect(panel, (83, 205, 226, int(180 * fade_ratio)), rect, 2, border_radius=10)
        pygame.draw.rect(panel, (20, 77, 102, int(120 * fade_ratio)), rect.inflate(-8, -8), 1, border_radius=8)

    def _draw_header(self, panel: pygame.Surface, rect: pygame.Rect, close_rect: pygame.Rect) -> None:
        title = self._title_font.render("PRIMORDIAL GUIDE", True, (221, 249, 255))
        panel.blit(title, (rect.x + 6, rect.y + 10))
        subtitle_text = self._header_summary()
        subtitle = self._small.render(subtitle_text, True, (139, 202, 225))
        panel.blit(subtitle, (rect.x + 6, rect.y + 44))
        hovered = self._region_hovered("button", action="close")
        self._draw_button(panel, close_rect, "Close", hovered=hovered)
        self._register_hit_region("button", close_rect, action="close")
        pygame.draw.line(panel, (38, 96, 122), (18, rect.bottom), (panel.get_width() - 18, rect.bottom), 1)

    def _draw_search(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        focused = self.navigation.search_focused
        hovered = self._region_hovered("search")
        fill = (13, 45, 63) if focused or hovered else (7, 27, 44)
        border = (108, 234, 232) if focused else ((65, 157, 178) if hovered else (42, 104, 132))
        pygame.draw.rect(panel, fill, rect, border_radius=7)
        pygame.draw.rect(panel, border, rect, 1, border_radius=7)
        query = self.navigation.search_query
        placeholder = "Search guide..."
        text = query if query else placeholder
        color = (230, 252, 255) if query else (104, 150, 172)
        panel.blit(self._font.render(text, True, color), (rect.x + 12, rect.y + 9))
        if query:
            clear_rect = pygame.Rect(rect.right - 31, rect.y + 7, 22, 24)
            self._draw_button(panel, clear_rect, "x", hovered=self._region_hovered("button", action="clear_search"))
            self._register_hit_region("button", clear_rect, action="clear_search")
        self._register_hit_region("search", rect)

    def _draw_nav(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (6, 23, 39), (40, 103, 132))
        indices = self.navigation.visible_section_indices
        if not indices:
            message = "No sections match your search."
            y = rect.y + 14
            for line in self._wrap_text(message, self._font, rect.width - 24):
                panel.blit(self._font.render(line, True, (190, 224, 234)), (rect.x + 12, y))
                y += 23
            return

        visible_rows = self._visible_nav_rows(rect)
        self.navigation.ensure_selected_nav_visible(visible_rows)
        max_first = max(0, len(indices) - visible_rows)
        self.navigation.nav_first_visible = min(self.navigation.nav_first_visible, max_first)
        shown = indices[self.navigation.nav_first_visible:self.navigation.nav_first_visible + visible_rows]
        y = rect.y + 10
        for section_index in shown:
            section = self.document.sections[section_index]
            row_rect = pygame.Rect(rect.x + 10, y, rect.width - 20, NAV_ROW_HEIGHT - 6)
            selected = section_index == self.navigation.selected_section_index
            hovered = self._region_hovered("section", section_index=section_index)
            if selected:
                pygame.draw.rect(panel, (18, 75, 96), row_rect, border_radius=7)
                pygame.draw.rect(panel, (102, 234, 235), row_rect, 1, border_radius=7)
            elif hovered:
                pygame.draw.rect(panel, (12, 47, 66), row_rect, border_radius=7)
                pygame.draw.rect(panel, (55, 146, 174), row_rect, 1, border_radius=7)
            color = (232, 252, 255) if selected else (166, 205, 221)
            if section.level > 2:
                color = (132, 178, 198) if not selected else color
            label_rect = row_rect.inflate(-16, -6)
            lines = self._wrap_text(section.title, self._font, label_rect.width)[:2]
            line_y = label_rect.y + 1
            for line in lines:
                panel.blit(self._font.render(line, True, color), (label_rect.x, line_y))
                line_y += 19
            self._register_hit_region("section", row_rect, section_index=section_index)
            y += NAV_ROW_HEIGHT

        if self.navigation.nav_first_visible > 0:
            panel.blit(self._tiny.render("more above", True, (108, 152, 174)), (rect.right - 82, rect.y + 5))
        if self.navigation.nav_first_visible + visible_rows < len(indices):
            panel.blit(self._tiny.render("more below", True, (108, 152, 174)), (rect.right - 82, rect.bottom - 20))

    def _draw_content(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (7, 24, 39), (42, 104, 132))
        section = self._selected_section()
        title = section.title if section is not None else "No Matching Sections"
        y = rect.y + 16
        for line in self._wrap_text(title, self._section_font, rect.width - 40)[:2]:
            panel.blit(self._section_font.render(line, True, (234, 251, 255)), (rect.x + 18, y))
            y += 25
        pygame.draw.line(panel, (35, 88, 112), (rect.x + 16, y + 4), (rect.right - 16, y + 4), 1)
        y += 18

        body_rect = pygame.Rect(rect.x + 18, y, rect.width - 36, rect.bottom - y - 14)
        content_lines = self._content_lines(section, body_rect.width)
        visible_lines = max(1, body_rect.height // 23)
        self.navigation.set_content_bounds(
            line_count=len(content_lines),
            visible_lines=visible_lines,
        )
        start = self.navigation.content_scroll
        for line in content_lines[start:start + visible_lines]:
            color = (205, 232, 240)
            if line.startswith("- "):
                color = (185, 222, 234)
            elif " | " in line:
                color = (168, 213, 226)
            panel.blit(self._font.render(line, True, color), (body_rect.x, y))
            y += 23
        if self.navigation.content_line_count > visible_lines:
            self._draw_scrollbar(panel, rect, self.navigation.content_scroll, self.navigation.content_line_count, visible_lines)

    def _draw_footer(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (5, 20, 32), (34, 88, 112))
        selected_pos = self.navigation.selected_visible_position + 1 if self.navigation.visible_section_indices else 0
        total = len(self.navigation.visible_section_indices)
        status = f"Section {selected_pos} / {total}"
        if self.navigation.search_query:
            status += f" · Search: {self.navigation.search_query}"
        if self.status_message:
            status += " · " + self.status_message
        panel.blit(self._small.render(status, True, (190, 230, 238)), (rect.x + 12, rect.y + 10))
        hint = "Mouse: click sections, search, scroll. Keyboard: type to search, Up/Down section, PageUp/PageDown scroll, Del clear search, Esc close."
        for line in self._wrap_text(hint, self._small, rect.width - 24)[:1]:
            panel.blit(self._small.render(line, True, (141, 190, 210)), (rect.x + 12, rect.y + 35))

    def _selected_section(self) -> HelpSection | None:
        if not self.document.sections:
            return None
        index = max(0, min(len(self.document.sections) - 1, self.navigation.selected_section_index))
        return self.document.sections[index]

    def _content_lines(self, section: HelpSection | None, max_width: int) -> list[str]:
        if section is None:
            return ["No sections match your search. Clear the search box to return to the full guide."]
        lines: list[str] = []
        for block in section.body.split("\n"):
            if not block.strip():
                lines.append("")
                continue
            prefix = ""
            text = block
            if block.startswith("- "):
                prefix = "- "
                text = block[2:]
            wrapped = self._wrap_text(text, self._font, max(1, max_width - self._font.size(prefix)[0]))
            for idx, line in enumerate(wrapped):
                lines.append((prefix if idx == 0 else "  ") + line)
        return lines or ["This section has no body text yet."]

    def _header_summary(self) -> str:
        source = self.document.source_path.name
        if not self.document.ok:
            return f"Documentation source: {source} · load issue"
        return f"Documentation source: {source} · {len(self.document.sections)} sections"

    def _visible_nav_rows(self, rect: pygame.Rect | None = None) -> int:
        nav_rect = rect or self._last_nav_rect
        if nav_rect.height <= 0:
            return 1
        return max(1, (nav_rect.height - 20) // NAV_ROW_HEIGHT)

    def _register_hit_region(
        self,
        kind: str,
        rect: pygame.Rect,
        *,
        section_index: int | None = None,
        action: str | None = None,
    ) -> None:
        self._hit_regions.append(
            HelpHitRegion(
                kind=kind,
                rect=rect.move(self._last_panel_rect.topleft),
                section_index=section_index,
                action=action,
            )
        )

    def _hit_region_at(self, pos: tuple[int, int]) -> HelpHitRegion | None:
        for region in reversed(self._hit_regions):
            if region.rect.collidepoint(pos):
                return region
        return None

    def _region_hovered(
        self,
        kind: str,
        *,
        section_index: int | None = None,
        action: str | None = None,
    ) -> bool:
        region = self._hover_region
        if region is None or region.kind != kind:
            return False
        if section_index is not None and region.section_index != section_index:
            return False
        if action is not None and region.action != action:
            return False
        return True

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

    def _draw_box(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        fill: tuple[int, int, int],
        border: tuple[int, int, int],
    ) -> None:
        pygame.draw.rect(panel, fill, rect, border_radius=8)
        pygame.draw.rect(panel, border, rect, 1, border_radius=8)

    def _draw_button(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        *,
        hovered: bool = False,
    ) -> None:
        fill = (18, 72, 92) if hovered else (10, 42, 60)
        border = (103, 232, 230) if hovered else (54, 135, 158)
        pygame.draw.rect(panel, fill, rect, border_radius=6)
        pygame.draw.rect(panel, border, rect, 1, border_radius=6)
        surf = self._small.render(text, True, (225, 250, 252))
        panel.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))

    def _draw_scrollbar(
        self,
        panel: pygame.Surface,
        rect: pygame.Rect,
        scroll: int,
        total_lines: int,
        visible_lines: int,
    ) -> None:
        track = pygame.Rect(rect.right - 9, rect.y + 60, 4, rect.height - 78)
        pygame.draw.rect(panel, (19, 54, 70), track, border_radius=2)
        ratio = visible_lines / max(1, total_lines)
        thumb_h = max(26, int(track.height * ratio))
        max_scroll = max(1, total_lines - visible_lines)
        thumb_y = track.y + int((track.height - thumb_h) * (scroll / max_scroll))
        pygame.draw.rect(panel, (84, 202, 216), pygame.Rect(track.x, thumb_y, track.width, thumb_h), border_radius=2)
