"""Navigation and search state for the in-app help overlay."""

from __future__ import annotations

from dataclasses import dataclass, field

from primordial.help import (
    HELP_DOCUMENTS,
    HelpDocument,
    HelpDocEntry,
    SearchResult,
    load_help_document_by_id,
    search_sections,
)


@dataclass(frozen=True)
class HelpNavItem:
    kind: str
    doc_id: str
    section_index: int | None
    title: str
    level: int


class HelpNavigation:
    """Track selected help section, search text, focus, and scroll offsets."""

    def __init__(self) -> None:
        self.expanded_groups: dict[str, bool] = {}
        self._pre_search_expanded: dict[str, bool] = {}
        self.documents: dict[str, HelpDocument] = {}
        self.selected_doc_id: str = HELP_DOCUMENTS[0].doc_id
        self.selected_section_index: int = 0
        self.focused_sidebar_index: int = 0
        self.sidebar_scroll: int = 0
        self.content_scroll: int = 0
        self.content_line_count: int = 0
        self.content_visible_lines: int = 1
        self.sidebar_total_rows: int = 0
        self.sidebar_visible_rows: int = 1
        self.search_query: str = ""
        self.search_focused: bool = False
        self.search_results: dict[str, list[SearchResult]] = {}
        self._dragging_sidebar_scrollbar: bool = False
        self._dragging_content_scrollbar: bool = False
        self._drag_start_y: int = 0
        self._drag_start_scroll: int = 0

        for entry in HELP_DOCUMENTS:
            self.documents[entry.doc_id] = load_help_document_by_id(entry.doc_id)
        self.expanded_groups[self.selected_doc_id] = True

    @property
    def sidebar_items(self) -> list[HelpNavItem]:
        if self.search_query.strip():
            return self._search_sidebar_items()
        items: list[HelpNavItem] = []
        for entry in HELP_DOCUMENTS:
            items.append(HelpNavItem(kind="group", doc_id=entry.doc_id, section_index=None, title=entry.title, level=0))
            if self.expanded_groups.get(entry.doc_id, False):
                doc = self.documents.get(entry.doc_id)
                if doc is not None:
                    for idx, section in enumerate(doc.sections):
                        items.append(HelpNavItem(kind="section", doc_id=entry.doc_id, section_index=idx, title=section.title, level=1))
        return items

    def _search_sidebar_items(self) -> list[HelpNavItem]:
        items: list[HelpNavItem] = []
        for entry in HELP_DOCUMENTS:
            results = self.search_results.get(entry.doc_id, [])
            if not results:
                continue
            items.append(HelpNavItem(kind="group", doc_id=entry.doc_id, section_index=None, title=entry.title, level=0))
            for result in results:
                items.append(HelpNavItem(kind="section", doc_id=entry.doc_id, section_index=result.section_index, title=result.title, level=1))
        return items

    @property
    def current_document(self) -> HelpDocument:
        return self.documents.get(self.selected_doc_id, HelpDocument(title="Error", sections=(), source_path=__import__('pathlib').Path("<error>"), error="unknown doc"))

    @property
    def selected_sidebar_position(self) -> int:
        for i, item in enumerate(self.sidebar_items):
            if item.kind == "section" and item.doc_id == self.selected_doc_id and item.section_index == self.selected_section_index:
                return i
        return 0

    def set_search_query(self, query: str) -> None:
        if not self.search_query.strip() and query.strip():
            self._pre_search_expanded = dict(self.expanded_groups)
        self.search_query = query
        self.search_results = {}
        if query.strip():
            for entry in HELP_DOCUMENTS:
                doc = self.documents.get(entry.doc_id)
                if doc is not None:
                    results = search_sections(doc.sections, query)
                    if results:
                        self.search_results[entry.doc_id] = results
                        self.expanded_groups[entry.doc_id] = True
        else:
            self.expanded_groups = dict(self._pre_search_expanded)
            self._pre_search_expanded = {}
        self.clamp_sidebar_scroll(total_rows=len(self.sidebar_items))
        self.clamp_content_scroll()
        self.clamp_focused_sidebar_index()

    def append_search_text(self, text: str) -> None:
        if text:
            self.set_search_query(self.search_query + text)

    def backspace_search(self) -> None:
        if self.search_query:
            self.set_search_query(self.search_query[:-1])

    def clear_search(self) -> None:
        self.set_search_query("")

    def toggle_group(self, doc_id: str) -> None:
        self.expanded_groups[doc_id] = not self.expanded_groups.get(doc_id, False)
        self.clamp_sidebar_scroll(total_rows=len(self.sidebar_items))
        self.clamp_focused_sidebar_index()

    def expand_group(self, doc_id: str) -> None:
        self.expanded_groups[doc_id] = True
        self.clamp_sidebar_scroll(total_rows=len(self.sidebar_items))
        self.clamp_focused_sidebar_index()

    def collapse_group(self, doc_id: str) -> None:
        self.expanded_groups[doc_id] = False
        self.clamp_sidebar_scroll(total_rows=len(self.sidebar_items))
        self.clamp_focused_sidebar_index()

    def select_section(self, doc_id: str, section_index: int) -> None:
        self.selected_doc_id = doc_id
        self.selected_section_index = section_index
        self.content_scroll = 0
        if not self.expanded_groups.get(doc_id, False):
            self.expanded_groups[doc_id] = True
        self.focused_sidebar_index = self.selected_sidebar_position
        self.ensure_selected_sidebar_visible()

    def move_selection(self, delta: int) -> None:
        items = self.sidebar_items
        if not items:
            return
        new_pos = max(0, min(len(items) - 1, self.focused_sidebar_index + delta))
        self.focused_sidebar_index = new_pos
        target = items[new_pos]
        if target.kind == "section" and target.section_index is not None:
            self.select_section(target.doc_id, target.section_index)
        else:
            self.ensure_sidebar_row_visible(new_pos)

    def handle_enter_on_selected(self) -> None:
        items = self.sidebar_items
        if not items:
            return
        current = min(self.focused_sidebar_index, len(items) - 1)
        target = items[current]
        if target.kind == "group":
            self.toggle_group(target.doc_id)
        elif target.kind == "section" and target.section_index is not None:
            self.select_section(target.doc_id, target.section_index)

    def handle_left(self) -> None:
        items = self.sidebar_items
        if not items:
            return
        current = min(self.focused_sidebar_index, len(items) - 1)
        target = items[current]
        if target.kind == "group" and self.expanded_groups.get(target.doc_id, False):
            self.collapse_group(target.doc_id)
        elif target.kind == "section":
            pass
        self.ensure_sidebar_row_visible(current)

    def handle_right(self) -> None:
        items = self.sidebar_items
        if not items:
            return
        current = min(self.focused_sidebar_index, len(items) - 1)
        target = items[current]
        if target.kind == "group" and not self.expanded_groups.get(target.doc_id, False):
            self.expand_group(target.doc_id)
        self.ensure_sidebar_row_visible(current)

    def scroll_sidebar(self, amount: int) -> None:
        self.sidebar_scroll += amount
        self.clamp_sidebar_scroll()

    def clamp_sidebar_scroll(self, *, total_rows: int | None = None, visible_rows: int | None = None) -> None:
        if total_rows is not None:
            self.sidebar_total_rows = max(0, total_rows)
        if visible_rows is not None:
            self.sidebar_visible_rows = max(1, visible_rows)
        max_scroll = max(0, self.sidebar_total_rows - self.sidebar_visible_rows)
        self.sidebar_scroll = max(0, min(max_scroll, self.sidebar_scroll))

    def ensure_sidebar_row_visible(self, row_index: int) -> None:
        if row_index < self.sidebar_scroll:
            self.sidebar_scroll = row_index
        elif row_index >= self.sidebar_scroll + self.sidebar_visible_rows:
            self.sidebar_scroll = row_index - self.sidebar_visible_rows + 1
        self.clamp_sidebar_scroll()

    def ensure_selected_sidebar_visible(self) -> None:
        self.ensure_sidebar_row_visible(self.selected_sidebar_position)

    def set_content_bounds(self, *, line_count: int, visible_lines: int) -> None:
        self.content_line_count = max(0, line_count)
        self.content_visible_lines = max(1, visible_lines)
        self.clamp_content_scroll()

    def scroll_content(self, amount: int) -> None:
        self.content_scroll += amount
        self.clamp_content_scroll()

    def clamp_content_scroll(self, *, line_count: int | None = None, visible_lines: int | None = None) -> None:
        if line_count is not None:
            self.content_line_count = max(0, line_count)
        if visible_lines is not None:
            self.content_visible_lines = max(1, visible_lines)
        max_scroll = max(0, self.content_line_count - self.content_visible_lines)
        self.content_scroll = max(0, min(max_scroll, self.content_scroll))

    def set_sidebar_bounds(self, *, total_rows: int, visible_rows: int) -> None:
        self.sidebar_total_rows = max(0, total_rows)
        self.sidebar_visible_rows = max(1, visible_rows)
        self.clamp_sidebar_scroll()

    def clamp_focused_sidebar_index(self) -> None:
        if not self.sidebar_items:
            self.focused_sidebar_index = 0
            return
        self.focused_sidebar_index = max(0, min(len(self.sidebar_items) - 1, self.focused_sidebar_index))
