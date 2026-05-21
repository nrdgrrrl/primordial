"""Navigation and search state for the in-app help overlay."""

from __future__ import annotations

from primordial.help import HelpDocument, SearchResult, search_sections


class HelpNavigation:
    """Track selected help section, search text, focus, and scroll offsets."""

    def __init__(self, document: HelpDocument) -> None:
        self.document = document
        self.selected_section_index = 0
        self.nav_first_visible = 0
        self.content_scroll = 0
        self.content_line_count = 0
        self.content_visible_lines = 1
        self.search_query = ""
        self.search_focused = False
        self.results: list[SearchResult] = []
        self._nav_scroll_from_wheel = False

    @property
    def visible_section_indices(self) -> list[int]:
        if self.search_query.strip():
            return [result.section_index for result in self.results]
        return list(range(len(self.document.sections)))

    @property
    def selected_visible_position(self) -> int:
        indices = self.visible_section_indices
        if not indices:
            return 0
        try:
            return indices.index(self.selected_section_index)
        except ValueError:
            return 0

    def set_document(self, document: HelpDocument) -> None:
        self.document = document
        self.selected_section_index = 0
        self.nav_first_visible = 0
        self.content_scroll = 0
        self.content_line_count = 0
        self.search_query = ""
        self.search_focused = False
        self.results = []
        self._nav_scroll_from_wheel = False

    def set_search_query(self, query: str) -> None:
        self.search_query = query
        self.results = search_sections(self.document.sections, query)
        indices = self.visible_section_indices
        if not indices:
            self.selected_section_index = 0
        elif self.selected_section_index not in indices:
            self.selected_section_index = indices[0]
        self.nav_first_visible = min(self.nav_first_visible, max(0, len(indices) - 1))
        self.content_scroll = 0
        self._nav_scroll_from_wheel = False

    def append_search_text(self, text: str) -> None:
        if not text:
            return
        self.set_search_query(self.search_query + text)

    def backspace_search(self) -> None:
        if self.search_query:
            self.set_search_query(self.search_query[:-1])

    def clear_search(self) -> None:
        self.set_search_query("")

    def move_selection(self, delta: int) -> None:
        indices = self.visible_section_indices
        if not indices:
            self.selected_section_index = 0
            self.content_scroll = 0
            return
        try:
            position = indices.index(self.selected_section_index)
        except ValueError:
            position = 0
        position = max(0, min(len(indices) - 1, position + delta))
        self.selected_section_index = indices[position]
        self.content_scroll = 0
        self._nav_scroll_from_wheel = False

    def select_section(self, section_index: int) -> None:
        if 0 <= section_index < len(self.document.sections):
            self.selected_section_index = section_index
            self.content_scroll = 0
            self._nav_scroll_from_wheel = False

    def scroll_nav(self, amount: int, visible_rows: int) -> None:
        indices = self.visible_section_indices
        max_first = max(0, len(indices) - max(1, visible_rows))
        self.nav_first_visible = max(0, min(max_first, self.nav_first_visible + amount))
        self._nav_scroll_from_wheel = True

    def ensure_selected_nav_visible(self, visible_rows: int) -> None:
        if self._nav_scroll_from_wheel:
            self._nav_scroll_from_wheel = False
            return
        position = self.selected_visible_position
        if position < self.nav_first_visible:
            self.nav_first_visible = position
        elif position >= self.nav_first_visible + visible_rows:
            self.nav_first_visible = position - visible_rows + 1

    def set_content_bounds(self, *, line_count: int, visible_lines: int) -> None:
        self.content_line_count = max(0, line_count)
        self.content_visible_lines = max(1, visible_lines)
        self.clamp_content_scroll()

    def scroll_content(self, amount: int) -> None:
        self.content_scroll += amount
        self.clamp_content_scroll()

    def clamp_content_scroll(self) -> None:
        max_scroll = max(0, self.content_line_count - self.content_visible_lines)
        self.content_scroll = max(0, min(max_scroll, self.content_scroll))
