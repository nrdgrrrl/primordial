"""Category navigation state for the settings overlay."""

from __future__ import annotations


class SettingsNavigation:
    """Track the active category and selected row per category."""

    def __init__(self, categories: list[str]) -> None:
        if not categories:
            raise ValueError("SettingsNavigation requires at least one category")
        self.categories = categories
        self.category_index = 0
        self.selected_by_category = {category: 0 for category in categories}

    @property
    def category(self) -> str:
        return self.categories[self.category_index]

    @property
    def selected(self) -> int:
        return self.selected_by_category[self.category]

    @selected.setter
    def selected(self, value: int) -> None:
        self.selected_by_category[self.category] = value

    def move_category(self, direction: int, item_count_for_category) -> None:
        self.category_index = (self.category_index + direction) % len(self.categories)
        self.clamp_selected(item_count_for_category(self.category))

    def set_category(self, category: str, item_count: int) -> None:
        if category not in self.categories:
            return
        self.category_index = self.categories.index(category)
        self.clamp_selected(item_count)

    def move_selection(self, direction: int, item_count: int) -> None:
        if item_count <= 0:
            self.selected = 0
            return
        self.selected = (self.selected + direction) % item_count

    def clamp_selected(self, item_count: int) -> None:
        if item_count <= 0:
            self.selected = 0
            return
        self.selected %= item_count
