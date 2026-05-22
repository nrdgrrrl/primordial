"""In-app documentation browser overlay."""

from __future__ import annotations

import pygame

from primordial.help import (
    HELP_DOC_BY_ID,
    HelpDocument,
    HelpSection,
)

from .help_layout import (
    GROUP_ROW_HEIGHT,
    SIDEBAR_ROW_HEIGHT,
    calculate_help_layout,
)
from .help_mouse import HelpHitRegion
from .help_navigation import HelpNavigation


class HelpOverlay:
    """Render and operate the in-app help/documentation browser."""

    def __init__(self) -> None:
        self.navigation = HelpNavigation()
        self.visible = False
        self.fade = 0
        self.fade_dir = 0
        self.status_message = ""
        self._shade: pygame.Surface | None = None
        self._hit_regions: list[HelpHitRegion] = []
        self._hover_region: HelpHitRegion | None = None
        self._last_panel_rect = pygame.Rect(0, 0, 0, 0)
        self._last_sidebar_rect = pygame.Rect(0, 0, 0, 0)
        self._last_content_rect = pygame.Rect(0, 0, 0, 0)
        self._last_sidebar_scrollbar_rect = pygame.Rect(0, 0, 0, 0)
        self._last_content_scrollbar_rect = pygame.Rect(0, 0, 0, 0)
        self._last_sidebar_scrollbar_thumb_rect = pygame.Rect(0, 0, 0, 0)
        self._last_content_scrollbar_thumb_rect = pygame.Rect(0, 0, 0, 0)
        self._sidebar_row_heights: list[int] = []

        self._title_font = pygame.font.Font(None, 34)
        self._section_font = pygame.font.Font(None, 28)
        self._font = pygame.font.Font(None, 24)
        self._small = pygame.font.Font(None, 20)
        self._tiny = pygame.font.Font(None, 18)

    def open(self, *, doc_id: str | None = None) -> None:
        if doc_id is not None:
            self.navigation.select_section(doc_id, 0)
        self.visible = True
        self.fade_dir = 1
        self.navigation.search_focused = False

    def close(self) -> None:
        self.fade_dir = -1
        self.navigation.search_focused = False

    @property
    def doc_id(self) -> str:
        return self.navigation.selected_doc_id

    @property
    def document(self) -> HelpDocument:
        return self.navigation.current_document

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.MOUSEMOTION:
            if self.navigation._dragging_sidebar_scrollbar or self.navigation._dragging_content_scrollbar:
                self._handle_scrollbar_drag(event.pos)
            self._hover_region = self._hit_region_at(event.pos)
            return None
        if event.type == pygame.MOUSEWHEEL:
            self._handle_wheel(event)
            return None
        if event.type == pygame.MOUSEBUTTONUP:
            self.navigation._dragging_sidebar_scrollbar = False
            self.navigation._dragging_content_scrollbar = False
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
            if self.navigation.search_focused:
                self.navigation.scroll_sidebar(-3)
            else:
                self.navigation.move_selection(-1)
            return None
        if event.key == pygame.K_DOWN:
            if self.navigation.search_focused:
                self.navigation.scroll_sidebar(3)
            else:
                self.navigation.move_selection(1)
            return None
        if event.key == pygame.K_LEFT:
            self.navigation.handle_left()
            return None
        if event.key == pygame.K_RIGHT:
            self.navigation.handle_right()
            return None
        if event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
            self.navigation.handle_enter_on_selected()
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
        self._last_sidebar_rect = layout.sidebar_rect
        self._last_content_rect = layout.content_rect

        self._draw_panel_glow(panel, fade_ratio)
        self._draw_header(panel, layout.header_rect, layout.close_rect)
        self._draw_search(panel, layout.search_rect)
        self._draw_sidebar(panel, layout.sidebar_rect)
        self._draw_sidebar_scrollbar(panel, layout.sidebar_scrollbar_rect)
        self._draw_content(panel, layout.content_rect)
        self._draw_content_scrollbar(panel, layout.content_scrollbar_rect)
        self._draw_footer(panel, layout.footer_rect)

        screen.blit(panel, panel_rect.topleft)

    def _layout_for_screen(self, screen: pygame.Surface):
        return calculate_help_layout(
            screen.get_size(),
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
        if region.sidebar_scrollbar and region.scrollbar_part == "thumb":
            self.navigation._dragging_sidebar_scrollbar = True
            self.navigation._drag_start_y = event.pos[1]
            self.navigation._drag_start_scroll = self.navigation.sidebar_scroll
            return None
        if region.content_scrollbar and region.scrollbar_part == "thumb":
            self.navigation._dragging_content_scrollbar = True
            self.navigation._drag_start_y = event.pos[1]
            self.navigation._drag_start_scroll = self.navigation.content_scroll
            return None
        if region.sidebar_scrollbar:
            self._page_scroll_sidebar(event.pos[1])
            return None
        if region.content_scrollbar:
            self._page_scroll_content(event.pos[1])
            return None
        if region.kind == "group" and region.doc_id is not None:
            self.navigation.toggle_group(region.doc_id)
            self.navigation.search_focused = False
        elif region.kind == "section" and region.doc_id is not None and region.section_index is not None:
            self.navigation.select_section(region.doc_id, region.section_index)
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

    def _handle_scrollbar_drag(self, pos: tuple[int, int]) -> None:
        dy = pos[1] - self.navigation._drag_start_y
        if self.navigation._dragging_sidebar_scrollbar:
            total = self.navigation.sidebar_total_rows
            visible = self.navigation.sidebar_visible_rows
            if total <= visible:
                return
            geometry = self._sidebar_scrollbar_geometry()
            if geometry is None:
                return
            track_rect, thumb_rect = geometry
            track_h = track_rect.height
            thumb_h = thumb_rect.height
            scroll_range = total - visible
            travel = max(1, track_h - thumb_h)
            self.navigation.sidebar_scroll = max(
                0,
                min(scroll_range, int(round(self.navigation._drag_start_scroll + dy * scroll_range / travel))),
            )
        elif self.navigation._dragging_content_scrollbar:
            total = self.navigation.content_line_count
            visible = self.navigation.content_visible_lines
            if total <= visible:
                return
            geometry = self._content_scrollbar_geometry()
            if geometry is None:
                return
            track_rect, thumb_rect = geometry
            track_h = track_rect.height
            thumb_h = thumb_rect.height
            scroll_range = total - visible
            travel = max(1, track_h - thumb_h)
            self.navigation.content_scroll = max(
                0,
                min(scroll_range, int(round(self.navigation._drag_start_scroll + dy * scroll_range / travel))),
            )

    def _handle_wheel(self, event: pygame.event.Event) -> None:
        y = int(getattr(event, "y", 0))
        if y == 0 and getattr(event, "button", None) in (4, 5):
            y = 1 if event.button == 4 else -1
        pos = pygame.mouse.get_pos()
        amount = -y
        panel_pos = (pos[0] - self._last_panel_rect.x, pos[1] - self._last_panel_rect.y)
        if panel_pos[0] < self._last_content_rect.x:
            self.navigation.scroll_sidebar(amount * 3)
        else:
            self.navigation.scroll_content(amount * 3)

    def _draw_panel_glow(self, panel: pygame.Surface, fade_ratio: float) -> None:
        rect = panel.get_rect()
        pygame.draw.rect(panel, (10, 40, 62, int(190 * fade_ratio)), rect, border_radius=10)
        pygame.draw.rect(panel, (83, 205, 226, int(180 * fade_ratio)), rect, 2, border_radius=10)
        pygame.draw.rect(panel, (20, 77, 102, int(120 * fade_ratio)), rect.inflate(-8, -8), 1, border_radius=8)

    def _draw_header(self, panel: pygame.Surface, rect: pygame.Rect, close_rect: pygame.Rect) -> None:
        title = self._title_font.render("PRIMORDIAL GUIDE", True, (221, 249, 255))
        panel.blit(title, (rect.x + 6, rect.y + 4))
        subtitle = self._small.render("Browse all help topics in the sidebar", True, (139, 202, 225))
        panel.blit(subtitle, (rect.x + 6, rect.y + 34))
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
        panel.blit(self._small.render(text, True, color), (rect.x + 10, rect.y + 10))
        if query:
            clear_rect = pygame.Rect(rect.right - 26, rect.y + 7, 18, 22)
            self._draw_button(panel, clear_rect, "x", hovered=self._region_hovered("button", action="clear_search"), font=self._tiny)
            self._register_hit_region("button", clear_rect, action="clear_search")
        self._register_hit_region("search", rect)

    def _draw_sidebar(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (6, 23, 39), (40, 103, 132))
        items = self.navigation.sidebar_items

        visible_height = rect.height - 20
        visible_rows = max(1, visible_height // SIDEBAR_ROW_HEIGHT)
        self.navigation.set_sidebar_bounds(total_rows=len(items), visible_rows=visible_rows)

        if not items:
            message = "No sections match your search."
            y = rect.y + 14
            for line in self._wrap_text(message, self._font, rect.width - 20):
                panel.blit(self._font.render(line, True, (190, 224, 234)), (rect.x + 10, y))
                y += 23
            return

        row_heights = []
        for item in items:
            if item.kind == "group":
                row_heights.append(GROUP_ROW_HEIGHT)
            else:
                label_w = rect.width - 36
                wrapped = self._wrap_text(item.title, self._small, label_w)
                h = max(SIDEBAR_ROW_HEIGHT, len(wrapped) * 18 + 8)
                row_heights.append(h)
        self._sidebar_row_heights = row_heights
        total_rows = len(items)
        accum = 0
        visible_rows = 0
        for h in row_heights:
            if accum + h > visible_height:
                break
            accum += h
            visible_rows += 1
        self.navigation.set_sidebar_bounds(total_rows=total_rows, visible_rows=max(1, visible_rows))

        first = self.navigation.sidebar_scroll
        y = rect.y + 10
        for row_idx in range(first, total_rows):
            item = items[row_idx]
            rh = row_heights[row_idx]
            if y + rh > rect.bottom - 6:
                break

            if item.kind == "group":
                self._draw_group_row(panel, rect, item, y, rh)
            elif item.kind == "section":
                self._draw_section_row(panel, rect, item, y, rh)

            y += rh

    def _draw_group_row(self, panel: pygame.Surface, sidebar_rect: pygame.Rect, item, y: int, height: int) -> None:
        is_expanded = self.navigation.expanded_groups.get(item.doc_id, False)
        is_selected_doc = item.doc_id == self.navigation.selected_doc_id
        row_rect = pygame.Rect(sidebar_rect.x + 4, y, sidebar_rect.width - 8, height)
        hovered = self._region_hovered("group", doc_id=item.doc_id)

        if is_selected_doc:
            pygame.draw.rect(panel, (14, 55, 74), row_rect, border_radius=6)
        elif hovered:
            pygame.draw.rect(panel, (10, 38, 56), row_rect, border_radius=6)
        if is_selected_doc:
            pygame.draw.rect(panel, (83, 210, 220), row_rect, 1, border_radius=6)
        elif hovered:
            pygame.draw.rect(panel, (50, 130, 158), row_rect, 1, border_radius=6)

        arrow = "v " if is_expanded else "> "
        color = (232, 252, 255) if is_selected_doc else (185, 218, 232)
        label = arrow + item.title
        label_w = row_rect.width - 12
        wrapped = self._wrap_text(label, self._small, label_w)[:2]
        line_y = row_rect.y + 4
        for line in wrapped:
            panel.blit(self._small.render(line, True, color), (row_rect.x + 6, line_y))
            line_y += 18

        self._register_hit_region("group", row_rect, doc_id=item.doc_id)

    def _draw_section_row(self, panel: pygame.Surface, sidebar_rect: pygame.Rect, item, y: int, height: int) -> None:
        is_selected = item.doc_id == self.navigation.selected_doc_id and item.section_index == self.navigation.selected_section_index
        row_rect = pygame.Rect(sidebar_rect.x + 10, y, sidebar_rect.width - 14, height)
        hovered = self._region_hovered("section", doc_id=item.doc_id, section_index=item.section_index)

        if is_selected:
            pygame.draw.rect(panel, (18, 75, 96), row_rect, border_radius=5)
            pygame.draw.rect(panel, (102, 234, 235), row_rect, 1, border_radius=5)
        elif hovered:
            pygame.draw.rect(panel, (12, 47, 66), row_rect, border_radius=5)

        color = (232, 252, 255) if is_selected else (166, 205, 221)
        label_w = row_rect.width - 20
        wrapped = self._wrap_text(item.title, self._small, label_w)[:3]
        line_y = row_rect.y + 2
        for line in wrapped:
            panel.blit(self._small.render(line, True, color), (row_rect.x + 14, line_y))
            line_y += 18

        self._register_hit_region("section", row_rect, doc_id=item.doc_id, section_index=item.section_index)

    def _draw_sidebar_scrollbar(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        total = self.navigation.sidebar_total_rows
        visible = self.navigation.sidebar_visible_rows
        if total <= visible:
            return
        self._last_sidebar_scrollbar_rect = rect
        geometry = self._sidebar_scrollbar_geometry()
        if geometry is None:
            return
        _, thumb_rect = geometry
        pygame.draw.rect(panel, (14, 40, 56), rect, border_radius=4)
        thumb_color = (100, 210, 220) if self.navigation._dragging_sidebar_scrollbar else (70, 180, 200)
        pygame.draw.rect(panel, thumb_color, thumb_rect, border_radius=4)
        self._last_sidebar_scrollbar_rect = rect
        self._last_sidebar_scrollbar_thumb_rect = thumb_rect
        self._register_hit_region(
            "sidebar_scrollbar_track",
            rect,
            sidebar_scrollbar=True,
            scrollbar_part="track",
        )
        self._register_hit_region(
            "sidebar_scrollbar_thumb",
            thumb_rect,
            sidebar_scrollbar=True,
            scrollbar_part="thumb",
        )

    def _draw_content(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (7, 24, 39), (42, 104, 132))
        section = self._selected_section()
        title = section.title if section is not None else "No Matching Sections"
        y = rect.y + 16
        content_width = rect.width - 36
        for line in self._wrap_text(title, self._section_font, content_width)[:2]:
            panel.blit(self._section_font.render(line, True, (234, 251, 255)), (rect.x + 18, y))
            y += 25
        pygame.draw.line(panel, (35, 88, 112), (rect.x + 16, y + 4), (rect.right - 16, y + 4), 1)
        y += 18

        body_rect = pygame.Rect(rect.x + 18, y, content_width, rect.bottom - y - 14)
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

    def _draw_content_scrollbar(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        total = self.navigation.content_line_count
        visible = self.navigation.content_visible_lines
        if total <= visible:
            return
        self._last_content_scrollbar_rect = rect
        geometry = self._content_scrollbar_geometry()
        if geometry is None:
            return
        _, thumb_rect = geometry
        pygame.draw.rect(panel, (14, 40, 56), rect, border_radius=4)
        thumb_color = (100, 210, 220) if self.navigation._dragging_content_scrollbar else (70, 180, 200)
        pygame.draw.rect(panel, thumb_color, thumb_rect, border_radius=4)
        self._last_content_scrollbar_rect = rect
        self._last_content_scrollbar_thumb_rect = thumb_rect
        self._register_hit_region(
            "content_scrollbar_track",
            rect,
            content_scrollbar=True,
            scrollbar_part="track",
        )
        self._register_hit_region(
            "content_scrollbar_thumb",
            thumb_rect,
            content_scrollbar=True,
            scrollbar_part="thumb",
        )

    def _draw_footer(self, panel: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_box(panel, rect, (5, 20, 32), (34, 88, 112))
        entry = HELP_DOC_BY_ID.get(self.navigation.selected_doc_id)
        doc_title = entry.title if entry else self.navigation.selected_doc_id
        section_count = len(self.navigation.current_document.sections)
        status = f"{doc_title} · Section {self.navigation.selected_section_index + 1} / {section_count}"
        if self.navigation.search_query:
            status += f" · Search: {self.navigation.search_query}"
        if self.status_message:
            status += " · " + self.status_message
        panel.blit(self._small.render(status, True, (190, 230, 238)), (rect.x + 12, rect.y + 8))
        hint = "Up/Down navigate, Left/Right collapse/expand, Enter select, / search, Esc close. Mouse: click sidebar, wheel to scroll, drag scrollbars."
        hint_y = rect.y + 32
        for line in self._wrap_text(hint, self._small, rect.width - 24)[:2]:
            panel.blit(self._small.render(line, True, (141, 190, 210)), (rect.x + 12, hint_y))
            hint_y += 18

    def _selected_section(self) -> HelpSection | None:
        doc = self.navigation.current_document
        if not doc.sections:
            return None
        index = max(0, min(len(doc.sections) - 1, self.navigation.selected_section_index))
        return doc.sections[index]

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

    def _register_hit_region(
        self,
        kind: str,
        rect: pygame.Rect,
        *,
        section_index: int | None = None,
        action: str | None = None,
        doc_id: str | None = None,
        sidebar_scrollbar: bool = False,
        content_scrollbar: bool = False,
        scrollbar_part: str | None = None,
    ) -> None:
        self._hit_regions.append(
            HelpHitRegion(
                kind=kind,
                rect=rect.move(self._last_panel_rect.topleft),
                section_index=section_index,
                action=action,
                doc_id=doc_id,
                sidebar_scrollbar=sidebar_scrollbar,
                content_scrollbar=content_scrollbar,
                scrollbar_part=scrollbar_part,
            )
        )

    def _sidebar_scrollbar_geometry(self) -> tuple[pygame.Rect, pygame.Rect] | None:
        total = self.navigation.sidebar_total_rows
        visible = self.navigation.sidebar_visible_rows
        if total <= visible or self._last_sidebar_scrollbar_rect.width <= 0:
            return None
        track_rect = self._last_sidebar_scrollbar_rect.copy()
        ratio = visible / max(1, total)
        thumb_h = max(20, int(track_rect.height * ratio))
        thumb_h = min(thumb_h, track_rect.height)
        scroll_range = max(1, total - visible)
        travel = max(0, track_rect.height - thumb_h)
        thumb_y = track_rect.y + int(travel * (self.navigation.sidebar_scroll / scroll_range)) if travel else track_rect.y
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_h)
        return track_rect, thumb_rect

    def _content_scrollbar_geometry(self) -> tuple[pygame.Rect, pygame.Rect] | None:
        total = self.navigation.content_line_count
        visible = self.navigation.content_visible_lines
        if total <= visible or self._last_content_scrollbar_rect.width <= 0:
            return None
        track_rect = self._last_content_scrollbar_rect.copy()
        ratio = visible / max(1, total)
        thumb_h = max(20, int(track_rect.height * ratio))
        thumb_h = min(thumb_h, track_rect.height)
        scroll_range = max(1, total - visible)
        travel = max(0, track_rect.height - thumb_h)
        thumb_y = track_rect.y + int(travel * (self.navigation.content_scroll / scroll_range)) if travel else track_rect.y
        thumb_rect = pygame.Rect(track_rect.x, thumb_y, track_rect.width, thumb_h)
        return track_rect, thumb_rect

    def _page_scroll_sidebar(self, click_y: int) -> None:
        geometry = self._sidebar_scrollbar_geometry()
        if geometry is None:
            return
        _, thumb_rect = geometry
        click_y -= self._last_panel_rect.y
        if click_y < thumb_rect.top:
            self.navigation.scroll_sidebar(-(max(1, self.navigation.sidebar_visible_rows - 1)))
        elif click_y > thumb_rect.bottom:
            self.navigation.scroll_sidebar(max(1, self.navigation.sidebar_visible_rows - 1))

    def _page_scroll_content(self, click_y: int) -> None:
        geometry = self._content_scrollbar_geometry()
        if geometry is None:
            return
        _, thumb_rect = geometry
        click_y -= self._last_panel_rect.y
        if click_y < thumb_rect.top:
            self.navigation.scroll_content(-(max(1, self.navigation.content_visible_lines - 1)))
        elif click_y > thumb_rect.bottom:
            self.navigation.scroll_content(max(1, self.navigation.content_visible_lines - 1))

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
        doc_id: str | None = None,
    ) -> bool:
        region = self._hover_region
        if region is None or region.kind != kind:
            return False
        if section_index is not None and region.section_index != section_index:
            return False
        if action is not None and region.action != action:
            return False
        if doc_id is not None and region.doc_id != doc_id:
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
        font: pygame.font.Font | None = None,
    ) -> None:
        fill = (18, 72, 92) if hovered else (10, 42, 60)
        border = (103, 232, 230) if hovered else (54, 135, 158)
        pygame.draw.rect(panel, fill, rect, border_radius=6)
        pygame.draw.rect(panel, border, rect, 1, border_radius=6)
        f = font or self._small
        surf = f.render(text, True, (225, 250, 252))
        panel.blit(surf, (rect.centerx - surf.get_width() // 2, rect.centery - surf.get_height() // 2))
